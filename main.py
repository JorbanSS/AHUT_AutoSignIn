import base64
import hashlib
import json
import logging
import random
import smtplib
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from html import escape
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import requests


@dataclass
class User:
    student_Id: int
    username: str = ""
    password: str = "Ahgydx@920"
    latitude: float = 118.554951
    longitude: float = 31.675607
    email: str = ""
    token: str = ""
    taskId: int = 0
    is_encrypted: int = 0
    enabled: bool = True


CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8-sig") as f:
        config = json.load(f)
    if not isinstance(config, dict):
        raise ValueError("config.json must contain a JSON object")
    return config


def parse_log_level(level: str) -> int:
    if not isinstance(level, str):
        return logging.INFO
    return getattr(logging, level.upper(), logging.INFO)


def build_users(users_cfg) -> List[User]:
    users = []
    if not isinstance(users_cfg, list):
        raise ValueError("users must be a list")

    for item in users_cfg:
        if not isinstance(item, dict):
            raise ValueError("each user must be a JSON object")

        student_id = item.get("student_id", item.get("student_Id"))
        if student_id is None:
            raise ValueError("user.student_id is required")

        users.append(
            User(
                student_Id=int(student_id),
                username=str(item.get("username", "")),
                password=str(item.get("password", "Ahgydx@920")),
                latitude=float(item.get("latitude", 118.554951)),
                longitude=float(item.get("longitude", 31.675607)),
                email=str(item.get("email", "")).strip(),
                is_encrypted=int(item.get("is_encrypted", 0)),
                enabled=bool(item.get("enabled", True)),
            )
        )

    return users


try:
    CONFIG = load_config(CONFIG_PATH)
except Exception as exc:
    print(f"Failed to load config file: {exc}", file=sys.stderr)
    sys.exit(1)

LOG_GRADE = parse_log_level(CONFIG.get("log_level", "INFO"))
USER_LIST = build_users(CONFIG.get("users", []))
MAX_RETRIES = int(CONFIG.get("max_retries", 4))
MAX_TOKEN_RETRIES = int(CONFIG.get("max_token_retries", 3))
DEBUG_MODE = bool(CONFIG.get("debug", False))
MAX_WORKERS = int(CONFIG.get("max_workers", 20))
HTTP_TIMEOUT_SECONDS = int(CONFIG.get("http_timeout_seconds", 10))
EMAIL_CONFIG = CONFIG.get("email", {}) if isinstance(CONFIG.get("email", {}), dict) else {}


formatter = logging.Formatter(
    fmt="%(levelname)s [%(name)s] (%(asctime)s): %(message)s (Line: %(lineno)d [%(filename)s])",
    datefmt="%Y/%m/%d %H:%M:%S",
)
logger = logging.getLogger()
logger.setLevel(LOG_GRADE)
console_handler = logging.StreamHandler(stream=sys.stdout)
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.DEBUG)
logger.handlers.clear()
logger.addHandler(console_handler)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)


API_BASE_URL = "https://xskq.ahut.edu.cn/api"
WEB_DICT = {
    "token_api": f"{API_BASE_URL}/flySource-auth/oauth/token",
    "task_id_api": f"{API_BASE_URL}/flySource-yxgl/dormSignTask/getStudentTaskPage?userDataType=student&current=1&size=15",
    "auth_check_api": f"{API_BASE_URL}/flySource-base/wechat/getWechatMpConfig"
    "?configUrl=https://xskq.ahut.edu.cn/wise/pages/ssgl/dormsign"
    "?taskId={TASK_ID}&autoSign=1&scanSign=0&userId={STUDENT_ID}",
    "apiLog_api": f"{API_BASE_URL}/flySource-base/apiLog/save?menuTitle=%E6%99%9A%E5%AF%9D%E7%AD%BE%E5%88%B0",
    "sign_in_api": f"{API_BASE_URL}/flySource-yxgl/dormSignRecord/add",
}

UA_LIST = [
    "Mozilla/5.0 (Linux; Android 15; MIX Fold 4 Build/TKQ1.240502.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/128.0.6613.137 Mobile Safari/537.36 MicroMessenger/8.0.61.2660(0x28003D37) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (Linux; Android 15; LYA-AL10 Build/HUAWEILYA-AL10; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/128.0.6613.137 Mobile Safari/537.36 MicroMessenger/8.0.61.2660(0x28003D37) WeChat/arm64 Weixin NetType/5G Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (Linux; Android 15; SM-S938B Build/TP1A.240205.004; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/128.0.6613.137 Mobile Safari/537.36 MicroMessenger/8.0.61.2660(0x28003D37) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.61(0x18003D29) NetType/WIFI Language/zh_CN",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.61(0x18003D29) NetType/5G Language/zh_CN",
]


