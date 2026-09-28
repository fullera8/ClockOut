from datetime import date, datetime, timedelta
from pathlib import Path
import runpy

import pytest
import requests

import clockout.app as app_module
from clockout.app import build_app
from clockout.config import AppConfig, ConfigurationError, load_config
from clockout.messaging import SendResult
from clockout.state_machine import Choice, State
from clockout.ui import TrayApplication


START = datetime(2026, 9, 28, 16, 50)
WEBHOOK_URL = "https://example.invalid/workflow"


class RecordingStore:
    def __init__(self, done_dates: set[date] | None = None) -> None:
        self.done_dates = set() if done_dates is None else set(done_dates)
        self.path: Path | None = None

    def is_done_today(self, today: date) -> bool:
        return today in self.done_dates

    def mark_done_today(self, today: date) -> None:
        self.done_dates.add(today)


class RecordingMessenger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, message_text: str) -> SendResult:
        self.messages.append(message_text)
        return SendResult(success=True, status_code=202)


class FakeWidget:
    def __init__(self, _parent, text=None, command=None) -> None:
        self.text = text
        self.command = command
        self.visible = False

    def pack(self, **_kwargs) -> None:
        self.visible = True

    def pack_forget(self) -> None:
        self.visible = False

    def configure(self, **kwargs) -> None:
        self.text = kwargs["text"]

    def invoke(self) -> None:
        return self.command()


class FakeRoot:
    def __init__(self) -> None:
        self.withdrawn = False

    def title(self, _value) -> None:
        pass

    def withdraw(self) -> None:
        self.withdrawn = True

    def deiconify(self) -> None:
        self.withdrawn = False

    def attributes(self, *_args) -> None:
        pass

    def resizable(self, *_args) -> None:
        pass

    def winfo_screenwidth(self) -> int:
        return 1920

    def winfo_screenheight(self) -> int:
        return 1080

    def geometry(self, _value) -> None:
        pass

    def protocol(self, *_args) -> None:
        pass

    def lift(self) -> None:
        pass


class FakeTkModule:
    Label = FakeWidget
    Button = FakeWidget


class FakeIcon:
    pass


def make_headless_application_factory(clicked_at: datetime):
    def create_application(machine, scheduler) -> TrayApplication:
        return TrayApplication(
            machine,
            scheduler,
            root=FakeRoot(),
            icon=FakeIcon(),
            clock=lambda: clicked_at,
            tk_module=FakeTkModule(),
        )

    return create_application


def make_app(
    tmp_path: Path,
    done_dates: set[date] | None = None,
    clicked_at: datetime = START,
) -> tuple[TrayApplication, RecordingStore, RecordingMessenger]:
    store = RecordingStore(done_dates)
    messenger = RecordingMessenger()
    state_path = tmp_path / "completion-date"

    def create_store(path: Path) -> RecordingStore:
        store.path = path
        return store

    application = build_app(
        config_loader=lambda: AppConfig(webhook_url=WEBHOOK_URL),
        state_path_factory=lambda: state_path,
        store_factory=create_store,
        messenger_factory=lambda _url: messenger,
        now_provider=lambda: START,
        application_factory=make_headless_application_factory(clicked_at),
    )
    return application, store, messenger


def test_build_app_composes_factories_in_order_and_uses_local_start_time() -> None:
    calls = []
    state_path = Path("C:/test/ClockOut/completion-date")
    fake_store = RecordingStore()
    fake_messenger = RecordingMessenger()
    application = object()

    def load() -> AppConfig:
        calls.append("config")
        return AppConfig(webhook_url=WEBHOOK_URL)

    def make_path() -> Path:
        calls.append("path")
        return state_path

    def make_store(path: Path) -> RecordingStore:
        calls.append(("store", path))
        return fake_store

    def make_messenger(url: str) -> RecordingMessenger:
        calls.append(("messenger", url))
        return fake_messenger

    def make_state_machine(store, messenger, now):
        calls.append(("state_machine", store, messenger, now))
        return "machine"

    def make_scheduler(machine):
        calls.append(("scheduler", machine))
        return "scheduler"

    def make_application(machine, scheduler):
        calls.append(("application", machine, scheduler))
        return application

    result = build_app(
        config_loader=load,
        state_path_factory=make_path,
        store_factory=make_store,
        messenger_factory=make_messenger,
        state_machine_factory=make_state_machine,
        scheduler_factory=make_scheduler,
        application_factory=make_application,
        now_provider=lambda: START,
    )

    assert result is application
    assert calls == [
        "config",
        "path",
        ("store", state_path),
        ("messenger", WEBHOOK_URL),
        ("state_machine", fake_store, fake_messenger, START),
        ("scheduler", "machine"),
        ("application", "machine", "scheduler"),
    ]


