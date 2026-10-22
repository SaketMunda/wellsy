"""The user's real accounts, reached over standard protocols.

Mail is IMAP + SMTP, calendar is CalDAV, contacts are CardDAV. Every OS and
every mail provider speaks them, so the same code runs on a cheap Linux laptop
and on a Mac, with no app running and no per-OS automation layer. Mail uses
only the Python standard library; CalDAV/CardDAV use `httpx`, already a
WELLSY dependency.

Setup is one step: `wellsy accounts add` asks for an address and an app
password, finds the servers from the provider table below, tests the login,
and saves to `~/.config/wellsy/accounts.json` (mode 0600). Env vars
`WELLSY_MAIL_ADDRESS` + `WELLSY_MAIL_PASSWORD` work without a file.

What a provider needs is stated, not guessed: Gmail's IMAP takes an app
password, but Google's CalDAV/CardDAV need OAuth, so a Gmail account connects
mail only and says so. Outlook/Microsoft 365 turned off password IMAP, so it is
refused with that reason instead of failing at login.
"""

from __future__ import annotations

import getpass
import json
import os
import stat
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class MailAccount:
    address: str
    password: str
    imap_host: str
    smtp_host: str
    imap_port: int = 993
    smtp_port: int = 465          # 465 = implicit TLS, 587 = STARTTLS
    username: str | None = None    # defaults to the address
    smtp_saves_sent: bool = False  # Gmail files sent mail itself; others need an APPEND

    @property
    def login(self) -> str:
        return self.username or self.address


@dataclass(frozen=True)
class DavAccount:
    url: str
    username: str
    password: str


@dataclass(frozen=True)
class Accounts:
    mail: MailAccount | None = None
    calendar: DavAccount | None = None
    contacts: DavAccount | None = None


# domain -> servers. calendar/contacts None means the provider needs OAuth for
# them (the reason is kept so the user hears why, not "not found").
PROVIDERS: dict[str, dict] = {
    "gmail": {
        "domains": ("gmail.com", "googlemail.com"),
        "imap": ("imap.gmail.com", 993), "smtp": ("smtp.gmail.com", 465),
        "smtp_saves_sent": True,
        "calendar": None, "contacts": None,
        "dav_note": "Google calendar and contacts need Google sign-in (OAuth), not an app password",
        "password_help": "https://myaccount.google.com/apppasswords (needs 2-Step Verification on)",
    },
    "icloud": {
        "domains": ("icloud.com", "me.com", "mac.com"),
        "imap": ("imap.mail.me.com", 993), "smtp": ("smtp.mail.me.com", 587),
        "calendar": "https://caldav.icloud.com/", "contacts": "https://contacts.icloud.com/",
        "password_help": "https://account.apple.com → Sign-In and Security → App-Specific Passwords",
    },
    "yahoo": {
        "domains": ("yahoo.com", "yahoo.co.in", "yahoo.co.uk", "ymail.com"),
        "imap": ("imap.mail.yahoo.com", 993), "smtp": ("smtp.mail.yahoo.com", 465),
        "calendar": "https://caldav.calendar.yahoo.com/", "contacts": "https://carddav.address.yahoo.com/",
        "password_help": "Yahoo Account Security → Generate app password",
    },
    "fastmail": {
        "domains": ("fastmail.com", "fastmail.fm"),
        "imap": ("imap.fastmail.com", 993), "smtp": ("smtp.fastmail.com", 465),
        "calendar": "https://caldav.fastmail.com/", "contacts": "https://carddav.fastmail.com/",
        "password_help": "Fastmail Settings → Privacy & Security → App passwords",
    },
    "zoho": {
        "domains": ("zoho.com", "zohomail.com", "zoho.in"),
        "imap": ("imap.zoho.com", 993), "smtp": ("smtp.zoho.com", 465),
        "calendar": None, "contacts": None,
        "dav_note": "Zoho calendar/contacts are not set up here yet",
        "password_help": "Zoho Accounts → Security → App Passwords",
    },
}
UNSUPPORTED = {
    ("outlook.com", "hotmail.com", "live.com", "msn.com"):
        "Microsoft turned off password sign-in for Outlook mail; it needs Microsoft sign-in (OAuth), not supported yet",
}


def provider_for(address: str) -> tuple[str | None, dict | None, str | None]:
    """(name, provider, refusal). Unknown domains return (None, None, None):
    the caller asks for server names instead of guessing."""
    domain = address.rsplit("@", 1)[-1].strip().lower()
    for domains, why in UNSUPPORTED.items():
        if domain in domains:
            return None, None, why
    for name, p in PROVIDERS.items():
        if domain in p["domains"]:
            return name, p, None
    return None, None, None


def config_path() -> Path:
    override = os.environ.get("WELLSY_ACCOUNTS")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "wellsy" / "accounts.json"


