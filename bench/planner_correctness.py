"""Planner correctness, not just validity (step 9).

5b/5c scored the planner on *schema-valid* plans. The step-9 replay showed that
is not enough: a valid plan booked a dentist appointment as a note, drafted an
email it was asked to send, and resolved "tomorrow" to the wrong day. This
bench checks each plan against what the request needs — the right tool, the
right resolved date and time, ids threaded by reference, and no mutation the
user did not ask for.

The planner is the production one (`graph.make_model_planner`: prompt, day
table, tool signatures from the live MCP catalog); only the model is swapped
via `WELLSY_PLANNER_MODEL`. Temperature 0, so one run per phrasing; two
phrasings per intent.

    .venv/bin/python bench/planner_correctness.py --models qwen3.5:4b-q4_K_M qwen3:4b-instruct-2507-q4_K_M
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _next(weekday: int, today: dt.date) -> dt.date:
    d = (weekday - today.weekday()) % 7
    return today + dt.timedelta(days=d or 7)


def _when(v):
    from engine.agent.readback import parse_when

    return parse_when(v)


def _tools(plan):
    return [s.get("tool") for s in plan]


MUTATIONS = {"pim.calendar_create_event", "pim.calendar_move_event", "pim.reminders_create",
             "pim.reminders_complete", "pim.mail_create_draft", "pim.mail_send_draft",
             "pim.notes_create", "fs.fs_write_file", "fs.fs_delete_file"}


def cases(today: dt.date):
    tomorrow = today + dt.timedelta(days=1)
    monday, thursday = _next(0, today), _next(3, today)

    def only(plan, allowed):
        return all(t not in MUTATIONS or t in allowed for t in _tools(plan))

    def step(plan, tool):
        return next((s for s in plan if s.get("tool") == tool), None)

    def c_read(plan):
        s = step(plan, "pim.calendar_list_events")
        return bool(s) and only(plan, set()) and (_when(s["args"].get("start")) or dt.datetime.min).date() == tomorrow

    def c_remind(plan):
        s = step(plan, "pim.reminders_create")
        w = _when((s or {}).get("args", {}).get("due"))
        return bool(s) and only(plan, {"pim.reminders_create"}) and w is not None \
            and (w.date(), w.hour) == (tomorrow, 18)

    def c_book(plan):
        s = step(plan, "pim.calendar_create_event")
        w = _when((s or {}).get("args", {}).get("start"))
        return bool(s) and only(plan, {"pim.calendar_create_event"}) and w is not None \
            and (w.date(), w.hour) == (monday, 15) and "dentist" in str(s["args"].get("title", "")).lower()

    def c_delete(plan):
        s = step(plan, "fs.fs_delete_file")
        return bool(s) and only(plan, {"fs.fs_delete_file"}) and str(s["args"].get("path", "")).endswith("plan.txt")

    def c_draft_send(plan):
        t = _tools(plan)
        if "pim.mail_create_draft" not in t or "pim.mail_send_draft" not in t:
            return False
        i = t.index("pim.mail_create_draft")
        send = step(plan, "pim.mail_send_draft")
        return str(send["args"].get("draft_id", "")) in (f"${i + 1}.id", f"$s{i + 1}.id") \
            and only(plan, {"pim.mail_create_draft", "pim.mail_send_draft"})

    def c_move(plan):
        s = step(plan, "pim.calendar_move_event")
        w = _when((s or {}).get("args", {}).get("new_start"))
        return bool(s) and only(plan, {"pim.calendar_move_event"}) and w is not None \
            and (w.date(), w.hour) == (thursday, 14)

    def c_add_reminder(plan):
        s = step(plan, "pim.reminders_create")
        return bool(s) and only(plan, {"pim.reminders_create"}) and "milk" in str(s["args"].get("title", "")).lower()

    def c_question(plan):
        return only(plan, set())          # a question about the past changes nothing

    return [
        ("read", c_read, ["What's on my calendar tomorrow?", "Do I have anything scheduled tomorrow?"]),
        ("remind", c_remind, ["Remind me to call mom tomorrow at 6 pm.", "Set a reminder for tomorrow at 6pm to call mom."]),
        ("book", c_book, ["Book a dentist appointment on Monday at 3 pm.", "Put a dentist appointment on my calendar for Monday at 3pm."]),
        ("delete", c_delete, ["Delete the file plan.txt in my scratch folder.", "Remove plan.txt from scratch."]),
        ("draft+send", c_draft_send, ["Draft a reply to Dana saying Thursday works for us, and send it.",
                                      "Email Sam that I'm running late and send it."]),
        ("move", c_move, ["Move my design review to Thursday at 2 pm.", "Reschedule the design review to 2pm on Thursday."]),
        ("add", c_add_reminder, ["Add buying milk to my reminders.", "Remind me to buy milk."]),
        ("question", c_question, ["What did I just ask you to send?", "Did you send the email to Dana?"]),
    ]


async def run(models: list[str], out: Path) -> dict:
    from engine.agent.graph import make_model_planner
    from engine.agent.mcp_client import AgentTools

    async with AgentTools() as t:
        catalog = t.list_tools()
    today = dt.date.today()
    summary = {}
    with open(out, "w") as f:
        for model in models:
            os.environ["WELLSY_PLANNER_MODEL"] = model
            planner = make_model_planner()
            planner("warm up", catalog)
            ok, times = 0, []
            n = 0
            per = {}
            for name, check, phrasings in cases(today):
                for say in phrasings:
                    t0 = time.perf_counter()
                    res = planner(say, catalog)
                    ms = round((time.perf_counter() - t0) * 1000)
                    plan = res.get("plan") or []
                    good = check(plan) if name == "question" else (bool(plan) and check(plan))
                    ok += good
                    n += 1
                    times.append(ms)
                    per.setdefault(name, []).append(good)
                    row = {"model": model, "case": name, "say": say, "ok": good, "ms": ms, "plan": plan,
                           "clarify": res.get("clarify")}
                    f.write(json.dumps(row) + "\n")
                    print(json.dumps(row)[:400], flush=True)
            summary[model] = {"correct": f"{ok}/{n}", "planMs_p50": statistics.median(times),
                              "planMs_max": max(times),
                              "byCase": {k: f"{sum(v)}/{len(v)}" for k, v in per.items()}}
        f.write(json.dumps({"summary": summary, "date": today.isoformat(),
                            "method": "production planner prompt + live MCP catalog, temperature 0, "
                                      "one run per phrasing, checks in bench/planner_correctness.py"}) + "\n")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["qwen3.5:4b-q4_K_M", "qwen3:4b-instruct-2507-q4_K_M"])
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = Path(a.out) if a.out else REPO / "spec" / "results" / f"planner-correctness-{dt.datetime.now():%Y-%m-%d-%H%M}.jsonl"
    print(json.dumps(asyncio.run(run(a.models, out)), indent=2))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
