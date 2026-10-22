"""Spoken email addresses → written ones, deterministically (step 9 live run).

The owner said "sakith dot munda at the rate gmail dot com" ("at the rate" is
how "@" is read aloud in Indian English) and Whisper wrote it variously as
"sakeeth.mundiatharitgmail.com", "sakith.munda at the rate gmail.com" and
"socket. dot munda. add the rate. gmail.com". The planner then drafted to an
address with no "@". Turning the spoken form into an address is a grammar, not
a judgment, so it is done here and not left to a 4B model.

    normalize("email saket dot munda at the rate gmail dot com")
      -> "email saket.munda@gmail.com"

Only a span that ends in a plausible domain is rewritten, so "meet at the
station" and "dot the i's" are left alone. The result is what the read-back
spells out before anything is sent; this module never decides that an address
is right.
"""

from __future__ import annotations

import re

_AT = r"(?:at\s+the\s*rate(?:\s*of)?|add\s+the\s*rate|at the red|at rate|at sign|at symbol|at)"
_DOT = r"(?:\s*\.\s*|\s+dot\s+|\s*\.\s*dot\s*\.?\s*)"
# after a SPOKEN "at", only a known provider counts ("I'm at home dot com" is
# not an address); after a literal "@", any domain does
_PROVIDERS = r"(?:gmail|googlemail|yahoo|outlook|hotmail|icloud|live|proton(?:mail)?|rediffmail|zoho)"
_ANY_DOMAIN = r"[a-z0-9-]{2,}"
_TLDS = r"(?:com|in|co\.in|co\.uk|org|net|io|ai|dev|me|edu)"

# local part: one to four word-ish chunks joined by spoken/written dots or underscores
_LOCAL = r"[a-z0-9][a-z0-9_+-]*(?:(?:\s*\.\s*|\s+dot\s+|\s*\.\s*dot\s*\.?\s*|\s+underscore\s+|_)[a-z0-9][a-z0-9_+-]*){0,3}"
# a spoken "at" stands alone as a word: "mundiatharitgmail" must not split on
# its letters into a confident wrong address
_SPOKEN = re.compile(
    rf"\b(?P<local>{_LOCAL})(?:\s*\.?\s+{_AT}\s*\.?\s*(?P<domain>{_PROVIDERS})(?=[\s.])"
    rf"|\s*@\s*(?P<domain2>{_ANY_DOMAIN}))(?P<tld>(?:{_DOT}{_TLDS})+)\b",
    re.I,
)
_VALID = re.compile(r"^[a-z0-9][a-z0-9._%+-]*@[a-z0-9-]+(?:\.[a-z0-9-]+)+$", re.I)
_LEAD_WORDS = {"to", "is", "email", "mail", "address", "send", "the", "my", "at", "and", "friend"}


def _join(local: str) -> str:
    s = re.sub(r"\s+underscore\s+", "_", local, flags=re.I)
    s = re.sub(r"\s*\.\s*dot\s*\.?\s*|\s+dot\s+|\s*\.\s*", ".", s, flags=re.I)
    return re.sub(r"\s+", "", s)


def normalize(text: str) -> str:
    """Rewrite every spoken email address in `text`; everything else unchanged."""
    def repl(m: re.Match) -> str:
        words = m.group("local").split()
        # don't swallow leading ordinary words ("send it to saket dot munda ...")
        while len(words) > 1 and words[0].lower() in _LEAD_WORDS:
            words.pop(0)
        local = _join(" ".join(words))
        tld = re.sub(r"\s*\.\s*dot\s*\.?\s*|\s+dot\s+|\s*\.\s*", ".", m.group("tld"), flags=re.I)
        addr = f"{local}@{m.group('domain') or m.group('domain2')}{tld}".lower()
        if not _VALID.match(addr):
            return m.group(0)
        prefix = m.group(0)[: m.group(0).lower().find(words[0].lower())] if words else ""
        return prefix + addr

    return _SPOKEN.sub(repl, text or "")


def find(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9._%+-]*@[a-z0-9-]+(?:\.[a-z0-9-]+)+", normalize(text), re.I)


def spoken(address: str) -> str:
    """How the read-back says an address: the local part spelled letter by
    letter (that is where speech recognition goes wrong), the domain as words.
    'saket.munda@gmail.com' -> 's a k e t dot m u n d a, at gmail dot com'."""
    if "@" not in address:
        return address
    local, domain = address.split("@", 1)
    parts = []
    for chunk in re.split(r"([._-])", local):
        if chunk in (".", "_", "-"):
            parts.append({".": "dot", "_": "underscore", "-": "dash"}[chunk])
        elif chunk:
            parts.append(" ".join(chunk))
    return f"{' '.join(parts)}, at {domain.replace('.', ' dot ')}"
