import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

from .config import ConfigLoader
from .constants import DATE_FORMAT, DATETIME_FORMAT, RUN_STATE_FILE_NAME
from .email_service import Mailer
from .logging_setup import LoggerSetup
from .main_adapter import MainAdapter
from .models import AppConfig, UserConfig
from .scheduler import Scheduler
from .state_store import StateStore


def build_failure_result(student_id: int, exc: Exception) -> dict:
    message = f"{exc.__class__.__name__}: {exc}"
    return {
        "success": False,
        "errors": [message],
        "failure_logs": [f"[{datetime.now().strftime(DATETIME_FORMAT)}] student_id={student_id}, msg={message}"],
        "sign_time": datetime.now().strftime(DATETIME_FORMAT),
    }


def sign_user_with_schedule(user: UserConfig, execute_at: datetime, adapter: MainAdapter, debug: bool) -> dict:
    delay_seconds = (execute_at - datetime.now()).total_seconds()
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    result = adapter.sign_in_user(user, debug=debug)
    result["sign_time"] = datetime.now().strftime(DATETIME_FORMAT)
    return result


def get_state_file_path(config_path: Path) -> Path:
    return config_path.parent / "logs" / RUN_STATE_FILE_NAME


def get_next_start_datetime(start_hms: str) -> datetime:
    start_time = datetime.strptime(start_hms, "%H:%M:%S").time()
    next_date = datetime.now().date() + timedelta(days=1)
    return datetime.combine(next_date, start_time)


def sleep_until(target_time: datetime) -> None:
    while True:
        remaining = (target_time - datetime.now()).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(60.0, remaining))


