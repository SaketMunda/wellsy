"""Vision-turn wiring (step 4b prerequisite).

`describe_scene` / `query_object` route through `engine.voice.vision`: capture
the room or the screen once through the step-3 capture layer, hand the *verified*
pixels to the VLM, and fold `CaptureResult.provenance()` into the per-answer
line. The load-bearing invariant under test: **an unverified capture never
reaches the model** (INVARIANTS #6 / #15) — the gate refuses, speaks the remedy,
writes a `source: "refused"` audit line, and forwards nothing.
"""

from __future__ import annotations

import asyncio
import json

import numpy as np
import pytest

from engine.capture.base import CaptureError, CaptureResult, DisplayFrame
from engine.voice import vision
from engine.voice.intent_gate import build_intent_gate, build_provenance_logger
from engine.voice.wake import WakeState


# --------------------------------------------------------------------------- #
# route()                                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "transcript,expected",
    [
        ("what do you see", "camera"),
        ("do you see a chair", "camera"),
        ("what's in front of you", "camera"),
        ("what's on my screen", "screen"),
        ("what is on my screen", "screen"),
        ("read my screen", "screen"),
        ("are there any errors on my monitor", "screen"),
        ("what's on my display", "screen"),
        ("is there a bug on the screen", "screen"),
    ],
)
def test_route(transcript, expected):
    assert vision.route(transcript) == expected


# --------------------------------------------------------------------------- #
# capture_for_intent — verified only                                           #
# --------------------------------------------------------------------------- #


def _fake_result(source: str) -> CaptureResult:
    img = (np.random.rand(48, 64, 3) * 255).astype(np.uint8)
    df = DisplayFrame(index=0, image=img, width=64, height=48, is_primary=True)
    return CaptureResult(
        frames=[df],
        backend="fake",
        verified=True,
        verified_by="unit-test",
        source=source,
    )


def test_capture_for_intent_camera(monkeypatch):
    monkeypatch.setattr(vision, "capture_camera", lambda: _fake_result("camera"))
    monkeypatch.setattr(vision, "capture_screen", lambda: pytest.fail("should not capture screen"))
    cap = vision.capture_for_intent("what do you see")
    assert cap.frame_source == "camera"
    assert cap.size == (64, 48)
    assert cap.jpegs and cap.jpegs[0][:3] == b"\xff\xd8\xff"  # JPEG SOI
    assert cap.provenance()["captureVerified"] is True
    assert cap.provenance()["captureSource"] == "camera"


def test_capture_for_intent_screen(monkeypatch):
    monkeypatch.setattr(vision, "capture_screen", lambda: _fake_result("screen"))
    monkeypatch.setattr(vision, "capture_camera", lambda: pytest.fail("should not open camera"))
    cap = vision.capture_for_intent("what's on my screen")
    assert cap.frame_source == "screen"
    assert cap.provenance()["captureSource"] == "screen"


def test_capture_for_intent_propagates_refusal(monkeypatch):
    def _refuse():
        raise CaptureError(
            "screen recording permission isn't granted for this process",
            permission="screen",
            spoken="I can't see your screen — screen recording permission isn't granted for this process.",
        )

    monkeypatch.setattr(vision, "capture_screen", _refuse)
    with pytest.raises(CaptureError):
        vision.capture_for_intent("what's on my screen")


# --------------------------------------------------------------------------- #
# provenance folding                                                           #
# --------------------------------------------------------------------------- #


def test_log_answer_folds_capture(tmp_path, monkeypatch):
    from engine.honesty import provenance

    p = tmp_path / "provenance.jsonl"
    monkeypatch.setattr(provenance, "PROVENANCE_PATH", p)
    monkeypatch.setattr(provenance, "RUNS_DIR", tmp_path)

    cap = _fake_result("screen")
    provenance.log_answer(
        transcript="what's on my screen",
        answer="A code editor with a Python traceback.",
        source="vlm",
        frame_source="screen",
        tracks=[],
        frame_age_ms=42.0,
        llm_ms=1234.5,
        capture=cap.provenance(),
    )
    rec = json.loads(p.read_text().strip())
    assert rec["source"] == "vlm"
    assert rec["frameSource"] == "screen"
    assert rec["captureVerified"] is True
    assert rec["captureVerifiedBy"] == "unit-test"
    assert rec["captureSource"] == "screen"
    assert rec["displayCount"] == 1


# --------------------------------------------------------------------------- #
# IntentGate — the invariant: unverified capture never reaches the model       #
# --------------------------------------------------------------------------- #


class _FakeContext:
    """Just enough LLMContext surface for the gate + logger."""

    def __init__(self):
        self._messages = [{"role": "system", "content": "sys"}]

    def add_message(self, m):
        self._messages.append(m)

    def get_messages(self):
        return list(self._messages)

    def transform_messages(self, fn):
        self._messages[:] = fn(self._messages)


