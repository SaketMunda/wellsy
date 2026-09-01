"""`wellsy agent` / `wellsy tools` / `wellsy audit` / `wellsy autonomy`.

The approval surface for step 5 is CLI and typed text (Deliverable 5) — the
native UI is a later step and a *client* of this runtime, not part of it (D54).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from engine.agent import audit
from engine.agent.autonomy import AutonomyLedger
from engine.agent.mcp_client import AgentTools
from engine.agent.runner import auto_approver, run_agent


def _cli_approver(request: dict) -> dict:
    print("\n─── approval required ───────────────────────────────────", file=sys.stderr)
    print(f"  tool     : {request['tool']}", file=sys.stderr)
    print(f"  args     : {json.dumps(request['args'], default=str)}", file=sys.stderr)
    print(f"  risk     : {request['risk']}   capability: {request['capability']}", file=sys.stderr)
    print(f"  why      : {request.get('why','')}", file=sys.stderr)
    print(f"  policy   : {request['reason']}", file=sys.stderr)
    try:
        ans = input("  approve? [y/N] ").strip().lower()
    except EOFError:
        ans = "n"
    return {"approved": ans in ("y", "yes"), "source": "user:cli"}


def _event_printer(ev: dict) -> None:
    t = ev.get("type")
    if t == "ack":
        print(f"… {ev['text']}", file=sys.stderr)
    elif t == "plan_start":
        print(f"[agent] planning: {ev['outcome']}", file=sys.stderr)
    elif t == "approval_answer":
        verdict = "approved" if ev["answer"].get("approved") else "declined"
        print(f"[agent] {ev['request']['tool']} {verdict} by {ev['answer'].get('source')}", file=sys.stderr)


def run_agent_cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="wellsy agent", description="Run one agent outcome by typed text.")
    ap.add_argument("outcome", help="what you want done, in plain language")
    ap.add_argument("--yes", action="store_true", help="approve every gated step without prompting (no human in the loop)")
    ap.add_argument("--json", action="store_true", help="emit the AgentResult as JSON on stdout")
    ap.add_argument("--no-models", action="store_true", help="fail instead of calling the planner LLM (debug)")
    args = ap.parse_args(argv)

    approver = auto_approver if args.yes else _cli_approver
    res = asyncio.run(run_agent(
        args.outcome, approver=approver, on_event=_event_printer,
        use_models=not args.no_models,
    ))

    if args.json:
        print(json.dumps({
            "outcome": res.outcome, "planId": res.plan_id, "status": res.status,
            "report": res.report, "clarifyingQuestion": res.clarifying_question,
            "plan": res.plan, "stepResults": res.step_results, "approvals": res.approvals,
        }, indent=2, default=str))
    else:
        print(res.report)
        print(f"\n[status: {res.status} · plan {res.plan_id} · "
              f"{len(res.step_results)} step(s) · see `wellsy audit --plan {res.plan_id}`]",
              file=sys.stderr)
    return 0 if res.status in ("ok", "clarify") else 1


def list_tools_cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="wellsy tools")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    async def _load():
        async with AgentTools() as t:
            return t.list_tools()

    tools = asyncio.run(_load())
    if args.json:
        print(json.dumps(tools, indent=2, default=str))
    else:
        print(f"{len(tools)} MCP tools:\n")
        for t in tools:
            print(f"  {t['key']}")
            print(f"      {t['description'].splitlines()[0] if t['description'] else ''}")
        print(f"\n{len(tools)} tools across "
              f"{len({t['server'] for t in tools})} servers.")
    return 0 if len(tools) >= 15 else 2


def audit_cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="wellsy audit", description="Read the agent audit log (JSONL on disk).")
    ap.add_argument("--plan", default=None, help="only this plan id")
    ap.add_argument("--tail", type=int, default=20, help="show the last N actions")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    rows = audit.summarize(plan_id=args.plan)[-args.tail:]
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0
    if not rows:
        print("no audit entries")
        return 0
    for r in rows:
        rb = r.get("readBack") or {}
        verified = rb.get("verified")
        vflag = "verified" if verified else ("unverified" if verified is False else "n/a")
        print(f"  {r.get('t')}  {r['tool']:<28}  risk{r.get('risk')}  "
              f"{r.get('policyDecision'):<7}  {r.get('outcome'):<10}  read-back:{vflag}  "
              f"[{r.get('approvalSource') or '-'}]")
        if r.get("error"):
            print(f"      └─ {r['error']}")
    return 0


def autonomy_cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="wellsy autonomy", description="Autonomy levels — they rise against the audit log.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    status = AutonomyLedger().status()
    if args.json:
        print(json.dumps(status, indent=2))
        return 0
    if not status:
        print("no risk-2 action classes seen in the audit log yet — all still gated")
        return 0
    for s in status:
        state = "SILENT (promoted)" if s["promoted"] else "gated — needs approval"
        print(f"  {s['capability']:<20}  {s['cleanRuns']}/{s['threshold']} clean runs  →  {state}")
    return 0