def test_build_app_uses_default_components_and_local_datetime(monkeypatch) -> None:
    calls = []
    state_path = Path("C:/Users/tester/AppData/Local/ClockOut/completion-date")
    application = object()

    class Recorder:
        def __init__(self, name, result):
            self.name = name
            self.result = result

        def __call__(self, *args, **kwargs):
            calls.append((self.name, args, kwargs))
            return self.result

    config_loader = Recorder("config", AppConfig(webhook_url=WEBHOOK_URL))
    state_path_factory = Recorder("default_state_path", state_path)
    store_factory = Recorder("CompletionStore", "store")
    messenger_factory = Recorder("MessagingClient", "messenger")
    state_machine_factory = Recorder("StateMachine.start", "state-machine")
    scheduler_factory = Recorder("Scheduler", "scheduler")
    application_factory = Recorder("TrayApplication", application)
    now_provider = Recorder("local_datetime", START)

    class FakeStateMachine:
        start = staticmethod(state_machine_factory)

    class FakeLocalDateTime:
        now = staticmethod(now_provider)

    monkeypatch.setattr(app_module, "load_config", config_loader)
    monkeypatch.setattr(app_module, "default_state_path", state_path_factory)
    monkeypatch.setattr(app_module, "CompletionStore", store_factory)
    monkeypatch.setattr(app_module, "MessagingClient", messenger_factory)
    monkeypatch.setattr(app_module, "StateMachine", FakeStateMachine)
    monkeypatch.setattr(app_module, "Scheduler", scheduler_factory)
    monkeypatch.setattr(app_module, "TrayApplication", application_factory)
    monkeypatch.setattr(app_module, "datetime", FakeLocalDateTime)

    result = build_app()

    assert result is application
    assert calls == [
        ("config", (), {}),
        ("default_state_path", (), {}),
        ("CompletionStore", (state_path,), {}),
        ("MessagingClient", (WEBHOOK_URL,), {}),
        ("local_datetime", (), {}),
        ("StateMachine.start", ("store", "messenger", START), {}),
        ("Scheduler", ("state-machine",), {}),
        ("TrayApplication", ("state-machine", "scheduler"), {}),
    ]


def test_build_app_completed_today_stays_done_and_silent(tmp_path: Path) -> None:
    application, _store, messenger = make_app(tmp_path, done_dates={START.date()})

    assert application.state_machine.state is State.DONE

    result = application.poll()

    assert result.state is State.DONE
    assert not result.show_prompt
    assert application.root.withdrawn
    assert messenger.messages == []


@pytest.mark.parametrize(
    ("button_name", "choice", "message", "expected_state", "expected_delay"),
    (
        (
            "yes_button",
            Choice.YES,
            "I'll be home on time tonight.",
            State.DONE,
            None,
        ),
        (
            "thirty_minutes_button",
            Choice.THIRTY_MINUTES,
            "I'm going to be about 30 minutes late.",
            State.WAITING,
            timedelta(minutes=30),
        ),
        (
            "hour_button",
            Choice.HOUR,
            "I'm going to be about an hour late.",
            State.WAITING,
            timedelta(hours=1),
        ),
    ),
)
def test_build_app_routes_each_button_without_network(
    tmp_path: Path,
    monkeypatch,
    button_name: str,
    choice: Choice,
    message: str,
    expected_state: State,
    expected_delay: timedelta | None,
) -> None:
    def fail_network(*_args, **_kwargs):
        raise AssertionError("unexpected network request")

    monkeypatch.setattr(requests.Session, "post", fail_network)
    clicked_at = START + timedelta(minutes=7)
    application, store, messenger = make_app(tmp_path, clicked_at=clicked_at)

    application.poll()
    result = getattr(application, button_name).invoke()

    assert choice in (Choice.YES, Choice.THIRTY_MINUTES, Choice.HOUR)
    assert messenger.messages == [message]
    assert application.root.withdrawn
    assert application.state_machine.state is expected_state
    if expected_delay is None:
        assert store.done_dates == {clicked_at.date()}
        assert application.state_machine.next_prompt_deadline is None
    else:
        assert store.done_dates == set()
        assert application.state_machine.next_prompt_deadline == (
            clicked_at + expected_delay
        )
    assert result.state is expected_state


