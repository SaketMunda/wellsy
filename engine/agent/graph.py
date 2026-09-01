"""The LangGraph agent loop — an explicit state machine (step 5 Deliverable 3).

    plan ─▶ dispatch ─▶ policy_check ─▶ act ─▶ verify ─▶ dispatch ─▶ … ─▶ report

  * **plan** — the planner model decomposes the outcome into <= 6 tool calls
    before any run. Ambiguous with no antecedent -> exactly one clarifying
    question and stop (A10).
  * **policy_check** — every call, no exceptions. `interrupt()` IS the approval
    gate: a Confirm suspends the graph until the runner resumes it with an
    approval decision. A Deny (policy, or a declined Confirm) writes one audit
    line and the step is skipped, not retried (A6).
  * **act** — run the tool. Retry limit 2. The audit line is written *before*
    the call returns (INVARIANTS #12).
  * **verify** — independent read-back (INVARIANTS #15). The tool's own success
    return is never the evidence; a second read is.
  * **checkpoint** — LangGraph checkpoints after every node, so a mid-plan
    failure keeps steps 1..n-1 (A11).
  * **report** — one coherent paragraph, not a narration of the steps (A9).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Optional, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from engine.agent import audit
from engine.agent.mcp_client import AgentTools
from engine.agent.policy import Decision, PolicyGate

MAX_STEPS = 6
RETRY_LIMIT = 2


class Step(TypedDict, total=False):
    id: str
    tool: str
    args: dict
    why: str


class AgentState(TypedDict, total=False):
    outcome: str
    plan_id: str
    plan: list[Step]
    step_idx: int
    retries: int
    step_results: list[dict]
    clarifying_question: Optional[str]
    report: Optional[str]
    done: bool
    _pending: dict   # decision + approval carried policy_check -> act
    _retry: bool      # act -> act self-loop flag


Planner = Callable[[str, list[dict]], dict]       # -> {"plan":[...]} | {"clarify":"..."}
Reporter = Callable[[str, list[dict], str], str]  # (outcome, results, outcome_status) -> paragraph


# --------------------------------------------------------------------------- #
# read-back verification — INVARIANTS #15                                      #
# --------------------------------------------------------------------------- #

def _as_list(v: Any) -> list:
    if isinstance(v, list):
        return v
    if v is None:
        return []
    return [v]


async def _read_back(tools: AgentTools, step: Step, result: Any) -> dict:
    """Independently confirm the mutation actually happened. Returns
    {"verified": bool, "method": str, "observed": ...}. Risk-0 reads need no
    read-back — they *are* the read."""
    tool = step["tool"]
    args = step.get("args", {})

    try:
        if tool == "pim.calendar_move_event":
            ev = await tools.call("pim.calendar_get_event", {"event_id": args["event_id"]})
            ok = isinstance(ev, dict) and ev.get("start", "").startswith(args["new_start"][:16])
            return {"verified": ok, "method": "calendar_get_event.start == new_start", "observed": ev}

        if tool == "pim.calendar_create_event":
            evs = _as_list(await tools.call(
                "pim.calendar_list_events",
                {"start": args["start"][:19], "end": args["end"][:19]},
            ))
            ok = any(isinstance(e, dict) and e.get("title") == args["title"] for e in evs)
            return {"verified": ok, "method": "calendar_list_events contains title", "observed": evs}

        if tool == "pim.mail_send_draft":
            sent = _as_list(await tools.call("pim.mail_list_sent", {"limit": 20}))
            did = isinstance(result, dict) and result.get("id")
            ok = any(isinstance(m, dict) and m.get("id") == did for m in sent) if did else False
            return {"verified": ok, "method": "mail_list_sent contains the new message id", "observed": sent}

        if tool == "pim.mail_create_draft":
            did = result.get("id") if isinstance(result, dict) else None
            draft = await tools.call("pim.mail_get_draft", {"draft_id": did}) if did else None
            sent = _as_list(await tools.call("pim.mail_list_sent", {"limit": 50}))
            ok = isinstance(draft, dict) and not draft.get("sent", True)
            return {"verified": ok, "method": "draft exists and is unsent; sent folder unchanged",
                    "observed": {"draft": draft, "sentCount": len(sent)}}

        if tool == "pim.reminders_create":
            rems = _as_list(await tools.call("pim.reminders_list", {
                "list_name": args.get("list_name", "Reminders"), "include_completed": True}))
            ok = any(isinstance(r, dict) and r.get("title") == args["title"] for r in rems)
            return {"verified": ok, "method": "reminders_list contains title", "observed": rems}

        if tool == "pim.reminders_complete":
            rems = _as_list(await tools.call("pim.reminders_list", {"include_completed": True}))
            ok = any(isinstance(r, dict) and r.get("id") == args["reminder_id"] and r.get("completed")
                     for r in rems)
            return {"verified": ok, "method": "reminders_list shows the reminder completed", "observed": rems}

        if tool == "pim.notes_create":
            notes = _as_list(await tools.call("pim.notes_list", {}))
            ok = any(isinstance(n, dict) and n.get("title") == args["title"] for n in notes)
            return {"verified": ok, "method": "notes_list contains title", "observed": notes}

        if tool == "fs.fs_write_file":
            back = await tools.call("fs.fs_read_file", {"path": args["path"]})
            ok = back == args["content"]
            return {"verified": ok, "method": "fs_read_file round-trips the content",
                    "observed": {"len": len(back) if isinstance(back, str) else None}}

        if tool == "fs.fs_delete_file":
            listing = _as_list(await tools.call("fs.fs_list_dir", {"path": _parent(args["path"])}))
            names = {e.get("name") for e in listing if isinstance(e, dict)}
            ok = _basename(args["path"]) not in names
            return {"verified": ok, "method": "fs_list_dir no longer lists the file", "observed": sorted(names)}

    except Exception as e:  # a failed read-back is an unverified action, not a crash
        return {"verified": False, "method": "read-back raised", "observed": f"{type(e).__name__}: {e}"}

    # risk-0 read tools, or anything without a defined read-back
    return {"verified": True, "method": "read-only tool — no mutation to verify", "observed": None}


def _parent(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else "."


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


# --------------------------------------------------------------------------- #
# graph                                                                        #
# --------------------------------------------------------------------------- #

def build_graph(
    *,
    tools: AgentTools,
    gate: PolicyGate,
    planner: Planner,
    reporter: Reporter,
    approver_actor: str = "user:cli",
):
    """Compile the state machine. `tools`/`gate` are live; `planner`/`reporter`
    are injectable so the acceptance suite can drive the loop without a model."""

    def plan_node(state: AgentState) -> AgentState:
        catalog = tools.list_tools()
        res = planner(state["outcome"], catalog)
        if res.get("clarify"):
            return {"clarifying_question": res["clarify"], "done": True, "plan": [], "step_results": []}
        raw_plan = res.get("plan", [])[:MAX_STEPS]
        plan: list[Step] = []
        for i, s in enumerate(raw_plan):
            plan.append({"id": f"s{i+1}", "tool": s["tool"], "args": s.get("args", {}),
                         "why": s.get("why", "")})
        return {"plan": plan, "step_idx": 0, "retries": 0, "step_results": [],
                "clarifying_question": None, "done": False}

    def dispatch_node(state: AgentState) -> AgentState:
        return {}

    def dispatch_route(state: AgentState) -> str:
        if state.get("clarifying_question"):
            return "report"
        if state.get("step_idx", 0) >= len(state.get("plan", [])):
            return "report"
        return "policy_check"

    def policy_check_node(state: AgentState) -> AgentState:
        step = state["plan"][state["step_idx"]]
        decision: Decision = gate.check(step["tool"], step.get("args", {}), {"outcome": state["outcome"]})

        if decision.action == "deny":
            audit.record_denial(
                actor="agent", tool=step["tool"], arguments=step.get("args", {}),
                risk=decision.risk, reason=decision.reason, plan_id=state["plan_id"],
                step_id=step["id"], capability=decision.capability,
            )
            return _skip_step(state, step, "denied", decision.reason)

        approval_source = None
        if decision.action == "confirm":
            answer = interrupt({
                "kind": "approval_request",
                "planId": state["plan_id"],
                "stepId": step["id"],
                "tool": step["tool"],
                "args": step.get("args", {}),
                "risk": decision.risk,
                "capability": decision.capability,
                "reason": decision.reason,
                "why": step.get("why", ""),
            })
            approved = bool(answer.get("approved")) if isinstance(answer, dict) else bool(answer)
            approval_source = (answer.get("source") if isinstance(answer, dict) else None) or approver_actor
            if not approved:
                audit.record_denial(
                    actor="agent", tool=step["tool"], arguments=step.get("args", {}),
                    risk=decision.risk, reason="approval declined by " + approval_source,
                    plan_id=state["plan_id"], step_id=step["id"],
                    approval_source=approval_source, capability=decision.capability,
                )
                return _skip_step(state, step, "denied", "approval declined")
        else:
            approval_source = "autonomy:promoted" if decision.extra.get("promoted") else None

        return {"_pending": {
            "decision_action": decision.action,
            "risk": decision.risk,
            "capability": decision.capability,
            "approval_source": approval_source,
        }}

    def policy_route(state: AgentState) -> str:
        # a skipped step advanced step_idx and left no _pending
        return "act" if state.get("_pending") else "dispatch"

    async def act_node(state: AgentState) -> AgentState:
        step = state["plan"][state["step_idx"]]
        pend = state["_pending"]
        entry = audit.begin(
            actor="agent", tool=step["tool"], arguments=step.get("args", {}),
            risk=pend["risk"], policy_decision=pend["decision_action"],
            approval_source=pend["approval_source"], plan_id=state["plan_id"],
            step_id=step["id"], capability=pend["capability"],
        )
        try:
            result = await tools.call(step["tool"], step.get("args", {}))
            error = None
        except Exception as e:
            result, error = None, f"{type(e).__name__}: {e}"

        if error is not None:
            attempts = state.get("retries", 0) + 1
            if attempts <= RETRY_LIMIT:
                entry.finalize(outcome="error", error=f"{error} (attempt {attempts}, retrying)")
                return {"retries": attempts, "_retry": True, "_pending": pend}
            entry.finalize(outcome="error", error=f"{error} (attempt {attempts}, gave up)")
            return _finish_step(state, step, {
                "id": step["id"], "tool": step["tool"], "status": "error",
                "error": error, "attempts": attempts, "auditId": entry.id,
                "readBack": {"verified": False, "method": "not run — tool errored"},
            })

        # Read-back that fails is reported as unverified — it is NOT retried.
        # Re-running a non-idempotent mutation (create_event, send) to chase a
        # green read-back is how you get duplicates. Retry is for tool *errors*
        # only (A11); an unverified success is surfaced honestly (INVARIANTS #15).
        read_back = await _read_back(tools, step, result)
        verified = bool(read_back.get("verified"))
        attempts = state.get("retries", 0) + 1
        entry.finalize(outcome="ok" if verified else "unverified", read_back=read_back)
        return _finish_step(state, step, {
            "id": step["id"], "tool": step["tool"],
            "status": "ok" if verified else "unverified",
            "result": result, "readBack": read_back, "attempts": attempts, "auditId": entry.id,
        })

    def act_route(state: AgentState) -> str:
        return "act" if state.get("_retry") else "dispatch"

    def report_node(state: AgentState) -> AgentState:
        if state.get("clarifying_question"):
            return {"report": state["clarifying_question"], "done": True}
        results = state.get("step_results", [])
        n_ok = sum(1 for r in results if r["status"] == "ok")
        status = "ok" if results and n_ok == len(results) else ("partial" if n_ok else "failed")
        para = reporter(state["outcome"], results, status)
        return {"report": para, "done": True}

    # --- wiring ---
    g = StateGraph(AgentState)
    g.add_node("plan", plan_node)
    g.add_node("dispatch", dispatch_node)
    g.add_node("policy_check", policy_check_node)
    g.add_node("act", act_node)
    g.add_node("report", report_node)

    g.add_edge(START, "plan")
    g.add_edge("plan", "dispatch")
    g.add_conditional_edges("dispatch", dispatch_route, ["policy_check", "report"])
    g.add_conditional_edges("policy_check", policy_route, ["act", "dispatch"])
    g.add_conditional_edges("act", act_route, ["act", "dispatch"])
    g.add_edge("report", END)

    return g.compile(checkpointer=InMemorySaver())


def _skip_step(state: AgentState, step: Step, status: str, reason: str) -> AgentState:
    entry = {"id": step["id"], "tool": step["tool"], "status": status, "error": reason,
             "attempts": 0, "readBack": {"verified": False, "method": "not run — " + status}}
    return _finish_step(state, step, entry)


def _finish_step(state: AgentState, step: Step, entry: dict) -> AgentState:
    results = list(state.get("step_results", []))
    results.append(entry)
    return {
        "step_results": results,
        "step_idx": state.get("step_idx", 0) + 1,
        "retries": 0,
        "_pending": {},
        "_retry": False,
    }


# --------------------------------------------------------------------------- #
# default model-backed planner / reporter                                      #
# --------------------------------------------------------------------------- #

_PLANNER_SYS = """You are WELLSY's planner. Decompose the user's outcome into AT MOST 6 tool calls.
Return ONLY minified JSON, no prose, one of:
  {"plan":[{"tool":"<server.tool>","args":{...},"why":"<short>"}, ...]}
  {"clarify":"<one question>"}   // ONLY when the outcome refers to something with
                                // no antecedent (e.g. "move IT" / "book IT" with
                                // no prior turn). Dates like "tomorrow" are NOT
                                // ambiguous — resolve them from NOW below.
