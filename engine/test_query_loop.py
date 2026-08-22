"""Day 11 (day11-prompt.md Part 1.4): the try/except/finally around the VLM
call in `QueryLoop.handle_command`'s "unknown" branch is load-bearing --
D40's fourth amendment found that an unhandled exception there killed the
wake thread permanently and left `PreemptionSeam` stuck `active` forever,
freezing ambient T1. This is the same regression test that amendment used,
re-run against the Day 11 shape of the call (image-carrying, screen-capture
routing added) to prove the guarantee still holds with the new code path in
place, not just the old text-only one.
"""

from __future__ import annotations

import numpy as np
import pytest

from query_loop import QueryLoop
from tiers import PreemptionSeam


class _AlwaysRaisesLlm:
    """Stands in for llm.py's `Llm` -- `respond()` always raises, simulating
    Ollama being unreachable, timing out, or erroring mid-call."""

    def respond(self, transcript, frame_bgr=None, scene=None):
        raise RuntimeError("simulated Ollama failure")


class _NoopStt:
    def transcribe(self, audio):
        return ""


@pytest.fixture
def loop() -> QueryLoop:
    preemption = PreemptionSeam()
    return QueryLoop(preemption, _NoopStt(), llm=_AlwaysRaisesLlm())


def test_preemption_released_after_llm_exception(loop: QueryLoop, monkeypatch) -> None:
    # Stand in for the main capture loop's forced-look delivery -- normally
    # main.py's own thread calls this in response to poll_force_request();
    # here we fire it synchronously off a side thread the instant a request
    # comes in, so request_fresh_look() doesn't block for its full timeout.
    import threading

    def fake_main_loop() -> None:
        while not loop.preemption.poll_force_request():
            pass
        loop.preemption.deliver_fresh_look([], 5.0, np.zeros((4, 4, 3), dtype=np.uint8))

    t = threading.Thread(target=fake_main_loop, daemon=True)
    t.start()

    assert loop.preemption.active is False
    record = loop.handle_command("what am I looking at", source="push-to-talk")
    t.join(timeout=2.0)

    assert record["intent"] == "unknown"
    assert "llmError" in record
    # The whole point of the regression: release() in `finally` must run
    # even though `self.llm.respond(...)` raised.
    assert loop.preemption.active is False


def test_preemption_released_when_screen_capture_fails(loop: QueryLoop, monkeypatch) -> None:
    """Same guarantee, different failure point: screen routing added Day 11
    means there's a second thing that can raise before the LLM call even
    starts (ScreenCaptureError). The seam must still be released."""
    import screen_capture

    def _boom():
        raise screen_capture.ScreenCaptureError("simulated: Screen Recording permission not granted")

    monkeypatch.setattr(screen_capture, "capture_screen", _boom)
    # No fake main loop answering request_fresh_look() here -- the point of
    # this test is the screen-capture failure path, not re-proving the
    # camera-frame handoff (test 1 already does). Short-circuit the
    # fallback's wait instead of blocking 2s for its real timeout.
    monkeypatch.setattr(loop.preemption, "request_fresh_look", lambda timeout=2.0: None)

    assert loop.preemption.active is False
    record = loop.handle_command("what's on my screen", source="push-to-talk")

    assert record["intent"] == "unknown"
    # screen_capture failing falls back to the camera frame (query_loop.py),
    # which then has no main-loop thread answering request_fresh_look() in
    # this test, so it times out -- exercising the "capture process died
    # mid-query" path request_fresh_look() itself documents, and confirming
    # release() still runs even then.
    assert loop.preemption.active is False