@pytest.mark.parametrize(
    ("env", "dotenv_contents"),
    (
        ({}, None),
        (
            {"GCHAT_WEBHOOK_URL": ""},
            "GCHAT_WEBHOOK_URL=https://example.invalid/hidden\n",
        ),
        (
            {"GCHAT_WEBHOOK_URL": "   "},
            "GCHAT_WEBHOOK_URL=https://example.invalid/hidden\n",
        ),
        ({}, "GCHAT_WEBHOOK_URL=   \n"),
    ),
)
def test_build_app_propagates_sanitized_missing_or_blank_configuration(
    tmp_path: Path,
    env: dict[str, str],
    dotenv_contents: str | None,
) -> None:
    dotenv_path = tmp_path / ".env"
    if dotenv_contents is not None:
        dotenv_path.write_text(dotenv_contents, encoding="utf-8")

    constructed = []
    with pytest.raises(ConfigurationError) as error:
        build_app(
            config_loader=lambda: load_config(env=env, dotenv_path=dotenv_path),
            store_factory=lambda _path: constructed.append("store"),
        )

    assert str(error.value) == "GCHAT_WEBHOOK_URL must be set"
    assert "example.invalid" not in str(error.value)
    assert constructed == []


def test_main_runs_the_composed_application(monkeypatch) -> None:
    class FakeApplication:
        def __init__(self) -> None:
            self.run_called = False

        def run(self) -> None:
            self.run_called = True

    fake_application = FakeApplication()
    monkeypatch.setattr(app_module, "build_app", lambda: fake_application)

    app_module.main()

    assert fake_application.run_called


def test_python_module_entry_point_delegates_to_main(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(app_module, "main", lambda: calls.append("main"))

    runpy.run_module("clockout.__main__", run_name="__main__")

    assert calls == ["main"]


def test_console_script_points_to_the_same_main_entry_point() -> None:
    repository_root = Path(__file__).parents[1]
    pyproject = (repository_root / "pyproject.toml").read_text(encoding="utf-8")

    assert "[project.scripts]" in pyproject
    assert 'clockout = "clockout.app:main"' in pyproject


def test_readme_documents_windows_setup_launch_and_manual_verification_boundary() -> None:
    repository_root = Path(__file__).parents[1]
    readme = " ".join((repository_root / "README.md").read_text(encoding="utf-8").split())
    required_phrases = (
        "## Install on Windows",
        "py -3 -m venv .venv",
        'python -m pip install -e ".[dev]"',
        "Copy-Item .env.example .env",
        "Teams Workflows",
        "legacy name `GCHAT_WEBHOOK_URL`",
        "GCHAT_WEBHOOK_URL=https://...",
        "Never commit `.env`",
        "`.env.example` intentionally has an empty value",
        "## Launch",
        "python -m clockout",
        "clockout",
        "process must remain running",
        "manual shortcut guidance only",
        "shell:startup",
        'Set the shortcut\'s "Start in" directory',
        "does not install a Windows service, scheduled task, or startup registration",
        "does not register itself with Windows",
        "Automated tests use fake stores and messengers and never send an HTTP request.",
        "manual verification by a human",
        "does not establish end-to-end success",
    )

    for phrase in required_phrases:
        assert phrase in readme