def _mail_from_address(address: str, password: str) -> MailAccount:
    _, p, why = provider_for(address)
    if why:
        raise ValueError(why)
    if p is None:
        raise ValueError(f"unknown mail provider for {address!r}; set imap_host/smtp_host in {config_path()}")
    return MailAccount(address, password, p["imap"][0], p["smtp"][0], p["imap"][1], p["smtp"][1],
                       smtp_saves_sent=p.get("smtp_saves_sent", False))


def load_accounts() -> Accounts:
    """Env vars first (no file needed), then the config file. Missing is not
    an error here: each tool reports its own service as not connected."""
    env_addr, env_pw = os.environ.get("WELLSY_MAIL_ADDRESS"), os.environ.get("WELLSY_MAIL_PASSWORD")
    data: dict = {}
    path = config_path()
    if path.exists():
        data = json.loads(path.read_text())
    mail = None
    if env_addr and env_pw:
        mail = _mail_from_address(env_addr, env_pw)
    elif data.get("mail"):
        mail = MailAccount(**data["mail"])
    cal = DavAccount(**data["calendar"]) if data.get("calendar") else None
    con = DavAccount(**data["contacts"]) if data.get("contacts") else None
    if mail and not data.get("mail") and cal is None and con is None:
        # env-only: derive DAV from the provider table with the same password
        _, p, _ = provider_for(mail.address)
        if p and p.get("calendar"):
            cal = DavAccount(p["calendar"], mail.address, mail.password)
        if p and p.get("contacts"):
            con = DavAccount(p["contacts"], mail.address, mail.password)
    return Accounts(mail, cal, con)


def save_accounts(acc: Accounts) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {k: asdict(v) for k, v in (("mail", acc.mail), ("calendar", acc.calendar), ("contacts", acc.contacts)) if v}
    # create with 0600 before writing: the file holds an app password
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w") as f:
        json.dump(body, f, indent=2)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


def cli(argv: list[str]) -> int:
    """`wellsy accounts add | show | remove`."""
    cmd = argv[0] if argv else "show"
    if cmd == "show":
        acc = load_accounts()
        print(f"config: {config_path()}")
        print(f"  mail:     {acc.mail.address if acc.mail else 'not connected'}")
        print(f"  calendar: {acc.calendar.url if acc.calendar else 'not connected'}")
        print(f"  contacts: {acc.contacts.url if acc.contacts else 'not connected (contacts come from your mail)'}")
        return 0
    if cmd == "remove":
        config_path().unlink(missing_ok=True)
        print("removed")
        return 0
    if cmd != "add":
        print("usage: wellsy accounts [add | show | remove]", file=sys.stderr)
        return 2

    address = input("Email address: ").strip()
    name, p, why = provider_for(address)
    if why:
        print(f"Can't connect {address}: {why}.", file=sys.stderr)
        return 1
    if p is None:
        imap = input("IMAP server (host[:port]): ").strip()
        smtp = input("SMTP server (host[:port], 465 or 587): ").strip()
        ih, _, ip = imap.partition(":")
        sh, _, sp = smtp.partition(":")
        p = {"imap": (ih, int(ip or 993)), "smtp": (sh, int(sp or 465)), "calendar": None, "contacts": None}
    else:
        print(f"Provider: {name}. App password: {p['password_help']}")
    password = getpass.getpass("App password: ").replace(" ", "")
    mail = MailAccount(address, password, p["imap"][0], p["smtp"][0], p["imap"][1], p["smtp"][1],
                       smtp_saves_sent=p.get("smtp_saves_sent", False))

    from engine.agent.backends.mail import ImapMail
    from engine.agent.backends.base import ToolError

    try:
        n = ImapMail(mail).check()
    except ToolError as e:
        print(f"Mail login failed: {e}", file=sys.stderr)
        return 1
    print(f"Mail connected: {n} messages in the inbox.")

    cal = DavAccount(p["calendar"], address, password) if p.get("calendar") else None
    con = DavAccount(p["contacts"], address, password) if p.get("contacts") else None
    if cal or con:
        from engine.agent.backends.dav import CalDav, CardDav

        for label, acct, cls in (("Calendar", cal, CalDav), ("Contacts", con, CardDav)):
            if acct is None:
                continue
            try:
                print(f"{label} connected: {len(cls(acct).collections())} collection(s).")
            except ToolError as e:
                print(f"{label} not connected: {e}")
                if label == "Calendar":
                    cal = None
                else:
                    con = None
    elif p.get("dav_note"):
        print(f"Calendar and contacts: not connected. {p['dav_note']}. Contacts will come from your mail.")
    print(f"Saved to {save_accounts(Accounts(mail, cal, con))}")
    return 0
