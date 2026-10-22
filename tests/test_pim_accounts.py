"""The `accounts` PIM backend: IMAP/SMTP mail, CalDAV, CardDAV.

No network: IMAP/SMTP are fake objects patched into `mail`, CalDAV/CardDAV
run against an `httpx.MockTransport` that speaks just enough WebDAV.
"""

from __future__ import annotations

import email
import email.policy
import re
from email.message import EmailMessage

import httpx
import pytest

from engine.agent.backends import ToolError
from engine.agent.backends import accounts as acc
from engine.agent.backends import dav, mail
from engine.agent.backends.standard import AccountsPimBackend


def _msg(uid, frm, to, subject, date="Wed, 21 Oct 2026 10:00:00 +0530", body="hello"):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Date"] = frm, to, subject, date
    m["Message-ID"] = f"<m{uid}@x>"
    m.set_content(body)
    return m.as_bytes()


class FakeIMAP:
    """Just the imaplib surface `ImapMail` uses."""

    boxes: dict[str, dict[int, bytes]] = {}

    def __init__(self, host, port, timeout=None):
        self.cur = None
        self.calls = []

    def login(self, user, pw):
        if pw != "right":
            import imaplib

            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")

    def noop(self):
        return "OK", [b""]

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"',
                      b'(\\HasNoChildren \\Drafts) "/" "[Gmail]/Drafts"']

    def select(self, box, readonly=True):
        name = box.strip('"')
        if name not in self.boxes:
            return "NO", [b"no such mailbox"]
        self.cur = name
        return "OK", [str(len(self.boxes[name])).encode()]

    def fetch(self, rng, what):
        lo, hi = (int(x) for x in rng.split(":"))
        uids = sorted(self.boxes[self.cur])
        self.calls.append(("fetch", rng))
        return "OK", [f"{i} (UID {uids[i - 1]})".encode() for i in range(lo, hi + 1)]

    def uid(self, cmd, *args):
        box = self.boxes[self.cur]
        if cmd == "FETCH":
            out = []
            for u in args[0].split(","):
                blob = box.get(int(u))
                if blob is None:
                    continue
                if "HEADER.FIELDS" in args[1]:
                    blob = blob.split(b"\n\n", 1)[0] + b"\n\n"
                out += [(f"1 (UID {u} BODY[] {{{len(blob)}}}".encode(), blob), b")"]
            return "OK", out
        if cmd == "SEARCH":
            q = args[-1].strip('"').lower()
            hits = [str(u) for u, b in box.items() if q in b.split(b"\n\n")[0].decode().lower()]
            return "OK", [" ".join(hits).encode()]
        if cmd == "STORE":
            box.pop(int(args[0]), None)
            return "OK", [b""]
        raise AssertionError(cmd)

    def append(self, box, flags, date, blob):
        name = box.strip('"')
        uid = max(self.boxes[name], default=0) + 1
        self.boxes[name][uid] = blob.replace(b"\r\n", b"\n")
        return "OK", [f"[APPENDUID 7 {uid}] done".encode()]

    def expunge(self):
        return "OK", [b""]


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, u, p):
        pass

    def send_message(self, msg, from_addr, to_addrs):
        FakeSMTP.sent.append((from_addr, to_addrs, msg["Subject"]))


@pytest.fixture
def gmail(monkeypatch):
    FakeIMAP.boxes = {
        "INBOX": {u: _msg(u, f"Person {u} <p{u}@example.com>", "me@gmail.com", f"Subject {u}",
                          date=f"Wed, 21 Oct 2026 {u % 24:02d}:00:00 +0000") for u in range(100, 700)},
        "[Gmail]/Sent Mail": {5: _msg(5, "me@gmail.com", "Rahul Verma <rahul.v@example.com>", "Plans")},
        "[Gmail]/Drafts": {},
    }
    FakeIMAP.boxes["INBOX"][700] = _msg(700, "Rahul Verma <rahul.v@example.com>", "me@gmail.com", "Hi",
                                         date="Thu, 22 Oct 2026 09:00:00 +0000", body="see you at 5")
    FakeSMTP.sent = []
    monkeypatch.setattr(mail.imaplib, "IMAP4_SSL", FakeIMAP)
    monkeypatch.setattr(mail.smtplib, "SMTP_SSL", FakeSMTP)
    account = acc._mail_from_address("me@gmail.com", "right")
    return AccountsPimBackend(acc.Accounts(mail=account), local_path=None)


