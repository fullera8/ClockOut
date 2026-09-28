from datetime import date, datetime, timedelta

import pytest
from requests.exceptions import RequestException

from clockout.messaging import SendResult
from clockout.state_machine import Choice, State, StateMachine, TransitionResult


START = datetime(2026, 9, 28, 16, 50)
RETRY_MESSAGE = "Message not sent \u2014 retry?"
CHOICE_CASES = (
    (Choice.YES, "I'll be home on time tonight."),
    (Choice.THIRTY_MINUTES, "I'm going to be about 30 minutes late."),
    (Choice.HOUR, "I'm going to be about an hour late."),
)
DELAY_CASES = (
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
)


class RecordingStore:
    def __init__(self, done_dates=None, events=None) -> None:
        self.done_dates = set() if done_dates is None else set(done_dates)
        self.queries = []
        self.events = [] if events is None else events

    def is_done_today(self, today: date) -> bool:
        self.queries.append(today)
        return today in self.done_dates

    def mark_done_today(self, today: date) -> None:
        self.events.append(("mark", today))
        self.done_dates.add(today)


class ScriptedMessenger:
    def __init__(self, responses, events=None) -> None:
        self.responses = list(responses)
        self.messages = []
        self.events = [] if events is None else events

    def send(self, message_text: str) -> SendResult:
        self.messages.append(message_text)
        self.events.append(("send", message_text))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_prompting_machine(messenger, store=None):
    selected_store = RecordingStore() if store is None else store
    machine = StateMachine.start(selected_store, messenger, START)
    assert machine.result == TransitionResult(State.IDLE, False)
    assert machine.trigger_prompt(START) == TransitionResult(State.PROMPTING, True)
    return machine, selected_store


@pytest.mark.parametrize("done_today", [True, False])
def test_start_matches_store_for_local_date_and_trigger_behavior(done_today: bool) -> None:
    store = RecordingStore({START.date()} if done_today else set())
    machine = StateMachine.start(store, ScriptedMessenger([]), START)

    assert store.queries == [START.date()]
    expected_state = State.DONE if done_today else State.IDLE
    assert machine.result == TransitionResult(expected_state, False)

    triggered = machine.trigger_prompt(START)
    if done_today:
        assert triggered == TransitionResult(State.DONE, False)
    else:
        assert triggered == TransitionResult(State.PROMPTING, True)


@pytest.mark.parametrize(("choice", "expected_message"), CHOICE_CASES)
def test_every_choice_attempts_exactly_one_send(
    choice: Choice,
    expected_message: str,
) -> None:
    messenger = ScriptedMessenger([SendResult(success=True)])
    machine, _ = make_prompting_machine(messenger)

    machine.choose(choice, START + timedelta(minutes=5))

    assert messenger.messages == [expected_message]
    assert len(messenger.messages) == 1


def test_yes_sends_before_marking_clicked_at_local_date() -> None:
    events = []
    store = RecordingStore(events=events)
    messenger = ScriptedMessenger([SendResult(success=True)], events=events)
    machine, _ = make_prompting_machine(messenger, store)
    clicked_at = datetime(2026, 9, 29, 0, 5)

    result = machine.choose(Choice.YES, clicked_at)

    assert events == [
        ("send", "I'll be home on time tonight."),
        ("mark", clicked_at.date()),
    ]
    assert result == TransitionResult(State.DONE, False)


@pytest.mark.parametrize(("choice", "expected_message", "interval"), DELAY_CASES)
def test_delayed_choice_deadline_is_clicked_at_plus_exact_interval(
    choice: Choice,
    expected_message: str,
    interval: timedelta,
) -> None:
    messenger = ScriptedMessenger([SendResult(success=True)])
    machine, _ = make_prompting_machine(messenger)
    clicked_at = START + timedelta(minutes=17)

    result = machine.choose(choice, clicked_at)

    assert messenger.messages == [expected_message]
    assert result == TransitionResult(
        State.WAITING,
        False,
        None,
        clicked_at + interval,
    )


