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

Step 9 adds the agent's version of the same lie: **a completed action nobody
performed** ("I've sent it", "Your reminder is set"). Once the voice loop has
tools, the model can claim one without calling them — or before the result
arrives. Such a sentence passes only if **every** action verb in it is backed by
a read-back-verified tool of that kind in the agent's most recent run
(`verified_tools()`, fed by the agent bridge): "I've drafted it and sent it"
needs both a verified `mail_create_draft` and a verified `mail_send_draft`.
Otherwise it is replaced. (Step 9 replay: a time window let an earlier verified
reminder vouch for "I've drafted the email and sent it" on a run where both
steps had errored.)

`guard_sentence()` is pure; the processor only buffers streamed text into
sentences (TTS speaks whole sentences anyway, so this adds no latency).
"""

from __future__ import annotations

import re

SEE_REPLACEMENT = "I haven't looked. Ask me what I see and I'll check."
MOVE_REPLACEMENT = "I didn't move. Say move to the bottom right, and I will."
DENIAL_REPLACEMENT = "I can hear you through the microphone, and I can look through the camera when you ask."
ACTION_REPLACEMENT = "That part isn't done."

# which verified tools can back which verb
_VERB_TOOLS = {
    "sent": {"pim.mail_send_draft"},
    "drafted": {"pim.mail_create_draft"},
    "moved": {"pim.calendar_move_event"}, "rescheduled": {"pim.calendar_move_event"},
    "deleted": {"fs.fs_delete_file"}, "removed": {"fs.fs_delete_file"},
    "completed": {"pim.reminders_complete"}, "marked": {"pim.reminders_complete"},
    "saved": {"fs.fs_write_file", "pim.notes_create"}, "written": {"fs.fs_write_file", "pim.notes_create"},
    "wrote": {"fs.fs_write_file", "pim.notes_create"},
    # step 9 replay: a verified *note* vouched for "I've scheduled your dentist
    # appointment" — scheduling is a calendar verb
    "scheduled": {"pim.calendar_create_event", "pim.calendar_move_event"},
    "booked": {"pim.calendar_create_event"},
}
_CREATE_TOOLS = {"pim.calendar_create_event", "pim.reminders_create", "pim.notes_create",
                 "pim.mail_create_draft", "fs.fs_write_file"}
_ANY_MUTATION = _CREATE_TOOLS | {t for ts in _VERB_TOOLS.values() for t in ts} | {"pim.calendar_move_event"}
_VERB_WORD = re.compile(r"\b(sent|created|added|scheduled|booked|moved|rescheduled|deleted|removed|saved|"
                        r"set|drafted|written|wrote|completed|marked|updated|cancel+ed|done)\b")


# the object a claim names must be backed by a tool on that object (step 9
# replay: a verified calendar event vouched for "I also set a reminder")
_NOUN_TOOLS = [
    (re.compile(r"\breminders?\b"), {"pim.reminders_create", "pim.reminders_complete"}),
    (re.compile(r"\b(e-?mails?|mail|message|draft|reply)\b"), {"pim.mail_create_draft", "pim.mail_send_draft"}),
    (re.compile(r"\b(calendar|event|meeting|appointment)s?\b"), {"pim.calendar_create_event", "pim.calendar_move_event"}),
    (re.compile(r"\bnotes?\b"), {"pim.notes_create"}),
    (re.compile(r"\bfiles?\b"), {"fs.fs_write_file", "fs.fs_delete_file"}),
]


def _backed(sentence: str, verified: frozenset | set) -> bool:
    for pat, need in _NOUN_TOOLS:
        if pat.search(sentence) and not (need & set(verified)):
            return False
    for v in _VERB_WORD.findall(sentence):
        need = _VERB_TOOLS.get(v)
        if need is None:
            need = _CREATE_TOOLS if v in ("created", "added", "set") else _ANY_MUTATION
        if not (need & set(verified)):
            return False
    return True

_DONE_VERB = (r"(sent|created|added|scheduled|booked|moved|rescheduled|deleted|removed|saved|"
              r"set|set up|drafted|written|wrote|completed|marked|updated|cancel+ed)")
_ACTION_CLAIM = re.compile(
    r"\b("
    r"i('ve| have)? (also |just |now |already )*" + _DONE_VERB + r"|"
    r"(it|that|this)('s| is| has| was)( been)? (now |already )?" + _DONE_VERB + r"|"
    r"(your|the) (event|meeting|reminder|e-?mail|mail|message|note|draft|file|appointment)"
    r"('s| has| is| was)( been)? (now |already )?" + _DONE_VERB + r"|"
    r"^(all )?done"
    r")\b"
)

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


def guard_sentence(sentence: str, *, verified: frozenset | set = frozenset()) -> str | None:
    """The replacement for a fabricated claim, or None if the sentence is fine.
    `verified`: tool keys whose mutation a read-back confirmed in the agent's
    most recent run."""
    s = sentence.lower().replace("’", "'").strip()
    if _ACTION_CLAIM.search(s) and not _backed(s, verified):
        return ACTION_REPLACEMENT
    if _MOVE_CLAIM.search(s):
        return MOVE_REPLACEMENT
    if _SEE_CLAIM.search(s):
        return SEE_REPLACEMENT
    if _DENIAL.search(s):
        return DENIAL_REPLACEMENT
    return None


def build_claim_guard(pending, *, on_replace=None, verified_tools=None):
    """FrameProcessor placed after the LLM (and the provenance logger), before
    TTS. `pending` is the shared `VisionPending`; armed == an image is attached
    to this turn. `on_replace(original, replacement)` is an optional log hook.
    `verified_tools()` -> the verified mutation tool keys backing claims now."""

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
            verified: frozenset = frozenset()
            if verified_tools is not None:
                try:
                    verified = frozenset(verified_tools() or ())
                except Exception:
                    verified = frozenset()
            fixed = guard_sentence(text, verified=verified)
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
