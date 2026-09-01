"""IntentGate — the deterministic safety seam (INVARIANTS #3).

`parse_intent` runs on every committed transcript **before the LLM context
aggregator**. `stop`, `wake` and `sleep` are resolved by regex here and never
reach a model. If Pipecat's structure ever fights this, the seam is wrong — the
invariant does not move.

Placement in the pipeline: immediately after WakeGate, before `user_aggregator`.
So by the time a transcript could become an `LLMRunFrame`, this processor has
already had the chance to swallow it.

`decide()` is a pure function (no Pipecat import) — it is what the tests assert
on, alongside the existing `spec/intent-cases.json` suite for `parse_intent`.

**Vision turns (step 4b).** `describe_scene` / `query_object` no longer forward
blindly to the text LLM. They route through `engine.voice.vision`: capture the
room (camera) or the screen once, through the step-3 capture layer, and hand the
verified pixels to the VLM by appending an image message to the shared
`LLMContext` and emitting an `LLMRunFrame`. An **unverified capture never
reaches the model** — `capture_for_intent` raises `CaptureError`, the gate
speaks the remedy and writes a `source: "refused"` audit line, and nothing is
forwarded (INVARIANTS #6 / #12 / #15).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from engine.capture import CaptureError
from engine.honesty import provenance
from engine.honesty.intent import HELP_TEXT, parse_intent
from engine.voice import vision

# canned, not understood — same spirit as parse_intent's fixed grammar
_CANNED = {
    "help": HELP_TEXT,
    "presence": "I'm here.",
    "thanks": "Anytime.",
}

_VISION_INTENTS = ("describe_scene", "query_object")


@dataclass(frozen=True)
class Decision:
    action: str            # "stop" | "sleep" | "wake" | "canned" | "vision" | "forward"
    intent_type: str       # the parse_intent type, for the audit/metrics line
    say: str | None = None  # text for action == "canned"


def decide(transcript: str) -> Decision:
    intent = parse_intent(transcript)
    t = intent.type
    if t == "stop":
        return Decision("stop", t)
    if t == "sleep":
        return Decision("sleep", t)
    if t == "wake":
        return Decision("wake", t)
    if t in _CANNED:
        return Decision("canned", t, say=_CANNED[t])
    if t in _VISION_INTENTS:
        return Decision("vision", t)
    # unknown -> the text model answers
    return Decision("forward", t)


def build_intent_gate(wake_state, *, context=None, pending=None, on_decision=None):
    """Return an IntentGate FrameProcessor.

    `wake_state`  — the shared WakeState.
    `context`     — the pipeline's `LLMContext`; needed for the vision path
                    (image messages are appended here). If `None`, vision
                    intents fall back to a plain text forward.
    `pending`     — a `vision.VisionPending` shared with the provenance logger.
    `on_decision(Decision, transcript)` — optional metrics/audit hook.

    Factory so this module imports without Pipecat."""

    from pipecat.frames.frames import (
        Frame,
        InterruptionFrame,
        LLMRunFrame,
        TranscriptionFrame,
        TTSSpeakFrame,
    )
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class IntentGate(FrameProcessor):
        def __init__(self) -> None:
            super().__init__()
            self._wake = wake_state

        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)

            if not (
                isinstance(frame, TranscriptionFrame)
                and direction == FrameDirection.DOWNSTREAM
            ):
                await self.push_frame(frame, direction)
                return

            d = decide(frame.text)
            if on_decision is not None:
                try:
                    on_decision(d, frame.text)
                except Exception:
                    pass

            if d.action == "stop":
                # Cancel any in-progress bot output. Deterministic path — no
                # model, no await on generation.
                await self.push_frame(InterruptionFrame(), direction)
                return
            if d.action == "sleep":
                self._wake.sleep()
                await self.push_frame(
                    TTSSpeakFrame(text="Going to sleep.", append_to_context=False), direction
                )
                return
            if d.action == "wake":
                self._wake.wake()
                return
            if d.action == "canned":
                await self.push_frame(
                    TTSSpeakFrame(text=d.say or "", append_to_context=False), direction
                )
                return
            if d.action == "vision":
                await self._handle_vision(frame, direction, LLMContext, LLMRunFrame, TTSSpeakFrame)
                return
            # forward: let it flow to the aggregator / text LLM
            await self.push_frame(frame, direction)

        async def _handle_vision(self, frame, direction, LLMContext, LLMRunFrame, TTSSpeakFrame):
            if context is None or pending is None:
                # No VLM wiring (bare unit test / degraded mode) — text forward.
                await self.push_frame(frame, direction)
                return

            loop = asyncio.get_running_loop()
            try:
                cap = await loop.run_in_executor(
                    None, vision.capture_for_intent, frame.text
                )
            except CaptureError as e:
                # INVARIANTS #6 / #12 / #15 — refuse, speak the remedy, write the
                # audit line, forward nothing to the model.
                try:
                    provenance.log_answer(
                        transcript=frame.text,
                        answer=e.spoken,
                        source="refused",
                        frame_source=vision.route(frame.text),
                        tracks=[],
                        frame_age_ms=None,
                        llm_ms=None,
                        capture={"captureVerified": False, "captureRefusedReason": e.reason},
                    )
                except Exception:
                    pass
                await self.push_frame(
                    TTSSpeakFrame(text=e.spoken, append_to_context=False), direction
                )
                return

            # Verified capture — attach to the shared context and run the VLM.
            msg = await LLMContext.create_image_message(
                format="image/jpeg", size=cap.size, image=cap.jpegs[0], text=frame.text
            )
            context.add_message(msg)
            for extra in cap.jpegs[1:]:
                context.add_message(
                    await LLMContext.create_image_message(
                        format="image/jpeg", size=cap.size, image=extra,
                        text="(additional display)",
                    )
                )
            pending.arm(cap, frame.text, msg)
            await self.push_frame(LLMRunFrame(), direction)

    return IntentGate()


def build_provenance_logger(pending, *, context=None):
    """A FrameProcessor placed after the LLM and before TTS. When `pending` is
    armed (a vision turn is in flight), it accumulates the assistant's streamed
    text and, on `LLMFullResponseEndFrame`, writes exactly one
    `provenance.log_answer` line with the step-3 capture provenance folded in,
    then drops the image message from context (screen/camera content is
    retained only as that line — step 3 "on-demand only")."""

    import time

    from pipecat.frames.frames import (
        Frame,
        LLMFullResponseEndFrame,
        LLMFullResponseStartFrame,
        LLMTextFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class ProvenanceLogger(FrameProcessor):
        def __init__(self) -> None:
            super().__init__()
            self._buf: list[str] = []
            self._collecting = False

        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)

            if isinstance(frame, LLMFullResponseStartFrame):
                self._buf = []
                self._collecting = True
            elif isinstance(frame, LLMTextFrame) and self._collecting:
                self._buf.append(frame.text or "")
            elif isinstance(frame, LLMFullResponseEndFrame):
                self._collecting = False
                if pending.armed:
                    self._log(time, "".join(self._buf).strip())

            await self.push_frame(frame, direction)

        def _log(self, time_mod, answer: str) -> None:
            try:
                provenance.log_answer(
                    transcript=pending.transcript,
                    answer=answer,
                    source="vlm",
                    frame_source=pending.frame_source,
                    tracks=[],
                    frame_age_ms=(
                        round((time_mod.time() - pending.captured_at) * 1000, 1)
                        if pending.captured_at
                        else None
                    ),
                    llm_ms=(
                        round((time_mod.time() - pending.armed_at) * 1000, 1)
                        if pending.armed_at
                        else None
                    ),
                    capture=pending.capture_provenance,
                )
            except Exception:
                pass
            if context is not None and pending.image_message is not None:
                try:
                    target = pending.image_message
                    context.transform_messages(
                        lambda msgs: [m for m in msgs if m is not target]
                    )
                except Exception:
                    pass
            pending.disarm()

    return ProvenanceLogger()
