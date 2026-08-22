"""The JARVIS-boot greeting — added mid-Day-11 on the project owner's
explicit, live direction: *"Can we not use the wake up, but just initiate
by their own if I first appear in the frame."* Not a redesign of the wake
system (`parse_intent`'s `wake`/`sleep`/`stop` grammar is untouched, per
the day's own boundary rule that an LLM/heuristic must never own those) —
this is a new, narrow, additive behavior that sits next to it: when a
`person` track transitions from absent to present, speak one real
JARVIS-style greeting and open the same conversation-follow-up window
`handle_command` already opens after any answered command
(`QueryLoop._extend_conversation()`), so the very first thing you say
after walking into frame doesn't need "hey yap" in front of it.

**Deliberately not gated behind `QueryLoop.ambient_enabled`** (unlike
`ambient.py`'s appear/disappear narration, D38's "silence is default").
This is the one kind of unprompted speech the owner explicitly asked for
today — always on, not an opt-in mode — but scoped tight: it fires once
per genuine appearance, not continuously, so it doesn't reopen the exact
narration-fatigue problem D38 was built to close.

**Why a cooldown, not a one-shot-per-process flag:** a track briefly
lost to occlusion and immediately re-acquired (ByteTrack coasts short
gaps internally, so this is already rarer than it was with the old
tracker — D31) shouldn't re-trigger a greeting; someone genuinely leaving
and coming back later should. `REGREET_COOLDOWN_SECONDS` is a first-guess
constant, same caveat as every other untuned threshold in this project
(D11's alpha, D15's tau) — not tuned against real walk-away/return
footage this session.
"""

from __future__ import annotations

import random
import time
from datetime import datetime

REGREET_COOLDOWN_SECONDS = 120.0

# Real-time-based, not fabricated — datetime.now() is genuine data, same
# honesty rule D17 applied to "distance" (never print a number with no
# real source behind it). Hour buckets are first-guess, not astronomical.
_MORNING = list(range(5, 12))
_AFTERNOON = list(range(12, 17))
_EVENING = list(range(17, 22))

GREETINGS_MORNING = [
    "Good morning, sir. What's on the agenda today?",
    "Morning. Ready when you are.",
    "Good morning. Shall we get started?",
]
GREETINGS_AFTERNOON = [
    "Good afternoon, sir. What can I do for you?",
    "Afternoon. What's next?",
]
GREETINGS_EVENING = [
    "Good evening, sir. Anything I can help with?",
    "Evening. Standing by.",
]
GREETINGS_NIGHT = [
    "Still up, sir? What do you need?",
    "Burning the midnight oil, I see. How can I help?",
    "Late one tonight. What's the plan?",
]


def _pick_greeting(now: datetime | None = None) -> str:
    now = now or datetime.now()
    hour = now.hour
    if hour in _MORNING:
        bank = GREETINGS_MORNING
    elif hour in _AFTERNOON:
        bank = GREETINGS_AFTERNOON
    elif hour in _EVENING:
        bank = GREETINGS_EVENING
    else:
        bank = GREETINGS_NIGHT
    return random.choice(bank)


class PersonGreeter:
    def __init__(self, query_loop) -> None:
        self._query_loop = query_loop
        self._person_present = False
        self._last_greeted_at = 0.0

    def update(self, tracks: list[dict]) -> None:
        person_present = any(t["label"] == "person" for t in tracks)

        if person_present and not self._person_present:
            self._maybe_greet()
        self._person_present = person_present

    def _maybe_greet(self) -> None:
        now = time.monotonic()
        if now - self._last_greeted_at < REGREET_COOLDOWN_SECONDS:
            return
        if self._query_loop.preemption.active:
            return  # a real query is already in flight — don't talk over it
        if self._query_loop._speaking():
            return

        line = _pick_greeting()
        self._query_loop.speak_ambient(line)
        self._query_loop._extend_conversation()
        self._last_greeted_at = now
