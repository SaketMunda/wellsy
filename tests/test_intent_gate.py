"""IntentGate routing — INVARIANTS #3.

`parse_intent` itself is covered by `spec/intent-cases.json` via
`test_intent.py`. Here we assert the *gate's* contract: `stop` / `wake` /
`sleep` are resolved deterministically and never turn into an LLM request, and
only the model-bound intents forward. Pure `decide()` — no Pipecat, no model.
"""

from __future__ import annotations

import pytest

from engine.voice.intent_gate import decide


@pytest.mark.parametrize(
    "transcript,action,intent_type",
    [
        ("stop", "stop", "stop"),
        ("STOP now please", "stop", "stop"),
        ("hey wellsy", "wake", "wake"),
        ("wake up", "wake", "wake"),
        ("go to sleep", "sleep", "sleep"),
        ("be quiet", "sleep", "sleep"),
        ("what can you do", "canned", "help"),
        ("are you there", "canned", "presence"),
        ("thanks", "canned", "thanks"),
        ("what do you see", "forward", "describe_scene"),
        ("do you see a chair", "forward", "query_object"),
        ("what's the weather like tomorrow", "forward", "unknown"),
    ],
)
def test_decide_routing(transcript, action, intent_type):
    d = decide(transcript)
    assert d.action == action
    assert d.intent_type == intent_type


def test_stop_wake_sleep_never_forward():
    for t in ("stop", "hey wellsy", "wake up", "go to sleep", "shut up"):
        assert decide(t).action != "forward"


def test_canned_carries_text():
    assert decide("what can you do").say
    assert decide("thanks").say


def test_forward_has_no_canned_text():
    assert decide("tell me a joke").say is None
