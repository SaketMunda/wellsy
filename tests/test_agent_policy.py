"""PolicyGate — step 5 Deliverable 2 and acceptance item 7.

Covers the risk map, the fail-closed default for an unannotated tool
(INVARIANTS #9), the fs argument-escape upgrade to risk 3, and autonomy
promotion of a risk-2 class once the audit log shows enough clean runs.
"""

from __future__ import annotations

import json

import pytest

from engine.agent import audit
from engine.agent.autonomy import AutonomyLedger
from engine.agent.policy import PolicyGate


@pytest.fixture
def gate(agent_env):
    return PolicyGate(autonomy=AutonomyLedger())


def test_risk0_read_allowed_silently(gate):
    d = gate.check("pim.calendar_list_events", {"start": "x", "end": "y"})
    assert d.action == "allow" and d.risk == 0


def test_risk1_reversible_allowed(gate):
    d = gate.check("pim.mail_create_draft", {"to": ["a@b.c"], "subject": "", "body": ""})
    assert d.action == "allow" and d.risk == 1


def test_risk2_confirms_until_promoted(gate):
    d = gate.check("pim.calendar_move_event", {"event_id": "e", "new_start": "s", "new_end": "e2"})
    assert d.action == "confirm" and d.risk == 2
    assert d.requires_approval is True


def test_risk3_delete_always_confirms(gate):
    d = gate.check("fs.fs_delete_file", {"path": "note.txt"})
    assert d.action == "confirm" and d.risk == 3


def test_unannotated_tool_is_risk3_fail_closed(gate):
    """Acceptance item 7 — `pim.debug_echo` has no policy.yaml entry."""
    d = gate.check("pim.debug_echo", {"payload": 1})
    assert d.risk == 3
    assert d.action == "confirm"          # never 'allow'
    assert d.annotation.annotated is False
    assert "fail closed" in d.reason.lower() or "#9" in d.reason


def test_fs_path_escape_forces_risk3(gate):
    """A benign-looking write tool, but the path escapes every allowed root."""
    inside = gate.check("fs.fs_write_file", {"path": "ok.txt", "content": "x"})
    assert inside.action == "allow" and inside.risk == 1

    outside = gate.check("fs.fs_write_file", {"path": "/etc/passwd", "content": "x"})
    assert outside.risk == 3 and outside.action == "confirm"


def _clean_run(cap, tool, path):
    """Append a pending+final pair that looks like an approved, verified run."""
    e = audit.begin(
        actor="agent", tool=tool, arguments={}, risk=2, policy_decision="confirm",
        approval_source="user:cli", plan_id="p", step_id="s1", capability=cap,
    )
    e.finalize(outcome="ok", read_back={"verified": True, "method": "test"})


def test_autonomy_promotes_risk2_after_clean_runs(agent_env):
    gate = PolicyGate(autonomy=AutonomyLedger())
    cap = "calendar.write"
    # threshold is 2 in the fixture env
    assert gate.check("pim.calendar_move_event", {}).action == "confirm"

    _clean_run(cap, "pim.calendar_move_event", agent_env["audit_path"])
    assert gate.check("pim.calendar_move_event", {}).action == "confirm"  # 1 < 2

    _clean_run(cap, "pim.calendar_move_event", agent_env["audit_path"])
    d = gate.check("pim.calendar_move_event", {})
    assert d.action == "allow" and d.extra.get("promoted") is True


def test_autonomy_reset_by_an_error(agent_env):
    gate = PolicyGate(autonomy=AutonomyLedger())
    cap = "calendar.write"
    _clean_run(cap, "pim.calendar_move_event", agent_env["audit_path"])
    _clean_run(cap, "pim.calendar_move_event", agent_env["audit_path"])
    assert gate.check("pim.calendar_move_event", {}).action == "allow"

    bad = audit.begin(actor="agent", tool="pim.calendar_move_event", arguments={}, risk=2,
                      policy_decision="confirm", approval_source="user:cli",
                      plan_id="p", step_id="s9", capability=cap)
    bad.finalize(outcome="error", error="boom")

    # one error wipes the streak — back to gated
    assert gate.check("pim.calendar_move_event", {}).action == "confirm"


def test_risk3_never_promotes(agent_env):
    gate = PolicyGate(autonomy=AutonomyLedger())
    for _ in range(5):
        e = audit.begin(actor="agent", tool="fs.fs_delete_file", arguments={}, risk=3,
                        policy_decision="confirm", approval_source="user:cli",
                        plan_id="p", step_id="s1", capability="fs.delete")
        e.finalize(outcome="ok", read_back={"verified": True})
    assert gate.check("fs.fs_delete_file", {"path": "x"}).action == "confirm"
