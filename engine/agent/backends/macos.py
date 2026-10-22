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

import datetime as _dt
import json
import os
import subprocess
import sys
import threading

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


# Mail on a 600-message IMAP inbox can take several seconds to answer its first
# Apple event after launch; 20 s timed out in the owner's first live run.
OSA_TIMEOUT_S = float(os.environ.get("WELLSY_OSA_TIMEOUT", "30"))


def _osa(script: str) -> str:
    try:
        p = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True, text=True, timeout=OSA_TIMEOUT_S,
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
    # --- calendar ----------------------------------------------------------
    # EventKit (step 9 live run): Calendar's AppleScript `whose startDate` walks
    # every event of every calendar — with subscribed / holiday calendars and
    # recurrences it timed out at 20 s. EventKit answers a date-range predicate
    # from Calendar's own index. The osascript path stays as the fallback when
    # Calendar access is not granted to this process.

    def list_events(self, start: str, end: str) -> list[Event]:
        ek = _EventKit.get()
        if ek is None:
            return self._osa_list_events(start, end)
        return ek.list_events(start, end)

    def get_event(self, event_id: str) -> Event:
        ek = _EventKit.get()
        return ek.get_event(event_id) if ek is not None else self._osa_get_event(event_id)

    def create_event(self, title, start, end, *, calendar="Home", location=None, notes=None) -> Event:
        ek = _EventKit.get()
        if ek is None:
            return self._osa_create_event(title, start, end, calendar=calendar, location=location, notes=notes)
        return ek.create_event(title, start, end, calendar=calendar, location=location, notes=notes)

    def move_event(self, event_id: str, new_start: str, new_end: str) -> Event:
        ek = _EventKit.get()
        if ek is None:
            return self._osa_move_event(event_id, new_start, new_end)
        return ek.move_event(event_id, new_start, new_end)

    def _osa_list_events(self, start: str, end: str) -> list[Event]:
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

    def _osa_get_event(self, event_id: str) -> Event:
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

    def _osa_create_event(self, title, start, end, *, calendar="Home", location=None, notes=None) -> Event:
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

    def _osa_move_event(self, event_id: str, new_start: str, new_end: str) -> Event:
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
    # Step 9 live run: "inbox is empty" with 600+ messages. `app.inbox` (the
    # unified inbox) came back with no messages for the owner's accounts, and
    # the loop also called `m.datereceived()` (a typo for dateReceived). Now:
    # the unified inbox if it has messages, else every account's INBOX; dates
    # fetched in ONE bulk Apple event per mailbox, the newest `limit` picked,
    # and only those messages' fields fetched. Bodies are not fetched for a
    # listing (they are the slow part) — `get_message` reads one body.

    _INBOXES_JS = """
        const app = Application('Mail');
        function inboxes() {
          let unified = null;
          try { if (app.inbox.messages.length > 0) unified = app.inbox; } catch (e) {}
          if (unified) return [[unified, 'Inbox']];
          const out = [];
          for (const acc of app.accounts()) {
            for (const n of ['INBOX', 'Inbox', 'inbox']) {
              try { const mb = acc.mailboxes.byName(n); mb.name(); out.push([mb, acc.name() + '/' + n]); break; }
              catch (e) {}
            }
          }
          return out;
        }
    """

    def list_messages(self, *, mailbox="INBOX", limit=20) -> list[MailMessage]:
        script = self._INBOXES_JS + f"""
        const lim = {int(limit)};
        const cands = [];
        const boxes = inboxes();
        for (const [mb, label] of boxes) {{
          const dates = mb.messages.dateReceived();
          for (let i = 0; i < dates.length; i++) cands.push([dates[i] ? dates[i].getTime() : 0, mb, i, label]);
        }}
        cands.sort((a, b) => b[0] - a[0]);
        const out = [];
        for (const [t, mb, i, label] of cands.slice(0, lim)) {{
          const m = mb.messages[i];
          out.push({{id: String(m.id()), mailbox: label, sender: m.sender(),
            recipients: m.toRecipients.address(), subject: m.subject(), body: '',
            date: new Date(t).toISOString(), sent: false, unread: !m.readStatus()}});
        }}
        JSON.stringify({{boxes: boxes.length, total: cands.length, messages: out}});
        """
        res = _json(script) or {}
        if not res.get("boxes"):
            raise ToolError("Mail has no account inbox this process can read (is an account set up "
                            "and Automation access granted?)", code="not_found")
        return [MailMessage(**{k: v for k, v in r.items() if k != "unread"}) for r in res.get("messages", [])]

    def get_message(self, message_id: str) -> MailMessage:
        script = self._INBOXES_JS + f"""
        const want = {json.dumps(message_id)};
        let hit = null;
        for (const [mb, label] of inboxes().concat([[app.sentMailbox, 'Sent']])) {{
          const ms = mb.messages.whose({{id: Number(want)}})();
          if (ms.length) {{ hit = [ms[0], label]; break; }}
        }}
        if (!hit) ""; else {{
          const [m, label] = hit;
          JSON.stringify({{id: String(m.id()), mailbox: label, sender: m.sender(),
            recipients: m.toRecipients.address(), subject: m.subject(),
            body: m.content().slice(0, 8000), date: m.dateReceived().toISOString(),
            sent: label === 'Sent'}});
        }}
        """
        row = _json(script)
        if not row:
            raise ToolError(f"no message {message_id!r}", code="not_found")
        return MailMessage(**row)

    def list_sent(self, *, limit=20) -> list[MailMessage]:
        script = f"""
        const app = Application('Mail');
        const mb = app.sentMailbox;
        const dates = mb.messages.dateSent();
        const idx = dates.map((d, i) => [d ? d.getTime() : 0, i]).sort((a, b) => b[0] - a[0]).slice(0, {int(limit)});
        const out = [];
        for (const [t, i] of idx) {{ const m = mb.messages[i];
          out.push({{id: String(m.id()), mailbox: 'Sent', sender: m.sender(),
            recipients: m.toRecipients.address(), subject: m.subject(), body: '',
            date: new Date(t).toISOString(), sent: true}}); }}
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
        """Read-back for a draft (step 9 live run: unimplemented, so every draft
        was 'unverified' and the dependent send was blocked)."""
        script = f"""
        const app = Application('Mail');
        const ms = app.outgoingMessages.whose({{id: Number({json.dumps(draft_id)})}})();
        if (!ms.length) ""; else {{ const m = ms[0];
          JSON.stringify({{id: String(m.id()), to: m.toRecipients.address(),
            subject: m.subject(), body: m.content()}}); }}
        """
        row = _json(script)
        if not row:
            raise ToolError(f"no draft {draft_id!r}", code="not_found")
        return Draft(row["id"], list(row.get("to") or []), row.get("subject", ""), row.get("body", ""),
                     None, False)

    def send_draft(self, draft_id: str) -> MailMessage:
        # Mail gives the sent copy a new id, so the read-back matches the Sent
        # mailbox on subject + recipients (graph._read_back) — captured here.
        script = f"""
        const app = Application('Mail');
        const ms = app.outgoingMessages.whose({{id: Number({json.dumps(draft_id)})}})();
        if (!ms.length) ""; else {{ const m = ms[0];
          const info = {{id: {json.dumps(draft_id)}, subject: m.subject(), to: m.toRecipients.address()}};
          m.send();
          JSON.stringify(info); }}
        """
        row = _json(script)
        if not row:
            raise ToolError(f"no draft {draft_id!r}", code="not_found")
        return MailMessage(draft_id, "Sent", "me", list(row.get("to") or []), row.get("subject", ""),
                           "", _dt.datetime.now().astimezone().isoformat(), sent=True)

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
        # one indexed `whose` per field instead of fetching every person's
        # fields one Apple event at a time
        script = f"""
        const app = Application('Contacts');
        const q = {json.dumps(query)};
        const seen = {{}}; const out = [];
        const hits = app.people.whose({{_or: [{{name: {{_contains: q}}}}, {{organization: {{_contains: q}}}}]}})();
        let byEmail = [];
        try {{ byEmail = app.people.whose({{emails: {{value: {{_contains: q}}}}}})(); }} catch (e) {{}}
        for (const p of hits.concat(byEmail)) {{
          const id = p.id(); if (seen[id]) continue; seen[id] = 1;
          out.push({{id: id, name: p.name() || '', emails: p.emails.value(),
            phones: p.phones.value(), organization: p.organization() || null}});
          if (out.length >= 10) break;
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


# --------------------------------------------------------------------------- #
# EventKit — the calendar path (pyobjc-framework-EventKit, darwin-only extra) #
# --------------------------------------------------------------------------- #

class _EventKit:
    """Calendar through EventKit. `get()` returns None (and the backend falls
    back to osascript) when the binding is missing or access is not granted;
    the first call asks macOS for access and waits for the answer."""

    _inst = None
    _tried = False

    @classmethod
    def get(cls):
        if cls._tried:
            return cls._inst
        cls._tried = True
        if os.environ.get("WELLSY_MACOS_CALENDAR", "eventkit") != "eventkit":
            return None
        try:
            import EventKit  # noqa: F401
        except ImportError:
            return None
        inst = cls()
        cls._inst = inst if inst._authorize() else None
        return cls._inst

    def __init__(self) -> None:
        import EventKit

        self.EK = EventKit
        self.store = EventKit.EKEventStore.alloc().init()

    def _authorize(self) -> bool:
        EK = self.EK
        status = EK.EKEventStore.authorizationStatusForEntityType_(EK.EKEntityTypeEvent)
        full = getattr(EK, "EKAuthorizationStatusFullAccess", 3)
        if status in (full, getattr(EK, "EKAuthorizationStatusAuthorized", 3)):
            return True
        if status not in (getattr(EK, "EKAuthorizationStatusNotDetermined", 0),):
            return False                                    # denied / restricted / write-only
        done, granted = threading.Event(), {"ok": False}

        def cb(ok, err):
            granted["ok"] = bool(ok)
            done.set()

        req = getattr(self.store, "requestFullAccessToEventsWithCompletion_", None)
        if req is not None:
            req(cb)
        else:  # macOS < 14
            self.store.requestAccessToEntityType_completion_(EK.EKEntityTypeEvent, cb)
        done.wait(60)
        return granted["ok"]

    # -- conversions --
    @staticmethod
    def _ns(iso: str):
        from Foundation import NSDate

        d = _dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.astimezone()
        return NSDate.dateWithTimeIntervalSince1970_(d.timestamp())

    @staticmethod
    def _iso(nsdate) -> str:
        return _dt.datetime.fromtimestamp(nsdate.timeIntervalSince1970()).astimezone().isoformat(timespec="seconds")

    def _event(self, ev) -> Event:
        return Event(str(ev.eventIdentifier()), str(ev.title() or ""), self._iso(ev.startDate()),
                     self._iso(ev.endDate()), str(ev.calendar().title()),
                     str(ev.location()) if ev.location() else None,
                     str(ev.notes())[:2000] if ev.notes() else None)

    # -- operations --
    def list_events(self, start: str, end: str) -> list[Event]:
        pred = self.store.predicateForEventsWithStartDate_endDate_calendars_(self._ns(start), self._ns(end), None)
        evs = self.store.eventsMatchingPredicate_(pred) or []
        return sorted((self._event(e) for e in evs), key=lambda e: e.start)

    def get_event(self, event_id: str) -> Event:
        ev = self.store.eventWithIdentifier_(event_id)
        if ev is None:
            raise ToolError(f"no event {event_id!r}", code="not_found")
        return self._event(ev)

    def _calendar(self, name: str | None):
        if name:
            for c in self.store.calendarsForEntityType_(self.EK.EKEntityTypeEvent):
                if str(c.title()) == name and c.allowsContentModifications():
                    return c
        return self.store.defaultCalendarForNewEvents()

    def _save(self, ev) -> None:
        ok, err = self.store.saveEvent_span_commit_error_(ev, self.EK.EKSpanThisEvent, True, None)
        if not ok:
            raise ToolError(f"Calendar refused the change: {err}", code="backend_error")

    def create_event(self, title, start, end, *, calendar="Home", location=None, notes=None) -> Event:
        ev = self.EK.EKEvent.eventWithEventStore_(self.store)
        ev.setTitle_(title)
        ev.setStartDate_(self._ns(start))
        ev.setEndDate_(self._ns(end))
        ev.setCalendar_(self._calendar(calendar))
        if location:
            ev.setLocation_(location)
        if notes:
            ev.setNotes_(notes)
        self._save(ev)
        return self._event(ev)

    def move_event(self, event_id: str, new_start: str, new_end: str) -> Event:
        ev = self.store.eventWithIdentifier_(event_id)
        if ev is None:
            raise ToolError(f"no event {event_id!r}", code="not_found")
        ev.setStartDate_(self._ns(new_start))
        ev.setEndDate_(self._ns(new_end))
        self._save(ev)
        return self._event(ev)
