"""T2 (deep look) and T3 (respond) — real, wired, empty.

day8-prompt.md calls these "twenty minutes of empty functions" and is
explicit that skipping them is the mistake that costs the most later:
Day 10 (JARVIS query loop, T3) and Day 13 (depth/segmentation, T2) need to
plug into a seam that already exists, not restructure main.py's loop to
make room for one.

Neither does anything yet. Both exist so `main.py` has a real call site —
the preemption seam — for "T3 wants to run, tell T1/T2 to yield" once
Day 10 gives it something to preempt with.
"""

from __future__ import annotations

from typing import Any


def deep_look(frame_bgr, track: dict) -> dict | None:
    """T2: on-demand deep look at one track (depth/seg/pose/OCR/face —
    v2-architecture-research.md §2a). Not implemented until Day 13.
    Returns None until then; callers must treat None as "no deep info yet",
    not an error.
    """
    return None


def respond(query: str, context: dict[str, Any]) -> str | None:
    """T3: STT -> LLM -> TTS response loop (Day 10/11). Not implemented
    yet. Returns None until then.
    """
    return None


class PreemptionSeam:
    """Tracks whether T3 currently wants the floor. T0/T1 keep running
    regardless (they're cheap and always-on by design) — this is only
    where T2's optional, expensive work would check before starting, and
    where Day 10 hooks in "T3 is answering, don't kick off a deep look
    right now."

    A plain flag, not a lock: nothing sets it yet, so this is inert until
    Day 10 gives `request()`/`release()` a caller.
    """

    def __init__(self) -> None:
        self._active = False

    def request(self) -> None:
        self._active = True

    def release(self) -> None:
        self._active = False

    @property
    def active(self) -> bool:
        return self._active
