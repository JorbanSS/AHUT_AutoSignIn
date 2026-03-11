import json
import logging
import time
from pathlib import Path
from typing import List

from .models import AppConfig, SignTimeWindow, User


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8-sig") as file:
        config = json.load(file)
    if not isinstance(config, dict):
        raise ValueError("config.json must contain a JSON object")
    return config


def parse_log_level(level: str) -> int:
    if not isinstance(level, str):
        return logging.INFO
    return getattr(logging, level.upper(), logging.INFO)


def parse_hms(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string in HH:MM:SS format")

    text = value.strip()
    try:
        time.strptime(text, "%H:%M:%S")
    except ValueError as exc:
        raise ValueError(f"{field_name} must be in HH:MM:SS format") from exc

    return text


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


def build_sign_time_window(sign_time_window_cfg) -> SignTimeWindow:
    cfg = sign_time_window_cfg if isinstance(sign_time_window_cfg, dict) else {}
    start = parse_hms(str(cfg.get("start", "21:20:00")), "sign_time_window.start")
    end = parse_hms(str(cfg.get("end", "22:00:00")), "sign_time_window.end")
    return SignTimeWindow(start=start, end=end)


def load_app_config(config_path: Path) -> AppConfig:
    config = load_config(config_path)
    email_config = config.get("email", {})

    return AppConfig(
        log_level=parse_log_level(config.get("log_level", "INFO")),
        users=build_users(config.get("users", [])),
        max_retries=int(config.get("max_retries", 4)),
        max_token_retries=int(config.get("max_token_retries", 3)),
        debug=bool(config.get("debug", False)),
        max_workers=int(config.get("max_workers", 20)),
        http_timeout_seconds=int(config.get("http_timeout_seconds", 10)),
        email_config=email_config if isinstance(email_config, dict) else {},
        sign_time_window=build_sign_time_window(config.get("sign_time_window", {})),
    )