def run_once_with_config(app_config: AppConfig, adapter: MainAdapter) -> Dict[int, dict]:
    results: Dict[int, dict] = {}

    if not app_config.users:
        logging.error("no users found in config.json, please configure at least one user")
        return results

    admin_user = app_config.users[0]
    enabled_users = [user for user in app_config.users if user.enabled]
    normal_users = [user for user in enabled_users if user.student_Id != admin_user.student_Id]
    next_day_date = datetime.now().date() + timedelta(days=1)
    next_day_eta_map = Scheduler.build_next_day_eta_map(app_config, next_day_date)

    email_service = Mailer(app_config.email_config)
    start_time = time.time()

    if not enabled_users:
        logging.warning("no enabled users found in config.json, skip sign-in")
        email_service.send_summary_email_to_first_user(app_config.users, results, next_day_eta_map)
        return results

    schedule, admin_eta = Scheduler.build_schedule_with_admin_last(
        normal_users=normal_users,
        admin_enabled=admin_user.enabled,
        start_hms=app_config.sign_time_window.start,
        end_hms=app_config.sign_time_window.end,
    )

    Scheduler.log_estimated_plan(
        normal_users=normal_users,
        schedule=schedule,
        admin_user=admin_user,
        admin_enabled=admin_user.enabled,
        admin_eta=admin_eta,
        title="estimated sign-in plan:",
    )

    if normal_users:
        max_workers = max(1, min(app_config.max_workers, len(normal_users)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures_to_user = {
                executor.submit(
                    sign_user_with_schedule,
                    user,
                    schedule[user.student_Id],
                    adapter,
                    app_config.debug,
                ): user
                for user in normal_users
            }

            for future in as_completed(futures_to_user):
                user = futures_to_user[future]
                try:
                    result = future.result()
                except Exception as exc:
                    logging.exception("unexpected error when signing for %s", user.student_Id)
                    result = build_failure_result(user.student_Id, exc)

                results[user.student_Id] = result
                email_service.send_email_for_user(user, result)

    if admin_user.enabled:
        if admin_eta is not None:
            wait_seconds = (admin_eta - datetime.now()).total_seconds()
            if wait_seconds > 0:
                time.sleep(wait_seconds)

        logging.info("all non-admin users finished, start admin sign-in")
        try:
            admin_result = adapter.sign_in_user(admin_user, debug=app_config.debug)
            admin_result["sign_time"] = datetime.now().strftime(DATETIME_FORMAT)
        except Exception as exc:
            logging.exception("unexpected error when signing for admin %s", admin_user.student_Id)
            admin_result = build_failure_result(admin_user.student_Id, exc)

        results[admin_user.student_Id] = admin_result
        email_service.send_combined_email_to_admin_when_signed(
            admin_user=admin_user,
            admin_result=admin_result,
            all_users=app_config.users,
            results=results,
            next_day_eta_map=next_day_eta_map,
        )
    else:
        logging.warning("admin user is disabled; send summary email only")
        email_service.send_summary_email_to_first_user(app_config.users, results, next_day_eta_map)

    end_time = time.time()
    success_count = sum(1 for result in results.values() if result.get("success"))

    print(
        "Sign-in finished. total_users=%d, total_enabled=%d, success=%d, elapsed=%.2fs"
        % (len(app_config.users), len(enabled_users), success_count, end_time - start_time)
    )
    for student_id, result in results.items():
        print(f"  {student_id}: {result}")

    return results


def run(config_path: Path) -> int:
    try:
        app_config = ConfigLoader.load_app_config(config_path)
    except Exception as exc:
        print(f"Failed to load config file: {exc}", file=sys.stderr)
        return 1

    try:
        adapter = MainAdapter(force_reload=True)
    except Exception as exc:
        print(f"Failed to initialize main adapter: {exc}", file=sys.stderr)
        return 1

    try:
        LoggerSetup.setup_logging(app_config.log_level, config_path.parent / "logs")
        run_once_with_config(app_config, adapter)
        return 0
    finally:
        adapter.close()


def run_forever(config_path: Path) -> int:
    state_store = StateStore(get_state_file_path(config_path))

    while True:
        try:
            app_config = ConfigLoader.load_app_config(config_path)
        except Exception as exc:
            print(f"Failed to load config file: {exc}", file=sys.stderr)
            time.sleep(60)
            continue

        LoggerSetup.setup_logging(app_config.log_level, config_path.parent / "logs")
        today = datetime.now().strftime(DATE_FORMAT)

        if state_store.is_date_completed(today):
            next_start = get_next_start_datetime(app_config.sign_time_window.start)
            logging.info("daily run already completed for %s, skip duplicate execution", today)

            next_day_date = next_start.date()
            next_day_eta_map = Scheduler.build_next_day_eta_map(app_config, next_day_date)
            if app_config.users and next_day_eta_map:
                admin_user = app_config.users[0]
                enabled_users = [user for user in app_config.users if user.enabled]
                normal_users = [user for user in enabled_users if user.student_Id != admin_user.student_Id]
                schedule = {
                    user.student_Id: eta
                    for user, eta in [(user, next_day_eta_map.get(user.student_Id)) for user in normal_users]
                    if eta is not None
                }
                Scheduler.log_estimated_plan(
                    normal_users=normal_users,
                    schedule=schedule,
                    admin_user=admin_user,
                    admin_enabled=admin_user.enabled,
                    admin_eta=next_day_eta_map.get(admin_user.student_Id),
                    title=f"next-day estimated sign-in plan ({next_day_date.strftime(DATE_FORMAT)}):",
                )

            logging.info("waiting for next run at %s", next_start.strftime(DATETIME_FORMAT))
            sleep_until(next_start)
            continue

        adapter = None
        try:
            adapter = MainAdapter(force_reload=True)
        except Exception:
            logging.exception("failed to initialize main adapter, retry after 60 seconds")
            time.sleep(60)
            continue

        try:
            # main.py may alter root handlers during import/reload, so re-apply logger setup.
            LoggerSetup.setup_logging(app_config.log_level, config_path.parent / "logs")
            run_once_with_config(app_config, adapter)
            state_store.mark_date_completed(today)

            next_start = get_next_start_datetime(app_config.sign_time_window.start)
            next_day_date = next_start.date()
            admin_user = app_config.users[0] if app_config.users else None

            if admin_user is not None:
                enabled_users = [user for user in app_config.users if user.enabled]
                normal_users = [user for user in enabled_users if user.student_Id != admin_user.student_Id]
                next_day_eta_map = Scheduler.build_next_day_eta_map(app_config, next_day_date)
                schedule = {
                    user.student_Id: eta
                    for user, eta in [(user, next_day_eta_map.get(user.student_Id)) for user in normal_users]
                    if eta is not None
                }
                Scheduler.log_estimated_plan(
                    normal_users=normal_users,
                    schedule=schedule,
                    admin_user=admin_user,
                    admin_enabled=admin_user.enabled,
                    admin_eta=next_day_eta_map.get(admin_user.student_Id),
                    title=f"next-day estimated sign-in plan ({next_day_date.strftime(DATE_FORMAT)}):",
                )

            logging.info("daily cycle completed, waiting for next run at %s", next_start.strftime(DATETIME_FORMAT))
            sleep_until(next_start)
        except KeyboardInterrupt:
            logging.info("received keyboard interrupt, exit sign-in loop")
            return 0
        except Exception:
            logging.exception("unexpected error in sign-in loop, retry after 60 seconds")
            time.sleep(60)
        finally:
            if adapter is not None:
                adapter.close()


def main() -> int:
    config_path = Path(__file__).resolve().parent.parent / "config.json"
    return run_forever(config_path)
