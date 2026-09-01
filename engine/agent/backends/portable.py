"""Portable PIM backend — a JSON store under `runs/agent/`.

This is the default backend and the only one the acceptance tests touch. It is
a real store (writes persist, reads reflect writes, `send_draft` actually moves
a message into Sent), just not a real *account* — so A4's "the event actually
moves, verified by read-back" and A5's "the sent-items folder must be
unchanged" are checkable deterministically, on any platform, with no
credentials.

Seeded from `_seed()` on first use. Delete `runs/agent/pim_store.json` (or call
`PortablePimBackend(reset=True)`) to reseed. Times in the seed are relative to
`date.today()` so "what's on my calendar tomorrow?" always has an answer.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from engine.agent.backends.base import (
    Contact,
    Draft,
    Event,
    MailMessage,
    Note,
    Reminder,
    ToolError,
)

def _store_path() -> Path:
    override = os.environ.get("WELLSY_PIM_STORE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "runs" / "agent" / "pim_store.json"


STORE_PATH = _store_path()
STORE_DIR = STORE_PATH.parent


def _iso(d: datetime) -> str:
    return d.replace(microsecond=0).astimezone().isoformat()


def _seed() -> dict:
    today = date.today()

    def at(day_offset: int, hour: int, minute: int = 0) -> datetime:
        return datetime.combine(today + timedelta(days=day_offset), datetime.min.time()).replace(
            hour=hour, minute=minute
        )

    return {
        "events": [
            Event("evt-standup", "Team standup", _iso(at(1, 9, 30)), _iso(at(1, 10, 0)),
                  calendar="Work").to_dict(),
            Event("evt-review", "Design review", _iso(at(1, 15, 0)), _iso(at(1, 16, 0)),
                  calendar="Work", location="Zoom",
                  notes="Walk through the agent-runtime policy gate.").to_dict(),
            Event("evt-1on1", "1:1 with Priya", _iso(at(1, 16, 30)), _iso(at(1, 17, 0)),
                  calendar="Work").to_dict(),
            Event("evt-dentist", "Dentist", _iso(at(3, 11, 0)), _iso(at(3, 12, 0)),
                  calendar="Home").to_dict(),
            Event("evt-today-lunch", "Lunch with Sam", _iso(at(0, 12, 30)), _iso(at(0, 13, 30)),
                  calendar="Home").to_dict(),
        ],
        "reminders": [
            Reminder("rem-pentest", "Send pentest authorization letter", due=_iso(at(1, 12, 0))).to_dict(),
            Reminder("rem-groceries", "Buy groceries", list_name="Home").to_dict(),
        ],
        "notes": [
            Note("note-review-prep", "Design review prep",
                 "Points for the design review:\n- policy gate fails closed\n"
                 "- audit line written before the action returns\n- read-back verification").to_dict(),
        ],
        "contacts": [
            Contact("con-priya", "Priya Nair", emails=["priya@example.com"],
                    phones=["+1-555-0101"], organization="Wellsy").to_dict(),
            Contact("con-sam", "Sam Osei", emails=["sam.osei@example.com"],
                    organization="Wellsy").to_dict(),
            Contact("con-dana", "Dana Kim", emails=["dana.kim@partner.example"],
                    organization="Partner Co").to_dict(),
        ],
        "messages": [
            MailMessage("msg-dana-1", "INBOX", "Dana Kim <dana.kim@partner.example>",
                        ["me@example.com"], "Re: integration timeline",
                        "Can we push the integration review to next week? "
                        "Thursday works better on our side.\n\nThanks,\nDana",
                        _iso(at(-1, 14, 0))).to_dict(),
            MailMessage("msg-priya-1", "INBOX", "Priya Nair <priya@example.com>",
                        ["me@example.com"], "standup notes",
                        "Shared the standup notes in the doc. Nothing blocking.",
                        _iso(at(-1, 9, 45))).to_dict(),
        ],
        "sent": [
            MailMessage("msg-sent-old", "Sent", "me@example.com",
                        ["priya@example.com"], "Re: standup notes",
                        "Thanks Priya, looks good.", _iso(at(-2, 10, 0)), sent=True).to_dict(),
        ],
        "drafts": [],
    }


class PortablePimBackend:
    def __init__(self, *, reset: bool = False) -> None:
        self._lock = threading.RLock()
        self._path = _store_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if reset or os.environ.get("WELLSY_PIM_RESET") == "1" or not self._path.exists():
            self._write(_seed())

    # --- store io -------------------------------------------------------------
    def _read(self) -> dict:
        with self._lock:
            try:
                return json.loads(self._path.read_text())
            except FileNotFoundError:
                data = _seed()
                self._write(data)
                return data

    def _write(self, data: dict) -> None:
        with self._lock:
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2))
            tmp.replace(self._path)

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:10]}"

    # --- calendar ----------------------------------------------------------
    def list_events(self, start: str, end: str) -> list[Event]:
        s, e = _parse(start), _parse(end)
        out = []
        for row in self._read()["events"]:
            est = _parse(row["start"])
            if s <= est < e:
                out.append(Event(**row))
        return sorted(out, key=lambda ev: ev.start)

    def get_event(self, event_id: str) -> Event:
        for row in self._read()["events"]:
            if row["id"] == event_id:
                return Event(**row)
        raise ToolError(f"no event {event_id!r}", code="not_found")

    def create_event(self, title, start, end, *, calendar="Home", location=None, notes=None) -> Event:
        data = self._read()
        ev = Event(self._new_id("evt"), title, _norm(start), _norm(end), calendar, location, notes)
        data["events"].append(ev.to_dict())
        self._write(data)
        return ev

    def move_event(self, event_id: str, new_start: str, new_end: str) -> Event:
        data = self._read()
        for row in data["events"]:
            if row["id"] == event_id:
                row["start"], row["end"] = _norm(new_start), _norm(new_end)
                self._write(data)
                return Event(**row)
        raise ToolError(f"no event {event_id!r}", code="not_found")

    # --- reminders ----------------------------------------------------------
    def list_reminders(self, *, list_name=None, include_completed=False) -> list[Reminder]:
        out = []
        for row in self._read()["reminders"]:
            if list_name and row["list_name"] != list_name:
                continue
            if row["completed"] and not include_completed:
                continue
            out.append(Reminder(**row))
        return out

    def create_reminder(self, title, *, list_name="Reminders", due=None) -> Reminder:
        data = self._read()
        rem = Reminder(self._new_id("rem"), title, list_name, _norm(due) if due else None, False)
        data["reminders"].append(rem.to_dict())
        self._write(data)
        return rem

    def complete_reminder(self, reminder_id: str) -> Reminder:
        data = self._read()
        for row in data["reminders"]:
            if row["id"] == reminder_id:
                row["completed"] = True
                self._write(data)
                return Reminder(**row)
        raise ToolError(f"no reminder {reminder_id!r}", code="not_found")

    # --- mail -------------------------------------------------------------
    def list_messages(self, *, mailbox="INBOX", limit=20) -> list[MailMessage]:
        rows = [MailMessage(**r) for r in self._read()["messages"] if r["mailbox"] == mailbox]
        return sorted(rows, key=lambda m: m.date, reverse=True)[:limit]

    def get_message(self, message_id: str) -> MailMessage:
        for r in self._read()["messages"] + self._read()["sent"]:
            if r["id"] == message_id:
                return MailMessage(**r)
        raise ToolError(f"no message {message_id!r}", code="not_found")

    def list_sent(self, *, limit=20) -> list[MailMessage]:
        rows = [MailMessage(**r) for r in self._read()["sent"]]
        return sorted(rows, key=lambda m: m.date, reverse=True)[:limit]

    def create_draft(self, to, subject, body, *, in_reply_to=None) -> Draft:
        data = self._read()
        draft = Draft(self._new_id("draft"), list(to), subject, body, in_reply_to, False)
        data["drafts"].append(draft.to_dict())
        self._write(data)
        return draft

    def get_draft(self, draft_id: str) -> Draft:
        for r in self._read()["drafts"]:
            if r["id"] == draft_id:
                return Draft(**r)
        raise ToolError(f"no draft {draft_id!r}", code="not_found")

    def send_draft(self, draft_id: str) -> MailMessage:
        data = self._read()
        for r in data["drafts"]:
            if r["id"] == draft_id:
                if r["sent"]:
                    raise ToolError(f"draft {draft_id!r} already sent", code="already_sent")
                r["sent"] = True
                msg = MailMessage(
                    self._new_id("msg-sent"), "Sent", "me@example.com", list(r["to"]),
                    r["subject"], r["body"], _iso(datetime.now()), sent=True,
                )
                data["sent"].append(msg.to_dict())
                self._write(data)
                return msg
        raise ToolError(f"no draft {draft_id!r}", code="not_found")

    # --- notes -----------------------------------------------------------
    def list_notes(self, *, folder=None) -> list[Note]:
        return [Note(**r) for r in self._read()["notes"] if not folder or r["folder"] == folder]

    def get_note(self, note_id: str) -> Note:
        for r in self._read()["notes"]:
            if r["id"] == note_id:
                return Note(**r)
        raise ToolError(f"no note {note_id!r}", code="not_found")

    def create_note(self, title, body, *, folder="Notes") -> Note:
        data = self._read()
        note = Note(self._new_id("note"), title, body, folder)
        data["notes"].append(note.to_dict())
        self._write(data)
        return note

    # --- contacts ---------------------------------------------------------
    def search_contacts(self, query: str) -> list[Contact]:
        q = query.lower().strip()
        out = []
        for r in self._read()["contacts"]:
            hay = " ".join([r["name"], *(r["emails"]), r.get("organization") or ""]).lower()
            if q in hay:
                out.append(Contact(**r))
        return out

    def get_contact(self, contact_id: str) -> Contact:
        for r in self._read()["contacts"]:
            if r["id"] == contact_id:
                return Contact(**r)
        raise ToolError(f"no contact {contact_id!r}", code="not_found")


def _parse(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def _norm(s: str) -> str:
    return _parse(s).replace(microsecond=0).isoformat()
