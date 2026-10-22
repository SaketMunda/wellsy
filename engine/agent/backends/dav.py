"""Calendar over CalDAV, contacts over CardDAV, on `httpx` + `xml.etree`.

Kept deliberately small instead of adopting the `caldav` package: that pulls
in lxml, dnspython, niquests, pyyaml and three iCalendar libraries, which is
most of a megabyte-plus of wheels for a handful of requests. WELLSY needs four
operations, and the server does the hard part:

  * discovery: current-user-principal → home set → collections (RFC 4791/6352);
  * a time-range REPORT with server-side `<C:expand>`, so recurring events
    arrive as concrete UTC instances and no recurrence engine is needed here;
  * PUT of a minimal VEVENT to create, and a GET/edit/PUT with If-Match to move;
  * one addressbook fetch, cached for ten minutes, filtered locally for
    contact search (a few hundred vCards; servers differ on text-match).

A moved recurring instance is refused with a clear error rather than risking
the whole series.
"""

from __future__ import annotations

import re
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from engine.agent.backends.accounts import DavAccount
from engine.agent.backends.base import Contact, Event, ToolError

TIMEOUT_S = 20
NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav", "card": "urn:ietf:params:xml:ns:carddav"}
_CONTACT_CACHE_S = 600


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt.astimezone() if dt.tzinfo is None else dt


def _local_iso(dt: datetime) -> str:
    return dt.astimezone().replace(microsecond=0).isoformat()


# --- iCalendar / vCard text -----------------------------------------------
def unfold(text: str) -> list[str]:
    out: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        elif line:
            out.append(line)
    return out


def _unescape(v: str) -> str:
    return re.sub(r"\\([\\;,nN])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), v)


def _escape(v: str) -> str:
    return v.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _prop(line: str) -> tuple[str, dict, str]:
    head, _, value = line.partition(":")
    name, *params = head.split(";")
    return name.upper(), dict(p.split("=", 1) for p in params if "=" in p), value


def parse_dt(value: str, params: dict) -> tuple[datetime, bool]:
    """(aware datetime, all_day). UTC 'Z', TZID-qualified, floating, or DATE."""
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        d = datetime.strptime(value[:8], "%Y%m%d")
        return d.astimezone(), True
    fmt = "%Y%m%dT%H%M%S"
    if value.endswith("Z"):
        return datetime.strptime(value[:-1], fmt).replace(tzinfo=timezone.utc), False
    naive = datetime.strptime(value, fmt)
    tzid = params.get("TZID", "").strip('"')
    if tzid:
        try:
            return naive.replace(tzinfo=ZoneInfo(tzid)), False
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return naive.astimezone(), False


def _duration(v: str) -> timedelta:
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", v)
    if not m:
        return timedelta(hours=1)
    sign = -1 if m.group(1) == "-" else 1
    w, d, h, mi, s = (int(x or 0) for x in m.groups()[1:])
    return sign * timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)


def parse_events(ics: str, href: str, calendar: str) -> list[Event]:
    events, cur = [], None
    for line in unfold(ics):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT" and cur is not None:
            if "DTSTART" in cur:
                start, all_day = parse_dt(*cur["DTSTART"])
                if "DTEND" in cur:
                    end, _ = parse_dt(*cur["DTEND"])
                elif "DURATION" in cur:
                    end = start + _duration(cur["DURATION"][0])
                else:
                    end = start + (timedelta(days=1) if all_day else timedelta(0))
                rid = cur.get("RECURRENCE-ID", ("", {}))[0]
                events.append(Event(
                    id=f"{href}#{rid}" if rid else href,
                    title=_unescape(cur.get("SUMMARY", ("(no title)", {}))[0]),
                    start=_local_iso(start), end=_local_iso(end), calendar=calendar,
                    location=_unescape(cur["LOCATION"][0]) if cur.get("LOCATION") else None,
                    notes=_unescape(cur["DESCRIPTION"][0])[:1000] if cur.get("DESCRIPTION") else None,
                ))
            cur = None
        elif cur is not None:
            name, params, value = _prop(line)
            cur.setdefault(name, (value, params))
    return events


def parse_vcard(vcf: str, href: str) -> Contact | None:
    name, org, emails, phones = "", None, [], []
    for line in unfold(vcf):
        key, params, value = _prop(line)
        key = key.split(".")[-1]  # item1.EMAIL
        if key == "FN":
            name = _unescape(value)
        elif key == "N" and not name:
            parts = _unescape(value).split(";")
            name = " ".join(p for p in (parts[1:2] + parts[:1]) if p)
        elif key == "ORG":
            org = _unescape(value).split(";")[0] or None
        elif key == "EMAIL" and value:
            emails.append(value.strip())
        elif key == "TEL" and value:
            phones.append(value.strip())
    if not (name or emails):
        return None
    return Contact(href, name or emails[0], emails, phones, org)


