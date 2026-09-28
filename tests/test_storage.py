from datetime import date
from pathlib import Path

import clockout.storage as storage
from clockout.storage import CompletionStore, default_state_path


def test_default_state_path_uses_platformdirs(monkeypatch) -> None:
    app_data = Path("C:/Users/tester/AppData/Local/ClockOut")

    monkeypatch.setattr(storage.platformdirs, "user_data_path", lambda appname: app_data)

    assert default_state_path() == app_data / "completion-date"


def test_default_state_path_is_os_data_path_outside_repository() -> None:
    state_path = default_state_path()
    repository_root = Path(__file__).resolve().parents[1]

    assert state_path == storage.platformdirs.user_data_path("ClockOut") / "completion-date"
    assert not state_path.is_relative_to(repository_root)


def test_missing_state_is_not_done_and_does_not_create_parent(tmp_path: Path) -> None:
    state_path = tmp_path / "nested" / "completion-date"
    store = CompletionStore(state_path)

    assert not store.is_done_today(date(2026, 9, 28))
    assert not state_path.exists()
    assert not state_path.parent.exists()


def test_mark_done_creates_parent_and_persists_plain_local_date(tmp_path: Path) -> None:
    state_path = tmp_path / "nested" / "completion-date"
    store = CompletionStore(state_path)
    completed_date = date(2026, 9, 28)

    store.mark_done_today(completed_date)

    assert state_path.read_text(encoding="utf-8") == "2026-09-28"
    assert store.is_done_today(completed_date)


def test_omitted_date_uses_the_machine_local_calendar_date(tmp_path: Path) -> None:
    state_path = tmp_path / "completion-date"
    store = CompletionStore(state_path)

    store.mark_done_today()

    assert state_path.read_text(encoding="utf-8") == date.today().isoformat()
    assert store.is_done_today()


def test_mocked_local_next_day_rollover_is_not_done(tmp_path: Path, monkeypatch) -> None:
    class MockLocalDate:
        current = date(2026, 9, 28)

        @classmethod
        def today(cls) -> date:
            return cls.current

    monkeypatch.setattr(storage, "date", MockLocalDate)
    state_path = tmp_path / "completion-date"
    store = CompletionStore(state_path)

    store.mark_done_today()

    assert state_path.read_text(encoding="utf-8") == "2026-09-28"
    assert store.is_done_today()

    MockLocalDate.current = date(2026, 9, 29)

    assert not store.is_done_today()


def test_invalid_stale_future_and_empty_state_are_not_done(tmp_path: Path) -> None:
    state_path = tmp_path / "completion-date"
    store = CompletionStore(state_path)
    today = date(2026, 9, 28)

    for contents in ("", "not-a-date", "2026-09-27", "2026-09-29", "20260928"):
        state_path.write_text(contents, encoding="utf-8")

        assert not store.is_done_today(today)


def test_completion_only_matches_the_injected_calendar_date(tmp_path: Path) -> None:
    state_path = tmp_path / "completion-date"
    store = CompletionStore(state_path)
    completed_date = date(2026, 9, 28)

    store.mark_done_today(completed_date)

    assert store.is_done_today(completed_date)
    assert not store.is_done_today(date(2026, 9, 27))
    assert not store.is_done_today(date(2026, 9, 29))