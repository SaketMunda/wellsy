"""Read-only probe of the connected accounts (`wellsy accounts add` first).

It never writes, and it prints **counts and timings only** — no subjects,
senders, titles or bodies.

    .venv/bin/python bench/pim_probe.py [contact-query]
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
    from engine.agent.backends.standard import AccountsPimBackend

    b = AccountsPimBackend()
    a = b.accounts
    print(f"mail: {'connected' if a.mail else 'not connected'} · calendar: "
          f"{'connected' if a.calendar else 'not connected'} · contacts: {'connected' if a.contacts else 'from mail'}")
    query = sys.argv[1] if len(sys.argv) > 1 else "a"
    now = dt.datetime.now().astimezone().replace(microsecond=0)
    day = now.replace(hour=0, minute=0, second=0)
    rows = [
        timed("mail: inbox count (login)", lambda: [None] * b.mail.check()),
        timed("mail: newest 10 in inbox", lambda: b.list_messages(limit=10)),
        timed("mail: newest 10 again (warm)", lambda: b.list_messages(limit=10)),
        timed("mail: newest 5 sent", lambda: b.list_sent(limit=5)),
        timed(f"contacts: search {query!r}", lambda: b.search_contacts(query)),
    ]
    if a.calendar:
        rows += [
            timed("calendar: today + tomorrow", lambda: b.list_events(day.isoformat(), (day + dt.timedelta(days=2)).isoformat())),
            timed("calendar: next 7 days", lambda: b.list_events(day.isoformat(), (day + dt.timedelta(days=7)).isoformat())),
        ]
    out = Path(__file__).resolve().parents[1] / "spec" / "results" / f"pim-probe-{now:%Y-%m-%d-%H%M}.json"
    out.write_text(json.dumps({"date": now.isoformat(), "backend": "accounts",
                               "calendar": bool(a.calendar), "contacts": bool(a.contacts), "calls": rows}, indent=2) + "\n")
    print(f"wrote {out}")
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
