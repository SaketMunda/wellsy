"""T2 (deep look) and T3 (respond) — T3 wired for real on Day 10.

day8-prompt.md called these "twenty minutes of empty functions" and was
explicit that skipping them is the mistake that costs the most later. Day 10
is that payoff: `PreemptionSeam` has been sitting inert since Day 8 waiting
for its first caller — `engine/query_loop.py`'s T3 loop is that caller.
"""

from __future__ import annotations

import threading
from typing import Any


def deep_look(frame_bgr, track: dict) -> dict | None:
    """T2: on-demand deep look at one track (depth/seg/pose/OCR/face —
    v2-architecture-research.md §2a). Not implemented until Day 13.
    Returns None until then; callers must treat None as "no deep info yet",
    not an error.
    """
    return None


def respond(query: str, context: dict[str, Any]) -> str | None:
    """T3: STT -> intent -> describeScene -> TTS response loop. Superseded
    by engine/query_loop.py's QueryLoop, which is the real Day 10
    implementation; this stub stays for any caller still importing the
    Day 8 shape.
    """
    return None


class PreemptionSeam:
    """Tracks whether T3 currently wants the floor, AND is the actual
    hand-off mechanism between the main capture/detect loop (which owns the
    camera frame and T1 detector) and the T3 query thread (which owns the
    microphone and TTS).

    T0 (motion gate) keeps running every frame regardless of `active` — it's
    cheap and always-on by design (day10-prompt.md Part 1's "do not gate the
    gate"). What `active` actually suppresses in main.py's loop is T1's
    *own-schedule* detection (the periodic every-125ms due-check) — while a
    query is in flight, ambient sensing pauses and the only detection that
    runs is the one T3 explicitly asked for via `request_fresh_look()`. This
    is why the JSONL should visibly stop producing new `inferenceMs` values
    for the duration of a query except for exactly one entry (the forced
    look) — see day10-results.md row 4 for the captured evidence.
    """

    def __init__(self) -> None:
        self._active = False
        self._lock = threading.Lock()
        # T3 -> main loop: "I need a fresh detection right now."
        self._force_requested = threading.Event()
        # main loop -> T3: "here it is."
        self._result_ready = threading.Event()
        self._result: tuple[list[dict], float, Any] | None = None

    def request(self) -> None:
        with self._lock:
            self._active = True

    def release(self) -> None:
        with self._lock:
            self._active = False

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    def request_fresh_look(self, timeout: float = 2.0) -> tuple[list[dict], float, Any] | None:
        """Called by T3. Blocks until the main capture loop performs one
        forced, synchronous T1 detection on the current frame and hands
        back (tracks, inference_ms, frame_bgr), or returns None on timeout
        (e.g. the capture process died mid-query).

        `frame_bgr` was added Day 11 (day11-prompt.md Part 1) so the query
        loop can hand the VLM the actual pixels the tracks were computed
        from, not just their labels -- existing callers that only read
        `result[0]`/`result[1]` (query_loop.py's describe_scene/query_object
        path, verify_preemption.py) are unaffected by the tuple growing a
        third element."""
        self._result_ready.clear()
        self._force_requested.set()
        got = self._result_ready.wait(timeout)
        if not got:
            return None
        return self._result

    def poll_force_request(self) -> bool:
        """Called by the main loop once per captured frame. Returns True
        (and clears the flag) exactly once per `request_fresh_look` call."""
        if self._force_requested.is_set():
            self._force_requested.clear()
            return True
        return False

    def deliver_fresh_look(self, tracks: list[dict], inference_ms: float, frame_bgr: Any = None) -> None:
        """Called by the main loop right after it runs the forced detection
        `poll_force_request()` asked for."""
        self._result = (tracks, inference_ms, frame_bgr)
        self._result_ready.set()
