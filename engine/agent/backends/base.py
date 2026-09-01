"""The `PimBackend` protocol and its plain data types.

Every method raises `ToolError` on a real failure (not-found, permission
denied, backend unreachable). It never returns a fabricated success and never
returns a plausible-looking empty result to paper over an error — INVARIANTS #6
and #15. The MCP server turns a `ToolError` into an MCP tool error the policy
gate and audit log both see.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol, runtime_checkable


class ToolError(RuntimeError):
    """A backend operation genuinely failed. Carries a machine-readable
    `code` so `servers/pim.py` and the audit log can classify it."""

    def __init__(self, message: str, *, code: str = "backend_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Event:
    id: str
    title: str
    start: str  # ISO 8601 with offset, local timezone
    end: str
    calendar: str = "Home"
    location: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Reminder:
    id: str
    title: str
    list_name: str = "Reminders"
    due: str | None = None
    completed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Note:
    id: str
    title: str
    body: str
    folder: str = "Notes"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Contact:
    id: str
    name: str
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    organization: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MailMessage:
    id: str
    mailbox: str
    sender: str
    recipients: list[str]
    subject: str
    body: str
    date: str
    sent: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Draft:
    id: str
    to: list[str]
    subject: str
    body: str
    in_reply_to: str | None = None
    sent: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@runtime_checkable
class PimBackend(Protocol):
    """The whole platform seam. `servers/pim.py` imports nothing else."""

    # --- calendar ---------------------------------------------------------
    def list_events(self, start: str, end: str) -> list[Event]: ...
    def get_event(self, event_id: str) -> Event: ...
    def create_event(
        self, title: str, start: str, end: str, *, calendar: str = "Home",
        location: str | None = None, notes: str | None = None,
    ) -> Event: ...
    def move_event(self, event_id: str, new_start: str, new_end: str) -> Event: ...

    # --- reminders ------------------------------------------------------------
    def list_reminders(self, *, list_name: str | None = None, include_completed: bool = False) -> list[Reminder]: ...
    def create_reminder(self, title: str, *, list_name: str = "Reminders", due: str | None = None) -> Reminder: ...
    def complete_reminder(self, reminder_id: str) -> Reminder: ...

    # --- mail --------------------------------------------------------------
    def list_messages(self, *, mailbox: str = "INBOX", limit: int = 20) -> list[MailMessage]: ...
    def get_message(self, message_id: str) -> MailMessage: ...
    def list_sent(self, *, limit: int = 20) -> list[MailMessage]: ...
    def create_draft(
        self, to: list[str], subject: str, body: str, *, in_reply_to: str | None = None,
    ) -> Draft: ...
    def get_draft(self, draft_id: str) -> Draft: ...
    def send_draft(self, draft_id: str) -> MailMessage: ...

    # --- notes -----------------------------------------------------------
    def list_notes(self, *, folder: str | None = None) -> list[Note]: ...
    def get_note(self, note_id: str) -> Note: ...
    def create_note(self, title: str, body: str, *, folder: str = "Notes") -> Note: ...

    # --- contacts ------------------------------------------------------------
    def search_contacts(self, query: str) -> list[Contact]: ...
    def get_contact(self, contact_id: str) -> Contact: ...
