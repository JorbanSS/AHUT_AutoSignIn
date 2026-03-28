import json
import logging
import random
import time

import requests

from .api import generate_data, generate_header, generate_params, is_token_invalid
from .constants import WEB_DICT
from .models import User
from .time_utils import get_time

RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectTimeout,
    requests.exceptions.ReadTimeout,
    requests.exceptions.ConnectionError,
)


class SignInClient:
    def __init__(
        self,
        http_connect_timeout_seconds: int,
        http_read_timeout_seconds: int,
        request_retries: int,
        retry_backoff_seconds: float,
        min_sign_time: str = "21:20:00",
    ):
        self.http_connect_timeout_seconds = http_connect_timeout_seconds
        self.http_read_timeout_seconds = http_read_timeout_seconds
        self.request_retries = request_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.min_sign_time = min_sign_time

    def _backoff(self, attempt: int) -> float:
        return self.retry_backoff_seconds * (2 ** (attempt - 1))

    def _request(self, method: str, url: str, user: User, step: int, api_name: str, **kwargs):
        total_attempts = self.request_retries + 1
        timeout = (self.http_connect_timeout_seconds, self.http_read_timeout_seconds)

        for attempt in range(1, total_attempts + 1):
            started = time.monotonic()
            try:
                response = requests.request(method=method, url=url, timeout=timeout, **kwargs)
                elapsed_ms = int((time.monotonic() - started) * 1000)

                if response.status_code in RETRYABLE_STATUS_CODES and attempt < total_attempts:
                    wait_seconds = self._backoff(attempt)
                    logging.warning(
                        f"http retry student_id={user.student_Id}, step={step}, api={api_name}, "
                        f"attempt={attempt}/{total_attempts}, status={response.status_code}, "
                        f"timeout={timeout}, elapsed_ms={elapsed_ms}, wait={wait_seconds:.2f}s"
                    )
                    time.sleep(wait_seconds)
                    continue

                logging.info(
                    f"http request student_id={user.student_Id}, step={step}, api={api_name}, "
                    f"attempt={attempt}/{total_attempts}, status={response.status_code}, "
                    f"timeout={timeout}, elapsed_ms={elapsed_ms}"
                )
                return response
            except RETRYABLE_EXCEPTIONS as exc:
                elapsed_ms = int((time.monotonic() - started) * 1000)
                if attempt < total_attempts:
                    wait_seconds = self._backoff(attempt)
                    logging.warning(
                        f"http retry student_id={user.student_Id}, step={step}, api={api_name}, "
                        f"attempt={attempt}/{total_attempts}, error={exc.__class__.__name__}, "
                        f"timeout={timeout}, elapsed_ms={elapsed_ms}, wait={wait_seconds:.2f}s"
                    )
                    time.sleep(wait_seconds)
                    continue

                logging.error(
                    f"http request failed student_id={user.student_Id}, step={step}, api={api_name}, "
                    f"attempt={attempt}/{total_attempts}, error={exc.__class__.__name__}, "
                    f"timeout={timeout}, elapsed_ms={elapsed_ms}, msg={exc}"
                )
                raise
            except requests.exceptions.RequestException as exc:
                elapsed_ms = int((time.monotonic() - started) * 1000)
                logging.error(
                    f"http request failed student_id={user.student_Id}, step={step}, api={api_name}, "
                    f"attempt={attempt}/{total_attempts}, error={exc.__class__.__name__}, "
                    f"timeout={timeout}, elapsed_ms={elapsed_ms}, msg={exc}"
                )
                raise

        raise RuntimeError("unreachable request state")

    def sign_in_by_step(self, user: User, step: int, debug: bool = False) -> dict:
        if not debug:
            now_time = get_time()["time"]
            if now_time < self.min_sign_time:
                logging.error(
                    f"current time {now_time} is earlier than sign-in window start {self.min_sign_time}"
                )
                return {"success": False, "msg": "not_in_sign_time", "step": -1}

        if step == 0:
            token_result = self._request(
                "POST",
                WEB_DICT["token_api"],
                user=user,
                step=step,
                api_name="token_api",
                params=generate_params(user),
                headers=generate_header(user),
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
            task_result = self._request(
                "GET",
                WEB_DICT["task_id_api"],
                user=user,
                step=step,
                api_name="task_id_api",
                headers=generate_header(user, WEB_DICT["task_id_api"]),
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
            auth_result = self._request(
                "GET",
                url,
                user=user,
                step=step,
                api_name="auth_check_api",
                headers=generate_header(user, url),
            ).json()

            if auth_result.get("code") == 200:
                return {"success": True, "msg": "", "step": step + 1}

            msg = auth_result.get("msg", "auth_check_failed")
            if is_token_invalid(msg):
                user.token = ""
                return {"success": False, "msg": "token_invalid", "step": 0}
            return {"success": False, "msg": msg, "step": step}

        if step == 3:
            api_log_result = self._request(
                "POST",
                WEB_DICT["apiLog_api"],
                user=user,
                step=step,
                api_name="apiLog_api",
                headers=generate_header(user, WEB_DICT["apiLog_api"]),
            )
            if api_log_result.status_code == 200:
                return {"success": True, "msg": "", "step": step + 1}
            return {"success": False, "msg": "open_time_window_failed", "step": step}

        if step == 4:
            sign_in_result = self._request(
                "POST",
                WEB_DICT["sign_in_api"],
                user=user,
                step=step,
                api_name="sign_in_api",
                data=json.dumps(generate_data(user)),
                headers=generate_header(user, WEB_DICT["sign_in_api"]),
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


class SignInWorkflow:
    def __init__(self, client: SignInClient, max_retries: int, max_token_retries: int):
        self.client = client
        self.max_retries = max_retries
        self.max_token_retries = max_token_retries

    def sign_in(self, user: User, debug: bool = False) -> dict:
        logging.info(f"start sign-in workflow for {user.username}({user.student_Id})")
        step, retries, token_retries = 0, 0, 0
        error_history = []
        failure_logs = []

        while retries < self.max_retries and 0 <= step < 5:
            current_step = step
            try:
                result = self.client.sign_in_by_step(user, current_step, debug)
            except Exception as exc:
                msg = f"{exc.__class__.__name__}: {exc}"
                result = {"success": False, "msg": msg, "step": current_step}

            step = result["step"]

            if not result["success"]:
                msg = str(result.get("msg", "unknown_error"))
                if msg not in error_history:
                    error_history.append(msg)

                failure_logs.append(
                    f"[{get_time()['full']}] student_id={user.student_Id}, step={current_step}, next_step={step}, msg={msg}, retries={retries}, token_retries={token_retries}"
                )

                if msg == "token_invalid" and token_retries < self.max_token_retries:
                    token_retries += 1
                else:
                    retries += 1

            time.sleep(random.randint(50, 150) / 100)

        success = step == 5
        logging.info(
            f"finish sign-in workflow for {user.student_Id}, success={success}, retries={retries}, token_retries={token_retries}"
        )
        return {"success": success, "errors": error_history, "failure_logs": failure_logs}