def password_md5(pwd: str) -> str:
    return hashlib.md5(pwd.encode("utf-8")).hexdigest()


def generate_sign(url: str, token: str) -> Optional[str]:
    if not token:
        return None
    parsed_url = urlparse(url)
    api = parsed_url.path + "?sign="
    timestamp = int(time.time() * 1000)
    inner_hash = hashlib.md5(f"{timestamp}{token}".encode("utf-8")).hexdigest()
    final_hash = hashlib.md5(f"{api}{inner_hash}".encode("utf-8")).hexdigest()
    encoded_time = base64.b64encode(str(timestamp).encode("utf-8")).decode("utf-8")
    return f"{final_hash}1.{encoded_time}"


def get_time() -> dict:
    now = time.localtime()
    date = time.strftime("%Y-%m-%d", now)
    current_time = time.strftime("%H:%M:%S", now)
    full_datetime = time.strftime("%Y-%m-%d %H:%M:%S", now)
    week_list = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekday = week_list[now.tm_wday]
    return {"date": date, "time": current_time, "weekday": weekday, "full": full_datetime}


def generate_header(user: User, url: Optional[str] = None) -> dict:
    header = {
        "User-Agent": random.choice(UA_LIST),
        "authorization": "Basic Zmx5c291cmNlX3dpc2VfYXBwOkRBNzg4YXNkVURqbmFzZF9mbHlzb3VyY2VfZHNkYWREQUlVaXV3cWU=",
        "Content-Type": "application/json;charset=UTF-8",
        "X-Requested-With": "com.tencent.mm",
        "Origin": "https://xskq.ahut.edu.cn",
        "Referer": f"https://xskq.ahut.edu.cn/wise/pages/ssgl/dormsign?&userId={user.student_Id}",
    }
    if user.token:
        header["flysource-auth"] = f"bearer {user.token}"
        if url:
            sign = generate_sign(url, user.token)
            if sign:
                header["flysource-sign"] = sign
    return header


def generate_params(user: User) -> dict:
    return {
        "tenantId": "000000",
        "username": user.student_Id,
        "password": user.password if user.is_encrypted else password_md5(user.password),
        "type": "account",
        "grant_type": "password",
        "scope": "all",
    }


def generate_data(user: User) -> dict:
    date_data = get_time()
    return {
        "taskId": user.taskId,
        "signAddress": "",
        "locationAccuracy": round(random.uniform(25, 35), 2),
        "signLat": user.latitude,
        "signLng": user.longitude,
        "signType": 0,
        "fileId": "",
        "imgBase64": "/static/images/dormitory/photo.png",
        "signDate": date_data["date"],
        "signTime": date_data["time"],
        "signWeek": date_data["weekday"],
        "scanCode": "",
    }


def is_token_invalid(message: Optional[str]) -> bool:
    if not message:
        return False
    return any(keyword in message for keyword in ["请求未授权", "缺失身份信息", "鉴权失败"])


