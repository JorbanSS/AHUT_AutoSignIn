import json
import logging
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import load_app_config
from .email_service import EmailService
from .logging_setup import setup_logging
from .models import AppConfig, User
from .time_utils import get_time
from .workflow import SignInClient, SignInWorkflow

RUN_STATE_FILE_NAME = "run_state.json"
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def build_failure_result(student_id: int, exc: Exception) -> dict:
    return {
        "success": False,
        "errors": [str(exc)],
        "failure_logs": [f"[{get_time()['full']}] student_id={student_id}, msg={str(exc)}"],
        "sign_time": datetime.now().strftime(DATETIME_FORMAT),
    }


def resolve_effective_window(start_hms: str, end_hms: str) -> Tuple[datetime, datetime]:
    now = datetime.now()
    start_time = datetime.strptime(start_hms, "%H:%M:%S").time()
    end_time = datetime.strptime(end_hms, "%H:%M:%S").time()

    start_at = datetime.combine(now.date(), start_time)
    end_at = datetime.combine(now.date(), end_time)

    if end_at <= start_at:
        end_at += timedelta(days=1)

    if now >= end_at:
        logging.warning(
            f"current time {now.strftime('%H:%M:%S')} is later than time window end {end_hms}; run immediately"
        )
        return now, now

    if now > start_at:
        return now, end_at

    return start_at, end_at


def resolve_window_for_date(target_date: date, start_hms: str, end_hms: str) -> Tuple[datetime, datetime]:
    start_time = datetime.strptime(start_hms, "%H:%M:%S").time()
    end_time = datetime.strptime(end_hms, "%H:%M:%S").time()
    start_at = datetime.combine(target_date, start_time)
    end_at = datetime.combine(target_date, end_time)

    if end_at <= start_at:
        end_at += timedelta(days=1)

    return start_at, end_at


def draw_random_times(count: int, start_at: datetime, end_at: datetime) -> List[datetime]:
    span_seconds = max(0.0, (end_at - start_at).total_seconds())
    if count <= 0:
        return []

    if span_seconds <= 0:
        return [start_at for _ in range(count)]

    return [start_at + timedelta(seconds=random.uniform(0, span_seconds)) for _ in range(count)]


def build_schedule_from_window(
    normal_users: List[User],
    admin_enabled: bool,
    start_at: datetime,
    end_at: datetime,
) -> Tuple[Dict[int, datetime], Optional[datetime]]:
    if not admin_enabled:
        normal_times = sorted(draw_random_times(len(normal_users), start_at, end_at))
        shuffled_normals = normal_users[:]
        random.shuffle(shuffled_normals)
        schedule = {
            user.student_Id: eta for user, eta in zip(shuffled_normals, normal_times)
        }
        return schedule, None

    draw_count = len(normal_users) + 1
    all_times = sorted(draw_random_times(draw_count, start_at, end_at))

    admin_eta = all_times[-1]
    normal_times = all_times[:-1]

    shuffled_normals = normal_users[:]
    random.shuffle(shuffled_normals)
    schedule = {
        user.student_Id: eta for user, eta in zip(shuffled_normals, normal_times)
    }
    return schedule, admin_eta


def build_schedule_with_admin_last(
    normal_users: List[User],
    admin_enabled: bool,
    start_hms: str,
    end_hms: str,
) -> Tuple[Dict[int, datetime], Optional[datetime]]:
    start_at, end_at = resolve_effective_window(start_hms, end_hms)
    return build_schedule_from_window(normal_users, admin_enabled, start_at, end_at)


def build_schedule_for_date(
    normal_users: List[User],
    admin_enabled: bool,
    start_hms: str,
    end_hms: str,
    target_date: date,
) -> Tuple[Dict[int, datetime], Optional[datetime]]:
    start_at, end_at = resolve_window_for_date(target_date, start_hms, end_hms)
    return build_schedule_from_window(normal_users, admin_enabled, start_at, end_at)


