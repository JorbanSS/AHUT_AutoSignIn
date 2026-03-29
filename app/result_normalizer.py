from datetime import datetime
from typing import Any, List, Optional

from .constants import DATETIME_FORMAT


class ResultNormalizer:
    @staticmethod
    def _normalize_string_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return [str(item) for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def normalize(raw_result: Any) -> dict:
        success = False
        errors: List[str] = []
        failure_logs: List[str] = []

        if isinstance(raw_result, dict):
            success = bool(raw_result.get("success", False))
            errors = ResultNormalizer._normalize_string_list(raw_result.get("errors"))
            failure_logs = ResultNormalizer._normalize_string_list(raw_result.get("failure_logs"))

            if not errors and "data" in raw_result:
                errors = ResultNormalizer._normalize_string_list(raw_result.get("data"))
            if not errors and raw_result.get("msg"):
                errors = ResultNormalizer._normalize_string_list(raw_result.get("msg"))
        elif isinstance(raw_result, bool):
            success = raw_result
        elif raw_result is not None:
            errors = [str(raw_result)]

        return {
            "success": success,
            "errors": errors,
            "failure_logs": failure_logs,
            "sign_time": datetime.now().strftime(DATETIME_FORMAT),
        }

    @staticmethod
    def failure_result(message: str, extra_logs: Optional[List[str]] = None) -> dict:
        logs = extra_logs[:] if extra_logs else []
        if message:
            logs.insert(0, message)
        return {
            "success": False,
            "errors": [message] if message else [],
            "failure_logs": logs,
            "sign_time": datetime.now().strftime(DATETIME_FORMAT),
        }
