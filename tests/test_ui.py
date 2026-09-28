import ast
from datetime import datetime
from pathlib import Path

import pytest
import tkinter

import pystray

from clockout.scheduler import Scheduler
from clockout.state_machine import Choice, State, StateMachine, TransitionResult
from clockout.ui import (
    HOUR_LABEL,
    PROMPT_TEXT,
    THIRTY_MINUTES_LABEL,
    TRAY_EXIT_LABEL,
    TrayApplication,
    WINDOW_HEIGHT,
    WINDOW_MARGIN,
    WINDOW_WIDTH,
    YES_LABEL,
)


class FakeWidget:
    def __init__(self, _parent, text=None, command=None) -> None:
        self.text = text
        self.command = command
        self.visible = False
        self.pack_calls = []

    def pack(self, **kwargs) -> None:
        self.visible = True
        self.pack_calls.append(kwargs)

    def pack_forget(self) -> None:
        self.visible = False

    def configure(self, **kwargs) -> None:
        self.text = kwargs["text"]

    def invoke(self) -> None:
        self.command()


class FakeTkModule:
    Label = FakeWidget
    Button = FakeWidget

    def Tk(self):
        return FakeRoot()


class FakeRoot:
    def __init__(self) -> None:
        self.withdrawn = False
        self.destroyed = False
        self.quit_called = False
        self.after_calls = []
        self.after_cancel_calls = []
        self.attributes_calls = []
        self.resizable_calls = []
        self.geometry_value = None
        self.protocol_calls = []
        self.mainloop_called = False
        self.mainloop_withdrawn = []

    def title(self, _value) -> None:
        pass

    def withdraw(self) -> None:
        self.withdrawn = True

    def deiconify(self) -> None:
        self.withdrawn = False

    def attributes(self, *args) -> None:
        self.attributes_calls.append(args)

    def resizable(self, *_args) -> None:
        self.resizable_calls.append(_args)

    def winfo_screenwidth(self) -> int:
        return 1920

    def winfo_screenheight(self) -> int:
        return 1080

    def geometry(self, value) -> None:
        self.geometry_value = value

    def protocol(self, *args) -> None:
        self.protocol_calls.append(args)

    def lift(self) -> None:
        pass

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))
        return f"after-{len(self.after_calls)}"

    def after_cancel(self, job) -> None:
        self.after_cancel_calls.append(job)

    def mainloop(self) -> None:
        self.mainloop_called = True
        self.mainloop_withdrawn.append(self.withdrawn)

    def quit(self) -> None:
        self.quit_called = True

    def destroy(self) -> None:
        self.destroyed = True


class FakeIcon:
    def __init__(self) -> None:
        self.run_called = False
        self.stop_called = False

    def run(self) -> None:
        self.run_called = True

    def stop(self) -> None:
        self.stop_called = True


class DetachedFakeIcon(FakeIcon):
    def __init__(self) -> None:
        super().__init__()
        self.run_detached_called = False

    def run_detached(self) -> None:
        self.run_detached_called = True


class FakeMenuItem:
    def __init__(self, text, action) -> None:
        self.text = text
        self.action = action


class FakeMenu:
    def __init__(self, *items) -> None:
        self.items = items


class FakePystray:
    Menu = FakeMenu
    MenuItem = FakeMenuItem

    def __init__(self) -> None:
        self.created_icon = None

    def Icon(self, name, image, title, menu):
        self.created_icon = FakeIcon()
        self.created_icon.arguments = (name, image, title)
        self.created_icon.menu = menu
        return self.created_icon


class FakeMachine:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = []
        self.direct_send_calls = []

    def choose(self, choice, clicked_at):
        self.calls.append((choice, clicked_at))
        return self.results.pop(0)

    def send(self, message_text):
        self.direct_send_calls.append(message_text)
        raise AssertionError("the UI must not send messages directly")


class FakeScheduler:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = []

    def tick(self, now):
        self.calls.append(now)
        return self.results.pop(0)


def make_application(machine, scheduler, clock=None):
    return TrayApplication(
        machine,
        scheduler,
        root=FakeRoot(),
        icon=FakeIcon(),
        clock=(lambda: datetime(2026, 9, 28, 17, 3)) if clock is None else clock,
        tk_module=FakeTkModule(),
        poll_interval_ms=250,
    )


