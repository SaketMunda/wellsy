"""Drive the LangGraph loop end to end: spin up the MCP tools, run the graph,
service every `interrupt()` through an approver callback, and return a result.

This is the runtime's local entry point. The CLI is one caller; the voice loop
is another (step 9 — `engine.voice.agent_bridge` holds one `AgentRuntime` for
the whole session); a ROS 2 node is a third (D54 — the interface is a client
of this, not the other way round).

Checkpoints are durable (step 9): an `AsyncSqliteSaver` at
`runs/agent/checkpoints.sqlite` (`WELLSY_AGENT_CHECKPOINTS` overrides), so an
`interrupt()` waiting on an approval is on disk, keyed by its thread id, and a
second process can resume it with `Command(resume=...)`.
"""

from __future__ import annotations

import inspect
import os
import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
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


CHECKPOINT_PATH = Path(__file__).resolve().parents[2] / "runs" / "agent" / "checkpoints.sqlite"


def checkpoint_path() -> Path:
    override = os.environ.get("WELLSY_AGENT_CHECKPOINTS")
    return Path(override) if override else CHECKPOINT_PATH


class AgentRuntime:
    """The graph plus everything it needs, opened once and reused per turn:
    the MCP tool sessions, the policy gate, and a durable checkpointer.

        async with AgentRuntime() as rt:
            res = await rt.run("what's on my calendar tomorrow", approver=...)
    """

    def __init__(self, *, gate: PolicyGate | None = None, planner: Planner | None = None,
                 reporter: Reporter | None = None, use_models: bool = True,
                 durable: bool = True) -> None:
        self.gate = gate or PolicyGate()
        if planner is None:
            planner = make_model_planner() if use_models else _null_planner
        if reporter is None:
            reporter = make_model_reporter() if use_models else deterministic_report
        self._planner, self._reporter = planner, reporter
        self._durable = durable
        self._stack: AsyncExitStack | None = None
        self.tools: AgentTools | None = None
        self.checkpointer: Any = None
        self._sink: EventSink | None = None
        self._graph = None

    async def __aenter__(self) -> "AgentRuntime":
        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            self.tools = await stack.enter_async_context(AgentTools())
            if self._durable:
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

                path = checkpoint_path()
                path.parent.mkdir(parents=True, exist_ok=True)
                self.checkpointer = await stack.enter_async_context(
                    AsyncSqliteSaver.from_conn_string(str(path)))
            self._graph = build_graph(
                tools=self.tools, gate=self.gate, planner=self._planner,
                reporter=self._reporter, checkpointer=self.checkpointer,
                emit=lambda ev: self._sink(ev) if self._sink else None,
            )
        except BaseException:
            await stack.aclose()
            raise
        self._stack = stack
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None

    async def run(self, outcome: str, *, approver: Approver = auto_approver,
                  thread_id: str | None = None, on_event: EventSink | None = None,
                  emit_ack: bool = True) -> AgentResult:
        assert self._graph is not None, "use `async with AgentRuntime() as rt`"
        plan_id = uuid.uuid4().hex[:12]
        thread_id = thread_id or f"agent-{plan_id}"
        emit = on_event or (lambda _e: None)
        self._sink = emit

        # acknowledge-then-deliver: the fast path speaks first (deterministic,
        # no model, so it cannot blow the §1 budget) while the planner runs.
        if emit_ack and models.should_plan(outcome):
            emit({"type": "ack", "text": models.acknowledgement(outcome)})

        approvals: list[dict] = []
        config = {"configurable": {"thread_id": thread_id}}
        payload: Any = {"outcome": outcome, "plan_id": plan_id}
        try:
            emit({"type": "plan_start", "outcome": outcome})
            while True:
                result = await self._graph.ainvoke(payload, config)
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
        finally:
            self._sink = None

        res = AgentResult(
            outcome=outcome,
            plan_id=plan_id,
            report=result.get("report") or "",
            plan=result.get("plan", []),
            step_results=result.get("step_results", []),
            clarifying_question=result.get("clarifying_question"),
            approvals=approvals,
        )
        emit({"type": "done", "status": res.status, "report": res.report})
        return res


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
    """One outcome, one runtime, torn down after (the `wellsy agent` path)."""
    async with AgentRuntime(gate=gate, planner=planner, reporter=reporter,
                            use_models=use_models) as rt:
        return await rt.run(outcome, approver=approver, thread_id=thread_id,
                            on_event=on_event, emit_ack=emit_ack)


def _null_planner(outcome: str, catalog: list[dict]) -> dict:
    return {"clarify": "No planner is configured (use_models=False and no planner passed)."}


def audit_summary(plan_id: str | None = None) -> list[dict]:
    """Scenario A12 reads from here — the audit log on disk, not conversation
    memory."""
    return audit.summarize(plan_id=plan_id)
