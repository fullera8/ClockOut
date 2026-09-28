from collections.abc import Callable
from datetime import datetime
from threading import Thread
from typing import Any

import tkinter as tk

import pystray
from PIL import Image, ImageDraw

from .scheduler import Scheduler
from .state_machine import (
    Choice,
    RETRY_STATUS,
    StateMachine,
    TransitionResult,
)


PROMPT_TEXT = "Are you going to be home on time?"
YES_LABEL = "Yes"
THIRTY_MINUTES_LABEL = "I'll be another 30 min"
HOUR_LABEL = "I'll be another hour"
TRAY_EXIT_LABEL = "Exit"
WINDOW_WIDTH = 420
WINDOW_HEIGHT = 220
WINDOW_MARGIN = 16
POLL_INTERVAL_MS = 1000


class TrayApplication:
    def __init__(
        self,
        state_machine: StateMachine,
        scheduler: Scheduler,
        root: Any | None = None,
        icon: Any | None = None,
        clock: Callable[[], datetime] | None = None,
        tk_module: Any | None = None,
        pystray_module: Any | None = None,
        poll_interval_ms: int = POLL_INTERVAL_MS,
    ) -> None:
        self.state_machine = state_machine
        self.scheduler = scheduler
        self.clock = datetime.now if clock is None else clock
        self.poll_interval_ms = poll_interval_ms
        self._tk = tk if tk_module is None else tk_module
        self._pystray = pystray if pystray_module is None else pystray_module
        self.root = self._tk.Tk() if root is None else root
        self.icon = icon if icon is not None else self._build_icon()
        self._poll_job: Any | None = None
        self._tray_thread: Thread | None = None
        self._tray_started = False
        self._stopped = False

        self._configure_window()
        self._build_prompt()

    def _configure_window(self) -> None:
        self.root.title("ClockOut")
        self.root.withdraw()
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        screen_width = int(self.root.winfo_screenwidth())
        screen_height = int(self.root.winfo_screenheight())
        x = max(0, screen_width - WINDOW_WIDTH - WINDOW_MARGIN)
        y = max(0, screen_height - WINDOW_HEIGHT - WINDOW_MARGIN)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")
        protocol = getattr(self.root, "protocol", None)
        if protocol is not None:
            protocol("WM_DELETE_WINDOW", self.stop)

    def _build_prompt(self) -> None:
        self.prompt_label = self._tk.Label(self.root, text=PROMPT_TEXT)
        self.prompt_label.pack(fill="x", padx=20, pady=(18, 10))

        self.yes_button = self._tk.Button(
            self.root,
            text=YES_LABEL,
            command=lambda: self.choose(Choice.YES),
        )
        self.yes_button.pack(fill="x", padx=20, pady=2)

        self.thirty_minutes_button = self._tk.Button(
            self.root,
            text=THIRTY_MINUTES_LABEL,
            command=lambda: self.choose(Choice.THIRTY_MINUTES),
        )
        self.thirty_minutes_button.pack(fill="x", padx=20, pady=2)

        self.hour_button = self._tk.Button(
            self.root,
            text=HOUR_LABEL,
            command=lambda: self.choose(Choice.HOUR),
        )
        self.hour_button.pack(fill="x", padx=20, pady=2)

        self.retry_label = self._tk.Label(self.root, text=RETRY_STATUS)
        self.retry_label.pack(fill="x", padx=20, pady=(8, 0))
        self.retry_label.pack_forget()
        self.retry_status_label = self.retry_label

    def _build_icon(self) -> Any:
        image = Image.new("RGBA", (64, 64), "#1f6feb")
        draw = ImageDraw.Draw(image)
        draw.rectangle((12, 12, 52, 52), fill="#ffffff")
        menu = self._pystray.Menu(
            self._pystray.MenuItem(TRAY_EXIT_LABEL, self._exit_from_tray)
        )
        return self._pystray.Icon("ClockOut", image, "ClockOut", menu=menu)

    def _exit_from_tray(self, *_args: object) -> None:
        self.root.after(0, self.stop)

    def choose(self, choice: Choice) -> TransitionResult:
        result = self.state_machine.choose(choice, self.clock())
        self._apply_result(result)
        return result

    def poll(self) -> TransitionResult:
        result = self.scheduler.tick(self.clock())
        self._apply_result(result)
        return result

    def _apply_result(self, result: TransitionResult) -> None:
        if result.show_prompt:
            self._show_prompt(result.retry_status)
        else:
            self._hide_prompt()

    def _show_prompt(self, retry_status: str | None = None) -> None:
        self.root.deiconify()
        lift = getattr(self.root, "lift", None)
        if lift is not None:
            lift()
        if retry_status is None:
            self.retry_label.pack_forget()
            return
        self.retry_label.configure(text=retry_status)
        self.retry_label.pack(fill="x", padx=20, pady=(8, 0))

    def _hide_prompt(self) -> None:
        self.retry_label.pack_forget()
        self.root.withdraw()

    def _poll(self) -> None:
        if self._stopped:
            return
        self.poll()
        self._poll_job = self.root.after(self.poll_interval_ms, self._poll)

    def _start_tray(self) -> None:
        if self._tray_started:
            return
        self._tray_started = True
        run_detached = getattr(self.icon, "run_detached", None)
        if run_detached is not None:
            run_detached()
            return
        self._tray_thread = Thread(target=self.icon.run, daemon=True)
        self._tray_thread.start()

    def run(self) -> None:
        self._stopped = False
        self._start_tray()
        self._poll_job = self.root.after(0, self._poll)
        try:
            self.root.mainloop()
        finally:
            self.stop()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._poll_job is not None:
            after_cancel = getattr(self.root, "after_cancel", None)
            if after_cancel is not None:
                try:
                    after_cancel(self._poll_job)
                except Exception:
                    pass
            self._poll_job = None
        if self._tray_started:
            stop_icon = getattr(self.icon, "stop", None)
            if stop_icon is not None:
                try:
                    stop_icon()
                except Exception:
                    pass
            self._tray_started = False
        quit_root = getattr(self.root, "quit", None)
        if quit_root is not None:
            try:
                quit_root()
            except Exception:
                pass
        destroy_root = getattr(self.root, "destroy", None)
        if destroy_root is not None:
            try:
                destroy_root()
            except Exception:
                pass


__all__ = [
    "HOUR_LABEL",
    "POLL_INTERVAL_MS",
    "PROMPT_TEXT",
    "THIRTY_MINUTES_LABEL",
    "TRAY_EXIT_LABEL",
    "TrayApplication",
    "WINDOW_HEIGHT",
    "WINDOW_MARGIN",
    "WINDOW_WIDTH",
    "YES_LABEL",
]