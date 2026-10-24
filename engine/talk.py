"""`wellsy talk`, `wellsy ask`, `wellsy report`.

    wellsy talk                 # talk to WELLSY through the browser page (echo-cancelled), orb + HUD
    wellsy talk --no-orb        # same, no window
    wellsy talk --local         # the mic and speakers directly, no echo cancellation (headphones)
    wellsy talk --local --out "MacBook Pro Speakers"   # pick the speaker (or --in for the mic) by name
    wellsy talk --eval 8765     # serve Pipecat's eval transport instead of the mic
    wellsy ask "question"       # the brain alone, typed, answer printed (cost logged)
    wellsy report               # latency p50/p95, cost per task per brain, echo

The preset and brain come from engine/settings.toml (`preset`, `brain`), or from
WELLSY_PRESET / WELLSY_BRAIN for one run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from engine import runs
from engine import settings as cfg


def talk(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="wellsy talk")
    ap.add_argument("--no-orb", action="store_true", help="no orb/HUD window")
    ap.add_argument("--eval", type=int, metavar="PORT", help="serve Pipecat's eval transport on PORT")
    ap.add_argument("--local", action="store_true", help="mic and speakers directly, not the browser page")
    ap.add_argument("--no-browser", action="store_true", help="serve the page but don't open it")
    ap.add_argument("--in", dest="mic", default="", help="microphone, by part of its name")
    ap.add_argument("--out", dest="speaker", default="", help="speaker, by part of its name")
    args = ap.parse_args(argv)

    cfg.load_env()
    settings = cfg.load()
    from engine import voice

    if args.eval:
        async def _eval() -> None:
            await voice.run(settings, await voice.eval_transport(args.eval))
        asyncio.run(_eval())
        return 0
    local = args.local or args.mic or args.speaker or settings["voice"].get("transport") == "local"
    if local:
        transport = voice.local_transport(args.mic, args.speaker)

    def session(sess=None, stop=None):
        if local:
            return voice.run(settings, transport, session=sess, stop=stop)
        from engine import webrtc
        return webrtc.serve(settings, session=sess, stop=stop, open_browser=not args.no_browser)

    if args.no_orb:
        asyncio.run(session())
        return 0

    from engine.interface.session import OrbSession

    sess = OrbSession()
    sess.run(lambda stop: session(sess, stop))
    return 0


def ask(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="wellsy ask")
    ap.add_argument("task", nargs="+")
    args = ap.parse_args(argv)

    cfg.load_env()
    settings = cfg.load()
    from dataclasses import asdict

    from engine import brain

    task = " ".join(args.task)

    async def on_step(step: brain.Step) -> None:
        print(f"  · {step.kind}: {step.text}", flush=True)

    res = asyncio.run(brain.run(task, settings, on_step))
    runs.log("tasks", {"task_id": "ask", "label": "ask", "preset": settings["preset"],
                       **asdict(res), "cost": round(res.cost, 6)})
    print(f"\n{res.spoken}\n\n{res.answer}\n")
    for s in res.sources:
        print(f"  [{s['title']}] {s['url']}")
    print(f"\n{res.model}  {res.status}  {res.secs:.1f} s  "
          f"${res.llm_cost:.4f} LLM + ${res.search_cost:.4f} search ({res.search_calls}) = ${res.cost:.4f}")
    if res.error:
        print(f"error: {res.error}")
    return 0 if res.status == "done" else 1


def report(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="wellsy report")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    lat: dict[str, list[float]] = {}
    for r in runs.read("latency"):
        lat.setdefault(r.get("voice", "?"), []).append(float(r["secs"]))
    cost: dict[str, list[dict]] = {}
    for r in runs.read("tasks"):
        cost.setdefault(r.get("model", "?"), []).append(r)
    users = [r for r in runs.read("turns") if r.get("event") == "user"]
    out = {
        "latency_secs": {v: runs.summary(xs) for v, xs in lat.items()},
        "tasks": {m: {"n": len(rs), "done": sum(r["status"] == "done" for r in rs),
                      "cost_per_task": round(sum(r["cost"] for r in rs) / len(rs), 5),
                      "llm_cost_per_task": round(sum(r["llm_cost"] for r in rs) / len(rs), 5),
                      "secs": runs.summary([r["secs"] for r in rs])} for m, rs in cost.items()},
        "echo": {"user_turns": len(users),
                 "suspect_echo": sum(r.get("bot_overlap", 0) >= 0.6 and len(r.get("text", "").split()) >= 3
                                     for r in users),
                 "interruptions": sum(r.get("event") == "interruption" for r in runs.read("turns"))},
    }
    if args.json:
        print(json.dumps(out, indent=1))
        return 0
    print("Latency, end of user speech (VAD stop) -> first audio out")
    for v, s in out["latency_secs"].items():
        print(f"  {v}: n={s['n']}  p50={s.get('p50', 0) * 1000:.0f} ms  p95={s.get('p95', 0) * 1000:.0f} ms")
    print("Cost per task (OpenRouter usage.cost + search at list price)")
    for m, t in out["tasks"].items():
        print(f"  {m}: n={t['n']} done={t['done']}  ${t['cost_per_task']:.4f}/task "
              f"(LLM ${t['llm_cost_per_task']:.4f})  p50 {t['secs'].get('p50', 0):.1f} s")
    e = out["echo"]
    print(f"Echo: {e['suspect_echo']} of {e['user_turns']} user turns repeat the bot's own words; "
          f"{e['interruptions']} interruptions")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    return {"talk": talk, "ask": ask, "report": report}[argv[0]](argv[1:])