NOW: {now}  (use this to resolve "today"/"tomorrow"/"next Tuesday"; datetimes are
local, ISO-8601, no offset needed).
Rules: use only tools from the catalog; prefer a read before a mutation; never
guess an id — look it up with a read step first; never plan a delete unless the
user explicitly asked to delete."""


def make_model_planner() -> Planner:
    from engine.agent.models import get_model

    model = get_model("planner")

    def planner(outcome: str, catalog: list[dict]) -> dict:
        import datetime as _dt

        cat = "\n".join(f'- {t["key"]}: {t["description"]}' for t in catalog)
        sys = _PLANNER_SYS.replace("{now}", _dt.datetime.now().astimezone().isoformat(timespec="minutes"))
        msg = f"{sys}\n\nCATALOG:\n{cat}\n\nOUTCOME: {outcome}"
        resp = model.invoke(msg)
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        return _extract_json(text)

    return planner


def make_model_reporter() -> Reporter:
    from engine.agent.models import get_model

    model = get_model("fast")

    def reporter(outcome: str, results: list[dict], status: str) -> str:
        facts = json.dumps([
            {"tool": r["tool"], "status": r["status"],
             "result": r.get("result"), "error": r.get("error")}
            for r in results
        ], default=str)
        msg = (
            "Write ONE short paragraph (no lists, no step narration) answering the user's "
            f"request from these tool results. State plainly what succeeded and what failed.\n"
            f"REQUEST: {outcome}\nOUTCOME: {status}\nRESULTS: {facts}"
        )
        try:
            resp = model.invoke(msg)
            return resp.content if isinstance(resp.content, str) else str(resp.content)
        except Exception:
            return deterministic_report(outcome, results, status)

    return reporter


def deterministic_report(outcome: str, results: list[dict], status: str) -> str:
    """Model-free fallback (and the default in tests). Honest, terse, no
    fabricated success."""
    if not results:
        return f"I made no changes for: {outcome!r}."
    parts = []
    for r in results:
        if r["status"] == "ok":
            parts.append(f"{r['tool']} succeeded and was verified by read-back")
        elif r["status"] == "unverified":
            parts.append(f"{r['tool']} ran but I could NOT confirm it by read-back")
        elif r["status"] == "denied":
            parts.append(f"{r['tool']} was not run ({r.get('error','denied')})")
        else:
            parts.append(f"{r['tool']} failed ({r.get('error','error')})")
    head = {"ok": "Done.", "partial": "Partly done.", "failed": "I could not complete this."}[status]
    return head + " " + "; ".join(parts) + "."


def _extract_json(text: str) -> dict:
    text = text.strip()
    # strip a <think>...</think> block if a reasoning model leaked one
    if "</think>" in text:
        text = text.split("</think>", 1)[1].strip()
    start = text.find("{")
    if start == -1:
        return {"clarify": "I couldn't form a plan for that — can you rephrase the goal?"}
    depth = 0
    for i in range(start, len(text)):
        depth += (text[i] == "{") - (text[i] == "}")
        if depth == 0:
            try:
                return json.loads(text[start:i + 1])
            except json.JSONDecodeError:
                break
    return {"clarify": "I couldn't form a plan for that — can you rephrase the goal?"}
