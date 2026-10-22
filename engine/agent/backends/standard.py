"""`AccountsPimBackend` — the user's real accounts over standard protocols.

    mail      IMAP + SMTP            (`mail.ImapMail`, stdlib only)
    calendar  CalDAV                 (`dav.CalDav`)
    contacts  CardDAV, plus the people in the user's own mail
    reminders + notes  WELLSY's local store on this machine

Reminders and notes stay local on purpose: there is no standard protocol every
provider exposes for them (iCloud moved Reminders off CalDAV, Google Keep has
none), and a local JSON file costs nothing on any OS.

A service that isn't connected raises `ToolError(code="not_connected")` with
the reason, so the agent says "your calendar isn't connected" instead of
"you have nothing on today" (INVARIANTS #6 / #15).
"""

from __future__ import annotations

from pathlib import Path

from engine.agent.backends.accounts import Accounts, config_path, load_accounts, provider_for
from engine.agent.backends.base import Contact, ToolError
from engine.agent.backends.portable import PortablePimBackend


def _empty() -> dict:
    return {"events": [], "reminders": [], "notes": [], "contacts": [], "messages": [], "sent": [], "drafts": []}


class AccountsPimBackend:
    def __init__(self, accounts: Accounts | None = None, *, local_path: Path | None = None) -> None:
        self.accounts = accounts or load_accounts()
        a = self.accounts
        self._mail = self._cal = self._card = None
        if a.mail:
            from engine.agent.backends.mail import ImapMail

            self._mail = ImapMail(a.mail)
        if a.calendar:
            from engine.agent.backends.dav import CalDav

            self._cal = CalDav(a.calendar)
        if a.contacts:
            from engine.agent.backends.dav import CardDav

            self._card = CardDav(a.contacts)
        self._local = PortablePimBackend(path=local_path or config_path().with_name("local_store.json"), seed=_empty)

    # --- routing ------------------------------------------------------------
    def _need(self, svc, what: str):
        if svc is not None:
            return svc
        why = ""
        if what == "calendar" and self.accounts.mail:
            _, p, _ = provider_for(self.accounts.mail.address)
            why = f" ({p['dav_note']})" if p and p.get("dav_note") else ""
        raise ToolError(f"your {what} isn't connected{why}; run `wellsy accounts add`", code="not_connected")

    @property
    def mail(self):
        return self._need(self._mail, "mail")

    @property
    def cal(self):
        return self._need(self._cal, "calendar")

    # --- calendar ---------------------------------------------------------
    def list_events(self, start, end):
        return self.cal.list_events(start, end)

    def get_event(self, event_id):
        return self.cal.get_event(event_id)

    def create_event(self, title, start, end, *, calendar="Home", location=None, notes=None):
        return self.cal.create_event(title, start, end, calendar=calendar, location=location, notes=notes)

    def move_event(self, event_id, new_start, new_end):
        return self.cal.move_event(event_id, new_start, new_end)

    # --- reminders + notes: local -----------------------------------------
    def list_reminders(self, *, list_name=None, include_completed=False):
        return self._local.list_reminders(list_name=list_name, include_completed=include_completed)

    def create_reminder(self, title, *, list_name="Reminders", due=None):
        return self._local.create_reminder(title, list_name=list_name, due=due)

    def complete_reminder(self, reminder_id):
        return self._local.complete_reminder(reminder_id)

    def list_notes(self, *, folder=None):
        return self._local.list_notes(folder=folder)

    def get_note(self, note_id):
        return self._local.get_note(note_id)

    def create_note(self, title, body, *, folder="Notes"):
        return self._local.create_note(title, body, folder=folder)

    # --- mail ---------------------------------------------------------------
    def list_messages(self, *, mailbox="INBOX", limit=20):
        return self.mail.list_messages(mailbox=mailbox, limit=limit)

    def get_message(self, message_id):
        return self.mail.get_message(message_id)

    def list_sent(self, *, limit=20):
        return self.mail.list_sent(limit=limit)

    def create_draft(self, to, subject, body, *, in_reply_to=None):
        return self.mail.create_draft(to, subject, body, in_reply_to=in_reply_to)

    def get_draft(self, draft_id):
        return self.mail.get_draft(draft_id)

    def send_draft(self, draft_id):
        return self.mail.send_draft(draft_id)

    # --- contacts: address book first, then the people in the user's mail ---
    def search_contacts(self, query: str) -> list[Contact]:
        if self._card is None and self._mail is None:
            self._need(None, "contacts")
        out: list[Contact] = []
        seen: set[str] = set()
        errors = []
        for source in (self._card.search if self._card else None,
                       self._mail.correspondents if self._mail else None):
            if source is None:
                continue
            try:
                for c in source(query):
                    key = (c.emails[0] if c.emails else c.name).lower()
                    if key not in seen:
                        seen.add(key)
                        out.append(c)
            except ToolError as e:
                errors.append(e)
        if not out and errors:
            raise errors[0]
        return out[:10]

    def get_contact(self, contact_id: str) -> Contact:
        if contact_id.startswith("mail:"):
            addr = contact_id[5:]
            hits = [c for c in self.search_contacts(addr) if addr in c.emails]
            if hits:
                return hits[0]
            raise ToolError(f"no contact {contact_id!r}", code="not_found")
        if self._card is None:
            raise ToolError(f"no contact {contact_id!r}", code="not_found")
        return self._card.get(contact_id)

    def known_names(self, limit: int = 40) -> list[str]:
        """The user's own people, for speech-recognition hotwords: whom they
        mail most, then their address book. Empty when nothing is connected;
        never a hardcoded list."""
        names: list[str] = []
        for source in (self._mail.frequent_names if self._mail else None,
                       self._card.names if self._card else None):
            if source is None:
                continue
            try:
                names += [n for n in source() if n not in names]
            except ToolError:
                continue
        return names[:limit]