def sign_in_by_step(user: User, step: int, debug: bool = False) -> dict:
    if not debug:
        now_time = get_time()["time"]
        if now_time < "21:20:00":
            logger.error(f"current time {now_time} is earlier than sign-in window")
            return {"success": False, "msg": "not_in_sign_time", "step": -1}

    if step == 0:
        token_result = requests.post(
            WEB_DICT["token_api"],
            params=generate_params(user),
            headers=generate_header(user),
            timeout=HTTP_TIMEOUT_SECONDS,
        ).json()

        if "refresh_token" in token_result:
            user.token = token_result["refresh_token"]
            user.username = token_result.get("userName", user.username)
            return {"success": True, "msg": "", "step": step + 1}

        error_desc = token_result.get("error_description", "unknown_error")
        if "Bad credentials" in error_desc or "用户名或密码错误" in error_desc:
            error_desc = "wrong_password"
        return {"success": False, "msg": error_desc, "step": -1}

    if step == 1:
        task_result = requests.get(
            WEB_DICT["task_id_api"],
            headers=generate_header(user, WEB_DICT["task_id_api"]),
            timeout=HTTP_TIMEOUT_SECONDS,
        ).json()

        if task_result.get("code") == 200:
            task_id = task_result.get("data", {}).get("records", [{}])[0].get("taskId")
            if task_id:
                user.taskId = task_id
                return {"success": True, "msg": "", "step": step + 1}
            return {"success": False, "msg": "task_id_not_found", "step": step}

        msg = task_result.get("msg", "task_id_request_failed")
        if is_token_invalid(msg):
            user.token = ""
            return {"success": False, "msg": "token_invalid", "step": 0}
        return {"success": False, "msg": msg, "step": step}

    if step == 2:
        url = WEB_DICT["auth_check_api"].format(TASK_ID=user.taskId, STUDENT_ID=user.student_Id)
        auth_result = requests.get(
            url,
            headers=generate_header(user, url),
            timeout=HTTP_TIMEOUT_SECONDS,
        ).json()

        if auth_result.get("code") == 200:
            return {"success": True, "msg": "", "step": step + 1}

        msg = auth_result.get("msg", "auth_check_failed")
        if is_token_invalid(msg):
            user.token = ""
            return {"success": False, "msg": "token_invalid", "step": 0}
        return {"success": False, "msg": msg, "step": step}

    if step == 3:
        api_log_result = requests.post(
            WEB_DICT["apiLog_api"],
            headers=generate_header(user, WEB_DICT["apiLog_api"]),
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if api_log_result.status_code == 200:
            return {"success": True, "msg": "", "step": step + 1}
        return {"success": False, "msg": "open_time_window_failed", "step": step}

    if step == 4:
        sign_in_result = requests.post(
            WEB_DICT["sign_in_api"],
            data=json.dumps(generate_data(user)),
            headers=generate_header(user, WEB_DICT["sign_in_api"]),
            timeout=HTTP_TIMEOUT_SECONDS,
        ).json()

        msg = sign_in_result.get("msg", "")
        if sign_in_result.get("code") == 200 or "今天已完成签到" in msg:
            return {"success": True, "msg": "", "step": step + 1}

        if is_token_invalid(msg):
            user.token = ""
            return {"success": False, "msg": "token_invalid", "step": 0}

        if "未到签到时间" in msg:
            return {"success": False, "msg": "not_in_sign_time", "step": -1}

        return {"success": False, "msg": msg or "sign_in_failed", "step": step}

    return {"success": False, "msg": "invalid_step", "step": -1}


def sign_in(user: User, debug: bool = False) -> dict:
    logger.info(f"start sign-in workflow for {user.username}({user.student_Id})")
    step, retries, token_retries = 0, 0, 0
    error_history = []
    failure_logs = []

    while retries < MAX_RETRIES and 0 <= step < 5:
        current_step = step
        result = sign_in_by_step(user, current_step, debug)
        step = result["step"]

        if not result["success"]:
            msg = str(result.get("msg", "unknown_error"))
            if msg not in error_history:
                error_history.append(msg)

            failure_logs.append(
                f"[{get_time()['full']}] student_id={user.student_Id}, step={current_step}, next_step={step}, msg={msg}, retries={retries}, token_retries={token_retries}"
            )

            if step == 0 and token_retries < MAX_TOKEN_RETRIES:
                token_retries += 1
            else:
                retries += 1

        time.sleep(random.randint(50, 150) / 100)

    return {"success": step == 5, "errors": error_history, "failure_logs": failure_logs}


def build_mail_subject(result: dict) -> str:
    return "签到成功" if result.get("success") else "签到失败"


def build_mail_body(user: User, result: dict) -> str:
    if result.get("success"):
        display_name = user.username or str(user.student_Id)
        return (
            f"用户: {display_name} ({user.student_Id})\n"
            f"时间: {get_time()['full']}\n"
            "结果: 签到成功\n"
        )

    failure_logs = result.get("failure_logs", [])
    if failure_logs:
        return "\n".join(str(item) for item in failure_logs)

    errors = result.get("errors", [])
    if errors:
        return "\n".join(str(item) for item in errors)

    return "未记录到失败日志"


def build_summary_table_block_html(all_users: List[User], results: dict) -> str:
    rows = []
    for user in all_users:
        user_result = results.get(user.student_Id)
        enabled_status = "✅" if user.enabled else "❌"
        if user_result and user_result.get("success"):
            sign_status = "✅"
        else:
            sign_status = "❌"

        rows.append(
            "<tr>"
            f"<td>{escape(user.username or '')}</td>"
            f"<td>{user.student_Id}</td>"
            f"<td>{escape(user.email)}</td>"
            f"<td>{enabled_status}</td>"
            f"<td>{sign_status}</td>"
            "</tr>"
        )

    return (
        f"<p>签到时间: {escape(get_time()['full'])}</p>"
        "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse: collapse;'>"
        "<thead><tr><th>姓名</th><th>学号</th><th>邮箱</th><th>开启状态</th><th>执行结果</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def build_summary_table_html(all_users: List[User], results: dict) -> str:
    return (
        "<html><body>"
        f"{build_summary_table_block_html(all_users, results)}"
        "</body></html>"
    )


def send_mail(to_email: str, subject: str, body: str, subtype: str = "plain") -> bool:
    if not EMAIL_CONFIG.get("enabled", False):
        return False

    if not to_email:
        logger.warning("skip email: receiver email is empty")
        return False

    required_keys = ["smtp_server", "smtp_port", "sender_email", "sender_password"]
    missing = [key for key in required_keys if not EMAIL_CONFIG.get(key)]
    if missing:
        logger.error(f"email config missing required keys: {missing}")
        return False

    message = MIMEText(body, subtype, "utf-8")
    message["Subject"] = Header(subject, "utf-8")
    sender_name = str(EMAIL_CONFIG.get("sender_name", "AHUT Auto Sign-In"))
    sender_email = str(EMAIL_CONFIG["sender_email"])
    message["From"] = formataddr((str(Header(sender_name, "utf-8")), sender_email))
    message["To"] = to_email

    smtp_server = str(EMAIL_CONFIG["smtp_server"])
    smtp_port = int(EMAIL_CONFIG["smtp_port"])
    sender_password = str(EMAIL_CONFIG["sender_password"])

    try:
        use_ssl = bool(EMAIL_CONFIG.get("use_ssl", True))
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
            if EMAIL_CONFIG.get("use_tls", True):
                server.starttls(context=ssl.create_default_context())

        with server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, [to_email], message.as_string())
        logger.info(f"email sent to {to_email}")
        return True
    except Exception as exc:
        logger.error(f"failed to send email to {to_email}: {exc}")
        return False


def send_email_for_user(user: User, result: dict):
    send_mail(
        to_email=user.email,
        subject=build_mail_subject(result),
        body=build_mail_body(user, result),
        subtype="plain",
    )


def send_summary_email_to_first_user(all_users: List[User], results: dict):
    if not all_users:
        return

    first_user = all_users[0]
    summary_html = build_summary_table_html(all_users, results)
    send_mail(
        to_email=first_user.email,
        subject="签到列表汇总",
        body=summary_html,
        subtype="html",
    )


def send_combined_email_to_admin_when_signed(admin_user: User, admin_result: dict, all_users: List[User], results: dict):
    display_name = escape(admin_user.username or "")
    if admin_result.get("success"):
        admin_detail_html = "<p>管理员签到结果: ✅ 签到成功</p>"
    else:
        failure_logs = admin_result.get("failure_logs", [])
        if failure_logs:
            details = "\n".join(str(item) for item in failure_logs)
        else:
            errors = admin_result.get("errors", [])
            details = "\n".join(str(item) for item in errors) if errors else "未记录到失败日志"
        admin_detail_html = f"<p>管理员签到结果: ❌ 签到失败</p><pre>{escape(details)}</pre>"

    html_body = (
        "<html><body>"
        f"<p>管理员: {display_name} ({admin_user.student_Id})</p>"
        f"{admin_detail_html}"
        "<hr/>"
        "<h3>签到列表汇总</h3>"
        f"{build_summary_table_block_html(all_users, results)}"
        "</body></html>"
    )
    send_mail(
        to_email=admin_user.email,
        subject=build_mail_subject(admin_result),
        body=html_body,
        subtype="html",
    )


def run():
    if not USER_LIST:
        logger.error("no users found in config.json, please configure at least one user")
        return

    admin_user = USER_LIST[0]
    enabled_users = [user for user in USER_LIST if user.enabled]
    results = {}
    start_time = time.time()

    if not enabled_users:
        logger.warning("no enabled users found in config.json, skip sign-in")
    else:
        max_workers = max(1, min(MAX_WORKERS, len(enabled_users)))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures_to_user = {executor.submit(sign_in, user, debug=DEBUG_MODE): user for user in enabled_users}

            for future in as_completed(futures_to_user):
                user = futures_to_user[future]
                try:
                    result = future.result()
                except Exception as exc:
                    logger.exception(f"unexpected error when signing for {user.student_Id}")
                    result = {
                        "success": False,
                        "errors": [str(exc)],
                        "failure_logs": [f"[{get_time()['full']}] student_id={user.student_Id}, msg={str(exc)}"],
                    }

                results[user.student_Id] = result
                if user.student_Id != admin_user.student_Id:
                    send_email_for_user(user, result)

    admin_result = results.get(admin_user.student_Id)
    if admin_result is None:
        # Admin did not participate in sign-in, send summary separately.
        send_summary_email_to_first_user(USER_LIST, results)
    else:
        # Admin participated in sign-in, merge admin result and summary in one email.
        send_combined_email_to_admin_when_signed(admin_user, admin_result, USER_LIST, results)

    end_time = time.time()
    success_count = sum(1 for result in results.values() if result.get("success"))

    print(
        f"Sign-in finished. total_users={len(USER_LIST)}, total_enabled={len(enabled_users)}, success={success_count}, "
        f"elapsed={end_time - start_time:.2f}s"
    )
    for student_id, result in results.items():
        print(f"  {student_id}: {result}")


if __name__ == "__main__":
    run()
