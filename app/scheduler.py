import logging
import random
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .constants import DATETIME_FORMAT
from .models import AppConfig, UserConfig


class Scheduler:
    @staticmethod
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
                "current time %s is later than time window end %s; run immediately",
                now.strftime("%H:%M:%S"),
                end_hms,
            )
            return now, now

        if now > start_at:
            return now, end_at

        return start_at, end_at

    @staticmethod
    def resolve_window_for_date(target_date: date, start_hms: str, end_hms: str) -> Tuple[datetime, datetime]:
        start_time = datetime.strptime(start_hms, "%H:%M:%S").time()
        end_time = datetime.strptime(end_hms, "%H:%M:%S").time()

        start_at = datetime.combine(target_date, start_time)
        end_at = datetime.combine(target_date, end_time)

        if end_at <= start_at:
            end_at += timedelta(days=1)

        return start_at, end_at

    @staticmethod
    def draw_random_times(count: int, start_at: datetime, end_at: datetime) -> List[datetime]:
        if count <= 0:
            return []

        span_seconds = max(0.0, (end_at - start_at).total_seconds())
        if span_seconds <= 0:
            return [start_at for _ in range(count)]

        return [start_at + timedelta(seconds=random.uniform(0, span_seconds)) for _ in range(count)]

    @staticmethod
    def build_schedule_from_window(
        normal_users: List[UserConfig],
        admin_enabled: bool,
        start_at: datetime,
        end_at: datetime,
    ) -> Tuple[Dict[int, datetime], Optional[datetime]]:
        if not admin_enabled:
            normal_times = sorted(Scheduler.draw_random_times(len(normal_users), start_at, end_at))
            shuffled_normals = normal_users[:]
            random.shuffle(shuffled_normals)
            schedule = {user.student_Id: eta for user, eta in zip(shuffled_normals, normal_times)}
            return schedule, None

        all_times = sorted(Scheduler.draw_random_times(len(normal_users) + 1, start_at, end_at))
        admin_eta = all_times[-1]
        normal_times = all_times[:-1]

        shuffled_normals = normal_users[:]
        random.shuffle(shuffled_normals)
        schedule = {user.student_Id: eta for user, eta in zip(shuffled_normals, normal_times)}
        return schedule, admin_eta

    @staticmethod
    def build_schedule_with_admin_last(
        normal_users: List[UserConfig],
        admin_enabled: bool,
        start_hms: str,
        end_hms: str,
    ) -> Tuple[Dict[int, datetime], Optional[datetime]]:
        start_at, end_at = Scheduler.resolve_effective_window(start_hms, end_hms)
        return Scheduler.build_schedule_from_window(normal_users, admin_enabled, start_at, end_at)

    @staticmethod
    def build_schedule_for_date(
        normal_users: List[UserConfig],
        admin_enabled: bool,
        start_hms: str,
        end_hms: str,
        target_date: date,
    ) -> Tuple[Dict[int, datetime], Optional[datetime]]:
        start_at, end_at = Scheduler.resolve_window_for_date(target_date, start_hms, end_hms)
        return Scheduler.build_schedule_from_window(normal_users, admin_enabled, start_at, end_at)

    @staticmethod
    def build_next_day_eta_map(app_config: AppConfig, target_date: date) -> Dict[int, datetime]:
        if not app_config.users:
            return {}

        admin_user = app_config.users[0]
        enabled_users = [user for user in app_config.users if user.enabled]
        normal_users = [user for user in enabled_users if user.student_Id != admin_user.student_Id]

        schedule, admin_eta = Scheduler.build_schedule_for_date(
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

    @staticmethod
    def log_estimated_plan(
        normal_users: List[UserConfig],
        schedule: Dict[int, datetime],
        admin_user: UserConfig,
        admin_enabled: bool,
        admin_eta: Optional[datetime],
        title: str,
    ) -> None:
        logging.info(title)

        if normal_users:
            sorted_users = sorted(normal_users, key=lambda user: schedule[user.student_Id])
            for user in sorted_users:
                eta = schedule[user.student_Id].strftime(DATETIME_FORMAT)
                logging.info("  user student_id=%s, eta=%s", user.student_Id, eta)
        else:
            logging.info("  no non-admin users to schedule")

        if admin_enabled:
            effective_admin_eta = admin_eta or datetime.now()
            logging.info(
                "  admin student_id=%s, eta=%s",
                admin_user.student_Id,
                effective_admin_eta.strftime(DATETIME_FORMAT),
            )
        else:
            logging.info("  admin student_id=%s, disabled", admin_user.student_Id)
