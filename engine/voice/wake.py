"""Wake gate — transcribe-then-match, fuzzy, tolerant of STT error.

This is NOT a trained keyword spotter (decisions.md D39 has the reasoning and
openWakeWord as the upgrade path). The segmented STT already transcribes every
VAD-gated utterance; while asleep, WakeGate scores that transcript against
`wake_phrases.txt` with `difflib` and only lets a match through. While awake it
is a pass-through.

`wake_score` / `is_wake` are pure functions with no Pipecat import so
`wellsy tune-wake` and the tests can sweep the threshold against recorded audio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")


def _norm(text: str) -> str:
    return _WS.sub(" ", _PUNCT.sub("", text.lower())).strip()


def wake_score(transcript: str, phrases: list[str]) -> float:
    """Best match of any wake phrase against the transcript, 0..1.

    Two signals, max-combined:
      * whole-string `difflib` ratio (handles "wellsy" heard as "welsey"/"wellsey");
      * best ratio of the phrase against any same-length word window in the
        transcript (handles "um, wellsy, you there" — the phrase is buried).
    """
    t = _norm(transcript)
    if not t:
        return 0.0
    words = t.split()
    best = 0.0
    for phrase in phrases:
        p = _norm(phrase)
        if not p:
            continue
        best = max(best, SequenceMatcher(None, p, t).ratio())
        n = len(p.split())
        for i in range(0, max(1, len(words) - n + 1)):
            window = " ".join(words[i : i + n])
            best = max(best, SequenceMatcher(None, p, window).ratio())
    return best


def is_wake(transcript: str, phrases: list[str], threshold: float) -> bool:
    return wake_score(transcript, phrases) >= threshold


@dataclass
class WakeState:
    """Shared asleep/awake flag. WakeGate reads it; IntentGate flips it on the
    deterministic `wake` / `sleep` intents (INVARIANTS #3)."""

    awake: bool = False

    def wake(self) -> None:
        self.awake = True

    def sleep(self) -> None:
        self.awake = False


# --------------------------------------------------------------------------- #
# Pipecat processor — imported lazily by pipeline.py                           #
# --------------------------------------------------------------------------- #


def build_wake_gate(state: WakeState, cfg_provider):
    """Return a WakeGate FrameProcessor. `cfg_provider()` yields a fresh
    VoiceConfig (hot-reload). Factory so this module imports without Pipecat."""

    from pipecat.frames.frames import Frame, TranscriptionFrame, TTSSpeakFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class WakeGate(FrameProcessor):
        def __init__(self) -> None:
            super().__init__()
            self._state = state

        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)

            if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
                if self._state.awake:
                    await self.push_frame(frame, direction)
                    return
                cfg = cfg_provider()
                if is_wake(frame.text, cfg.wake_phrases, cfg.wake_threshold):
                    self._state.wake()
                    await self.push_frame(
                        TTSSpeakFrame(text="Yes?", append_to_context=False), direction
                    )
                # asleep and not a wake phrase: drop it — nothing reaches the LLM
                return

            await self.push_frame(frame, direction)

    return WakeGate()
