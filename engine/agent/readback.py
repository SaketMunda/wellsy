"""Read-back before commit, in words a person hears (step 9 Deliverable 4).

The graph already verifies *after* a mutation (INVARIANTS #15, `graph._read_back`).
This module is the other half: before an approval-gated step runs, the resolved
values — who, what, and above all **when** — are rendered as one spoken
sentence, so a wrong date is heard before it becomes a real calendar entry.

Why dates get their own check: step 5b caught the planner rendering "Monday" as
a Sunday and placing a reminder in July. `date_warnings()` compares the date
the planner resolved against the cues in what the user actually said
("tomorrow", a weekday, "October 20", "at 3 pm") and against the clock. A
mismatch is spoken first ("Careful: you said Monday, but I have Sunday,
October 19.") and, for a step the policy would have let run silently, it
forces an approval (`graph.policy_check_node`).

Everything here is deterministic: no model renders the read-back, so the
read-back cannot itself hallucinate.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Awaitable, Callable

# argument names that carry the step's "when", in priority order
_DATE_KEYS = ("start", "new_start", "due")
_END_KEYS = ("end", "new_end")

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = ["january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"]

_WEEKDAY_RE = re.compile(r"\b(" + "|".join(_WEEKDAYS) + r")\b")
_MONTH_DAY_RE = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b"
    r"|\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + "|".join(_MONTHS) + r")\b"
)
_TIME_RE = re.compile(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?=\W|$)")
_NOON_RE = re.compile(r"\b(noon|midday)\b")


def parse_when(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is not None:
        d = d.astimezone().replace(tzinfo=None)
    return d


def _clock(d: dt.datetime) -> str:
    h = d.hour % 12 or 12
    suffix = "AM" if d.hour < 12 else "PM"
    if d.hour == 12 and d.minute == 0:
        return "noon"
    return f"{h}:{d.minute:02d} {suffix}" if d.minute else f"{h} {suffix}"


def spoken_date(d: dt.datetime, now: dt.datetime | None = None) -> str:
    """'Saturday, October 18' — always the weekday AND the date, so a wrong
    weekday cannot hide behind a right-sounding date (or the reverse)."""
    s = f"{_WEEKDAYS[d.weekday()].capitalize()}, {_MONTHS[d.month - 1].capitalize()} {d.day}"
    if now is not None and d.year != now.year:
        s += f", {d.year}"
    return s


def spoken_when(start: dt.datetime, end: dt.datetime | None = None,
                now: dt.datetime | None = None) -> str:
    s = f"{spoken_date(start, now)} at {_clock(start)}"
    if end is not None and end > start:
        if end.date() == start.date():
            s = f"{spoken_date(start, now)} from {_clock(start)} to {_clock(end)}"
        else:
            s += f" until {spoken_date(end, now)} at {_clock(end)}"
    return s


def _first(args: dict, keys: tuple[str, ...]) -> dt.datetime | None:
    for k in keys:
        d = parse_when(args.get(k))
        if d is not None:
            return d
    return None


def date_warnings(outcome: str, args: dict, now: dt.datetime | None = None) -> list[str]:
    """Spoken warnings where the resolved date disagrees with what was said.
    Empty when there is no date argument, or nothing to compare it against."""
    when = _first(args or {}, _DATE_KEYS)
    if when is None:
        return []
    now = now or dt.datetime.now()
    # only the user's own words: the voice bridge appends the model's
    # restatement as "(meaning: ...)", and that is not what the user said
    text = (outcome or "").split("(meaning:", 1)[0].lower().replace("’", "'")
    have = spoken_date(when, now)
    out: list[str] = []

    if re.search(r"\b(today|tonight|this (morning|afternoon|evening))\b", text):
        if when.date() != now.date():
            out.append(f"you said today, but I have {have}")
    elif re.search(r"\btomorrow\b", text):
        if when.date() != now.date() + dt.timedelta(days=1):
            out.append(f"you said tomorrow, but I have {have}")

    wd = _WEEKDAY_RE.search(text)
    if wd and _WEEKDAYS.index(wd.group(1)) != when.weekday():
        out.append(f"you said {wd.group(1).capitalize()}, but I have {have}")

    md = _MONTH_DAY_RE.search(text)
    if md:
        month = md.group(1) or md.group(4)
        day = int(md.group(2) or md.group(3))
        if (_MONTHS.index(month) + 1, day) != (when.month, when.day):
            out.append(f"you said {month.capitalize()} {day}, but I have {have}")

    tm = _TIME_RE.search(text)
    if tm:
        hour = int(tm.group(1)) % 12 + (12 if tm.group(3).startswith("p") else 0)
        minute = int(tm.group(2) or 0)
        if (hour, minute) != (when.hour, when.minute):
            said = f"{int(tm.group(1))}{':' + tm.group(2) if tm.group(2) else ''} " \
                   f"{'PM' if tm.group(3).startswith('p') else 'AM'}"
            out.append(f"you said {said}, but I have {_clock(when)}")
    elif _NOON_RE.search(text) and (when.hour, when.minute) != (12, 0):
        out.append(f"you said noon, but I have {_clock(when)}")

    if when < now - dt.timedelta(minutes=1):
        out.append(f"{have} at {_clock(when)} has already passed")
    return out


def _quote(s: Any) -> str:
    return f"“{str(s).strip()}”" if s else "an untitled item"


def _people(to: Any) -> str:
    xs = [str(x) for x in (to if isinstance(to, list) else [to]) if x]
    if not xs:
        return "no recipient"
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


Lookup = Callable[[str, dict], Awaitable[Any]]


async def describe(tool: str, args: dict, lookup: Lookup | None = None,
                   now: dt.datetime | None = None) -> str:
    """The step as a spoken verb phrase: 'add “Dentist” to your calendar on
    Saturday, October 18 from 3 PM to 4 PM'. `lookup(tool, args)` lets it
    resolve an id to something a person recognises (a draft's subject and
    recipients, an event's title); a failed lookup falls back to the raw id."""
    a = args or {}
    start, end = _first(a, _DATE_KEYS), _first(a, _END_KEYS)
    when = spoken_when(start, end, now) if start else None

    async def _get(t: str, ar: dict) -> dict:
        if lookup is None:
            return {}
        try:
            r = await lookup(t, ar)
            return r if isinstance(r, dict) else {}
        except Exception:
            return {}

    if tool == "pim.calendar_create_event":
        s = f"add {_quote(a.get('title'))} to your calendar"
        return s + (f", {when}" if when else "")
    if tool == "pim.calendar_move_event":
        ev = await _get("pim.calendar_get_event", {"event_id": a.get("event_id")})
        name = _quote(ev.get("title")) if ev.get("title") else f"event {a.get('event_id')}"
        return f"move {name} to {when}" if when else f"move {name}"
    if tool == "pim.mail_send_draft":
        d = await _get("pim.mail_get_draft", {"draft_id": a.get("draft_id")})
        if d:
            return f"send the email {_quote(d.get('subject'))} to {_people(d.get('to'))}"
        return f"send draft {a.get('draft_id')}"
    if tool == "pim.mail_create_draft":
        return f"draft an email to {_people(a.get('to'))} about {_quote(a.get('subject'))}"
    if tool == "pim.reminders_create":
        return f"set a reminder {_quote(a.get('title'))}" + (f" for {when}" if when else ", with no due date")
    if tool == "pim.reminders_complete":
        return "mark that reminder as done"
    if tool == "pim.notes_create":
        return f"create a note {_quote(a.get('title'))}"
    if tool == "fs.fs_list_dir":
        return f"look in the folder {a.get('path') or 'scratch'}"
    if tool == "fs.fs_read_file":
        return f"read the file {a.get('path')}"
    if tool == "fs.fs_write_file":
        return f"write the file {a.get('path')}"
    if tool == "fs.fs_delete_file":
        return f"delete the file {a.get('path')}"
    return f"run {tool.split('.', 1)[-1].replace('_', ' ')}"


async def preview(tool: str, args: dict, outcome: str, lookup: Lookup | None = None,
                  now: dt.datetime | None = None) -> dict:
    """{"action": verb phrase, "dateWarnings": [...], "spoken": the question}."""
    now = now or dt.datetime.now()
    action = await describe(tool, args, lookup, now)
    warnings = date_warnings(outcome, args, now)
    lead = "".join(f"Careful: {w}. " for w in warnings)
    return {
        "action": action,
        "dateWarnings": warnings,
        "spoken": f"{lead}I'm about to {action}. Shall I go ahead?",
    }
