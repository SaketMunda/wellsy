"""`pim` MCP server — Calendar, Reminders, Mail, Notes, Contacts.

Thin: every tool validates its args, calls one `PimBackend` method, and
returns plain JSON-able data. No policy logic here — the `PolicyGate` sits
between the agent and this server. No model logic. The backend
(`WELLSY_PIM_BACKEND`) decides whether this talks to macOS or the portable
store.

Tool names are the policy-sidecar keys' second half: `pim.calendar_move_event`
etc. Risk annotations live in `engine/agent/policy.yaml`, never in this file
(step 5 Deliverable 2 — auditable and diffable, not in code).
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from engine.agent.backends import ToolError, get_pim_backend
from engine.agent.servers._break import breakable

mcp = FastMCP("pim")


def _b():
    return get_pim_backend()


def _guard(fn):
    """Turn a backend `ToolError` into a clean MCP error string the agent's
    verify step and the audit log can read, instead of a raw traceback."""

    import functools

    @functools.wraps(fn)
    def w(*a, **k):
        try:
            return fn(*a, **k)
        except ToolError as e:
            raise RuntimeError(f"{e.code}: {e}") from None

    return w


# --- calendar ----------------------------------------------------------------
@mcp.tool()
@_guard
@breakable("calendar_list_events")
def calendar_list_events(start: str, end: str) -> list[dict]:
    """List calendar events with start time in [start, end). ISO-8601 datetimes,
    local timezone assumed if no offset given."""
    return [e.to_dict() for e in _b().list_events(start, end)]


@mcp.tool()
@_guard
@breakable("calendar_get_event")
def calendar_get_event(event_id: str) -> dict:
    """Fetch one event by id. Used for read-back verification after a move."""
    return _b().get_event(event_id).to_dict()


@mcp.tool()
@_guard
@breakable("calendar_create_event")
def calendar_create_event(
    title: str, start: str, end: str, calendar: str = "Home",
    location: str | None = None, notes: str | None = None,
) -> dict:
    """Create a calendar event. Risk 2 — a real mutation."""
    return _b().create_event(title, start, end, calendar=calendar, location=location, notes=notes).to_dict()


@mcp.tool()
@_guard
@breakable("calendar_move_event")
def calendar_move_event(event_id: str, new_start: str, new_end: str) -> dict:
    """Move an existing event to a new start/end. Risk 2 — reversible mutation."""
    return _b().move_event(event_id, new_start, new_end).to_dict()


# --- reminders -------------------------------------------------------------------
@mcp.tool()
@_guard
@breakable("reminders_list")
def reminders_list(list_name: str | None = None, include_completed: bool = False) -> list[dict]:
    """List reminders, optionally from one list."""
    return [r.to_dict() for r in _b().list_reminders(list_name=list_name, include_completed=include_completed)]


@mcp.tool()
@_guard
@breakable("reminders_create")
def reminders_create(title: str, list_name: str = "Reminders", due: str | None = None) -> dict:
    """Create a reminder. Risk 1 — reversible, low-consequence."""
    return _b().create_reminder(title, list_name=list_name, due=due).to_dict()


@mcp.tool()
@_guard
@breakable("reminders_complete")
def reminders_complete(reminder_id: str) -> dict:
    """Mark a reminder complete. Risk 1 — reversible."""
    return _b().complete_reminder(reminder_id).to_dict()


# --- mail --------------------------------------------------------------------
@mcp.tool()
@_guard
@breakable("mail_list_messages")
def mail_list_messages(mailbox: str = "INBOX", limit: int = 20) -> list[dict]:
    """List messages in a mailbox, newest first."""
    return [m.to_dict() for m in _b().list_messages(mailbox=mailbox, limit=limit)]


@mcp.tool()
@_guard
@breakable("mail_get_message")
def mail_get_message(message_id: str) -> dict:
    """Fetch one message, including body."""
    return _b().get_message(message_id).to_dict()


@mcp.tool()
@_guard
@breakable("mail_list_sent")
def mail_list_sent(limit: int = 20) -> list[dict]:
    """List sent messages. The read-back for A5/A6: proves nothing was sent."""
    return [m.to_dict() for m in _b().list_sent(limit=limit)]


@mcp.tool()
@_guard
@breakable("mail_create_draft")
def mail_create_draft(to: list[str], subject: str, body: str, in_reply_to: str | None = None) -> dict:
    """Create a mail draft. Risk 1 — a draft is NOT a send. Nothing leaves the machine."""
    return _b().create_draft(to, subject, body, in_reply_to=in_reply_to).to_dict()


@mcp.tool()
@_guard
@breakable("mail_get_draft")
def mail_get_draft(draft_id: str) -> dict:
    """Fetch a draft by id."""
    return _b().get_draft(draft_id).to_dict()


@mcp.tool()
@_guard
@breakable("mail_send_draft")
def mail_send_draft(draft_id: str) -> dict:
    """Send a previously created draft. Risk 2 — content leaves the machine.
    Always gated until the audit log shows a clean run of this action class."""
    return _b().send_draft(draft_id).to_dict()


# --- notes -----------------------------------------------------------------------
@mcp.tool()
@_guard
@breakable("notes_list")
def notes_list(folder: str | None = None) -> list[dict]:
    """List notes, optionally in one folder."""
    return [n.to_dict() for n in _b().list_notes(folder=folder)]


@mcp.tool()
@_guard
@breakable("notes_get")
def notes_get(note_id: str) -> dict:
    """Fetch one note by id."""
    return _b().get_note(note_id).to_dict()


@mcp.tool()
@_guard
@breakable("notes_create")
def notes_create(title: str, body: str, folder: str = "Notes") -> dict:
    """Create a note. Risk 1 — reversible."""
    return _b().create_note(title, body, folder=folder).to_dict()


# --- contacts -------------------------------------------------------------------
@mcp.tool()
@_guard
@breakable("contacts_search")
def contacts_search(query: str) -> list[dict]:
    """Search contacts by name, email or organization substring."""
    return [c.to_dict() for c in _b().search_contacts(query)]


@mcp.tool()
@_guard
@breakable("contacts_get")
def contacts_get(contact_id: str) -> dict:
    """Fetch one contact by id."""
    return _b().get_contact(contact_id).to_dict()


# --- an intentionally unannotated tool ----------------------------------------
# Present so the acceptance suite can prove INVARIANTS #9: a tool with NO entry
# in policy.yaml is treated as risk 3 and fails closed. Do not annotate it.
@mcp.tool()
@_guard
def debug_echo(payload: Any) -> Any:
    """Unannotated on purpose (acceptance item 7). Echoes its input."""
    return {"echo": payload}


if __name__ == "__main__":  # pragma: no cover
    mcp.run("stdio")
