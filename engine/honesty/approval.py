"""Spoken approval — a fixed grammar, not a model (step 9 Deliverable 3).

A spoken "yes" is a safety surface: it is what lets a risk-2 or risk-3 tool
run. So it is parsed the way `parse_intent` parses `stop` (INVARIANTS #3) —
by regex, deterministically — and **anything that is not a clear yes is a no**.

    parse_approval("yes")                 -> "yes"
    parse_approval("yeah go ahead")       -> "yes"
    parse_approval("no")                  -> "no"
    parse_approval("yes, no wait")        -> "no"      (any negation wins)
    parse_approval("what time is it")     -> "unclear" (resolves to refusal)
    parse_approval("yes but tomorrow")    -> "unclear" (a yes with a change is not a yes)

The caller treats "no" and "unclear" identically (the step does not run) and
speaks the difference, so the user learns why.
"""

from __future__ import annotations

import re

# Any of these anywhere in the utterance means the answer is not yes.
_NEGATIVE = re.compile(
    r"\b(no|nope|nah|not|don'?t|do not|never|stop|cancel|abort|wait|hold on|hang on|"
    r"wrong|deny|denied|decline|negative|later|scratch that)\b"
)

# The whole utterance, once filler is removed, must be made of these.
_AFFIRM_PHRASES = [
    "yes", "yeah", "yep", "yup", "yes please", "sure", "ok", "okay", "alright", "all right",
    "go ahead", "go for it", "do it", "please do", "approve", "approved", "confirm",
    "confirmed", "correct", "that's right", "that is right", "right", "affirmative",
    "send it", "book it", "add it", "create it", "move it", "delete it", "save it",
    "sounds good", "absolutely", "definitely", "of course", "proceed",
    "do it now", "send it now", "go ahead now",
]
_FILLER = {"wellsy", "well", "um", "uh", "hmm", "so", "and", "then", "just", "thanks",
           "thank", "you"}
_AFFIRM_RE = re.compile(
    r"^(?:" + "|".join(sorted((re.escape(p) for p in _AFFIRM_PHRASES), key=len, reverse=True))
    + r")(?:\s+(?:" + "|".join(sorted((re.escape(p) for p in _AFFIRM_PHRASES), key=len, reverse=True))
    + r"))*$"
)


def _normalise(text: str) -> str:
    t = (text or "").lower().replace("’", "'")
    t = re.sub(r"[^a-z' ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_approval(text: str) -> str:
    """'yes' | 'no' | 'unclear'."""
    t = _normalise(text)
    if not t:
        return "unclear"
    if _NEGATIVE.search(t):
        return "no"
    words = [w for w in t.split() if w not in _FILLER]
    core = " ".join(words)
    if core and _AFFIRM_RE.match(core):
        return "yes"
    return "unclear"
