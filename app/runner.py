import logging
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import load_app_config
from .email_service import EmailService
from .logging_setup import setup_logging
from .models import User
from .time_utils import get_time
from .workflow import SignInClient, SignInWorkflow


def build_failure_result(student_id: int, exc: Exception) -> dict:
    return {
        "success": False,
        "errors": [str(exc)],
        "failure_logs": [f"[{get_time()['full']}] student_id={student_id}, msg={str(exc)}"],
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


def draw_random_times(count: int, start_at: datetime, end_at: datetime) -> List[datetime]:
    span_seconds = max(0.0, (end_at - start_at).total_seconds())
    if count <= 0:
        return []

    if span_seconds <= 0:
        return [start_at for _ in range(count)]

    return [start_at + timedelta(seconds=random.uniform(0, span_seconds)) for _ in range(count)]


def build_schedule_with_admin_last(
    normal_users: List[User],
    admin_user: User,
    admin_enabled: bool,
    start_hms: str,
    end_hms: str,
) -> Tuple[Dict[int, datetime], Optional[datetime]]:
    start_at, end_at = resolve_effective_window(start_hms, end_hms)

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


def log_estimated_plan(
    normal_users: List[User],
    schedule: Dict[int, datetime],
    admin_user: User,
    admin_enabled: bool,
    admin_eta: Optional[datetime],
) -> None:
    logging.info("estimated sign-in plan:")

    if normal_users:
        sorted_users = sorted(normal_users, key=lambda user: schedule[user.student_Id])
        for user in sorted_users:
            eta = schedule[user.student_Id].strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f"  user student_id={user.student_Id}, eta={eta}")
    else:
        logging.info("  no non-admin users to schedule")

    if admin_enabled:
        if admin_eta is None:
            admin_eta = datetime.now()
        logging.info(f"  admin student_id={admin_user.student_Id}, eta={admin_eta.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        logging.info(f"  admin student_id={admin_user.student_Id}, disabled")


def sign_user_with_schedule(user: User, execute_at: datetime, workflow: SignInWorkflow, debug: bool) -> dict:
    delay_seconds = (execute_at - datetime.now()).total_seconds()
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    return workflow.sign_in(user, debug=debug)


def run(config_path: Path) -> int:
    try:
        app_config = load_app_config(config_path)
    except Exception as exc:
        print(f"Failed to load config file: {exc}", file=sys.stderr)
        return 1

    setup_logging(app_config.log_level, config_path.parent / "logs")

    if not app_config.users:
        logging.error("no users found in config.json, please configure at least one user")
        return 0

    admin_user = app_config.users[0]
    enabled_users = [user for user in app_config.users if user.enabled]
    normal_users = [user for user in enabled_users if user.student_Id != admin_user.student_Id]
    results = {}
    start_time = time.time()

    workflow = SignInWorkflow(
        client=SignInClient(
            http_timeout_seconds=app_config.http_timeout_seconds,
            min_sign_time=app_config.sign_time_window.start,
        ),
        max_retries=app_config.max_retries,
        max_token_retries=app_config.max_token_retries,
    )
    email_service = EmailService(app_config.email_config)

    if not enabled_users:
        logging.warning("no enabled users found in config.json, skip sign-in")
        email_service.send_summary_email_to_first_user(app_config.users, results)
    else:
        schedule, admin_eta = build_schedule_with_admin_last(
            normal_users=normal_users,
            admin_user=admin_user,
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
            except Exception as exc:
                logging.exception(f"unexpected error when signing for admin {admin_user.student_Id}")
                admin_result = build_failure_result(admin_user.student_Id, exc)

            results[admin_user.student_Id] = admin_result
            email_service.send_combined_email_to_admin_when_signed(
                admin_user=admin_user,
                admin_result=admin_result,
                all_users=app_config.users,
                results=results,
            )
        else:
            logging.warning("admin user is disabled; send summary email only")
            email_service.send_summary_email_to_first_user(app_config.users, results)

    end_time = time.time()
    success_count = sum(1 for result in results.values() if result.get("success"))

    print(
        f"Sign-in finished. total_users={len(app_config.users)}, total_enabled={len(enabled_users)}, success={success_count}, "
        f"elapsed={end_time - start_time:.2f}s"
    )
    for student_id, result in results.items():
        print(f"  {student_id}: {result}")

    return 0