# --- WebDAV ---------------------------------------------------------------
class _Dav:
    home_prop = ""  # "c:calendar-home-set" | "card:addressbook-home-set"

    def __init__(self, account: DavAccount) -> None:
        self.acct = account
        self.http = httpx.Client(auth=(account.username, account.password), timeout=TIMEOUT_S,
                                 follow_redirects=True, headers={"User-Agent": "wellsy"})
        self._collections: list[dict] | None = None

    def _req(self, method: str, url: str, body: str | None = None, *, depth: str | None = None,
             headers: dict | None = None) -> httpx.Response:
        h = {"Content-Type": "application/xml; charset=utf-8"} if body and body.lstrip().startswith("<") else {}
        if depth is not None:
            h["Depth"] = depth
        h.update(headers or {})
        try:
            r = self.http.request(method, urljoin(self.acct.url, url), content=body, headers=h)
        except httpx.TimeoutException:
            raise ToolError(f"{self.acct.url} timed out", code="timeout") from None
        except httpx.HTTPError as e:
            raise ToolError(f"can't reach {self.acct.url}: {e}", code="unreachable") from None
        if r.status_code in (401, 403):
            raise ToolError(f"{self.acct.url} refused the login", code="auth_failed")
        if r.status_code == 404:
            raise ToolError(f"not found: {url}", code="not_found")
        if r.status_code == 412:
            raise ToolError("it changed on the server meanwhile; try again", code="conflict")
        if r.status_code >= 400:
            raise ToolError(f"{method} {url} -> HTTP {r.status_code}", code="backend_error")
        return r

    def _propfind(self, url: str, props: str, depth: str = "0") -> list[ET.Element]:
        body = f'<d:propfind xmlns:d="DAV:" xmlns:c="{NS["c"]}" xmlns:card="{NS["card"]}"><d:prop>{props}</d:prop></d:propfind>'
        return ET.fromstring(self._req("PROPFIND", url, body, depth=depth).content).findall("d:response", NS)

    def _href(self, url: str, prop: str) -> str:
        for resp in self._propfind(url, f"<{prop}/>"):
            el = resp.find(f".//{prop}/d:href", NS)
            if el is not None and el.text:
                return el.text.strip()
        raise ToolError(f"{self.acct.url} did not report {prop}", code="backend_error")

    def collections(self) -> list[dict]:
        if self._collections is None:
            principal = self._href(self.acct.url, "d:current-user-principal")
            home = self._href(principal, self.home_prop)
            out = []
            for resp in self._propfind(home, "<d:resourcetype/><d:displayname/><c:supported-calendar-component-set/>", "1"):
                href = resp.findtext("d:href", "", NS).strip()
                rt = resp.find(".//d:resourcetype", NS)
                if rt is None or not (rt.find("c:calendar", NS) is not None or rt.find("card:addressbook", NS) is not None):
                    continue
                comps = {c.get("name") for c in resp.findall(".//c:supported-calendar-component-set/c:comp", NS)}
                out.append({"href": href, "name": resp.findtext(".//d:displayname", "", NS) or href.rstrip("/").rsplit("/", 1)[-1],
                            "comps": comps})
            self._collections = out
        return self._collections

    def _report(self, href: str, body: str, data_tag: str) -> list[tuple[str, str, str]]:
        """[(href, etag, data)] from a REPORT multistatus."""
        root = ET.fromstring(self._req("REPORT", href, body, depth="1").content)
        out = []
        for resp in root.findall("d:response", NS):
            data = resp.findtext(f".//{data_tag}", "", NS)
            if data:
                out.append((resp.findtext("d:href", "", NS).strip(), resp.findtext(".//d:getetag", "", NS), data))
        return out


