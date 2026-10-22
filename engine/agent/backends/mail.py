"""Mail over IMAP + SMTP, standard library only.

The server does the work: the newest N messages are a sequence-number range
(no walk over the whole inbox), only headers are fetched for a listing, and a
search is an IMAP SEARCH. That is why a 600-message inbox lists in one round
trip instead of timing out the way the Mail.app automation did.

Message ids are `<mailbox>#<uid>`. A draft is a real message in the account's
Drafts folder (so it shows on the phone too); sending it goes through SMTP,
files a copy in Sent when the provider doesn't, and removes the draft.

Contacts are derived from the mail itself: "email Rahul" is resolved from the
people the user actually corresponds with, which works for every provider,
including Gmail where CardDAV needs OAuth.
"""

from __future__ import annotations

import email
import email.policy
import imaplib
import re
import smtplib
import socket
import ssl
import threading
import time
from collections import Counter
from email.message import EmailMessage
from email.utils import format_datetime, getaddresses, make_msgid, parsedate_to_datetime
from datetime import datetime

from engine.agent.backends.accounts import MailAccount
from engine.agent.backends.base import Contact, Draft, MailMessage, ToolError

TIMEOUT_S = 20
BODY_CHARS = 4000
_HEADERS = "FROM TO CC SUBJECT DATE MESSAGE-ID"
_LIST_RE = re.compile(r'\((?P<flags>[^)]*)\) (?P<delim>"[^"]*"|NIL) (?P<name>.+)')


def _q(mailbox: str) -> str:
    return '"' + mailbox.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _unq(name: str) -> str:
    name = name.strip()
    if name.startswith('"') and name.endswith('"'):
        name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return name


def _addrs(*values: str | None) -> list[str]:
    return [a for _, a in getaddresses([v for v in values if v]) if a]


def _iso(date_header: str | None) -> str:
    if not date_header:
        return ""
    try:
        return parsedate_to_datetime(date_header).astimezone().replace(microsecond=0).isoformat()
    except (TypeError, ValueError):
        return ""


def _text(msg: email.message.Message) -> str:
    part = msg.get_body(preferencelist=("plain", "html")) if hasattr(msg, "get_body") else None
    if part is None:
        return ""
    try:
        body = part.get_content()
    except (KeyError, LookupError):
        body = part.get_payload(decode=True).decode("utf-8", "replace") if part.get_payload(decode=True) else ""
    if part.get_content_type() == "text/html":
        body = re.sub(r"(?is)<(script|style).*?</\1>|<[^>]+>", " ", body)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", body)).strip()[:BODY_CHARS]


