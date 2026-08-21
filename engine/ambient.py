"""Ambient narration — Part 2 of day10-prompt.md, and the smallest module
in the day's biggest product change: silence is now the default. Days 1-6
narrated constantly; this is the same appear/disappear idea (events.ts's
job in the browser build) reduced to what it costs when it's opt-in rather
than always-on, and only reachable when `QueryLoop.ambient_enabled` is
explicitly True (say "hey yap, wake up" — decisions.md D38).

Deliberately not a port of events.ts/generateLine.ts/templates.ts — no LLM
today (day10-prompt.md's hard rule) and no authored joke-line bank; this is
the same track-id-diffing idea at the minimum viable size, since ambient
mode's whole point on Day 10 is that it's off, not that it's eloquent.
"""

from __future__ import annotations

import time

from scene import _article, _plural

MIN_INTERVAL_SECONDS = 4.0


class AmbientNarrator:
    def __init__(self, query_loop) -> None:
        self._query_loop = query_loop
        self._last_ids: set[int] = set()
        self._last_spoken_at = 0.0
        self._bootstrapped = False

    def update(self, tracks: list[dict]) -> None:
        current_ids = {t["id"] for t in tracks}
        by_id = {t["id"]: t for t in tracks}

        if not self._bootstrapped:
            # Don't narrate "everything appeared" the instant ambient mode
            # turns on — only genuine changes after that baseline.
            self._last_ids = current_ids
            self._bootstrapped = True
            return

        if not self._query_loop.ambient_enabled:
            self._last_ids = current_ids
            return

        appeared = current_ids - self._last_ids
        disappeared = self._last_ids - current_ids
        self._last_ids = current_ids

        if not appeared and not disappeared:
            return
        if time.monotonic() - self._last_spoken_at < MIN_INTERVAL_SECONDS:
            return
        if self._query_loop._speaking():
            return

        if appeared:
            track = by_id[next(iter(appeared))]
            line = f"{_article(track['label'])} {track['label']} just showed up."
        else:
            line = "something just left."

        self._query_loop.speak_ambient(line)
        self._last_spoken_at = time.monotonic()
