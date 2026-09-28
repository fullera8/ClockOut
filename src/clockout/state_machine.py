from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Protocol


RETRY_STATUS = "Message not sent — retry?"


class State(str, Enum):
    IDLE = "IDLE"
    PROMPTING = "PROMPTING"
    WAITING = "WAITING"
    DONE = "DONE"


class Choice(str, Enum):
    YES = "YES"
    THIRTY_MINUTES = "THIRTY_MINUTES"
    HOUR = "HOUR"


IDLE = State.IDLE
PROMPTING = State.PROMPTING
WAITING = State.WAITING
DONE = State.DONE
YES = Choice.YES
THIRTY_MINUTES = Choice.THIRTY_MINUTES
HOUR = Choice.HOUR


class CompletionStoreLike(Protocol):
    def is_done_today(self, today: date) -> bool:
        ...

    def mark_done_today(self, today: date) -> None:
        ...


class SendResultLike(Protocol):
    success: bool


class MessagingClientLike(Protocol):
    def send(self, message_text: str) -> SendResultLike:
        ...


@dataclass(frozen=True, slots=True)
class TransitionResult:
    state: State
    show_prompt: bool
    retry_status: str | None = None
    next_prompt_deadline: datetime | None = None

    @property
    def status(self) -> str | None:
        return self.retry_status


class StateMachine:
    def __init__(
        self,
        store: CompletionStoreLike,
        messenger: MessagingClientLike,
        state: State,
        active_date: date,
    ) -> None:
        self._store = store
        self._messenger = messenger
        self.state = state
        self._active_date = active_date
        self._retry_status: str | None = None
        self._next_prompt_deadline: datetime | None = None

    @classmethod
    def start(
        cls,
        store: CompletionStoreLike,
        messenger: MessagingClientLike,
        now: datetime,
    ) -> "StateMachine":
        state = State.DONE if store.is_done_today(now.date()) else State.IDLE
        return cls(store, messenger, state, now.date())

    @property
    def retry_status(self) -> str | None:
        return self._retry_status

    @property
    def next_prompt_deadline(self) -> datetime | None:
        return self._next_prompt_deadline

    @property
    def result(self) -> TransitionResult:
        return self._snapshot()

    def trigger_prompt(self, now: datetime) -> TransitionResult:
        self._handle_date_rollover(now)

        if self.state is State.IDLE:
            self.state = State.PROMPTING
            self._retry_status = None
            self._next_prompt_deadline = None

        return self._snapshot()

    def choose(self, choice: Choice, clicked_at: datetime) -> TransitionResult:
        self._handle_date_rollover(clicked_at)
        if self.state is not State.PROMPTING:
            raise ValueError("choice is only valid while PROMPTING")

        try:
            selected_choice = Choice(choice)
        except ValueError as error:
            raise ValueError(f"unsupported choice: {choice}") from error

        messages = {
            Choice.YES: "I'll be home on time tonight.",
            Choice.THIRTY_MINUTES: "I'm going to be about 30 minutes late.",
            Choice.HOUR: "I'm going to be about an hour late.",
        }

        if not self._send_succeeded(messages[selected_choice]):
            self._retry_status = RETRY_STATUS
            self._next_prompt_deadline = None
            return self._snapshot()

        self._retry_status = None
        if selected_choice is Choice.YES:
            self._store.mark_done_today(clicked_at.date())
            self.state = State.DONE
            self._next_prompt_deadline = None
        else:
            minutes = 30 if selected_choice is Choice.THIRTY_MINUTES else 60
            self.state = State.WAITING
            self._next_prompt_deadline = clicked_at + timedelta(minutes=minutes)

        return self._snapshot()

    def refresh(self, now: datetime) -> TransitionResult:
        self._handle_date_rollover(now)

        if (
            self.state is State.WAITING
            and self._next_prompt_deadline is not None
            and now >= self._next_prompt_deadline
        ):
            self.state = State.PROMPTING
            self._retry_status = None
            self._next_prompt_deadline = None

        return self._snapshot()

    def _handle_date_rollover(self, now: datetime) -> None:
        current_date = now.date()
        if current_date == self._active_date:
            return

        if self.state is State.DONE:
            self.state = State.IDLE
            self._retry_status = None
            self._next_prompt_deadline = None

        self._active_date = current_date

    def _send_succeeded(self, message_text: str) -> bool:
        try:
            result = self._messenger.send(message_text)
        except Exception:
            return False

        if isinstance(result, bool):
            return result
        return getattr(result, "success", False) is True

    def _snapshot(self) -> TransitionResult:
        return TransitionResult(
            state=self.state,
            show_prompt=self.state is State.PROMPTING,
            retry_status=self._retry_status,
            next_prompt_deadline=self._next_prompt_deadline,
        )


def start(
    store: CompletionStoreLike,
    messenger: MessagingClientLike,
    now: datetime,
) -> StateMachine:
    return StateMachine.start(store, messenger, now)


__all__ = [
    "Choice",
    "CompletionStoreLike",
    "DONE",
    "HOUR",
    "IDLE",
    "MessagingClientLike",
    "PROMPTING",
    "RETRY_STATUS",
    "State",
    "StateMachine",
    "THIRTY_MINUTES",
    "TransitionResult",
    "WAITING",
    "YES",
    "start",
]