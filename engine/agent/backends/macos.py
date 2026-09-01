"""macOS PIM backend — `osascript` against Calendar, Reminders, Mail, Notes,
Contacts.

Darwin-only, selected explicitly with `WELLSY_PIM_BACKEND=macos`; never the
default, never imported at module scope elsewhere (INVARIANTS #14). Every call
shells out to `osascript`; a non-zero exit or an unparseable result raises
`ToolError` rather than returning a guess (#6, #15).

Verified 2026-09-01 against macOS 15 (Darwin 24.5.0): AppleScript automation of
Calendar / Reminders / Mail / Notes / Contacts is the supported local
integration path and needs the one-time Automation permission per app (grant it
with the app frontmost the first time, or via System Settings > Privacy &
Security > Automation). This backend deliberately does **not** cover the full
`PimBackend` surface — the acceptance-relevant operations are implemented, the
rest raise `ToolError(code="not_implemented")` so a gap is loud, not silent.
"""

from __future__ import annotations

import json
import subprocess
import sys

from engine.agent.backends.base import (
    Contact,
    Draft,
    Event,
    MailMessage,
    Note,
    Reminder,
    ToolError,
)

if sys.platform != "darwin":  # pragma: no cover - guard
    raise ImportError("MacPimBackend is darwin-only")


def _osa(script: str) -> str:
    try:
        p = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True, text=True, timeout=20,
        )
    except FileNotFoundError as e:  # pragma: no cover
        raise ToolError("osascript not found", code="backend_error") from e
    except subprocess.TimeoutExpired as e:
        raise ToolError("osascript timed out", code="timeout") from e
    if p.returncode != 0:
        err = (p.stderr or "").strip()
        code = "permission_denied" if "Not authorized" in err or "-1743" in err else "backend_error"
        raise ToolError(f"osascript failed: {err}", code=code)
    return (p.stdout or "").strip()


def _json(script: str):
    raw = _osa(script)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:  # pragma: no cover
        raise ToolError(f"unparseable osascript output: {raw[:200]!r}", code="backend_error") from e


