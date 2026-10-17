"""Deterministic intent parsing — Python port of src/voice/parseIntent.ts.

Day 10 (decisions.md D37): T3 lives in the engine, so the query loop needs
this in Python rather than round-tripping transcripts through a socket to
the browser and back. Ported logic, not reinvented — same patterns, same
priority order, same cases (spec/intent-cases.json, read by both this file's
tests and parseIntent.test.ts). The TS original stays alive for
browser-only mode and is frozen as legacy.

Pure function of a transcript string; every branch is a fixed pattern, no
model, no async. This is pattern-matching, not language understanding —
off-script phrasing falls through to `unknown`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Intent:
    type: str
    object: str | None = None
    transcript: str | None = None

    def to_dict(self) -> dict:
        d: dict = {"type": self.type}
        if self.type in ("query_object", "move_orb"):
            d["object"] = self.object
        if self.type == "unknown":
            d["transcript"] = self.transcript
        return d


_STOP = re.compile(r"\bstop\b")
_WAKE = re.compile(r"\b(wake up|hey wellsy|wake)\b")
_SLEEP = re.compile(r"\b(go to sleep|shut up|be quiet|quiet down|hush|sleep now|sleep)\b")
_HELP = re.compile(r"\b(what can you do|help|what commands|list commands)\b")
_DESCRIBE = re.compile(
    r"\b(what do you see|what('?s| is) in front of you|describe the scene|describe scene|what can you see|what is there)\b"
)
# Screen grounding (A8). A question / read verb plus an explicit screen word ->
# describe_scene; `engine.voice.vision.route()` then captures the screen rather
# than the camera. Kept narrow — an interrogative is required, so "turn off my
# monitor" does not match. This is still the "describe" family, not a new
# safety-path intent (INVARIANTS #3 is about stop/wake/sleep).
_SCREEN = re.compile(
    r"\b(what('?s| is| are)?|which|any|anything|is there|are there|do you see|"
    r"can you see|read|show me|tell me)\b[^?]*\b(screen|monitor|my display)\b"
)
# Questions about the user themself — "what am I wearing", "can you see me".
# Step 6c live run: these fell through to the text model, which then claimed to
# see through a camera it never opened. Routed to the camera like any
# describe_scene; `vision.route()` picks camera because no screen word is present.
_SELF_VISION = re.compile(
    r"\b(what (am i|i'?m|i am) (currently |now )?(wearing|holding|doing)|"
    r"you\b(?: \w+){0,3} see me|see me now|look at me|how do i look|what do i look like|"
    r"am i visible)\b"
)
_QUERY = re.compile(r"(?:do you see|can you see|is there|are there)\s+(.+?)\??$")
# Real usage found (decisions.md D39 amendment, day 10 retest): common
# conversational filler ("are you there", "thanks") isn't a command, but
# answering it with "i didn't understand that" reads as broken rather than
# as a deliberately narrow grammar. Two more fixed patterns, still zero
# model — canned, not understood.
_PRESENCE = re.compile(r"\b(are you there|you there|are you listening|are you awake)\b")
_THANKS = re.compile(r"\b(thanks|thank you|thankyou|appreciate it)\b")
# Move the on-screen orb. Deterministic, like stop/wake/sleep — it drives the UI,
# never the model. Matches "move to the center", "go to the bottom right",
# "get out of the way" (-> a default corner). The corner phrase is captured in
# .object and resolved by engine.interface.backends.qt.backend.normalize_corner.
#
# Matched against the transcript with internal punctuation flattened (step 6c
# live run: Whisper wrote "move to the... right. screen" and the old
# `[^.?!]*?` span stopped at the ellipsis). The span is capped at 40 chars so a
# verb early in a long sentence can't latch onto a far-off direction word, and
# "right now" / "right away" / "right here" are not directions.
_MOVE_ORB = re.compile(
    r"\b(move|go|jump|snap|shift|get)\b.{0,40}?\b("
    r"top[- ]?left|top[- ]?right|bottom[- ]?left|bottom[- ]?right|"
    r"upper[- ]?left|upper[- ]?right|lower[- ]?left|lower[- ]?right|"
    r"left[- ]?bottom|right[- ]?bottom|left[- ]?top|right[- ]?top|"
    r"left[- ]corner|right[- ]corner|top[- ]corner|bottom[- ]corner|"
    r"out of (?:the|my) way|"
    r"cent(?:er|re)|middle|top|bottom|left|right(?! now| away| here| there)|corner|away)\b"
)
_INNER_PUNCT = re.compile(r"[.,;:!?…]+")
# A bare placement with no verb — the second half of a move request split by a
# pause ("...can you shift to" / "the bottom right corner"). Whole utterance only.
_BARE_CORNER = re.compile(
    r"^(?:(?:to|in|into|at) )?(?:the )?((?:top|bottom|upper|lower)[- ]?(?:left|right)|"
    r"(?:left|right) corner|cent(?:er|re))(?: corner)?(?: of the screen)?(?: please)?$"
)
_DETERMINER = re.compile(r"^(a|an|the|any)\s+")
_TRIM_PUNCT = re.compile(r"[.!?]+$")
_WHITESPACE = re.compile(r"\s+")


def _normalize(transcript: str) -> str:
    text = transcript.lower().strip()
    text = _TRIM_PUNCT.sub("", text)
    text = _WHITESPACE.sub(" ", text)
    return text


def _strip_determiner(phrase: str) -> str:
    return _DETERMINER.sub("", phrase.strip())


_COURTESY = {"wellsy", "hey", "ok", "okay", "so", "very", "much", "please", "a", "lot", "for",
             "that", "this", "everything", "the", "now", "again", "oh", "great", "cool", "nice",
             "and", "you", "me", "all", "just", "really", "well", "hi", "hello", "um", "uh"}


def _only_filler(text: str, pattern: re.Pattern) -> bool:
    rest = _INNER_PUNCT.sub(" ", pattern.sub(" ", text))
    return len([w for w in rest.split() if w not in _COURTESY]) <= 1


def parse_intent(transcript: str) -> Intent:
    text = _normalize(transcript)
    if not text:
        return Intent("unknown", transcript=transcript)

    if _STOP.search(text):
        return Intent("stop")
    if _WAKE.search(text):
        return Intent("wake")
    if _SLEEP.search(text):
        return Intent("sleep")
    # Canned filler only when the filler IS the utterance. Step 9: with tools
    # behind the model, "Thanks. And what's on my calendar today?" answered
    # "Anytime." and dropped the request; "help me book a dentist" would have
    # recited the help text. stop/wake/sleep above are untouched (INVARIANTS #3).
    if _HELP.search(text) and _only_filler(text, _HELP):
        return Intent("help")
    if _PRESENCE.search(text) and _only_filler(text, _PRESENCE):
        return Intent("presence")
    if _THANKS.search(text) and _only_filler(text, _THANKS):
        return Intent("thanks")
    flat = _WHITESPACE.sub(" ", _INNER_PUNCT.sub(" ", text)).strip()
    m = _MOVE_ORB.search(flat)
    if m:
        return Intent("move_orb", object=m.group(2))
    m = _BARE_CORNER.match(flat)
    if m:
        return Intent("move_orb", object=m.group(1))
    if _DESCRIBE.search(text) or _SCREEN.search(text) or _SELF_VISION.search(text):
        return Intent("describe_scene")

    match = _QUERY.search(text)
    if match:
        obj = _strip_determiner(match.group(1))
        if obj:
            return Intent("query_object", object=obj)

    return Intent("unknown", transcript=transcript)


HELP_TEXT = (
    "i handle a few things: wake up, sleep, stop -- which silences me until "
    "you wake me again -- what do you see, do you see a -- something, and "
    "help. anything else, i will say so. press escape for an instant stop, "
    "no voice needed."
)