def test_ui_uses_real_tkinter_and_pystray_without_browser_or_toast() -> None:
    import clockout.ui as ui_module

    assert ui_module.tk is tkinter
    assert ui_module.pystray is pystray

    source = Path(ui_module.__file__).read_text(encoding="utf-8")
    assert "self._tk.Tk()" in source
    assert "self._pystray.Icon(" in source
    tree = ast.parse(source)
    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.append(node.module)

    forbidden_modules = {"webbrowser", "win10toast", "plyer", "winrt", "toast"}
    assert not any(
        module.split(".")[0] in forbidden_modules for module in imported_modules
    )


def test_window_starts_with_exact_controls_hidden_and_topmost_at_corner() -> None:
    application = make_application(
        FakeMachine([]),
        FakeScheduler([]),
    )

    assert application.root.withdrawn
    assert application.prompt_label.text == PROMPT_TEXT
    assert application.yes_button.text == YES_LABEL
    assert application.thirty_minutes_button.text == THIRTY_MINUTES_LABEL
    assert application.hour_button.text == HOUR_LABEL
    assert not application.retry_label.visible
    assert application.root.attributes_calls == [("-topmost", True)]
    assert application.root.resizable_calls == [(False, False)]
    assert application.root.geometry_value == (
        f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+"
        f"{1920 - WINDOW_WIDTH - WINDOW_MARGIN}+"
        f"{1080 - WINDOW_HEIGHT - WINDOW_MARGIN}"
    )


def test_buttons_route_choices_with_current_local_click_time() -> None:
    clicked_at = datetime(2026, 9, 28, 17, 4)
    machine = FakeMachine(
        [
            TransitionResult(State.WAITING, False),
            TransitionResult(State.WAITING, False),
            TransitionResult(State.DONE, False),
        ]
    )
    application = make_application(
        machine,
        FakeScheduler([]),
        clock=lambda: clicked_at,
    )

    application.yes_button.invoke()
    application.thirty_minutes_button.invoke()
    application.hour_button.invoke()

    assert machine.calls == [
        (Choice.YES, clicked_at),
        (Choice.THIRTY_MINUTES, clicked_at),
        (Choice.HOUR, clicked_at),
    ]
    assert machine.direct_send_calls == []


@pytest.mark.parametrize(
    ("button_name", "choice", "success_state"),
    (
        ("yes_button", Choice.YES, State.DONE),
        ("thirty_minutes_button", Choice.THIRTY_MINUTES, State.WAITING),
        ("hour_button", Choice.HOUR, State.WAITING),
    ),
)
def test_successful_choice_hides_prompt_for_done_or_waiting(
    button_name: str,
    choice: Choice,
    success_state: State,
) -> None:
    clicked_at = datetime(2026, 9, 28, 17, 4)
    machine = FakeMachine([TransitionResult(success_state, False)])
    application = make_application(
        machine,
        FakeScheduler([TransitionResult(State.PROMPTING, True)]),
        clock=lambda: clicked_at,
    )

    application.poll()
    assert not application.root.withdrawn
    getattr(application, button_name).invoke()

    assert application.root.withdrawn
    assert not application.retry_label.visible
    assert machine.calls == [(choice, clicked_at)]
    assert machine.direct_send_calls == []


@pytest.mark.parametrize(
    ("button_name", "choice", "success_state"),
    (
        ("yes_button", Choice.YES, State.DONE),
        ("thirty_minutes_button", Choice.THIRTY_MINUTES, State.WAITING),
        ("hour_button", Choice.HOUR, State.WAITING),
    ),
)
def test_failed_choice_stays_visible_with_exact_retry_and_allows_reclick(
    button_name: str,
    choice: Choice,
    success_state: State,
) -> None:
    clicked_at = datetime(2026, 9, 28, 17, 4)
    machine = FakeMachine(
        [
            TransitionResult(
                State.PROMPTING,
                True,
                "Message not sent — retry?",
            ),
            TransitionResult(success_state, False),
        ]
    )
    application = make_application(
        machine,
        FakeScheduler([TransitionResult(State.PROMPTING, True)]),
        clock=lambda: clicked_at,
    )

    application.poll()
    button = getattr(application, button_name)
    button.invoke()

    assert not application.root.withdrawn
    assert application.retry_label.visible
    assert application.retry_label.text == "Message not sent — retry?"
    assert machine.calls == [(choice, clicked_at)]

    button.invoke()

    assert application.root.withdrawn
    assert not application.retry_label.visible
    assert machine.calls == [(choice, clicked_at), (choice, clicked_at)]
    assert machine.direct_send_calls == []