def log_estimated_plan(
    normal_users: List[User],
    schedule: Dict[int, datetime],
    admin_user: User,
    admin_enabled: bool,
    admin_eta: Optional[datetime],
    title: str = "estimated sign-in plan:",
) -> None:
    logging.info(title)

    if normal_users:
        sorted_users = sorted(normal_users, key=lambda user: schedule[user.student_Id])
        for user in sorted_users:
            eta = schedule[user.student_Id].strftime(DATETIME_FORMAT)
            logging.info(f"  user student_id={user.student_Id}, eta={eta}")
    else:
        logging.info("  no non-admin users to schedule")

    if admin_enabled:
        if admin_eta is None:
            admin_eta = datetime.now()
        logging.info(f"  admin student_id={admin_user.student_Id}, eta={admin_eta.strftime(DATETIME_FORMAT)}")
    else:
        logging.info(f"  admin student_id={admin_user.student_Id}, disabled")


def sign_user_with_schedule(user: User, execute_at: datetime, workflow: SignInWorkflow, debug: bool) -> dict:
    delay_seconds = (execute_at - datetime.now()).total_seconds()
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    result = workflow.sign_in(user, debug=debug)
    result["sign_time"] = datetime.now().strftime(DATETIME_FORMAT)
    return result


def build_next_day_eta_map(app_config: AppConfig, target_date: date) -> Dict[int, datetime]:
    if not app_config.users:
        return {}

    admin_user = app_config.users[0]
    enabled_users = [user for user in app_config.users if user.enabled]
    normal_users = [user for user in enabled_users if user.student_Id != admin_user.student_Id]
    schedule, admin_eta = build_schedule_for_date(
        normal_users=normal_users,
        admin_enabled=admin_user.enabled,
        start_hms=app_config.sign_time_window.start,
        end_hms=app_config.sign_time_window.end,
        target_date=target_date,
    )
    next_day_eta_map: Dict[int, datetime] = dict(schedule)
    if admin_user.enabled and admin_eta is not None:
        next_day_eta_map[admin_user.student_Id] = admin_eta
    return next_day_eta_map


def run_once_with_config(app_config: AppConfig) -> Dict[int, dict]:
    results: Dict[int, dict] = {}

    if not app_config.users:
        logging.error("no users found in config.json, please configure at least one user")
        return results

    admin_user = app_config.users[0]
    next_day_date = datetime.now().date() + timedelta(days=1)
    next_day_eta_map = build_next_day_eta_map(app_config, next_day_date)
    enabled_users = [user for user in app_config.users if user.enabled]
    normal_users = [user for user in enabled_users if user.student_Id != admin_user.student_Id]
    start_time = time.time()

    workflow = SignInWorkflow(
        client=SignInClient(
            http_connect_timeout_seconds=app_config.http_connect_timeout_seconds,
            http_read_timeout_seconds=app_config.http_read_timeout_seconds,
            request_retries=app_config.http_request_retries,
            retry_backoff_seconds=app_config.http_retry_backoff_seconds,
            min_sign_time=app_config.sign_time_window.start,
        ),
        max_retries=app_config.max_retries,
        max_token_retries=app_config.max_token_retries,
    )
    email_service = EmailService(app_config.email_config)

    if not enabled_users:
        logging.warning("no enabled users found in config.json, skip sign-in")
        email_service.send_summary_email_to_first_user(app_config.users, results, next_day_eta_map)
    else:
        schedule, admin_eta = build_schedule_with_admin_last(
            normal_users=normal_users,
            admin_enabled=admin_user.enabled,
            start_hms=app_config.sign_time_window.start,
            end_hms=app_config.sign_time_window.end,
        )

        log_estimated_plan(normal_users, schedule, admin_user, admin_user.enabled, admin_eta)

        if normal_users:
            max_workers = max(1, min(app_config.max_workers, len(normal_users)))

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures_to_user = {
                    executor.submit(
                        sign_user_with_schedule,
                        user,
                        schedule[user.student_Id],
                        workflow,
                        app_config.debug,
                    ): user
                    for user in normal_users
                }

                for future in as_completed(futures_to_user):
                    user = futures_to_user[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        logging.exception(f"unexpected error when signing for {user.student_Id}")
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
                admin_result = workflow.sign_in(admin_user, debug=app_config.debug)
                admin_result["sign_time"] = datetime.now().strftime(DATETIME_FORMAT)
            except Exception as exc:
                logging.exception(f"unexpected error when signing for admin {admin_user.student_Id}")
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
        f"Sign-in finished. total_users={len(app_config.users)}, total_enabled={len(enabled_users)}, success={success_count}, "
        f"elapsed={end_time - start_time:.2f}s"
    )
    for student_id, result in results.items():
        print(f"  {student_id}: {result}")

    return results