class ImapMail:
    def __init__(self, account: MailAccount) -> None:
        self.acct = account
        self._conn: imaplib.IMAP4 | None = None
        self._lock = threading.RLock()
        self._special: dict[str, str] | None = None
        self._sent_drafts: set[str] = set()

    # --- connection ---------------------------------------------------------
    def _connect(self) -> imaplib.IMAP4:
        try:
            conn = imaplib.IMAP4_SSL(self.acct.imap_host, self.acct.imap_port, timeout=TIMEOUT_S)
            conn.login(self.acct.login, self.acct.password)
            return conn
        except imaplib.IMAP4.error as e:
            raise ToolError(f"mail login refused by {self.acct.imap_host}: {e}", code="auth_failed") from None
        except (socket.timeout, TimeoutError):
            raise ToolError(f"mail server {self.acct.imap_host} timed out", code="timeout") from None
        except OSError as e:
            raise ToolError(f"can't reach mail server {self.acct.imap_host}: {e}", code="unreachable") from None

    def _imap(self) -> imaplib.IMAP4:
        if self._conn is not None:
            try:
                self._conn.noop()
                return self._conn
            except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError):
                self._conn = None
        self._conn = self._connect()
        return self._conn

    def _run(self, fn):
        """One retry on a dropped connection; every other failure is a
        ToolError, never an empty result."""
        with self._lock:
            for attempt in (0, 1):
                try:
                    return fn(self._imap())
                except (imaplib.IMAP4.abort, ConnectionError, ssl.SSLError):
                    self._conn = None
                    if attempt:
                        raise ToolError("mail connection dropped", code="unreachable") from None
                except (socket.timeout, TimeoutError):
                    self._conn = None
                    raise ToolError("mail server timed out", code="timeout") from None
                except imaplib.IMAP4.error as e:
                    raise ToolError(f"mail server error: {e}", code="backend_error") from None

    def check(self) -> int:
        """Login + inbox count; used by `wellsy accounts add`."""
        return self._run(lambda c: self._select(c, "INBOX"))

    # --- mailboxes ----------------------------------------------------------
    def _mailboxes(self, c: imaplib.IMAP4) -> dict[str, str]:
        """RFC 6154 special-use names: {'Sent': '[Gmail]/Sent Mail', ...}."""
        if self._special is None:
            typ, rows = c.list()
            found: dict[str, str] = {}
            names = []
            for raw in rows or []:
                m = _LIST_RE.match(raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw))
                if not m:
                    continue
                name = _unq(m.group("name"))
                names.append(name)
                for use in ("Sent", "Drafts", "Trash"):
                    if f"\\{use}" in m.group("flags"):
                        found.setdefault(use, name)
            for use, guesses in (("Sent", ("Sent", "Sent Messages", "Sent Items", "INBOX.Sent")),
                                 ("Drafts", ("Drafts", "INBOX.Drafts"))):
                if use not in found:
                    found[use] = next((g for g in guesses if g in names), use)
            self._special = found
        return self._special

    def _resolve(self, c: imaplib.IMAP4, mailbox: str) -> str:
        if mailbox.upper() == "INBOX":
            return "INBOX"
        return self._mailboxes(c).get(mailbox.capitalize(), mailbox)

    def _select(self, c: imaplib.IMAP4, mailbox: str, readonly: bool = True) -> int:
        typ, data = c.select(_q(mailbox), readonly=readonly)
        if typ != "OK":
            raise ToolError(f"no mailbox {mailbox!r}", code="not_found")
        return int(data[0] or 0)

    # --- fetch helpers -----------------------------------------------------
    @staticmethod
    def _fetch(c: imaplib.IMAP4, uids: list[bytes], what: str) -> list[tuple[str, bytes]]:
        if not uids:
            return []
        typ, data = c.uid("FETCH", b",".join(uids).decode(), f"(UID {what})")
        out = []
        for item in data or []:
            if isinstance(item, tuple):
                m = re.search(rb"UID (\d+)", item[0])
                if m:
                    out.append((m.group(1).decode(), item[1]))
        return out

    def _headers(self, mailbox: str, raw: list[tuple[str, bytes]], sent: bool) -> list[MailMessage]:
        msgs = []
        for uid, blob in raw:
            h = email.message_from_bytes(blob, policy=email.policy.default)
            msgs.append(MailMessage(
                id=f"{mailbox}#{uid}", mailbox=mailbox, sender=str(h.get("From", "")),
                recipients=_addrs(h.get("To"), h.get("Cc")), subject=str(h.get("Subject", "")),
                body="", date=_iso(h.get("Date")), sent=sent,
            ))
        return sorted(msgs, key=lambda m: m.date, reverse=True)

    def _newest(self, mailbox: str, limit: int, sent: bool) -> list[MailMessage]:
        def go(c):
            box = self._resolve(c, mailbox)
            n = self._select(c, box)
            if n == 0:
                return []
            lo = max(1, n - max(1, limit) + 1)
            typ, data = c.fetch(f"{lo}:{n}", "(UID)")
            uids = [m.group(1) for d in data or [] if (m := re.search(rb"UID (\d+)", d if isinstance(d, bytes) else d[0]))]
            return self._headers(box, self._fetch(c, uids, f"BODY.PEEK[HEADER.FIELDS ({_HEADERS})]"), sent)
        return self._run(go)[:limit]

    def _one(self, message_id: str) -> tuple[str, str, email.message.Message]:
        box, _, uid = message_id.rpartition("#")
        if not box or not uid.isdigit():
            raise ToolError(f"no message {message_id!r}", code="not_found")

        def go(c):
            self._select(c, box)
            got = self._fetch(c, [uid.encode()], "BODY.PEEK[]")
            if not got:
                raise ToolError(f"no message {message_id!r}", code="not_found")
            return email.message_from_bytes(got[0][1], policy=email.policy.default)
        return box, uid, self._run(go)

    # --- PimBackend mail ------------------------------------------------------
    def list_messages(self, *, mailbox: str = "INBOX", limit: int = 20) -> list[MailMessage]:
        return self._newest(mailbox, limit, sent=False)

    def list_sent(self, *, limit: int = 20) -> list[MailMessage]:
        return self._newest("Sent", limit, sent=True)

    def get_message(self, message_id: str) -> MailMessage:
        box, uid, m = self._one(message_id)
        sent = box == self._run(lambda c: self._mailboxes(c)["Sent"])
        return MailMessage(message_id, box, str(m.get("From", "")), _addrs(m.get("To"), m.get("Cc")),
                           str(m.get("Subject", "")), _text(m), _iso(m.get("Date")), sent=sent)

    def create_draft(self, to, subject, body, *, in_reply_to=None) -> Draft:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.acct.address, ", ".join(to), subject
        msg["Date"] = format_datetime(datetime.now().astimezone())
        msg["Message-ID"] = make_msgid(domain=self.acct.address.rsplit("@", 1)[-1])
        if in_reply_to:
            try:
                _, _, orig = self._one(in_reply_to)
                if orig.get("Message-ID"):
                    msg["In-Reply-To"] = msg["References"] = str(orig["Message-ID"])
            except ToolError:
                pass
        msg.set_content(body)

        def go(c):
            box = self._mailboxes(c)["Drafts"]
            typ, data = c.append(_q(box), "(\\Draft \\Seen)", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
            if typ != "OK":
                raise ToolError(f"couldn't save the draft: {data}", code="backend_error")
            m = re.search(rb"APPENDUID \d+ (\d+)", data[0] or b"")
            if m:
                return box, m.group(1).decode()
            self._select(c, box)
            typ, hits = c.uid("SEARCH", None, "HEADER", "Message-ID", msg["Message-ID"])
            ids = (hits[0] or b"").split()
            if not ids:
                raise ToolError("draft saved but not found again", code="backend_error")
            return box, ids[-1].decode()
        box, uid = self._run(go)
        return Draft(f"{box}#{uid}", list(to), subject, body, in_reply_to, False)

    def get_draft(self, draft_id: str) -> Draft:
        if draft_id in self._sent_drafts:
            raise ToolError(f"draft {draft_id!r} already sent", code="already_sent")
        _, _, m = self._one(draft_id)
        return Draft(draft_id, _addrs(m.get("To"), m.get("Cc")), str(m.get("Subject", "")), _text(m),
                     None, False)

    def send_draft(self, draft_id: str) -> MailMessage:
        if draft_id in self._sent_drafts:
            raise ToolError(f"draft {draft_id!r} already sent", code="already_sent")
        box, uid, m = self._one(draft_id)
        to = _addrs(m.get("To"), m.get("Cc"), m.get("Bcc"))
        if not to:
            raise ToolError("the draft has no recipient", code="invalid_args")
        del m["Bcc"]
        del m["Date"]
        m["Date"] = format_datetime(datetime.now().astimezone())
        self._smtp_send(m, to)
        self._sent_drafts.add(draft_id)

        def file_and_clean(c):
            if not self.acct.smtp_saves_sent:
                c.append(_q(self._mailboxes(c)["Sent"]), "(\\Seen)", imaplib.Time2Internaldate(time.time()), m.as_bytes())
            self._select(c, box, readonly=False)
            c.uid("STORE", uid, "+FLAGS.SILENT", "(\\Deleted)")
            c.expunge()
        try:
            self._run(file_and_clean)
        except ToolError:
            pass  # the mail went out; a leftover draft is not a failed send
        return MailMessage(f"sent:{m.get('Message-ID', '')}", "Sent", self.acct.address, to,
                           str(m.get("Subject", "")), _text(m), datetime.now().astimezone().replace(microsecond=0).isoformat(),
                           sent=True)

    def _smtp_send(self, msg: email.message.Message, to: list[str]) -> None:
        a = self.acct
        try:
            if a.smtp_port == 465:
                s = smtplib.SMTP_SSL(a.smtp_host, a.smtp_port, timeout=TIMEOUT_S)
            else:
                s = smtplib.SMTP(a.smtp_host, a.smtp_port, timeout=TIMEOUT_S)
                s.starttls(context=ssl.create_default_context())
            with s:
                s.login(a.login, a.password)
                s.send_message(msg, from_addr=a.address, to_addrs=to)
        except smtplib.SMTPAuthenticationError as e:
            raise ToolError(f"mail server refused the login for sending: {e}", code="auth_failed") from None
        except smtplib.SMTPRecipientsRefused as e:
            raise ToolError(f"recipient refused: {', '.join(e.recipients)}", code="invalid_args") from None
        except (smtplib.SMTPException, OSError) as e:
            raise ToolError(f"sending failed: {e}", code="unreachable") from None

    def frequent_names(self, *, recent: int = 60, limit: int = 25) -> list[str]:
        """Display names of the people the user wrote to most in their last
        `recent` sent messages, for speech-recognition hotwords."""
        def go(c):
            box = self._mailboxes(c)["Sent"]
            n = self._select(c, box)
            if n == 0:
                return []
            typ, data = c.fetch(f"{max(1, n - recent + 1)}:{n}", "(UID)")
            uids = [m.group(1) for d in data or [] if (m := re.search(rb"UID (\d+)", d if isinstance(d, bytes) else d[0]))]
            counts: Counter = Counter()
            for _, blob in self._fetch(c, uids, "BODY.PEEK[HEADER.FIELDS (TO CC)]"):
                h = email.message_from_bytes(blob, policy=email.policy.default)
                for name, _ in getaddresses([str(h.get("To", "")), str(h.get("Cc", ""))]):
                    if name and "@" not in name:
                        counts[name.strip('"')] += 1
            return [name for name, _ in counts.most_common(limit)]
        return self._run(go)

    # --- contacts from correspondence --------------------------------------
    def correspondents(self, query: str, *, per_box: int = 40) -> list[Contact]:
        """People in the user's mail whose name or address matches `query`,
        most frequent first. The server searches; only headers come back."""
        q = query.strip()
        if not q:
            return []

        def go(c):
            seen: Counter = Counter()
            names: dict[str, str] = {}
            for box in ("INBOX", self._mailboxes(c)["Sent"]):
                try:
                    self._select(c, box)
                except ToolError:
                    continue
                typ, hits = c.uid("SEARCH", "CHARSET", "UTF-8", "OR", "FROM", _q(q), "TO", _q(q))
                uids = (hits[0] or b"").split()[-per_box:]
                for _, blob in self._fetch(c, uids, "BODY.PEEK[HEADER.FIELDS (FROM TO CC)]"):
                    h = email.message_from_bytes(blob, policy=email.policy.default)
                    for name, addr in getaddresses([str(h.get(k, "")) for k in ("From", "To", "Cc")]):
                        addr = addr.lower()
                        if not addr or addr == self.acct.address.lower():
                            continue
                        if q.lower() in name.lower() or q.lower() in addr:
                            seen[addr] += 1
                            if name and len(name) > len(names.get(addr, "")):
                                names[addr] = name
            return seen, names
        seen, names = self._run(go)
        return [Contact(f"mail:{a}", names.get(a) or a.split("@")[0], [a]) for a, _ in seen.most_common(10)]