def test_gate_refuses_unverified_capture_and_forwards_nothing(monkeypatch):
    asyncio.run(_gate_refuses_unverified_capture_and_forwards_nothing(monkeypatch))


async def _gate_refuses_unverified_capture_and_forwards_nothing(monkeypatch):
    from pipecat.frames.frames import (
        LLMRunFrame,
        TranscriptionFrame,
        TTSSpeakFrame,
    )
    from pipecat.tests.utils import run_test

    logged = {}

    def _refuse(_transcript):
        raise CaptureError(
            "screen recording permission isn't granted for this process",
            spoken="I can't see your screen — screen recording permission isn't granted for this process.",
        )

    monkeypatch.setattr(vision, "capture_for_intent", _refuse)
    monkeypatch.setattr(
        "engine.voice.intent_gate.provenance.log_answer",
        lambda **kw: logged.update(kw),
    )

    ctx = _FakeContext()
    pending = vision.VisionPending()
    gate = build_intent_gate(WakeState(awake=True), context=ctx, pending=pending)

    frames_in = [TranscriptionFrame("what's on my screen", "", "t0", finalized=True)]
    down, _up = await run_test(gate, frames_to_send=frames_in)

    # the spoken remedy, and NOT a wallpaper description
    spoken = [f for f in down if isinstance(f, TTSSpeakFrame)]
    assert spoken and "screen recording permission" in spoken[0].text
    # nothing model-bound was emitted
    assert not any(isinstance(f, (TranscriptionFrame, LLMRunFrame)) for f in down)
    # the refusal was audited
    assert logged.get("source") == "refused"
    assert logged["capture"]["captureVerified"] is False
    # context was never touched
    assert len(ctx.get_messages()) == 1


def test_gate_runs_vlm_on_verified_capture(monkeypatch):
    asyncio.run(_gate_runs_vlm_on_verified_capture(monkeypatch))


async def _gate_runs_vlm_on_verified_capture(monkeypatch):
    from pipecat.frames.frames import LLMRunFrame, TranscriptionFrame
    from pipecat.tests.utils import run_test

    monkeypatch.setattr(
        vision, "capture_for_intent", lambda _t: vision.VisionCapture(
            result=_fake_result("camera"),
            frame_source="camera",
            jpegs=[b"\xff\xd8\xffFAKEJPEG"],
            size=(64, 48),
            captured_at=1.0,
        )
    )

    ctx = _FakeContext()
    pending = vision.VisionPending()
    gate = build_intent_gate(WakeState(awake=True), context=ctx, pending=pending)

    frames_in = [TranscriptionFrame("what do you see", "", "t0", finalized=True)]
    down, _up = await run_test(gate, frames_to_send=frames_in)
    assert any(isinstance(f, LLMRunFrame) for f in down)
    assert not any(isinstance(f, TranscriptionFrame) for f in down)
    # an image message got appended, and the turn is armed for the logger
    assert len(ctx.get_messages()) == 2
    img_msg = ctx.get_messages()[-1]
    content = img_msg["content"]
    assert any(part.get("type") == "image_url" for part in content)
    assert pending.armed
    assert pending.frame_source == "camera"


def test_provenance_logger_writes_on_response_end_and_drops_image(monkeypatch):
    asyncio.run(_provenance_logger_writes_on_response_end_and_drops_image(monkeypatch))


async def _provenance_logger_writes_on_response_end_and_drops_image(monkeypatch):
    from pipecat.frames.frames import (
        LLMFullResponseEndFrame,
        LLMFullResponseStartFrame,
        LLMTextFrame,
    )
    from pipecat.tests.utils import run_test

    logged = {}
    monkeypatch.setattr(
        "engine.voice.intent_gate.provenance.log_answer",
        lambda **kw: logged.update(kw),
    )

    ctx = _FakeContext()
    img_msg = {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,x"}}]}
    ctx.add_message(img_msg)

    pending = vision.VisionPending()
    pending.arm(
        vision.VisionCapture(
            result=_fake_result("screen"),
            frame_source="screen",
            jpegs=[b"x"],
            size=(1, 1),
            captured_at=1.0,
        ),
        "what's on my screen",
        img_msg,
    )

    logger = build_provenance_logger(pending, context=ctx)
    frames_in = [
        LLMFullResponseStartFrame(),
        LLMTextFrame("A code editor "),
        LLMTextFrame("with a traceback."),
        LLMFullResponseEndFrame(),
    ]
    down, _up = await run_test(logger, frames_to_send=frames_in)
    # everything passes through untouched
    assert sum(isinstance(f, LLMTextFrame) for f in down) == 2

    assert logged["answer"] == "A code editor with a traceback."
    assert logged["source"] == "vlm"
    assert logged["frame_source"] == "screen"
    assert logged["capture"]["captureVerified"] is True
    assert not pending.armed              # disarmed
    assert img_msg not in ctx.get_messages()  # image dropped from context