# --- provider table -------------------------------------------------------
def test_provider_table_is_honest_about_oauth():
    assert acc.provider_for("x@gmail.com")[0] == "gmail"
    assert acc.PROVIDERS["gmail"]["calendar"] is None  # Google CalDAV needs OAuth
    assert acc.provider_for("x@icloud.com")[1]["calendar"] == "https://caldav.icloud.com/"
    name, p, why = acc.provider_for("x@outlook.com")
    assert name is None and "OAuth" in why
    assert acc.provider_for("x@unknown-isp.org") == (None, None, None)


def test_saved_config_is_private(tmp_path, monkeypatch):
    monkeypatch.setenv("WELLSY_ACCOUNTS", str(tmp_path / "a.json"))
    path = acc.save_accounts(acc.Accounts(mail=acc._mail_from_address("me@icloud.com", "pw")))
    assert path.stat().st_mode & 0o777 == 0o600
    loaded = acc.load_accounts()
    assert loaded.mail.imap_host == "imap.mail.me.com" and loaded.calendar is None


def test_env_only_icloud_derives_dav(monkeypatch):
    monkeypatch.setenv("WELLSY_MAIL_ADDRESS", "me@icloud.com")
    monkeypatch.setenv("WELLSY_MAIL_PASSWORD", "pw")
    a = acc.load_accounts()
    assert a.calendar.url == "https://caldav.icloud.com/" and a.contacts.url == "https://contacts.icloud.com/"


# --- mail ---------------------------------------------------------------------
def test_newest_messages_are_one_range_not_a_walk(gmail):
    msgs = gmail.list_messages(limit=10)
    assert len(msgs) == 10
    assert msgs[0].subject == "Hi" and msgs[0].body == ""  # headers only
    assert gmail._mail._conn.calls == [("fetch", "592:601")]  # 601 messages, newest 10


def test_full_message_body(gmail):
    newest = gmail.list_messages(limit=1)[0]
    m = gmail.get_message(newest.id)
    assert "see you at 5" in m.body and m.recipients == ["me@gmail.com"]


def test_wrong_password_is_an_error_not_an_empty_inbox(monkeypatch, gmail):
    bad = AccountsPimBackend(acc.Accounts(mail=acc._mail_from_address("me@gmail.com", "wrong")))
    with pytest.raises(ToolError) as e:
        bad.list_messages()
    assert e.value.code == "auth_failed"


def test_draft_send_cycle(gmail):
    d = gmail.create_draft(["rahul.v@example.com"], "Lunch", "Friday?")
    assert d.id == "[Gmail]/Drafts#1"
    assert gmail.get_draft(d.id).to == ["rahul.v@example.com"]
    sent = gmail.send_draft(d.id)
    assert FakeSMTP.sent == [("me@gmail.com", ["rahul.v@example.com"], "Lunch")]
    assert sent.sent and sent.recipients == ["rahul.v@example.com"]
    assert FakeIMAP.boxes["[Gmail]/Drafts"] == {}            # draft removed
    assert len(FakeIMAP.boxes["[Gmail]/Sent Mail"]) == 1     # Gmail files sent mail itself
    with pytest.raises(ToolError) as e:
        gmail.send_draft(d.id)
    assert e.value.code == "already_sent"


def test_contacts_come_from_correspondence(gmail):
    hits = gmail.search_contacts("rahul")
    assert [(c.name, c.emails) for c in hits] == [("Rahul Verma", ["rahul.v@example.com"])]
    assert gmail.get_contact(hits[0].id).emails == ["rahul.v@example.com"]


