"""End-to-end agent runtime — acceptance items 1-7 from step5-agent-runtime.md,
all driven by typed text with a *scripted* planner (no LLM in the test path).

The graph, policy gate, MCP servers, audit log, read-back verification and
`interrupt()`-based approval are all real.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json

import pytest

from engine.agent import audit
from engine.agent.graph import deterministic_report
from engine.agent.runner import auto_approver, deny_approver, run_agent


def run(coro):
    return asyncio.run(coro)


def _plan(*steps):
    def planner(outcome, catalog):
        return {"plan": list(steps)}
    return planner


def _iso(days, hour, minute=0):
    d = dt.date.today() + dt.timedelta(days=days)
    return dt.datetime.combine(d, dt.time(hour, minute)).isoformat()


# --- item 1 ----------------------------------------------------------------
def test_list_tools_returns_15_plus_with_schemas(agent_env):
    from engine.agent.mcp_client import AgentTools

    async def _go():
        async with AgentTools() as t:
            return t.list_tools()

    tools = run(_go())
    assert len(tools) >= 15
    for entry in tools:
        assert entry["key"] and entry["description"]
        assert entry["inputSchema"] is None or entry["inputSchema"]["type"] == "object"


# --- item 4 / A4 ---------------------------------------------------------------
def test_reversible_mutation_is_gated_and_verified_by_readback(agent_env):
    planner = _plan(
        {"tool": "pim.calendar_get_event", "args": {"event_id": "evt-review"}, "why": "look up"},
        {"tool": "pim.calendar_move_event",
         "args": {"event_id": "evt-review", "new_start": _iso(3, 15), "new_end": _iso(3, 16)},
         "why": "move it"},
    )
    seen = []
    res = run(run_agent("Move my design review to Thursday", approver=auto_approver,
                        planner=planner, reporter=deterministic_report, use_models=False,
                        on_event=seen.append))

    assert res.status == "ok"
    move = [s for s in res.step_results if s["tool"] == "pim.calendar_move_event"][0]
    assert move["status"] == "ok"
    # the read-back is an INDEPENDENT get_event, not the move's own return
    assert "calendar_get_event" in move["readBack"]["method"]
    assert move["readBack"]["verified"] is True
    # it was gated
    assert any(e["type"] == "approval_request" for e in seen)

    # audit line for the move written with a read-back result
    a = [r for r in audit.summarize(plan_id=res.plan_id) if r["tool"] == "pim.calendar_move_event"][0]
    assert a["policyDecision"] == "confirm" and a["outcome"] == "ok"
    assert a["readBack"]["verified"] is True


# --- item 2 / A5 + A6 -------------------------------------------------------
def test_draft_then_send_denied_does_not_send(agent_env):
    planner = _plan(
        {"tool": "pim.mail_create_draft",
         "args": {"to": ["dana.kim@partner.example"], "subject": "Re: integration timeline",
                  "body": "Thursday works for us."}, "why": "draft the reply"},
        {"tool": "pim.mail_send_draft", "args": {"draft_id": "will-be-ignored"}, "why": "send"},
    )
    # NOTE: scripted draft_id is wrong on purpose is NOT what we test here; use a
    # planner that threads the real id via a read is overkill — instead run the
    # draft step, then a send step whose id we patch from the draft result.

    async def _drive():
        # first: just the draft, confirm nothing sent (A5)
        r1 = await run_agent("Draft a reply to Dana", approver=deny_approver,
                             planner=_plan({"tool": "pim.mail_create_draft",
                                            "args": {"to": ["dana.kim@partner.example"],
                                                     "subject": "Re: integration timeline",
                                                     "body": "Thursday works."},
                                            "why": "draft"}),
                             reporter=deterministic_report, use_models=False)
        draft_id = r1.step_results[0]["result"]["id"]
        return r1, draft_id

    r1, draft_id = run(_drive())
    assert r1.status == "ok"
    # A5: sent folder unchanged (seed has exactly one sent message)
    from engine.agent.backends import get_pim_backend
    assert len(get_pim_backend().list_sent()) == 1

    # A6: send it, but deny the approval
    send_planner = _plan({"tool": "pim.mail_send_draft", "args": {"draft_id": draft_id}, "why": "send"})
    r2 = run(run_agent("Send it", approver=deny_approver, planner=send_planner,
                       reporter=deterministic_report, use_models=False))
    assert r2.status == "failed"
    step = r2.step_results[0]
    assert step["status"] == "denied"
    assert step["attempts"] == 0            # never executed
    assert "not run" in deterministic_report("Send it", r2.step_results, "failed").lower()
    assert len(get_pim_backend().list_sent()) == 1   # still nothing sent

    # denial audit line exists
    a = [r for r in audit.summarize(plan_id=r2.plan_id) if r["tool"] == "pim.mail_send_draft"][0]
    assert a["outcome"] == "denied" and a["policyDecision"] == "deny"

    # A6 also: approving actually sends, verified by read-back
    r3 = run(run_agent("Send it now", approver=auto_approver, planner=send_planner,
                       reporter=deterministic_report, use_models=False))
    assert r3.status == "ok"
    assert r3.step_results[0]["readBack"]["verified"] is True
    assert len(get_pim_backend().list_sent()) == 2


# --- item 3 / invariant #9 ------------------------------------------------
def test_asking_twice_without_approval_never_runs_risk3(agent_env):
    # a note to delete
    from engine.agent.backends import get_pim_backend  # noqa: F401
    scratch = agent_env["scratch"]
    (scratch / "victim.txt").write_text("do not delete me")

    planner = _plan({"tool": "fs.fs_delete_file", "args": {"path": "victim.txt"}, "why": "delete"})
    for _ in range(2):
        r = run(run_agent("delete victim.txt", approver=deny_approver, planner=planner,
                          reporter=deterministic_report, use_models=False))
        assert r.step_results[0]["status"] == "denied"
    assert (scratch / "victim.txt").exists()   # never executed


# --- item 7 --------------------------------------------------------------------
def test_unannotated_tool_treated_as_risk3(agent_env):
    planner = _plan({"tool": "pim.debug_echo", "args": {"payload": {"x": 1}}, "why": "echo"})
    r = run(run_agent("echo something", approver=deny_approver, planner=planner,
                      reporter=deterministic_report, use_models=False))
    step = r.step_results[0]
    assert step["status"] == "denied"          # fail closed, gated
    a = audit.summarize(plan_id=r.plan_id)[0]
    assert a["risk"] == 3


# --- item 5 / A11 --------------------------------------------------------------
def test_midplan_tool_failure_preserves_progress(agent_env, monkeypatch):
    monkeypatch.setenv("WELLSY_AGENT_BREAK_TOOLS", "reminders_create")

    planner = _plan(
        {"tool": "pim.calendar_list_events",
         "args": {"start": _iso(0, 0), "end": _iso(5, 0)}, "why": "read calendar"},
        {"tool": "pim.reminders_create", "args": {"title": "A11 broken step"}, "why": "broken"},
        {"tool": "pim.notes_create", "args": {"title": "A11 note", "body": "kept"}, "why": "note"},
        {"tool": "pim.contacts_search", "args": {"query": "Priya"}, "why": "read contacts"},
    )
    r = run(run_agent("do a four step thing", approver=auto_approver, planner=planner,
                      reporter=deterministic_report, use_models=False))

    assert len(r.step_results) == 4
    by_id = {s["id"]: s for s in r.step_results}
    assert by_id["s1"]["status"] == "ok"
    assert by_id["s2"]["status"] == "error"
    assert by_id["s2"]["attempts"] == 3          # 1 try + retry limit 2
    assert by_id["s3"]["status"] == "ok"         # progress AFTER the failure preserved
    assert by_id["s4"]["status"] == "ok"
    assert r.status == "partial"

    report = deterministic_report("do a four step thing", r.step_results, "partial")
    assert "partly done" in report.lower()
    assert "failed" in report.lower()
    assert "succeeded" in report.lower()        # honest about what worked
    # no fabricated success: the broken step is not reported ok anywhere
    assert by_id["s2"].get("result") is None

    # audit reflects the retries and the eventual give-up
    errs = [a for a in audit.summarize(plan_id=r.plan_id)
            if a["tool"] == "pim.reminders_create" and a["outcome"] == "error"]
    assert len(errs) == 3


# --- item 6 / A12 --------------------------------------------------------------
def test_audit_readback_matches_the_log(agent_env):
    planner = _plan(
        {"tool": "pim.calendar_get_event", "args": {"event_id": "evt-review"}, "why": "read"},
        {"tool": "pim.calendar_move_event",
         "args": {"event_id": "evt-review", "new_start": _iso(4, 9), "new_end": _iso(4, 10)},
         "why": "move"},
        {"tool": "pim.reminders_create", "args": {"title": "follow up"}, "why": "remind"},
    )
    r = run(run_agent("prep and move", approver=auto_approver, planner=planner,
                      reporter=deterministic_report, use_models=False))

    logged = audit.summarize(plan_id=r.plan_id)
    # every consequential step in the result appears in the audit log, same tools, same order
    assert [x["tool"] for x in logged] == [s["tool"] for s in r.step_results]
    for step, entry in zip(r.step_results, logged):
        assert entry["outcome"] == step["status"]
        assert entry["planId"] == r.plan_id


# --- A10 -------------------------------------------------------------------
def test_ambiguity_asks_exactly_one_question(agent_env):
    def planner(outcome, catalog):
        return {"clarify": "Which event should I move to next Tuesday?"}

    r = run(run_agent("Book it for next Tuesday", approver=auto_approver, planner=planner,
                      reporter=deterministic_report, use_models=False))
    assert r.status == "clarify"
    assert r.clarifying_question == "Which event should I move to next Tuesday?"
    assert r.report == r.clarifying_question
    assert r.step_results == []
