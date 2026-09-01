"""Drive the LangGraph loop end to end: spin up the MCP tools, run the graph,
service every `interrupt()` through an approver callback, and return a result.

This is the runtime's local entry point. The CLI is one caller; a future UI or
ROS 2 node is another (D54 — the interface is a client of this, not the other
way round).
"""

from __future__ import annotations

import inspect
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from langgraph.types import Command

from engine.agent import audit, models
from engine.agent.graph import (
    Planner,
    Reporter,
    build_graph,
    deterministic_report,
    make_model_planner,
    make_model_reporter,
)
from engine.agent.mcp_client import AgentTools
from engine.agent.policy import PolicyGate

# approver(request: dict) -> {"approved": bool, "source": str} | bool
Approver = Callable[[dict], Any] | Callable[[dict], Awaitable[Any]]
EventSink = Callable[[dict], None]


@dataclass
class AgentResult:
    outcome: str
    plan_id: str
    report: str
    plan: list[dict] = field(default_factory=list)
    step_results: list[dict] = field(default_factory=list)
    clarifying_question: Optional[str] = None
    approvals: list[dict] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.clarifying_question:
            return "clarify"
        if not self.step_results:
            return "noop"
        n_ok = sum(1 for r in self.step_results if r["status"] == "ok")
        return "ok" if n_ok == len(self.step_results) else ("partial" if n_ok else "failed")


async def _maybe_await(v: Any) -> Any:
    return await v if inspect.isawaitable(v) else v


def auto_approver(_: dict) -> dict:
    """Approve everything — for `--yes` / non-interactive test paths where the
    intent is explicitly 'no human in the loop'. Never the default."""
    return {"approved": True, "source": "user:auto"}


def deny_approver(_: dict) -> dict:
    return {"approved": False, "source": "user:auto"}


async def run_agent(
    outcome: str,
    *,
    approver: Approver = auto_approver,
    gate: PolicyGate | None = None,
    planner: Planner | None = None,
    reporter: Reporter | None = None,
    thread_id: str | None = None,
    on_event: EventSink | None = None,
    emit_ack: bool = True,
    use_models: bool = True,
) -> AgentResult:
    plan_id = uuid.uuid4().hex[:12]
    thread_id = thread_id or f"agent-{plan_id}"
    emit = on_event or (lambda _e: None)

    gate = gate or PolicyGate()
    if planner is None:
        planner = make_model_planner() if use_models else _null_planner
    if reporter is None:
        reporter = make_model_reporter() if use_models else deterministic_report

    # acknowledge-then-deliver: the fast path speaks first (deterministic, no
    # model, so it cannot blow the §1 budget) while the planner runs behind it.
    if emit_ack and models.should_plan(outcome):
        emit({"type": "ack", "text": models.acknowledgement(outcome)})

    approvals: list[dict] = []

    async with AgentTools() as tools:
        graph = build_graph(tools=tools, gate=gate, planner=planner, reporter=reporter)
        config = {"configurable": {"thread_id": thread_id}}
        payload: Any = {"outcome": outcome, "plan_id": plan_id}

        emit({"type": "plan_start", "outcome": outcome})
        while True:
            result = await graph.ainvoke(payload, config)
            interrupts = result.get("__interrupt__")
            if not interrupts:
                break
            request = dict(interrupts[0].value)
            emit({"type": "approval_request", "request": request})
            answer = await _maybe_await(approver(request))
            if isinstance(answer, bool):
                answer = {"approved": answer, "source": "user:cli"}
            approvals.append({"request": request, "answer": answer})
            emit({"type": "approval_answer", "request": request, "answer": answer})
            payload = Command(resume=answer)

        state = result

    res = AgentResult(
        outcome=outcome,
        plan_id=plan_id,
        report=state.get("report") or "",
        plan=state.get("plan", []),
        step_results=state.get("step_results", []),
        clarifying_question=state.get("clarifying_question"),
        approvals=approvals,
    )
    emit({"type": "done", "status": res.status, "report": res.report})
    return res


def _null_planner(outcome: str, catalog: list[dict]) -> dict:
    return {"clarify": "No planner is configured (use_models=False and no planner passed)."}


def audit_summary(plan_id: str | None = None) -> list[dict]:
    """Scenario A12 reads from here — the audit log on disk, not conversation
    memory."""
    return audit.summarize(plan_id=plan_id)