def test_calendar_not_connected_says_why(gmail):
    with pytest.raises(ToolError) as e:
        gmail.list_events("2026-10-22T00:00:00+05:30", "2026-10-23T00:00:00+05:30")
    assert e.value.code == "not_connected" and "OAuth" in str(e.value)


def test_reminders_and_notes_are_local_and_start_empty(gmail, tmp_path):
    b = AccountsPimBackend(gmail.accounts, local_path=tmp_path / "local.json")
    assert b.list_reminders() == [] and b.list_notes() == []  # never the demo seed
    b.create_reminder("Call mom")
    assert [r.title for r in b.list_reminders()] == ["Call mom"]


# --- CalDAV / CardDAV -----------------------------------------------------
_ICS = """BEGIN:VCALENDAR\r
BEGIN:VEVENT\r
UID:a1\r
DTSTART:20261022T043000Z\r
DTEND:20261022T053000Z\r
SUMMARY:Dentist\\, Dr. Rao\r
LOCATION:MG Road\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:r1\r
RECURRENCE-ID:20261022T090000Z\r
DTSTART:20261022T090000Z\r
DURATION:PT30M\r
SUMMARY:Standup\r
END:VEVENT\r
END:VCALENDAR\r
"""
_VCF = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Priya Shah\r\nitem1.EMAIL;type=INTERNET:priya@example.com\r\nORG:Acme;\r\nEND:VCARD\r\n"


def _ms(*responses: str) -> bytes:
    return (f'<d:multistatus xmlns:d="DAV:" xmlns:c="{dav.NS["c"]}" xmlns:card="{dav.NS["card"]}">'
            + "".join(responses) + "</d:multistatus>").encode()


def _dav_server(store: dict):
    def handle(req: httpx.Request) -> httpx.Response:
        p, body = req.url.path, req.content.decode()
        if req.method == "PROPFIND" and "current-user-principal" in body:
            return httpx.Response(207, content=_ms('<d:response><d:href>/</d:href><d:propstat><d:prop>'
                                                   '<d:current-user-principal><d:href>/p/</d:href></d:current-user-principal>'
                                                   '</d:prop></d:propstat></d:response>'))
        if req.method == "PROPFIND" and "home-set" in body:
            tag = "c:calendar-home-set" if "calendar-home-set" in body else "card:addressbook-home-set"
            return httpx.Response(207, content=_ms(f'<d:response><d:href>/p/</d:href><d:propstat><d:prop><{tag}>'
                                                   f'<d:href>/home/</d:href></{tag}></d:prop></d:propstat></d:response>'))
        if req.method == "PROPFIND":
            return httpx.Response(207, content=_ms(
                '<d:response><d:href>/home/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>'
                '<d:response><d:href>/home/work/</d:href><d:propstat><d:prop><d:displayname>Work</d:displayname>'
                '<d:resourcetype><d:collection/><c:calendar/><card:addressbook/></d:resourcetype>'
                '<c:supported-calendar-component-set><c:comp name="VEVENT"/></c:supported-calendar-component-set>'
                '</d:prop></d:propstat></d:response>'))
        if req.method == "REPORT" and "calendar-query" in body:
            assert "<c:expand" in body  # recurrences are the server's job
            items = "".join(f'<d:response><d:href>{h}</d:href><d:propstat><d:prop><d:getetag>"1"</d:getetag>'
                            f'<c:calendar-data>{ics}</c:calendar-data></d:prop></d:propstat></d:response>'
                            for h, ics in store.items() if h.endswith(".ics"))
            return httpx.Response(207, content=_ms(items))
        if req.method == "REPORT":
            return httpx.Response(207, content=_ms('<d:response><d:href>/home/work/p.vcf</d:href><d:propstat><d:prop>'
                                                   f'<card:address-data>{_VCF}</card:address-data></d:prop></d:propstat></d:response>'))
        if req.method == "GET":
            if p not in store:
                return httpx.Response(404)
            return httpx.Response(200, text=store[p], headers={"ETag": '"1"'})
        if req.method == "PUT":
            if req.headers.get("If-None-Match") == "*" and p in store:
                return httpx.Response(412)
            store[p] = req.content.decode()
            return httpx.Response(201)
        return httpx.Response(405)
    return httpx.MockTransport(handle)


