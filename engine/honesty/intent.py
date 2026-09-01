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
        if self.type == "query_object":
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
_QUERY = re.compile(r"(?:do you see|can you see|is there|are there)\s+(.+?)\??$")
# Real usage found (decisions.md D39 amendment, day 10 retest): common
# conversational filler ("are you there", "thanks") isn't a command, but
# answering it with "i didn't understand that" reads as broken rather than
# as a deliberately narrow grammar. Two more fixed patterns, still zero
# model — canned, not understood.
_PRESENCE = re.compile(r"\b(are you there|you there|are you listening|are you awake)\b")
_THANKS = re.compile(r"\b(thanks|thank you|thankyou|appreciate it)\b")
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
    if _HELP.search(text):
        return Intent("help")
    if _PRESENCE.search(text):
        return Intent("presence")
    if _THANKS.search(text):
        return Intent("thanks")
    if _DESCRIBE.search(text):
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
