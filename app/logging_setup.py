import logging
import sys
from datetime import datetime
from pathlib import Path

from .constants import DATE_FORMAT


class LoggerSetup:
    @staticmethod
    def get_daily_log_file(log_root_dir: Path) -> Path:
        now = datetime.now()
        month_dir = log_root_dir / f"{now.year:04d}{now.month:02d}"
        month_dir.mkdir(parents=True, exist_ok=True)
        return month_dir / f"{now.strftime(DATE_FORMAT)}.log"

    @staticmethod
    def setup_logging(log_level: int, log_root_dir: Path) -> None:
        formatter = logging.Formatter(
            fmt="%(levelname)s [%(name)s] (%(asctime)s): %(message)s (Line: %(lineno)d [%(filename)s])",
            datefmt="%Y/%m/%d %H:%M:%S",
        )

        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)

        console_handler = logging.StreamHandler(stream=sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.DEBUG)

        file_handler = logging.FileHandler(LoggerSetup.get_daily_log_file(log_root_dir), encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)

        root_logger.handlers.clear()
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
