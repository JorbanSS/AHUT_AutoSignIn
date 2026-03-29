import json
import logging
import time
from pathlib import Path
from typing import Any, List

from .models import AppConfig, SignTimeWindow, UserConfig


class ConfigLoader:
    @staticmethod
    def load_config(config_path: Path) -> dict:
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with config_path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("config.json must contain a JSON object")

        return data

    @staticmethod
    def parse_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"1", "true", "yes", "on"}:
                return True
            if text in {"0", "false", "no", "off"}:
                return False
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        return default

    @staticmethod
    def parse_log_level(level: Any) -> int:
        if not isinstance(level, str):
            return logging.INFO
        return getattr(logging, level.upper(), logging.INFO)

    @staticmethod
    def parse_hms(value: Any, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be a string in HH:MM:SS format")

        text = value.strip()
        try:
            time.strptime(text, "%H:%M:%S")
        except ValueError as exc:
            raise ValueError(f"{field_name} must be in HH:MM:SS format") from exc

        return text

    @staticmethod
    def parse_positive_int(value: Any, field_name: str) -> int:
        parsed = int(value)
        if parsed <= 0:
            raise ValueError(f"{field_name} must be a positive integer")
        return parsed

    @staticmethod
    def parse_non_negative_int(value: Any, field_name: str) -> int:
        parsed = int(value)
        if parsed < 0:
            raise ValueError(f"{field_name} must be a non-negative integer")
        return parsed

    @staticmethod
    def parse_positive_float(value: Any, field_name: str) -> float:
        parsed = float(value)
        if parsed <= 0:
            raise ValueError(f"{field_name} must be a positive number")
        return parsed

    @staticmethod
    def build_users(users_cfg: Any) -> List[UserConfig]:
        if not isinstance(users_cfg, list):
            raise ValueError("users must be a list")

        users: List[UserConfig] = []
        for item in users_cfg:
            if not isinstance(item, dict):
                raise ValueError("each user must be a JSON object")

            student_id = item.get("student_id", item.get("student_Id"))
            if student_id is None:
                raise ValueError("user.student_id (or user.student_Id) is required")

            users.append(
                UserConfig(
                    student_Id=int(student_id),
                    username=str(item.get("username", "")),
                    password=str(item.get("password", "Ahgydx@920")),
                    latitude=float(item.get("latitude", 118.554951)),
                    longitude=float(item.get("longitude", 31.675607)),
                    email=str(item.get("email", "")).strip(),
                    is_encrypted=int(item.get("is_encrypted", 0)),
                    enabled=ConfigLoader.parse_bool(item.get("enabled", True), default=True),
                )
            )

        return users

    @staticmethod
    def build_sign_time_window(sign_time_window_cfg: Any) -> SignTimeWindow:
        cfg = sign_time_window_cfg if isinstance(sign_time_window_cfg, dict) else {}
        return SignTimeWindow(
            start=ConfigLoader.parse_hms(cfg.get("start", "21:20:00"), "sign_time_window.start"),
            end=ConfigLoader.parse_hms(cfg.get("end", "22:00:00"), "sign_time_window.end"),
        )

    @staticmethod
    def load_app_config(config_path: Path) -> AppConfig:
        config = ConfigLoader.load_config(config_path)
        email_config = config.get("email", {})

        legacy_timeout = ConfigLoader.parse_positive_int(
            config.get("http_timeout_seconds", 10), "http_timeout_seconds"
        )
        connect_timeout = ConfigLoader.parse_positive_int(
            config.get("http_connect_timeout_seconds", 3),
            "http_connect_timeout_seconds",
        )
        read_timeout = ConfigLoader.parse_positive_int(
            config.get("http_read_timeout_seconds", legacy_timeout),
            "http_read_timeout_seconds",
        )
        request_retries = ConfigLoader.parse_non_negative_int(
            config.get("http_request_retries", 2),
            "http_request_retries",
        )
        retry_backoff_seconds = ConfigLoader.parse_positive_float(
            config.get("http_retry_backoff_seconds", 1.0),
            "http_retry_backoff_seconds",
        )

        return AppConfig(
            log_level=ConfigLoader.parse_log_level(config.get("log_level", "INFO")),
            users=ConfigLoader.build_users(config.get("users", [])),
            max_retries=ConfigLoader.parse_positive_int(config.get("max_retries", 4), "max_retries"),
            max_token_retries=ConfigLoader.parse_non_negative_int(
                config.get("max_token_retries", 3), "max_token_retries"
            ),
            debug=ConfigLoader.parse_bool(config.get("debug", False), default=False),
            max_workers=ConfigLoader.parse_positive_int(config.get("max_workers", 20), "max_workers"),
            http_connect_timeout_seconds=connect_timeout,
            http_read_timeout_seconds=read_timeout,
            http_request_retries=request_retries,
            http_retry_backoff_seconds=retry_backoff_seconds,
            email_config=email_config if isinstance(email_config, dict) else {},
            sign_time_window=ConfigLoader.build_sign_time_window(config.get("sign_time_window", {})),
        )