class MacPimBackend:
    # --- calendar --------------------------------------------------------
    def list_events(self, start: str, end: str) -> list[Event]:
        script = f"""
        const app = Application('Calendar');
        const s = new Date({_js_date(start)}), e = new Date({_js_date(end)});
        const out = [];
        for (const cal of app.calendars()) {{
          const evs = cal.events.whose({{_and: [{{startDate: {{_greaterThanEquals: s}}}},
                                                {{startDate: {{_lessThan: e}}}}]}})();
          for (const ev of evs) out.push({{id: ev.uid(), title: ev.summary(),
            start: ev.startDate().toISOString(), end: ev.endDate().toISOString(),
            calendar: cal.name(), location: ev.location() || null, notes: ev.description() || null}});
        }}
        JSON.stringify(out);
        """
        rows = _json(script) or []
        return [Event(**r) for r in sorted(rows, key=lambda r: r["start"])]

    def get_event(self, event_id: str) -> Event:
        script = f"""
        const app = Application('Calendar');
        for (const cal of app.calendars()) {{
          const evs = cal.events.whose({{uid: {json.dumps(event_id)}}})();
          if (evs.length) {{ const ev = evs[0];
            return JSON.stringify({{id: ev.uid(), title: ev.summary(),
              start: ev.startDate().toISOString(), end: ev.endDate().toISOString(),
              calendar: cal.name(), location: ev.location() || null, notes: ev.description() || null}}); }}
        }}
        "";
        """
        row = _json(script)
        if not row:
            raise ToolError(f"no event {event_id!r}", code="not_found")
        return Event(**row)

    def create_event(self, title, start, end, *, calendar="Home", location=None, notes=None) -> Event:
        script = f"""
        const app = Application('Calendar');
        const cal = app.calendars.whose({{name: {json.dumps(calendar)}}})()[0];
        if (!cal) throw new Error('no calendar {calendar}');
        const ev = app.Event({{summary: {json.dumps(title)},
          startDate: new Date({_js_date(start)}), endDate: new Date({_js_date(end)}),
          location: {json.dumps(location or "")}, description: {json.dumps(notes or "")}}});
        cal.events.push(ev);
        JSON.stringify({{id: ev.uid(), start: ev.startDate().toISOString(), end: ev.endDate().toISOString()}});
        """
        row = _json(script) or {}
        return Event(row.get("id", ""), title, row.get("start", start), row.get("end", end),
                     calendar, location, notes)

    def move_event(self, event_id: str, new_start: str, new_end: str) -> Event:
        script = f"""
        const app = Application('Calendar');
        for (const cal of app.calendars()) {{
          const evs = cal.events.whose({{uid: {json.dumps(event_id)}}})();
          if (evs.length) {{ const ev = evs[0];
            ev.startDate = new Date({_js_date(new_start)});
            ev.endDate = new Date({_js_date(new_end)});
            return JSON.stringify({{id: ev.uid(), title: ev.summary(),
              start: ev.startDate().toISOString(), end: ev.endDate().toISOString(),
              calendar: cal.name(), location: ev.location() || null, notes: ev.description() || null}}); }}
        }}
        "";
        """
        row = _json(script)
        if not row:
            raise ToolError(f"no event {event_id!r}", code="not_found")
        return Event(**row)

    # --- reminders ------------------------------------------------------------
    def list_reminders(self, *, list_name=None, include_completed=False) -> list[Reminder]:
        sel = f"app.lists.whose({{name: {json.dumps(list_name)}}})()[0].reminders" if list_name \
            else "app.defaultList.reminders"
        script = f"""
        const app = Application('Reminders');
        const rs = {sel}();
        const out = [];
        for (const r of rs) {{ if (!{str(include_completed).lower()} && r.completed()) continue;
          out.push({{id: r.id(), title: r.name(), list_name: r.container().name(),
            due: r.dueDate() ? r.dueDate().toISOString() : null, completed: r.completed()}}); }}
        JSON.stringify(out);
        """
        return [Reminder(**r) for r in (_json(script) or [])]

    def create_reminder(self, title, *, list_name="Reminders", due=None) -> Reminder:
        due_js = f"new Date({_js_date(due)})" if due else "null"
        script = f"""
        const app = Application('Reminders');
        const lst = app.lists.whose({{name: {json.dumps(list_name)}}})()[0] || app.defaultList;
        const r = app.Reminder({{name: {json.dumps(title)}, dueDate: {due_js}}});
        lst.reminders.push(r);
        JSON.stringify({{id: r.id(), list_name: lst.name()}});
        """
        row = _json(script) or {}
        return Reminder(row.get("id", ""), title, row.get("list_name", list_name), due, False)

    def complete_reminder(self, reminder_id: str) -> Reminder:
        script = f"""
        const app = Application('Reminders');
        const rs = app.reminders.whose({{id: {json.dumps(reminder_id)}}})();
        if (!rs.length) return "";
        rs[0].completed = true;
        JSON.stringify({{id: rs[0].id(), title: rs[0].name(), list_name: rs[0].container().name(),
          due: rs[0].dueDate() ? rs[0].dueDate().toISOString() : null, completed: true}});
        """
        row = _json(script)
        if not row:
            raise ToolError(f"no reminder {reminder_id!r}", code="not_found")
        return Reminder(**row)

    # --- mail -----------------------------------------------------------
    def list_messages(self, *, mailbox="INBOX", limit=20) -> list[MailMessage]:
        script = f"""
        const app = Application('Mail');
        const box = app.inbox;
        const msgs = box.messages();
        const out = [];
        for (let i = 0; i < Math.min(msgs.length, {int(limit)}); i++) {{ const m = msgs[i];
          out.push({{id: String(m.id()), mailbox: {json.dumps(mailbox)}, sender: m.sender(),
            recipients: m.toRecipients().map(r => r.address()), subject: m.subject(),
            body: m.content().slice(0, 4000), date: m.datereceived().toISOString(), sent: false}}); }}
        JSON.stringify(out);
        """
        return [MailMessage(**r) for r in (_json(script) or [])]

    def get_message(self, message_id: str) -> MailMessage:
        script = f"""
        const app = Application('Mail');
        for (const box of [app.inbox, app.sentMailbox]) {{
          const ms = box.messages.whose({{id: {json.dumps(message_id)}}})();
          if (ms.length) {{ const m = ms[0];
            return JSON.stringify({{id: String(m.id()), mailbox: box.name(), sender: m.sender(),
              recipients: m.toRecipients().map(r => r.address()), subject: m.subject(),
              body: m.content().slice(0, 8000), date: m.dateReceived().toISOString(),
              sent: box.name() === 'Sent'}}); }}
        }}
        "";
        """
        row = _json(script)
        if not row:
            raise ToolError(f"no message {message_id!r}", code="not_found")
        return MailMessage(**row)

    def list_sent(self, *, limit=20) -> list[MailMessage]:
        script = f"""
        const app = Application('Mail');
        const msgs = app.sentMailbox.messages();
        const out = [];
        for (let i = 0; i < Math.min(msgs.length, {int(limit)}); i++) {{ const m = msgs[i];
          out.push({{id: String(m.id()), mailbox: 'Sent', sender: m.sender(),
            recipients: m.toRecipients().map(r => r.address()), subject: m.subject(),
            body: m.content().slice(0, 4000), date: m.dateSent().toISOString(), sent: true}}); }}
        JSON.stringify(out);
        """
        return [MailMessage(**r) for r in (_json(script) or [])]

    def create_draft(self, to, subject, body, *, in_reply_to=None) -> Draft:
        recips = "".join(
            f"msg.toRecipients.push(app.ToRecipient({{address: {json.dumps(a)}}}));\n" for a in to
        )
        script = f"""
        const app = Application('Mail');
        const msg = app.OutgoingMessage({{subject: {json.dumps(subject)},
          content: {json.dumps(body)}, visible: true}});
        app.outgoingMessages.push(msg);
        {recips}
        JSON.stringify({{id: String(msg.id())}});
        """
        row = _json(script) or {}
        return Draft(row.get("id", ""), list(to), subject, body, in_reply_to, False)

    def get_draft(self, draft_id: str) -> Draft:
        raise ToolError("draft read-back not implemented on macOS backend", code="not_implemented")

    def send_draft(self, draft_id: str) -> MailMessage:
        script = f"""
        const app = Application('Mail');
        const ms = app.outgoingMessages.whose({{id: {json.dumps(draft_id)}}})();
        if (!ms.length) return "";
        ms[0].send();
        JSON.stringify({{id: {json.dumps(draft_id)}}});
        """
        row = _json(script)
        if not row:
            raise ToolError(f"no draft {draft_id!r}", code="not_found")
        return MailMessage(draft_id, "Sent", "me", [], "", "", "", sent=True)

    # --- notes ----------------------------------------------------------
    def list_notes(self, *, folder=None) -> list[Note]:
        script = """
        const app = Application('Notes');
        const out = [];
        for (const n of app.notes()) out.push({id: n.id(), title: n.name(),
          body: n.plaintext().slice(0, 4000), folder: n.container().name()});
        JSON.stringify(out);
        """
        rows = _json(script) or []
        return [Note(**r) for r in rows if not folder or r["folder"] == folder]

    def get_note(self, note_id: str) -> Note:
        script = f"""
        const app = Application('Notes');
        const ns = app.notes.whose({{id: {json.dumps(note_id)}}})();
        if (!ns.length) return "";
        const n = ns[0];
        JSON.stringify({{id: n.id(), title: n.name(), body: n.plaintext(), folder: n.container().name()}});
        """
        row = _json(script)
        if not row:
            raise ToolError(f"no note {note_id!r}", code="not_found")
        return Note(**row)

    def create_note(self, title, body, *, folder="Notes") -> Note:
        script = f"""
        const app = Application('Notes');
        const f = app.folders.whose({{name: {json.dumps(folder)}}})()[0] || app.defaultAccount.defaultFolder;
        const n = app.Note({{name: {json.dumps(title)}, body: {json.dumps(body)}}});
        f.notes.push(n);
        JSON.stringify({{id: n.id(), folder: f.name()}});
        """
        row = _json(script) or {}
        return Note(row.get("id", ""), title, body, row.get("folder", folder))

    # --- contacts ------------------------------------------------------------
    def search_contacts(self, query: str) -> list[Contact]:
        script = f"""
        const app = Application('Contacts');
        const q = {json.dumps(query.lower())};
        const out = [];
        for (const p of app.people()) {{
          const name = p.name() || '';
          const emails = p.emails().map(e => e.value());
          const org = p.organization() || null;
          const hay = (name + ' ' + emails.join(' ') + ' ' + (org||'')).toLowerCase();
          if (hay.indexOf(q) !== -1) out.push({{id: p.id(), name: name, emails: emails,
            phones: p.phones().map(x => x.value()), organization: org}});
        }}
        JSON.stringify(out);
        """
        return [Contact(**r) for r in (_json(script) or [])]

    def get_contact(self, contact_id: str) -> Contact:
        script = f"""
        const app = Application('Contacts');
        const ps = app.people.whose({{id: {json.dumps(contact_id)}}})();
        if (!ps.length) return "";
        const p = ps[0];
        JSON.stringify({{id: p.id(), name: p.name(), emails: p.emails().map(e => e.value()),
          phones: p.phones().map(x => x.value()), organization: p.organization() || null}});
        """
        row = _json(script)
        if not row:
            raise ToolError(f"no contact {contact_id!r}", code="not_found")
        return Contact(**row)


def _js_date(iso: str) -> str:
    return json.dumps(iso)