def load_run_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {}

    try:
        with state_path.open("r", encoding="utf-8") as file:
            state = json.load(file)
    except Exception as exc:
        logging.warning(f"failed to read run state file {state_path}: {exc}")
        return {}

    if not isinstance(state, dict):
        logging.warning(f"invalid run state in {state_path}, expected JSON object")
        return {}

    return state


def save_run_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
        file.write("\n")
    tmp_path.replace(state_path)


def get_state_file_path(config_path: Path) -> Path:
    return config_path.parent / "logs" / RUN_STATE_FILE_NAME


def is_date_completed(state_path: Path, date_str: str) -> bool:
    state = load_run_state(state_path)
    return str(state.get("last_completed_date", "")) == date_str


def mark_date_completed(state_path: Path, date_str: str) -> None:
    state = load_run_state(state_path)
    state["last_completed_date"] = date_str
    state["last_finished_at"] = datetime.now().strftime(DATETIME_FORMAT)
    save_run_state(state_path, state)


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


def log_next_day_plan(app_config: AppConfig, target_date: date) -> None:
    if not app_config.users:
        return

    admin_user = app_config.users[0]
    enabled_users = [user for user in app_config.users if user.enabled]
    normal_users = [user for user in enabled_users if user.student_Id != admin_user.student_Id]

    if not enabled_users:
        logging.info(f"no enabled users found for next-day plan ({target_date.strftime(DATE_FORMAT)})")
        return

    schedule, admin_eta = build_schedule_for_date(
        normal_users=normal_users,
        admin_enabled=admin_user.enabled,
        start_hms=app_config.sign_time_window.start,
        end_hms=app_config.sign_time_window.end,
        target_date=target_date,
    )
    log_estimated_plan(
        normal_users=normal_users,
        schedule=schedule,
        admin_user=admin_user,
        admin_enabled=admin_user.enabled,
        admin_eta=admin_eta,
        title=f"next-day estimated sign-in plan ({target_date.strftime(DATE_FORMAT)}):",
    )


def run(config_path: Path) -> int:
    try:
        app_config = load_app_config(config_path)
    except Exception as exc:
        print(f"Failed to load config file: {exc}", file=sys.stderr)
        return 1

    setup_logging(app_config.log_level, config_path.parent / "logs")
    run_once_with_config(app_config)
    return 0


def run_forever(config_path: Path) -> int:
    state_path = get_state_file_path(config_path)

    while True:
        try:
            app_config = load_app_config(config_path)
        except Exception as exc:
            print(f"Failed to load config file: {exc}", file=sys.stderr)
            time.sleep(60)
            continue

        setup_logging(app_config.log_level, config_path.parent / "logs")
        today = datetime.now().strftime(DATE_FORMAT)

        try:
            if is_date_completed(state_path, today):
                next_start = get_next_start_datetime(app_config.sign_time_window.start)
                logging.info(f"daily run already completed for {today}, skip duplicate execution")
                log_next_day_plan(app_config, next_start.date())
                logging.info(f"waiting for next run at {next_start.strftime(DATETIME_FORMAT)}")
                sleep_until(next_start)
                continue

            run_once_with_config(app_config)
            mark_date_completed(state_path, today)

            next_start = get_next_start_datetime(app_config.sign_time_window.start)
            log_next_day_plan(app_config, next_start.date())
            logging.info(f"daily cycle completed, waiting for next run at {next_start.strftime(DATETIME_FORMAT)}")
            sleep_until(next_start)
        except KeyboardInterrupt:
            logging.info("received keyboard interrupt, exit sign-in loop")
            return 0
        except Exception:
            logging.exception("unexpected error in sign-in loop, retry after 60 seconds")
            time.sleep(60)




