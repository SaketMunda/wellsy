"""Read-only probe of the macOS PIM backend against the real accounts.

Run it from the same terminal you run `wellsy run` in (macOS grants Automation
and Calendar access per app, so permissions from another app don't carry over).
It never writes, and it prints **counts and timings only** — no subjects,
senders, titles or bodies.

    .venv/bin/python bench/macos_pim_probe.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def timed(label, fn):
    t0 = time.perf_counter()
    try:
        out = fn()
        ms = (time.perf_counter() - t0) * 1000
        n = len(out) if hasattr(out, "__len__") else 1
        print(f"  OK    {label:<38} {ms:8.0f} ms   {n} item(s)")
        return {"call": label, "ok": True, "ms": round(ms), "n": n}
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        print(f"  FAIL  {label:<38} {ms:8.0f} ms   {type(e).__name__}: {str(e)[:120]}")
        return {"call": label, "ok": False, "ms": round(ms), "error": f"{type(e).__name__}: {e}"[:300]}


def main() -> int:
    from engine.agent.backends.macos import MacPimBackend, _EventKit

    b = MacPimBackend()
    now = dt.datetime.now().astimezone().replace(microsecond=0)
    day = now.replace(hour=0, minute=0, second=0)
    ek = _EventKit.get()
    print(f"calendar path: {'EventKit (access granted)' if ek else 'osascript fallback (EventKit unavailable or access not granted)'}")
    rows = [
        timed("calendar: today + tomorrow", lambda: b.list_events(day.isoformat(), (day + dt.timedelta(days=2)).isoformat())),
        timed("calendar: next 7 days", lambda: b.list_events(day.isoformat(), (day + dt.timedelta(days=7)).isoformat())),
        timed("mail: newest 10 in inbox", lambda: b.list_messages(limit=10)),
        timed("mail: newest 5 sent", lambda: b.list_sent(limit=5)),
        timed("reminders: default list", lambda: b.list_reminders()),
        timed("contacts: search 'a'", lambda: b.search_contacts("a")),
    ]
    out = Path(__file__).resolve().parents[1] / "spec" / "results" / f"macos-pim-probe-{now:%Y-%m-%d-%H%M}.json"
    out.write_text(json.dumps({"date": now.isoformat(), "calendarPath": "eventkit" if ek else "osascript",
                               "calls": rows}, indent=2) + "\n")
    print(f"wrote {out}")
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