class CalDav(_Dav):
    home_prop = "c:calendar-home-set"

    def calendars(self) -> list[dict]:
        # no supported-component-set reported means "all components"
        return [c for c in self.collections() if not c["comps"] or "VEVENT" in c["comps"]]

    def list_events(self, start: str, end: str) -> list[Event]:
        s, e = _parse_iso(start), _parse_iso(end)
        tr = f'start="{_utc(s)}" end="{_utc(e)}"'
        body = (f'<c:calendar-query xmlns:d="DAV:" xmlns:c="{NS["c"]}"><d:prop><d:getetag/>'
                f'<c:calendar-data><c:expand {tr}/></c:calendar-data></d:prop>'
                f'<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">'
                f'<c:time-range {tr}/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
        out = []
        for cal in self.calendars():
            for href, _, ics in self._report(cal["href"], body, "c:calendar-data"):
                out.extend(ev for ev in parse_events(ics, href, cal["name"]) if s <= _parse_iso(ev.start) < e)
        return sorted(out, key=lambda ev: ev.start)

    def get_event(self, event_id: str) -> Event:
        href, _, rid = event_id.partition("#")
        cal = next((c["name"] for c in self.calendars() if href.startswith(c["href"])), "")
        events = parse_events(self._req("GET", href).text, href, cal)
        if rid:
            when, _ = parse_dt(rid, {})
            day = when.astimezone()
            hits = [ev for ev in self.list_events((day - timedelta(days=1)).isoformat(), (day + timedelta(days=1)).isoformat())
                    if ev.id == event_id]
            if hits:
                return hits[0]
            raise ToolError(f"no event {event_id!r}", code="not_found")
        if not events:
            raise ToolError(f"no event {event_id!r}", code="not_found")
        return events[0]

    def create_event(self, title, start, end, *, calendar="Home", location=None, notes=None) -> Event:
        cals = self.calendars()
        if not cals:
            raise ToolError("no calendar on this account accepts events", code="not_found")
        cal = next((c for c in cals if c["name"].lower() == (calendar or "").lower()), cals[0])
        uid = f"{uuid.uuid4()}@wellsy"
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//WELLSY//EN", "BEGIN:VEVENT", f"UID:{uid}",
                 f"DTSTAMP:{_utc(datetime.now(timezone.utc))}", f"DTSTART:{_utc(_parse_iso(start))}",
                 f"DTEND:{_utc(_parse_iso(end))}", f"SUMMARY:{_escape(title)}"]
        if location:
            lines.append(f"LOCATION:{_escape(location)}")
        if notes:
            lines.append(f"DESCRIPTION:{_escape(notes)}")
        lines += ["END:VEVENT", "END:VCALENDAR"]
        href = cal["href"].rstrip("/") + f"/{uid.split('@')[0]}.ics"
        self._req("PUT", href, "\r\n".join(lines) + "\r\n",
                  headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"})
        return self.get_event(href)  # read back what the server stored

    def move_event(self, event_id: str, new_start: str, new_end: str) -> Event:
        href, _, rid = event_id.partition("#")
        if rid:
            raise ToolError("that's one occurrence of a repeating event; moving it isn't supported yet",
                            code="unsupported")
        r = self._req("GET", href)
        ics, etag = r.text, r.headers.get("ETag")
        if "RRULE:" in ics:
            raise ToolError("that's a repeating event; moving the whole series isn't supported yet", code="unsupported")
        out, in_event = [], False
        for line in unfold(ics):
            if line == "BEGIN:VEVENT":
                in_event = True
            elif line == "END:VEVENT":
                in_event = False
            elif in_event:
                name = _prop(line)[0]
                if name == "DTSTART":
                    line = f"DTSTART:{_utc(_parse_iso(new_start))}"
                elif name == "DTEND":
                    line = f"DTEND:{_utc(_parse_iso(new_end))}"
                elif name == "DURATION":
                    line = f"DTEND:{_utc(_parse_iso(new_end))}"
            out.append(line)
        headers = {"Content-Type": "text/calendar; charset=utf-8"}
        if etag:
            headers["If-Match"] = etag
        self._req("PUT", href, "\r\n".join(out) + "\r\n", headers=headers)
        return self.get_event(href)


class CardDav(_Dav):
    home_prop = "card:addressbook-home-set"

    def __init__(self, account: DavAccount) -> None:
        super().__init__(account)
        self._all: tuple[float, list[Contact]] | None = None

    def _everyone(self) -> list[Contact]:
        if self._all and time.monotonic() - self._all[0] < _CONTACT_CACHE_S:
            return self._all[1]
        body = (f'<card:addressbook-query xmlns:d="DAV:" xmlns:card="{NS["card"]}">'
                f'<d:prop><d:getetag/><card:address-data/></d:prop></card:addressbook-query>')
        people = []
        for book in self.collections():
            for href, _, vcf in self._report(book["href"], body, "card:address-data"):
                if (c := parse_vcard(vcf, href)) is not None:
                    people.append(c)
        self._all = (time.monotonic(), people)
        return people

    def search(self, query: str) -> list[Contact]:
        q = query.lower().strip()
        hits = [c for c in self._everyone()
                if q in " ".join([c.name, *c.emails, c.organization or ""]).lower()]
        return hits[:10]

    def get(self, contact_id: str) -> Contact:
        c = parse_vcard(self._req("GET", contact_id).text, contact_id)
        if c is None:
            raise ToolError(f"no contact {contact_id!r}", code="not_found")
        return c

    def names(self) -> list[str]:
        return [c.name for c in self._everyone() if c.name]
