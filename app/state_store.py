import json
import logging
from datetime import datetime
from pathlib import Path

from .constants import DATETIME_FORMAT


class StateStore:
    def __init__(self, state_path: Path):
        self.state_path = state_path

    def load(self) -> dict:
        if not self.state_path.exists():
            return {}

        try:
            with self.state_path.open("r", encoding="utf-8") as file:
                state = json.load(file)
        except Exception as exc:
            logging.warning(f"failed to read run state file {self.state_path}: {exc}")
            return {}

        if not isinstance(state, dict):
            logging.warning(f"invalid run state in {self.state_path}, expected JSON object")
            return {}

        return state

    def save(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)
            file.write("\n")
        tmp_path.replace(self.state_path)

    def is_date_completed(self, date_str: str) -> bool:
        state = self.load()
        return str(state.get("last_completed_date", "")) == date_str

    def mark_date_completed(self, date_str: str) -> None:
        state = self.load()
        state["last_completed_date"] = date_str
        state["last_finished_at"] = datetime.now().strftime(DATETIME_FORMAT)
        self.save(state)
