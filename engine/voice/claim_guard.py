"""ClaimGuard — the text model may not claim a sense or an action it never used
(INVARIANTS #6 / #15).

Step 6c live run: with no capture taken, WELLSY said "I see you clearly
through the camera"; with the orb untouched it said "I'm in the right corner"
three times. The prompt now forbids both, but a prompt is a request to a model.
This is the deterministic backstop: on a turn with no image attached, any
sentence that claims to see the user / room / screen, that the camera is on, or
that the orb moved is replaced before it reaches TTS or the context.

Vision turns (an image is attached — `pending.armed`) pass through untouched:
there the model did look.

`guard_sentence()` is pure; the processor only buffers streamed text into
sentences (TTS speaks whole sentences anyway, so this adds no latency).
"""

from __future__ import annotations

import re

SEE_REPLACEMENT = "I haven't looked. Ask me what I see and I'll check."
MOVE_REPLACEMENT = "I didn't move. Say move to the bottom right, and I will."
DENIAL_REPLACEMENT = "I can hear you through the microphone, and I can look through the camera when you ask."

_SEE_CLAIM = re.compile(
    r"\b("
    r"i (can |could )?(clearly )?see you(?! mean)|"
    r"i('m| am) (now )?(seeing|watching|looking at) (you|your|the room|the screen)|"
    r"watching your every move|"
    r"(the |your |my )?camera is (on|working|active|running)|"
    r"through (the|my|your) camera|"
    r"i (can )?see (the|your) (room|screen|desk|face|outfit|shirt|clothes)|"
    r"i see (that )?you('re| are)"
    r")\b"
)
_MOVE_CLAIM = re.compile(
    r"\b("
    r"i('m| am| have|'ve)? (now )?(moving|moved|adjusting|repositioned)|"
    r"i('m| am) (now )?(in|at|on) the (top|bottom|upper|lower|left|right|cent(er|re)|middle)|"
    r"there you go"
    r")\b"
)
# The opposite failure: denying a sense it has (step 6c second live run, after
# waking: "I don't have a sense of hearing or the ability to capture sound").
_DENIAL = re.compile(
    r"\b("
    r"i (don't|do not|can't|cannot) (have )?(a sense of |the ability to )?(hear|hearing|listen|capture sound|detect (singing|speech|sound))|"
    r"i('m| am) (a )?text[- ]based|"
    r"i (don't|do not) have (a |any )?(camera|microphone|ears|eyes|voice)"
    r")\b"
)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def guard_sentence(sentence: str) -> str | None:
    """The replacement for a fabricated claim, or None if the sentence is fine."""
    s = sentence.lower().replace("’", "'")
    if _MOVE_CLAIM.search(s):
        return MOVE_REPLACEMENT
    if _SEE_CLAIM.search(s):
        return SEE_REPLACEMENT
    if _DENIAL.search(s):
        return DENIAL_REPLACEMENT
    return None


def build_claim_guard(pending, *, on_replace=None):
    """FrameProcessor placed after the LLM (and the provenance logger), before
    TTS. `pending` is the shared `VisionPending`; armed == an image is attached
    to this turn. `on_replace(original, replacement)` is an optional log hook."""

    from pipecat.frames.frames import (
        Frame,
        InterruptionFrame,
        LLMFullResponseEndFrame,
        LLMFullResponseStartFrame,
        LLMTextFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    class ClaimGuard(FrameProcessor):
        def __init__(self) -> None:
            super().__init__()
            self._buf = ""
            self._said: set[str] = set()

        async def _emit(self, text: str, direction) -> None:
            fixed = guard_sentence(text)
            if fixed is not None:
                if on_replace is not None:
                    try:
                        on_replace(text, fixed)
                    except Exception:
                        pass
                if fixed in self._said:      # say each correction once per reply
                    return
                self._said.add(fixed)
                text = fixed + " "
            await self.push_frame(LLMTextFrame(text), direction)

        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)

            if isinstance(frame, LLMFullResponseStartFrame):
                self._buf, self._said = "", set()
            elif isinstance(frame, InterruptionFrame):
                self._buf = ""
            elif isinstance(frame, LLMTextFrame) and not pending.armed:
                self._buf += frame.text or ""
                parts = _SENTENCE_END.split(self._buf)
                self._buf = parts.pop()
                for p in parts:
                    await self._emit(p + " ", direction)
                return
            elif isinstance(frame, LLMFullResponseEndFrame) and self._buf:
                tail, self._buf = self._buf, ""
                await self._emit(tail, direction)

            await self.push_frame(frame, direction)

    return ClaimGuard()
