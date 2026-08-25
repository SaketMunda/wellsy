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
import threading
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
    "Morning, sir. How are you today?",
    "Rise and shine. What's first?",
]
GREETINGS_AFTERNOON = [
    "Good afternoon, sir. What can I do for you?",
    "Afternoon. What's next?",
    "Afternoon, sir. How's it going?",
]
GREETINGS_EVENING = [
    "Good evening, sir. Anything I can help with?",
    "Evening. Standing by.",
    "Evening, sir. How was your day?",
]
GREETINGS_NIGHT = [
    "Still up, sir? What do you need?",
    "Burning the midnight oil, I see. How can I help?",
    "Late one tonight. What's the plan?",
]

# Real usage bug, reported live: a 3-line bank with plain random.choice()
# picked the same line often enough across a short test session to look
# broken ("it always says the same thing"), which is exactly what
# uniform-random small-sample selection does. Excluding the immediately
# preceding line skews the odds toward variety without needing a bigger
# bank or a fake "shuffle so it never repeats" guarantee.
_last_line: str | None = None


def _pick_greeting(now: datetime | None = None) -> str:
    global _last_line
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

    choices = [line for line in bank if line != _last_line] or bank
    line = random.choice(choices)
    _last_line = line
    return line


# Real usage bug #1, reported live: the greeting fired once with nobody in
# frame at all. `any(t["label"] == "person" for t in tracks)` triggered on
# a single noisy frame. MIN_PERSON_SCORE=0.6 + a 2-frame debounce fixed
# that case.
#
# Real usage bug #2, reported live minutes later, with a screenshot: an
# empty-room gaming chair, its headrest wings apparently reading as
# shoulders, was tracked and locked as `person` at **83% confidence, 100%
# label confidence, sustained across frames** -- not a flicker. Bug #1's
# fix does not touch this: a threshold below 83% never catches it, and a
# threshold above it risks rejecting real people at similar confidence.
# This is the underlying detector being *confidently and consistently*
# wrong, not a debounce/flicker problem -- a different failure class,
# stated plainly rather than folded into the same "fixed" claim that was
# already made once and was wrong.
#
# What changed here is not a real fix for that -- there isn't one at this
# layer, short of retraining or reprompting the detector against this
# exact chair, which needs the owner's own room and iteration this agent
# can't do blind. What changed is how conservative the *unprompted-speech*
# gate is, specifically because the cost of the two failure directions is
# asymmetric: greeting furniture in an empty room is the embarrassing,
# visible failure; staying quiet an extra beat when a real person is
# standing there is not -- they still have the wake phrase.
#
# Real usage bug #3, reported live minutes after bug #2's fix shipped: a
# real person (the owner) walked into frame and got no greeting at all.
# The aspect-ratio check below (`_looks_person_shaped`) was guessed from
# one screenshot of the chair's shape, with zero data about how the owner
# actually appears in their own camera framing -- sitting close to a desk
# very plausibly produces a box wider than tall (shoulders/upper body),
# the exact opposite of the assumption baked into that guess. Rather than
# guess a fourth number, the shape check is demoted to diagnostic-only
# (logged, never blocks) until there's a real measurement of what the
# owner's own "present" box actually looks like. `MIN_PERSON_SCORE` and
# `PRESENCE_DEBOUNCE_FRAMES` stay as they were -- also unverified against
# real footage, also candidates if this still doesn't fire -- but changing
# every knob at once after one report makes it impossible to tell which
# change did what, so only the newest, least-tested one moves this round.
MIN_PERSON_SCORE = 0.9
PRESENCE_DEBOUNCE_FRAMES = 5
MIN_ASPECT_RATIO = 1.0  # diagnostic only, logged below -- does not gate the greeting
DIAG_LOG_INTERVAL_SECONDS = 2.0


class PersonGreeter:
    def __init__(self, query_loop) -> None:
        self._query_loop = query_loop
        self._person_present = False
        self._last_greeted_at = 0.0
        self._pending_frames = 0
        self._last_diag_log = 0.0

    def update(self, tracks: list[dict]) -> None:
        self._log_diagnostics(tracks)
        person_seen = any(
            t["label"] == "person" and t.get("score", 1.0) >= MIN_PERSON_SCORE
            for t in tracks
        )

        if person_seen:
            self._pending_frames += 1
        else:
            self._pending_frames = 0

        person_present = self._pending_frames >= PRESENCE_DEBOUNCE_FRAMES

        if person_present and not self._person_present:
            self._maybe_greet()
        self._person_present = person_present

    def _log_diagnostics(self, tracks: list[dict]) -> None:
        """Real numbers instead of another guess. Throttled so this can't
        become the same per-frame log-spam problem `--debug` exists to
        avoid -- fires at most once every DIAG_LOG_INTERVAL_SECONDS, and
        only when a `person` track actually exists to report on."""
        people = [t for t in tracks if t["label"] == "person"]
        if not people:
            return
        now = time.monotonic()
        if now - self._last_diag_log < DIAG_LOG_INTERVAL_SECONDS:
            return
        self._last_diag_log = now
        for t in people:
            score = t.get("score", 1.0)
            bbox = t.get("bbox")
            aspect = None
            if bbox and len(bbox) == 4 and bbox[2] > 0:
                aspect = round(bbox[3] / bbox[2], 2)
            self._query_loop._log(
                f"greeter diag: id={t.get('id')} score={score:.2f} "
                f"(need >= {MIN_PERSON_SCORE}) aspect(h/w)={aspect} "
                f"(informational only, need >= {MIN_ASPECT_RATIO} if it were enforced) "
                f"pending_frames={self._pending_frames}/{PRESENCE_DEBOUNCE_FRAMES}"
            )

    def _maybe_greet(self) -> None:
        now = time.monotonic()
        if now - self._last_greeted_at < REGREET_COOLDOWN_SECONDS:
            return
        if self._query_loop.preemption.active:
            return  # a real query is already in flight — don't talk over it
        if self._query_loop._speaking():
            return

        line = _pick_greeting()
        # Real gap, found from a live log: nothing ever logged what the
        # greeting actually said, or whether it played -- `speak_ambient()`
        # is fire-and-forget by design, so a live report of "it detected me
        # but said nothing" was previously undiagnosable from the terminal
        # alone. This makes the attempt and its outcome visible.
        self._query_loop._log(f"greeting: \"{line}\"")
        handle = self._query_loop.speak_ambient(line)
        self._query_loop._extend_conversation()
        self._last_greeted_at = now
        if handle is not None:
            threading.Thread(
                target=self._log_greeting_outcome, args=(handle,), daemon=True
            ).start()

    def _log_greeting_outcome(self, handle) -> None:
        handle.wait()
        if getattr(handle, "_cancelled", None) is not None and handle._cancelled.is_set():
            self._query_loop._log("greeting: cancelled before it played")
        elif getattr(handle, "audio_started_at", None) is None:
            self._query_loop._log("greeting: generation finished but audio never started -- check for a silent exception in tts.py's background thread")
        else:
            self._query_loop._log("greeting: played")
