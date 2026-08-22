"""PersonGreeter — added mid-Day-11 (day11-prompt.md's session log, the
"can we not use the wake up" ask). Tests the transition logic (absent ->
present triggers exactly one greeting, repeats within the cooldown don't
re-trigger, a genuine gap does) without needing a real camera, tracker, or
TTS — same "fake the collaborator, test the logic" style as
test_query_loop.py's fakes.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from greeting import (
    GREETINGS_AFTERNOON,
    GREETINGS_EVENING,
    GREETINGS_MORNING,
    GREETINGS_NIGHT,
    PersonGreeter,
    REGREET_COOLDOWN_SECONDS,
    _pick_greeting,
)
from datetime import datetime


def _tracks(*labels: str) -> list[dict]:
    return [{"id": i, "label": label} for i, label in enumerate(labels)]


@pytest.fixture
def fake_loop():
    loop = MagicMock()
    loop.preemption.active = False
    loop._speaking.return_value = False
    return loop


def test_greets_on_first_person_appearance(fake_loop):
    greeter = PersonGreeter(fake_loop)
    greeter.update(_tracks("person"))
    assert fake_loop.speak_ambient.call_count == 1
    assert fake_loop._extend_conversation.call_count == 1


def test_does_not_greet_when_no_person_present(fake_loop):
    greeter = PersonGreeter(fake_loop)
    greeter.update(_tracks("chair", "bed"))
    assert fake_loop.speak_ambient.call_count == 0


def test_does_not_regreet_while_person_stays_present(fake_loop):
    greeter = PersonGreeter(fake_loop)
    greeter.update(_tracks("person"))
    greeter.update(_tracks("person", "chair"))
    greeter.update(_tracks("person"))
    assert fake_loop.speak_ambient.call_count == 1


def test_does_not_regreet_within_cooldown_after_a_gap(fake_loop, monkeypatch):
    t = [1000.0]
    monkeypatch.setattr("greeting.time.monotonic", lambda: t[0])

    greeter = PersonGreeter(fake_loop)
    greeter.update(_tracks("person"))
    assert fake_loop.speak_ambient.call_count == 1

    # person leaves, then comes back well inside the cooldown window
    greeter.update(_tracks())
    t[0] += REGREET_COOLDOWN_SECONDS / 2
    greeter.update(_tracks("person"))
    assert fake_loop.speak_ambient.call_count == 1


def test_regreets_after_a_genuine_gap_past_the_cooldown(fake_loop, monkeypatch):
    t = [1000.0]
    monkeypatch.setattr("greeting.time.monotonic", lambda: t[0])

    greeter = PersonGreeter(fake_loop)
    greeter.update(_tracks("person"))
    assert fake_loop.speak_ambient.call_count == 1

    greeter.update(_tracks())
    t[0] += REGREET_COOLDOWN_SECONDS + 1
    greeter.update(_tracks("person"))
    assert fake_loop.speak_ambient.call_count == 2


def test_does_not_greet_while_a_real_query_is_in_flight(fake_loop):
    fake_loop.preemption.active = True
    greeter = PersonGreeter(fake_loop)
    greeter.update(_tracks("person"))
    assert fake_loop.speak_ambient.call_count == 0


def test_does_not_greet_while_already_speaking(fake_loop):
    fake_loop._speaking.return_value = True
    greeter = PersonGreeter(fake_loop)
    greeter.update(_tracks("person"))
    assert fake_loop.speak_ambient.call_count == 0


@pytest.mark.parametrize(
    "hour,expected_bank",
    [
        (7, GREETINGS_MORNING),
        (14, GREETINGS_AFTERNOON),
        (19, GREETINGS_EVENING),
        (2, GREETINGS_NIGHT),
    ],
)
def test_pick_greeting_uses_real_time_of_day(hour, expected_bank):
    now = datetime(2026, 8, 22, hour, 0, 0)
    line = _pick_greeting(now)
    assert line in expected_bank
