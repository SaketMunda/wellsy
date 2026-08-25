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
    PRESENCE_DEBOUNCE_FRAMES,
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


def _settle_present(greeter: PersonGreeter, label: str = "person") -> None:
    """A single noisy frame ('person' seen once) doesn't count as a real
    appearance -- PRESENCE_DEBOUNCE_FRAMES requires back-to-back updates
    first. Tests that want a person to actually register as present call
    this instead of a single `update()`."""
    for _ in range(PRESENCE_DEBOUNCE_FRAMES):
        greeter.update(_tracks(label))


def test_greets_on_first_person_appearance(fake_loop):
    greeter = PersonGreeter(fake_loop)
    _settle_present(greeter)
    assert fake_loop.speak_ambient.call_count == 1
    assert fake_loop._extend_conversation.call_count == 1


def test_single_noisy_frame_does_not_greet(fake_loop):
    """The real bug reported live: a greeting fired with nobody in frame --
    a one-off false-positive detection. One update alone must never greet."""
    greeter = PersonGreeter(fake_loop)
    greeter.update(_tracks("person"))
    assert fake_loop.speak_ambient.call_count == 0


def test_low_confidence_person_does_not_greet(fake_loop):
    greeter = PersonGreeter(fake_loop)
    low_conf = [{"id": 0, "label": "person", "score": 0.2}]
    greeter.update(low_conf)
    greeter.update(low_conf)
    assert fake_loop.speak_ambient.call_count == 0


def test_confident_wide_chair_does_not_greet(fake_loop):
    """Real regression test for the bug reported live with a screenshot:
    an empty-room gaming chair tracked and locked as `person` at 83%
    detection confidence, 100% label confidence, sustained across frames
    -- not a low-confidence flicker. The score alone (83% > the old 60%
    floor) would not have stopped this; MIN_PERSON_SCORE=0.9 plus the
    wider-than-tall bbox sanity check together should."""
    greeter = PersonGreeter(fake_loop)
    chair = [{"id": 1, "label": "person", "score": 0.83, "bbox": [500, 180, 420, 380]}]
    for _ in range(10):
        greeter.update(chair)
    assert fake_loop.speak_ambient.call_count == 0


def test_real_person_bbox_taller_than_wide_still_greets(fake_loop):
    """Guard against the aspect-ratio check swallowing real people too."""
    greeter = PersonGreeter(fake_loop)
    person = [{"id": 1, "label": "person", "score": 0.94, "bbox": [200, 100, 300, 600]}]
    for _ in range(PRESENCE_DEBOUNCE_FRAMES):
        greeter.update(person)
    assert fake_loop.speak_ambient.call_count == 1


def test_wide_high_confidence_person_still_greets(fake_loop):
    """Real regression test for the bug reported live right after bug #2's
    fix shipped: a real person sitting close to a desk got no greeting at
    all. The aspect-ratio check (wider-than-tall boxes rejected) was a
    guess made from one chair screenshot with no data on how the owner
    actually appears in their own camera framing -- plausibly wider than
    tall at that distance. The shape check is now diagnostic-only and must
    never block a high-confidence, sustained person detection regardless
    of box proportions."""
    greeter = PersonGreeter(fake_loop)
    wide_person = [{"id": 1, "label": "person", "score": 0.95, "bbox": [100, 200, 600, 300]}]
    for _ in range(PRESENCE_DEBOUNCE_FRAMES):
        greeter.update(wide_person)
    assert fake_loop.speak_ambient.call_count == 1


def test_does_not_greet_when_no_person_present(fake_loop):
    greeter = PersonGreeter(fake_loop)
    greeter.update(_tracks("chair", "bed"))
    assert fake_loop.speak_ambient.call_count == 0


def test_does_not_regreet_while_person_stays_present(fake_loop):
    greeter = PersonGreeter(fake_loop)
    _settle_present(greeter)
    greeter.update(_tracks("person", "chair"))
    greeter.update(_tracks("person"))
    assert fake_loop.speak_ambient.call_count == 1


def test_does_not_regreet_within_cooldown_after_a_gap(fake_loop, monkeypatch):
    t = [1000.0]
    monkeypatch.setattr("greeting.time.monotonic", lambda: t[0])

    greeter = PersonGreeter(fake_loop)
    _settle_present(greeter)
    assert fake_loop.speak_ambient.call_count == 1

    # person leaves, then comes back well inside the cooldown window
    greeter.update(_tracks())
    t[0] += REGREET_COOLDOWN_SECONDS / 2
    _settle_present(greeter)
    assert fake_loop.speak_ambient.call_count == 1


def test_regreets_after_a_genuine_gap_past_the_cooldown(fake_loop, monkeypatch):
    t = [1000.0]
    monkeypatch.setattr("greeting.time.monotonic", lambda: t[0])

    greeter = PersonGreeter(fake_loop)
    _settle_present(greeter)
    assert fake_loop.speak_ambient.call_count == 1

    greeter.update(_tracks())
    t[0] += REGREET_COOLDOWN_SECONDS + 1
    _settle_present(greeter)
    assert fake_loop.speak_ambient.call_count == 2


def test_does_not_greet_while_a_real_query_is_in_flight(fake_loop):
    fake_loop.preemption.active = True
    greeter = PersonGreeter(fake_loop)
    _settle_present(greeter)
    assert fake_loop.speak_ambient.call_count == 0


def test_does_not_greet_while_already_speaking(fake_loop):
    fake_loop._speaking.return_value = True
    greeter = PersonGreeter(fake_loop)
    _settle_present(greeter)
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
