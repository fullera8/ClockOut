from datetime import date, datetime, time, timedelta

import pytest

from clockout.messaging import SendResult
from clockout.scheduler import Scheduler
from clockout.state_machine import Choice, State, StateMachine


WEEKDAY_BEFORE_PROMPT = datetime(2026, 9, 28, 16, 49, 59)
WEEKDAY_PROMPT_TIME = datetime(2026, 9, 28, 16, 50)
LOCAL_WEEKDAYS = (
    date(2026, 9, 28),
    date(2026, 9, 29),
    date(2026, 9, 30),
    date(2026, 10, 1),
    date(2026, 10, 2),
)
LOCAL_WEEKENDS = (date(2026, 10, 3), date(2026, 10, 4))


class FakeStore:
    def __init__(self, done_dates: set[date] | None = None) -> None:
        self.done_dates = set() if done_dates is None else set(done_dates)

    def is_done_today(self, today: date) -> bool:
        return today in self.done_dates

    def mark_done_today(self, today: date) -> None:
        self.done_dates.add(today)


class FakeMessenger:
    def __init__(self, results: list[SendResult | bool] | None = None) -> None:
        self.results = [] if results is None else list(results)
        self.messages: list[str] = []

    def send(self, message_text: str) -> SendResult | bool:
        self.messages.append(message_text)
        return self.results.pop(0)


def make_scheduler(
    now: datetime = WEEKDAY_BEFORE_PROMPT,
    done_dates: set[date] | None = None,
) -> tuple[Scheduler, StateMachine]:
    machine = StateMachine.start(
        FakeStore(done_dates),
        FakeMessenger(),
        now,
    )
    return Scheduler(machine), machine


@pytest.mark.parametrize("local_date", LOCAL_WEEKDAYS)
@pytest.mark.parametrize(
    ("clock_time", "expected_state"),
    (
        (time(16, 49, 59), State.IDLE),
        (time(16, 50), State.PROMPTING),
        (time(16, 50, 1), State.PROMPTING),
    ),
)
def test_weekday_daily_prompt_boundary(
    local_date: date,
    clock_time: time,
    expected_state: State,
) -> None:
    now = datetime.combine(local_date, clock_time)
    scheduler, machine = make_scheduler(now)

    result = scheduler.tick(now)

    assert result.state is expected_state
    assert result.show_prompt is (expected_state is State.PROMPTING)
    assert machine.state is expected_state


@pytest.mark.parametrize("local_date", LOCAL_WEEKENDS)
@pytest.mark.parametrize(
    "clock_time",
    (time(16, 49, 59), time(16, 50), time(17, 0)),
)
def test_weekend_does_not_trigger_daily_prompt(
    local_date: date,
    clock_time: time,
) -> None:
    now = datetime.combine(local_date, clock_time)
    scheduler, machine = make_scheduler(now)

    result = scheduler.tick(now)

    assert result.state is State.IDLE
    assert not result.show_prompt
    assert machine.state is State.IDLE


@pytest.mark.parametrize(
    "clock_time",
    (time(16, 49, 59), time(16, 50), time(17, 0)),
)
def test_completed_date_stays_silent_same_day(clock_time: time) -> None:
    now = datetime.combine(WEEKDAY_PROMPT_TIME.date(), clock_time)
    scheduler, machine = make_scheduler(now, done_dates={now.date()})

    result = scheduler.tick(now)

    assert result.state is State.DONE
    assert not result.show_prompt
    assert machine.state is State.DONE


def test_done_state_rolls_to_new_local_date_before_daily_gate() -> None:
    scheduler, machine = make_scheduler(
        WEEKDAY_PROMPT_TIME,
        done_dates={WEEKDAY_PROMPT_TIME.date()},
    )
    next_day_before_prompt = datetime(2026, 9, 29, 16, 49, 59)
    next_day_at_prompt = datetime(2026, 9, 29, 16, 50)

    before_prompt = scheduler.tick(next_day_before_prompt)
    at_prompt = scheduler.tick(next_day_at_prompt)

    assert before_prompt.state is State.IDLE
    assert not before_prompt.show_prompt
    assert at_prompt.state is State.PROMPTING
    assert machine.state is State.PROMPTING


