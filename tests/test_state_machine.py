from datetime import date, datetime, timedelta

from clockout.messaging import SendResult
from clockout.state_machine import (
    Choice,
    State,
    StateMachine,
    TransitionResult,
)


START = datetime(2026, 9, 28, 16, 50)


class FakeStore:
    def __init__(self, done_dates: set[date] | None = None, events=None) -> None:
        self.done_dates = set() if done_dates is None else set(done_dates)
        self.events = [] if events is None else events

    def is_done_today(self, today: date) -> bool:
        return today in self.done_dates

    def mark_done_today(self, today: date) -> None:
        self.events.append(("mark", today))
        self.done_dates.add(today)


class FakeMessenger:
    def __init__(self, results: list[SendResult | bool], events=None) -> None:
        self.results = list(results)
        self.messages: list[str] = []
        self.events = [] if events is None else events

    def send(self, message_text: str) -> SendResult | bool:
        self.messages.append(message_text)
        self.events.append(("send", message_text))
        return self.results.pop(0)


def test_start_uses_local_date_and_trigger_enters_prompting() -> None:
    store = FakeStore(done_dates={START.date()})
    messenger = FakeMessenger([])

    done_machine = StateMachine.start(store, messenger, START)
    assert done_machine.result == TransitionResult(State.DONE, False)
    assert done_machine.trigger_prompt(START).state is State.DONE

    idle_machine = StateMachine.start(FakeStore(), messenger, START)
    result = idle_machine.trigger_prompt(START)
    assert result == TransitionResult(State.PROMPTING, True)


def test_each_choice_sends_exact_message_and_yes_marks_after_send() -> None:
    events = []
    store = FakeStore(events=events)
    messenger = FakeMessenger(
        [SendResult(success=True)],
        events=events,
    )
    machine = StateMachine.start(store, messenger, START)
    machine.trigger_prompt(START)

    result = machine.choose(Choice.YES, START + timedelta(minutes=5))

    assert messenger.messages == ["I'll be home on time tonight."]
    assert events == [
        ("send", "I'll be home on time tonight."),
        ("mark", date(2026, 9, 28)),
    ]
    assert result.state is State.DONE
    assert not result.show_prompt


def test_thirty_minutes_and_hour_anchor_deadlines_to_click_time() -> None:
    click_time = START + timedelta(minutes=17)
    for choice, expected_message, interval in (
        (
            Choice.THIRTY_MINUTES,
            "I'm going to be about 30 minutes late.",
            timedelta(minutes=30),
        ),
        (
            Choice.HOUR,
            "I'm going to be about an hour late.",
            timedelta(minutes=60),
        ),
    ):
        messenger = FakeMessenger([SendResult(success=True)])
        machine = StateMachine.start(FakeStore(), messenger, START)
        machine.trigger_prompt(START)

        result = machine.choose(choice, click_time)

        assert messenger.messages == [expected_message]
        assert result.state is State.WAITING
        assert result.next_prompt_deadline == click_time + interval
        assert not result.show_prompt


def test_send_failure_stays_prompting_without_mark_or_automatic_retry() -> None:
    store = FakeStore()
    messenger = FakeMessenger([SendResult(success=False), SendResult(success=True)])
    machine = StateMachine.start(store, messenger, START)
    machine.trigger_prompt(START)

    failed = machine.choose(Choice.YES, START)
    assert failed == TransitionResult(
        State.PROMPTING,
        True,
        "Message not sent — retry?",
    )
    assert store.done_dates == set()

    refreshed = machine.refresh(START + timedelta(hours=1))
    assert refreshed == failed
    assert messenger.messages == ["I'll be home on time tonight."]

    retried = machine.choose(Choice.YES, START + timedelta(hours=1))
    assert retried.state is State.DONE
    assert messenger.messages == [
        "I'll be home on time tonight.",
        "I'll be home on time tonight.",
    ]


def test_refresh_waits_until_deadline_inclusive() -> None:
    click_time = START + timedelta(minutes=7)
    deadline = click_time + timedelta(minutes=30)
    machine = StateMachine.start(
        FakeStore(),
        FakeMessenger([SendResult(success=True)]),
        START,
    )
    machine.trigger_prompt(START)
    machine.choose(Choice.THIRTY_MINUTES, click_time)

    before = machine.refresh(deadline - timedelta(microseconds=1))
    assert before.state is State.WAITING
    assert before.next_prompt_deadline == deadline

    at_deadline = machine.refresh(deadline)
    assert at_deadline == TransitionResult(State.PROMPTING, True)

    after = machine.refresh(deadline + timedelta(seconds=1))
    assert after == at_deadline


def test_refresh_rolls_done_state_into_idle_on_local_date_change() -> None:
    day_two = START + timedelta(days=1)
    store = FakeStore(done_dates={START.date()})
    machine = StateMachine.start(
        store,
        FakeMessenger([]),
        START,
    )

    result = machine.refresh(day_two)

    assert result == TransitionResult(State.IDLE, False)
    assert machine.trigger_prompt(day_two).state is State.PROMPTING