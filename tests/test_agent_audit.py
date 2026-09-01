"""Audit log — INVARIANTS #12 and acceptance items 2 & 6.

The pending line must be on disk *before* the action returns; a denial writes
one terminal line; secrets are redacted; `summarize()` reconstructs one row per
action from the file, not from memory.
"""

from __future__ import annotations

import json

from engine.agent import audit


def _lines(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def test_pending_line_written_before_finalize(agent_env):
    path = agent_env["audit_path"]
    entry = audit.begin(
        actor="agent", tool="pim.mail_send_draft", arguments={"draft_id": "d1"},
        risk=2, policy_decision="confirm", approval_source="user:cli",
        plan_id="p1", step_id="s1", capability="mail.send",
    )
    # before finalize: exactly one line, phase pending, outcome pending
    rows = _lines(path)
    assert len(rows) == 1
    assert rows[0]["phase"] == "pending" and rows[0]["outcome"] == "pending"
    assert rows[0]["tool"] == "pim.mail_send_draft"

    entry.finalize(outcome="ok", read_back={"verified": True, "method": "sent folder"})
    rows = _lines(path)
    assert len(rows) == 2
    assert rows[1]["phase"] == "final" and rows[1]["outcome"] == "ok"
    assert rows[1]["readBack"]["verified"] is True


def test_secrets_are_redacted(agent_env):
    audit.begin(
        actor="agent", tool="x.y", arguments={"password": "hunter2", "note": "ok",
                                              "nested": {"api_key": "sk-123"}},
        risk=1, policy_decision="allow", approval_source=None,
        plan_id="p", step_id="s", capability="c",
    )
    row = _lines(agent_env["audit_path"])[0]
    assert row["arguments"]["password"] == "***"
    assert row["arguments"]["nested"]["api_key"] == "***"
    assert row["arguments"]["note"] == "ok"


def test_denial_writes_one_terminal_line(agent_env):
    audit.record_denial(
        actor="agent", tool="pim.mail_send_draft", arguments={"draft_id": "d1"},
        risk=2, reason="approval declined by user:cli", plan_id="p", step_id="s2",
        approval_source="user:cli", capability="mail.send",
    )
    rows = _lines(agent_env["audit_path"])
    # a pending + a final for the same auditId, terminal outcome 'denied'
    assert {r["outcome"] for r in rows} == {"pending", "denied"}
    summary = audit.summarize()
    assert len(summary) == 1
    assert summary[0]["outcome"] == "denied"
    assert summary[0]["policyDecision"] == "deny"


def test_summarize_is_derived_from_disk(agent_env):
    for i in range(3):
        e = audit.begin(actor="agent", tool=f"pim.t{i}", arguments={}, risk=0,
                        policy_decision="allow", approval_source=None,
                        plan_id="pX", step_id=f"s{i}", capability="read")
        e.finalize(outcome="ok")
    e = audit.begin(actor="agent", tool="pim.other", arguments={}, risk=0,
                    policy_decision="allow", approval_source=None,
                    plan_id="pOTHER", step_id="s0", capability="read")
    e.finalize(outcome="ok")

    rows = audit.summarize(plan_id="pX")
    assert [r["tool"] for r in rows] == ["pim.t0", "pim.t1", "pim.t2"]
    assert all(r["outcome"] == "ok" for r in rows)
