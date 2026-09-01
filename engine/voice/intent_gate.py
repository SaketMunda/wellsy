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
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.honesty.intent import HELP_TEXT, parse_intent

# canned, not understood — same spirit as parse_intent's fixed grammar
_CANNED = {
    "help": HELP_TEXT,
    "presence": "I'm here.",
    "thanks": "Anytime.",
}


@dataclass(frozen=True)
class Decision:
    action: str            # "stop" | "sleep" | "wake" | "canned" | "forward"
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
    # describe_scene / query_object / unknown -> the model answers
    return Decision("forward", t)


def build_intent_gate(wake_state, on_decision=None):
    """Return an IntentGate FrameProcessor. `wake_state` is the shared WakeState;
    `on_decision(Decision, transcript)` is an optional hook for metrics/audit.
    Factory so this module imports without Pipecat."""

    from pipecat.frames.frames import (
        Frame,
        InterruptionFrame,
        TranscriptionFrame,
        TTSSpeakFrame,
    )
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
            # forward: let it flow to the aggregator / LLM
            await self.push_frame(frame, direction)

    return IntentGate()
