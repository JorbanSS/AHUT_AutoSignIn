import base64
import hashlib
import random
import time
from typing import Optional
from urllib.parse import urlparse

from .constants import UA_LIST
from .models import User
from .time_utils import get_time


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
