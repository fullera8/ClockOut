from datetime import date
from pathlib import Path

import platformdirs


_STATE_FILENAME = "completion-date"


def default_state_path() -> Path:
    return platformdirs.user_data_path("ClockOut") / _STATE_FILENAME


class CompletionStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def is_done_today(self, today: date | None = None) -> bool:
        expected_date = (date.today() if today is None else today).isoformat()

        try:
            return self.path.read_text(encoding="utf-8") == expected_date
        except (OSError, UnicodeError):
            return False

    def mark_done_today(self, today: date | None = None) -> None:
        completed_date = date.today() if today is None else today
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(completed_date.isoformat(), encoding="utf-8")