@pytest.mark.parametrize(("choice", "expected_message", "interval"), DELAY_CASES)
def test_refresh_stays_waiting_before_deadline_and_prompts_at_deadline(
    choice: Choice,
    expected_message: str,
    interval: timedelta,
) -> None:
    messenger = ScriptedMessenger([SendResult(success=True)])
    machine, _ = make_prompting_machine(messenger)
    clicked_at = START + timedelta(minutes=7)
    deadline = clicked_at + interval
    machine.choose(choice, clicked_at)

    before = machine.refresh(deadline - timedelta(microseconds=1))
    assert before == TransitionResult(State.WAITING, False, None, deadline)
    assert messenger.messages == [expected_message]

    at_deadline = machine.refresh(deadline)
    assert at_deadline == TransitionResult(State.PROMPTING, True)
    assert messenger.messages == [expected_message]


@pytest.mark.parametrize(
    ("choice", "expected_message", "interval"),
    (
        (Choice.YES, "I'll be home on time tonight.", None),
        *DELAY_CASES,
    ),
)
def test_non_2xx_failure_preserves_prompt_until_same_choice_is_reclicked(
    choice: Choice,
    expected_message: str,
    interval: timedelta | None,
) -> None:
    events = []
    store = RecordingStore(events=events)
    messenger = ScriptedMessenger(
        [
            SendResult(success=False, status_code=500, error="HTTP request failed"),
            SendResult(success=True),
        ],
        events=events,
    )
    machine, _ = make_prompting_machine(messenger, store)

    failed = machine.choose(choice, START)

    assert failed == TransitionResult(State.PROMPTING, True, RETRY_MESSAGE)
    assert failed.next_prompt_deadline is None
    assert store.done_dates == set()
    assert not any(event[0] == 'mark' for event in store.events)
    assert events == [("send", expected_message)]

    refreshed = machine.refresh(START + timedelta(days=1))
    assert refreshed == failed
    assert messenger.messages == [expected_message]
    assert len(messenger.messages) == 1

    retry_clicked_at = START + timedelta(hours=1)
    retried = machine.choose(choice, retry_clicked_at)
    assert messenger.messages == [expected_message, expected_message]
    assert len(messenger.messages) == 2
    if choice is Choice.YES:
        assert retried == TransitionResult(State.DONE, False)
        assert events == [
            ("send", expected_message),
            ("send", expected_message),
            ("mark", retry_clicked_at.date()),
        ]
    else:
        assert interval is not None
        assert retried == TransitionResult(
            State.WAITING,
            False,
            None,
            retry_clicked_at + interval,
        )
        assert events == [
            ("send", expected_message),
            ("send", expected_message),
        ]


@pytest.mark.parametrize(("choice", "expected_message"), CHOICE_CASES)
def test_network_exception_preserves_prompt_without_mark_or_retry(
    choice: Choice,
    expected_message: str,
) -> None:
    events = []
    store = RecordingStore(events=events)
    messenger = ScriptedMessenger(
        [RequestException("simulated network failure")],
        events=events,
    )
    machine, _ = make_prompting_machine(messenger, store)

    failed = machine.choose(choice, START)

    assert failed == TransitionResult(State.PROMPTING, True, RETRY_MESSAGE)
    assert failed.next_prompt_deadline is None
    assert store.done_dates == set()
    assert not any(event[0] == 'mark' for event in store.events)
    assert events == [("send", expected_message)]

    refreshed = machine.refresh(START + timedelta(hours=1))
    assert refreshed == failed
    assert messenger.messages == [expected_message]
    assert len(messenger.messages) == 1


def test_prior_done_rolls_to_idle_on_next_local_date() -> None:
    store = RecordingStore({START.date()})
    machine = StateMachine.start(store, ScriptedMessenger([]), START)

    next_day = START + timedelta(days=1)
    rolled = machine.refresh(next_day)

    assert rolled == TransitionResult(State.IDLE, False)
    assert machine.trigger_prompt(next_day) == TransitionResult(State.PROMPTING, True)