def test_done_state_rolls_through_weekend_and_prompts_next_eligible_weekday() -> None:
    friday = datetime(2026, 10, 2, 17, 0)
    saturday = datetime(2026, 10, 3, 17, 0)
    sunday = datetime(2026, 10, 4, 17, 0)
    monday_before_prompt = datetime(2026, 10, 5, 16, 49, 59)
    monday_at_prompt = datetime(2026, 10, 5, 16, 50)
    scheduler, machine = make_scheduler(friday, done_dates={friday.date()})

    assert scheduler.tick(saturday).state is State.IDLE
    assert scheduler.tick(sunday).state is State.IDLE
    assert scheduler.tick(monday_before_prompt).state is State.IDLE
    result = scheduler.tick(monday_at_prompt)
    assert result.state is State.PROMPTING
    assert result.show_prompt
    assert machine.state is State.PROMPTING


@pytest.mark.parametrize(
    ("choice", "interval"),
    (
        (Choice.THIRTY_MINUTES, timedelta(minutes=30)),
        (Choice.HOUR, timedelta(hours=1)),
    ),
)
def test_wait_deadline_is_refreshed_from_click_time(
    choice: Choice,
    interval: timedelta,
) -> None:
    click_time = datetime(2026, 9, 28, 17, 7)
    machine = StateMachine.start(
        FakeStore(),
        FakeMessenger([SendResult(success=True)]),
        WEEKDAY_PROMPT_TIME,
    )
    scheduler = Scheduler(machine)
    machine.trigger_prompt(WEEKDAY_PROMPT_TIME)
    machine.choose(choice, click_time)
    deadline = click_time + interval

    before_deadline = scheduler.tick(deadline - timedelta(microseconds=1))
    at_deadline = scheduler.tick(deadline)

    assert before_deadline.state is State.WAITING
    assert before_deadline.next_prompt_deadline == deadline
    assert at_deadline.state is State.PROMPTING
    assert at_deadline.show_prompt
    assert at_deadline.next_prompt_deadline is None


class CountingStateMachine(StateMachine):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.trigger_count = 0

    def trigger_prompt(self, now: datetime):
        self.trigger_count += 1
        return super().trigger_prompt(now)


def test_repeated_ticks_do_not_trigger_daily_prompt_twice() -> None:
    machine = CountingStateMachine.start(
        FakeStore(),
        FakeMessenger(),
        WEEKDAY_BEFORE_PROMPT,
    )
    scheduler = Scheduler(machine)

    first = scheduler.tick(WEEKDAY_PROMPT_TIME)
    second = scheduler.tick(WEEKDAY_PROMPT_TIME)
    third = scheduler.tick(WEEKDAY_PROMPT_TIME + timedelta(minutes=1))

    assert first.state is State.PROMPTING
    assert second == first
    assert third == first
    assert machine.trigger_count == 1


class StopAfterWait:
    def __init__(self) -> None:
        self.stopped = False
        self.waited: list[float | None] = []
        self.calls: list[str | tuple[str, float | None]] = []

    def is_set(self) -> bool:
        self.calls.append("is_set")
        return self.stopped

    def wait(self, timeout: float | None = None) -> bool:
        self.calls.append(("wait", timeout))
        self.waited.append(timeout)
        self.stopped = True
        return True


def test_run_ticks_then_stops_cleanly_through_stop_event_wait() -> None:
    provided_times = [WEEKDAY_PROMPT_TIME]
    scheduler, machine = make_scheduler()
    stop_event = StopAfterWait()

    scheduler = Scheduler(
        machine,
        now_provider=provided_times.pop,
        poll_interval=0.25,
    )
    scheduler.run(stop_event)

    assert machine.state is State.PROMPTING
    assert stop_event.waited == [0.25]
    assert stop_event.calls == ["is_set", ("wait", 0.25), "is_set"]