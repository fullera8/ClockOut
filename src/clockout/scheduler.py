from datetime import datetime, time
from typing import Callable, Protocol

from .state_machine import State, StateMachine, TransitionResult


DAILY_PROMPT_TIME = time(16, 50)
DEFAULT_POLL_INTERVAL = 1.0


class StopEventLike(Protocol):
    def is_set(self) -> bool:
        ...

    def wait(self, timeout: float | None = None) -> bool:
        ...


class Scheduler:
    def __init__(
        self,
        state_machine: StateMachine,
        now_provider: Callable[[], datetime] | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        self._state_machine = state_machine
        self._now_provider = datetime.now if now_provider is None else now_provider
        self._poll_interval = poll_interval

    def tick(self, now: datetime) -> TransitionResult:
        result = self._state_machine.refresh(now)

        if (
            result.state is State.IDLE
            and now.weekday() < 5
            and now.time() >= DAILY_PROMPT_TIME
        ):
            return self._state_machine.trigger_prompt(now)

        return result

    def run(self, stop_event: StopEventLike) -> None:
        while not stop_event.is_set():
            self.tick(self._now_provider())
            stop_event.wait(self._poll_interval)


__all__ = ["DEFAULT_POLL_INTERVAL", "DAILY_PROMPT_TIME", "Scheduler"]