@pytest.fixture
def caldav():
    store = {"/home/work/a1.ics": _ICS}
    c = dav.CalDav(acc.DavAccount("https://dav.example.com/", "me", "pw"))
    c.http = httpx.Client(transport=_dav_server(store), base_url="https://dav.example.com")
    return c, store


def test_caldav_lists_expanded_events_in_local_time(caldav):
    c, _ = caldav
    evs = c.list_events("2026-10-22T00:00:00+05:30", "2026-10-23T00:00:00+05:30")
    assert [e.title for e in evs] == ["Dentist, Dr. Rao", "Standup"]
    assert evs[0].calendar == "Work" and evs[0].location == "MG Road"
    assert evs[1].id.endswith("#20261022T090000Z")
    assert dav._parse_iso(evs[1].end) - dav._parse_iso(evs[1].start) == dav.timedelta(minutes=30)


def test_caldav_create_then_move_reads_back_from_server(caldav):
    c, store = caldav
    ev = c.create_event("Lunch", "2026-10-23T13:00:00+05:30", "2026-10-23T14:00:00+05:30", calendar="Work")
    assert ev.title == "Lunch" and dav._parse_iso(ev.start) == dav._parse_iso("2026-10-23T13:00:00+05:30")
    moved = c.move_event(ev.id, "2026-10-23T15:00:00+05:30", "2026-10-23T16:00:00+05:30")
    assert dav._parse_iso(moved.start) == dav._parse_iso("2026-10-23T15:00:00+05:30")
    assert "DTSTART:20261023T093000Z" in store[ev.id]


def test_moving_one_occurrence_is_refused(caldav):
    c, _ = caldav
    with pytest.raises(ToolError) as e:
        c.move_event("/home/work/a1.ics#20261022T090000Z", "2026-10-22T10:00:00Z", "2026-10-22T11:00:00Z")
    assert e.value.code == "unsupported"


def test_carddav_search():
    c = dav.CardDav(acc.DavAccount("https://dav.example.com/", "me", "pw"))
    c.http = httpx.Client(transport=_dav_server({}), base_url="https://dav.example.com")
    hits = c.search("priya")
    assert [(h.name, h.emails, h.organization) for h in hits] == [("Priya Shah", ["priya@example.com"], "Acme")]
    assert c.names() == ["Priya Shah"]


def test_ics_tzid_and_all_day():
    ics = ("BEGIN:VEVENT\nDTSTART;TZID=Asia/Kolkata:20261022T100000\nDTEND;TZID=Asia/Kolkata:20261022T110000\n"
           "SUMMARY:A\nEND:VEVENT\nBEGIN:VEVENT\nDTSTART;VALUE=DATE:20261024\nSUMMARY:Holiday\nEND:VEVENT\n")
    a, h = dav.parse_events(ics, "/x.ics", "Home")
    assert dav._parse_iso(a.start) == dav._parse_iso("2026-10-22T10:00:00+05:30")
    assert h.title == "Holiday" and (dav._parse_iso(h.end) - dav._parse_iso(h.start)).days == 1


def test_hotwords_come_from_the_users_own_mail(gmail):
    FakeIMAP.boxes["[Gmail]/Sent Mail"][6] = _msg(6, "me@gmail.com", "Rahul Verma <r@x.com>, Anjali K <a@x.com>", "x")
    assert gmail.known_names() == ["Rahul Verma", "Anjali K"]


def test_no_account_means_no_hotwords(monkeypatch):
    from engine.voice import pipeline

    class Asr:
        hotwords = ""

    class Stt:
        _asr = Asr()

    stt = Stt()
    pipeline._load_hotwords(stt)
    import time

    time.sleep(0.1)
    assert stt._asr.hotwords == ""
