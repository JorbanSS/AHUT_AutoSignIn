import importlib
import inspect
import logging
import sys
import threading
from typing import Any, Callable, Dict, List

from .async_loop_runner import AsyncLoopRunner
from .models import UserConfig
from .result_normalizer import ResultNormalizer


class MainAdapter:
    def __init__(self, force_reload: bool = True):
        self.force_reload = force_reload
        self.module = self._load_main_module()
        self.user_cls = getattr(self.module, "User", None)
        self.sign_in_func = getattr(self.module, "sign_in", None)
        self.main_func = getattr(self.module, "main", None)

        self._async_runner = AsyncLoopRunner()
        self._fallback_lock = threading.Lock()

        if not callable(self.sign_in_func) and not callable(self.main_func):
            raise RuntimeError("main.py does not expose callable sign_in or main entrypoint")
        if self.user_cls is None:
            raise RuntimeError("main.py does not expose User class")

    def close(self) -> None:
        self._async_runner.close()

    def _load_main_module(self):
        try:
            if "main" in sys.modules and self.force_reload:
                return importlib.reload(sys.modules["main"])
            return importlib.import_module("main")
        except ModuleNotFoundError as exc:
            if exc.name == "aiohttp":
                raise RuntimeError(
                    "Failed to import main.py because dependency 'aiohttp' is missing. "
                    "Run: pip install -r requirements.txt"
                ) from exc
            raise RuntimeError(f"Failed to import main.py: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to import main.py: {exc}") from exc

    @staticmethod
    def _filter_kwargs(callable_obj: Callable[..., Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
        try:
            signature = inspect.signature(callable_obj)
        except (TypeError, ValueError):
            return kwargs

        params = signature.parameters.values()
        accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params)
        if accepts_kwargs:
            return kwargs

        valid_names = {param.name for param in params}
        return {name: value for name, value in kwargs.items() if name in valid_names}

    def _invoke(self, callable_obj: Callable[..., Any], *args, **kwargs) -> Any:
        filtered_kwargs = self._filter_kwargs(callable_obj, kwargs)
        result = callable_obj(*args, **filtered_kwargs)
        return self._async_runner.run(result)

    def _build_main_user(self, user_cfg: UserConfig):
        candidate_kwargs = {
            "student_Id": user_cfg.student_Id,
            "student_id": user_cfg.student_Id,
            "username": user_cfg.username,
            "password": user_cfg.password,
            "latitude": user_cfg.latitude,
            "longitude": user_cfg.longitude,
            "is_encrypted": user_cfg.is_encrypted,
            "email": user_cfg.email,
            "enabled": user_cfg.enabled,
        }

        filtered_kwargs = self._filter_kwargs(self.user_cls, candidate_kwargs)
        if not filtered_kwargs:
            return self.user_cls(user_cfg.student_Id)

        try:
            return self.user_cls(**filtered_kwargs)
        except TypeError:
            filtered_kwargs.pop("student_id", None)
            filtered_kwargs.pop("student_Id", None)
            return self.user_cls(user_cfg.student_Id, **filtered_kwargs)

    def _extract_result_for_user(self, user_cfg: UserConfig, raw_result: Any) -> Any:
        if isinstance(raw_result, dict):
            if "success" in raw_result:
                return raw_result
            for key in (user_cfg.student_Id, str(user_cfg.student_Id)):
                if key in raw_result:
                    return raw_result[key]
        return raw_result

    def _call_sign_in(self, main_user: Any, debug: bool) -> Any:
        if not callable(self.sign_in_func):
            raise RuntimeError("sign_in is not callable")
        return self._invoke(self.sign_in_func, main_user, debug=debug)

    def _call_main_single_user(self, main_user: Any, user_cfg: UserConfig) -> Any:
        if not callable(self.main_func):
            raise RuntimeError("main is not callable")

        with self._fallback_lock:
            has_user_list = hasattr(self.module, "USER_LIST")
            original_user_list = getattr(self.module, "USER_LIST", None)
            if has_user_list:
                setattr(self.module, "USER_LIST", [main_user])
            try:
                raw_result = self._invoke(self.main_func)
            finally:
                if has_user_list:
                    setattr(self.module, "USER_LIST", original_user_list)

        return self._extract_result_for_user(user_cfg, raw_result)

    def sign_in_user(self, user_cfg: UserConfig, debug: bool) -> dict:
        main_user = None
        fallback_errors: List[str] = []

        try:
            main_user = self._build_main_user(user_cfg)
        except Exception as exc:
            return ResultNormalizer.failure_result(
                f"failed to build main.User for {user_cfg.student_Id}: {exc}"
            )

        try:
            if callable(self.sign_in_func):
                raw_result = self._call_sign_in(main_user, debug=debug)
            else:
                raw_result = self._call_main_single_user(main_user, user_cfg)
            return ResultNormalizer.normalize(raw_result)
        except Exception as sign_in_exc:
            fallback_errors.append(f"sign_in route failed: {sign_in_exc}")
            logging.exception("sign_in route failed for student_id=%s", user_cfg.student_Id)

            if callable(self.main_func):
                try:
                    raw_result = self._call_main_single_user(main_user, user_cfg)
                    result = ResultNormalizer.normalize(raw_result)
                    if not result["success"] and fallback_errors:
                        result["failure_logs"].extend(fallback_errors)
                    return result
                except Exception as fallback_exc:
                    fallback_errors.append(f"main route failed: {fallback_exc}")
                    logging.exception("main fallback route failed for student_id=%s", user_cfg.student_Id)

            return ResultNormalizer.failure_result(
                "all main.py call routes failed",
                extra_logs=fallback_errors,
            )
        finally:
            if main_user is not None:
                self._close_main_user(main_user)

    def _close_main_user(self, main_user: Any) -> None:
        close_method = getattr(main_user, "close", None)
        if callable(close_method):
            try:
                result = close_method()
                self._async_runner.run(result)
            except Exception:
                logging.exception("failed to close main user session")
