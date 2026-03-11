from dataclasses import dataclass
from typing import List


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


@dataclass
class SignTimeWindow:
    start: str = "21:20:00"
    end: str = "22:00:00"


@dataclass
class AppConfig:
    log_level: int
    users: List[User]
    max_retries: int
    max_token_retries: int
    debug: bool
    max_workers: int
    http_timeout_seconds: int
    email_config: dict
    sign_time_window: SignTimeWindow