def test_send_failure_keeps_prompt_visible_and_shows_retry_status() -> None:
    machine = FakeMachine(
        [TransitionResult(State.PROMPTING, True, "Message not sent — retry?")]
    )
    application = make_application(machine, FakeScheduler([]))

    application.yes_button.invoke()

    assert not application.root.withdrawn
    assert application.retry_label.visible
    assert application.retry_label.text == "Message not sent — retry?"


def test_scheduler_poll_shows_prompt_and_hides_successful_result() -> None:
    now = datetime(2026, 9, 28, 16, 50)
    scheduler = FakeScheduler(
        [
            TransitionResult(State.PROMPTING, True),
            TransitionResult(State.WAITING, False),
        ]
    )
    application = make_application(FakeMachine([]), scheduler, clock=lambda: now)

    application.poll()
    assert not application.root.withdrawn
    application.poll()
    assert application.root.withdrawn
    assert scheduler.calls == [now, now]


def test_scheduler_polling_shows_due_prompt_and_preserves_click_deadline() -> None:
    class Store:
        def is_done_today(self, today) -> bool:
            return False

        def mark_done_today(self, today) -> None:
            raise AssertionError("the delayed choice must not mark the day done")

    class Messenger:
        def __init__(self) -> None:
            self.messages = []

        def send(self, message_text):
            self.messages.append(message_text)
            return True

    current_time = [datetime(2026, 9, 28, 16, 50)]
    machine = StateMachine.start(Store(), Messenger(), current_time[0])
    scheduler = Scheduler(machine)
    application = make_application(
        machine,
        scheduler,
        clock=lambda: current_time[0],
    )

    application.poll()
    assert not application.root.withdrawn

    current_time[0] = datetime(2026, 9, 28, 17, 7)
    application.thirty_minutes_button.invoke()
    click_deadline = datetime(2026, 9, 28, 17, 37)
    assert machine.next_prompt_deadline == click_deadline
    assert application.root.withdrawn

    current_time[0] = datetime(2026, 9, 28, 17, 36, 59)
    application.poll()
    assert application.root.withdrawn
    assert machine.next_prompt_deadline == click_deadline

    current_time[0] = click_deadline
    application.poll()
    assert not application.root.withdrawn
    assert machine.next_prompt_deadline is None


def test_tray_exit_queues_cleanup_on_tk_event_loop() -> None:
    root = FakeRoot()
    pystray_module = FakePystray()
    application = TrayApplication(
        FakeMachine([]),
        FakeScheduler([]),
        root=root,
        clock=lambda: datetime(2026, 9, 28, 16, 49),
        tk_module=FakeTkModule(),
        pystray_module=pystray_module,
    )

    assert pystray_module.created_icon is not None
    menu_items = pystray_module.created_icon.menu.items
    assert [item.text for item in menu_items] == [TRAY_EXIT_LABEL]

    menu_items[0].action(None)

    assert len(root.after_calls) == 1
    delay, callback = root.after_calls[0]
    assert delay == 0
    assert callback == application.stop
    assert not root.quit_called
    assert not root.destroyed

    callback()

    assert root.quit_called
    assert root.destroyed


def test_run_starts_detached_tray_and_tk_mainloop_and_stop_cleans_up() -> None:
    root = FakeRoot()
    icon = DetachedFakeIcon()
    application = TrayApplication(
        FakeMachine([]),
        FakeScheduler([]),
        root=root,
        icon=icon,
        clock=lambda: datetime(2026, 9, 28, 16, 49),
        tk_module=FakeTkModule(),
    )

    application.run()
    application.stop()

    assert icon.run_detached_called
    assert not icon.run_called
    assert icon.stop_called
    assert root.after_calls[0][0] == 0
    assert root.mainloop_called
    assert root.mainloop_withdrawn == [True]
    assert root.quit_called
    assert root.destroyed
    assert root.after_cancel_calls == ["after-1"]
    assert TRAY_EXIT_LABEL == "Exit"