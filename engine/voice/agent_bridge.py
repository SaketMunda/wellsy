"""The agent becomes the brain of the voice loop (step 9 Deliverable 1-5).

Before this, `wellsy voice` had ears and no tools and `wellsy agent` had tools
and no ears. Now there is one runtime: the voice loop's LLM stage carries one
tool, `use_tools`, and the model's own tool-calling decides when a turn needs
the agent. No classifier (that is step 8) — the routing is the planner model's
native function calling, measured below.

Three tiers, cheapest first:

  1. **deterministic** — stop / wake / sleep / move_orb / approval answers.
     `IntentGate`, regex, no model, no graph. Unchanged.
  2. **conversational** — the model answers with text. Streams straight to TTS
     exactly as before; this module is not on that path.
  3. **agentic** — the model calls `use_tools`. Then, in order:
       a. an honest, deterministic ack is spoken at once ("Let me check your
          calendar.") — `models.acknowledgement()`, no model, never a claim;
       b. the LangGraph turn runs on the session's `AgentRuntime` (MCP tools,
          policy gate, audit log, read-back, SQLite checkpoints);
       c. every `interrupt()` is asked **aloud** with its read-back
          ("I'm about to add “Dentist” to your calendar, Saturday, October 18
          from 3 PM to 4 PM. Shall I go ahead?"), the HUD opens at the same
          time, and the answer comes from speech (`approval.parse_approval`),
          a click, or Esc — whichever is first. Anything unclear is a no, and
          a no is spoken;
       d. the structured, read-back-verified result goes back to the model as
          the tool result and the model says it in one or two sentences.

The tool is registered async (`cancel_on_interruption=False`): the user speaking
"yes" must not cancel the turn that asked. Async results are appended to the
context as new messages rather than editing an IN_PROGRESS placeholder, which
keeps the conversation append-only — on Qwen3.5 an edit costs a re-prefill
(5c §6).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Callable

from engine.agent import models
from engine.honesty import spoken_email
from engine.honesty.approval import parse_approval
from engine.interface.session import approval_view

TOOL_NAME = "use_tools"

TOOL_DESCRIPTION = (
    "Use the user's own data and apps: calendar events, reminders, email (inbox, "
    "drafts, sending), notes, contacts, and files in the scratch folder. Call this "
    "whenever answering needs any of that, or when the user asks you to create, "
    "change, send, move or delete something there. Never answer such a request "
    "from memory, and never say it is done without this tool's result. Call it only "
    "for what the user's latest message asks; a question about what was said or "
    "done earlier is answered from the conversation, never by calling this again."
)
_REFERENCE = re.compile(r"\b(it|that|this|them|those|these|him|her|there|the same|again|retry|one more time)\b")

APPROVAL_TIMEOUT_S = 45.0
_RESULT_CHARS = 600          # per step, in the tool result the model reads —
_RESULT_TOTAL_CHARS = 1200   # it stays in the history, so it is context budget

SPOKEN_DECLINED = "Okay, I won't do that."
SPOKEN_UNCLEAR = "I didn't hear a clear yes, so I won't do that."
SPOKEN_TIMEOUT = "I didn't get an answer, so I won't do that."
SPOKEN_STOPPED = "Stopped. I won't do that."
SPOKEN_FAILED = "Sorry, I couldn't get to your tools just now."


def tools_schema():
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema

    return ToolsSchema(standard_tools=[FunctionSchema(
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        properties={"request": {
            "type": "string",
            # short: the ack waits for the whole tool call (Ollama emits it
            # only when complete) — a 70-token restatement is ~1 s of silence
            "description": "The request in a few words (under 12), with 'it' or 'that' "
                           "replaced by what it refers to.",
        }},
        required=["request"],
    )])


# --------------------------------------------------------------------------- #
# approval broker — one pending spoken/clicked answer at a time               #
# --------------------------------------------------------------------------- #

class ApprovalBroker:
    """Holds the one approval the graph is blocked on. Answered by whichever
    surface gets there first: speech (IntentGate), a HUD click (Qt main
    thread), Esc, or the timeout. Resolution is idempotent — the first answer
    wins and later ones are ignored."""

    def __init__(self) -> None:
        self._fut: asyncio.Future | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.request: dict | None = None
        self.stopped = False          # "stop" during a run: refuse everything after

    @property
    def pending(self) -> bool:
        return self._fut is not None and not self._fut.done()

    async def ask(self, request: dict, timeout: float = APPROVAL_TIMEOUT_S) -> dict:
        if self.stopped:
            return {"approved": False, "source": "voice:stop", "verdict": "stopped"}
        self._loop = asyncio.get_running_loop()
        self._fut = self._loop.create_future()
        self.request = request
        try:
            return await asyncio.wait_for(asyncio.shield(self._fut), timeout)
        except asyncio.TimeoutError:
            return {"approved": False, "source": "voice:timeout", "verdict": "timeout"}
        finally:
            self._fut, self.request = None, None

    def answer(self, approved: bool, source: str, verdict: str | None = None) -> bool:
        """Event-loop thread. True if this answer resolved a pending request."""
        if not self.pending:
            return False
        self._fut.set_result({"approved": bool(approved), "source": source,
                              "verdict": verdict or ("yes" if approved else "no")})
        return True

    def answer_threadsafe(self, approved: bool, source: str, verdict: str | None = None) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self.answer, approved, source, verdict)

    def answer_spoken(self, text: str) -> str:
        """Resolve from a transcript. Returns the verdict ('yes'|'no'|'unclear')."""
        verdict = parse_approval(text)
        self.answer(verdict == "yes", f"voice:{verdict}", verdict)
        return verdict

    def stop(self) -> None:
        """Deterministic stop: deny what is pending and anything else this run asks."""
        self.stopped = True
        self.answer(False, "voice:stop", "stopped")


# --------------------------------------------------------------------------- #
# the tool result the model reads                                              #
# --------------------------------------------------------------------------- #

def _trim(v: Any, n: int) -> Any:
    s = json.dumps(v, default=str, ensure_ascii=False)
    return v if len(s) <= n else s[:n] + "…(truncated)"


def voice_result(res) -> dict:
    """The structured, honest result handed back to the conversation model.
    `done` lists only steps whose read-back confirmed them."""
    from engine.agent.graph import deterministic_report

    if res.clarifying_question:
        return {"status": "clarify", "ask_the_user": res.clarifying_question}
    steps, budget = [], _RESULT_TOTAL_CHARS
    for r in res.step_results:
        item = {"tool": r["tool"], "status": r["status"],
                "verified": bool((r.get("readBack") or {}).get("verified"))}
        if r.get("error"):
            item["error"] = r["error"]
        if r.get("result") is not None and budget > 0:
            item["result"] = _trim(r["result"], min(_RESULT_CHARS, budget))
            budget -= len(json.dumps(item["result"], default=str))
        steps.append(item)
    return {
        "status": res.status,
        "summary": deterministic_report(res.outcome, res.step_results,
                                        res.status if res.status in ("ok", "partial", "failed") else "failed"),
        "steps": steps,
        "rule": "Say only what these steps show. An action is done only if its status is ok "
                "and verified is true. Read dates as weekday and date.",
    }


def verified_mutations(res) -> list[str]:
    from engine.agent.policy import PolicyGate

    gate = PolicyGate()
    return [r["tool"] for r in res.step_results
            if r["status"] == "ok" and gate.annotation_for(r["tool"]).risk >= 1]


# --------------------------------------------------------------------------- #
# the bridge                                                                   #
# --------------------------------------------------------------------------- #

class VoiceAgentBridge:
    """One per voice session. Owns the `AgentRuntime` (opened in the background
    at start so the first agentic turn doesn't pay for spawning MCP servers),
    the approval broker, and the pipecat function handler."""

    def __init__(self, *, runtime_factory: Callable[[], Any] | None = None,
                 on_event: Callable[[dict], None] | None = None,
                 show_hud: Callable[[dict], None] | None = None,
                 hide_hud: Callable[[], None] | None = None,
                 approval_timeout_s: float = APPROVAL_TIMEOUT_S,
                 on_turn: Callable[[dict], None] | None = None) -> None:
        self.broker = ApprovalBroker()
        self._factory = runtime_factory or _default_runtime
        self._on_event = on_event
        self._show_hud, self._hide_hud = show_hud, hide_hud
        self._timeout = approval_timeout_s
        self._on_turn = on_turn
        self._rt = None
        self._ready: asyncio.Task | None = None
        self._session = f"voice-{int(time.time())}"
        self._n = 0
        self._hud_open = False
        # the mutations a read-back confirmed in the most recent agent run —
        # the only evidence ClaimGuard accepts for "I've sent it"
        self.verified_tools: frozenset[str] = frozenset()
        self.last_verified_mutation_at: float | None = None
        self.running = False

    # -- lifecycle ------------------------------------------------------ #

    def start(self) -> None:
        if self._ready is None:
            self._ready = asyncio.get_running_loop().create_task(self._open())

    async def _open(self):
        rt = self._factory()
        await rt.__aenter__()
        self._rt = rt
        return rt

    async def runtime(self):
        self.start()
        return await self._ready

    async def close(self) -> None:
        if self._ready is not None and not self._ready.done():
            self._ready.cancel()
        if self._rt is not None:
            try:
                await self._rt.__aexit__(None, None, None)
            except Exception:
                pass
            self._rt = None

    # -- events / HUD --------------------------------------------------- #

    def _event(self, ev: dict) -> None:
        if self._on_event is not None:
            try:
                self._on_event(ev)
            except Exception:
                pass
        t = ev.get("type")
        if t == "plan_ready" and ev.get("steps"):
            self._show({"kind": "plan", "title": "Plan", "steps": [
                {"tool": s["tool"], "decision": s.get("decision", "allow")} for s in ev["steps"]]})
        elif t == "step_done":
            rb = ev.get("readBack") or {}
            self._show({"kind": "verify", "title": "Read-back", "claimed": ev.get("tool", ""),
                        "verified": bool(rb.get("verified")), "method": rb.get("method", "")})

    def _show(self, view: dict) -> None:
        if self._show_hud is not None:
            try:
                self._show_hud(view)
                self._hud_open = True
            except Exception:
                pass

    def hide_hud(self) -> None:
        if self._hud_open and self._hide_hud is not None and not self.broker.pending:
            try:
                self._hide_hud()
            except Exception:
                pass
            self._hud_open = False

    def provenance_view(self, res) -> dict:
        lines = []
        for r in res.step_results:
            rb = r.get("readBack") or {}
            lines.append(f"{r['tool']} — {r['status']}"
                         + (f" — read-back: {rb.get('method')}" if rb.get("method") else "")
                         + (f" — audit {r['auditId']}" if r.get("auditId") else ""))
        return {"kind": "provenance", "title": "Where this answer came from",
                "lines": lines or ["no tool ran"], "planId": res.plan_id}

    # -- the pipecat function handler ------------------------------------ #

    async def handle(self, params) -> None:
        from pipecat.frames.frames import TTSSpeakFrame

        t0 = time.perf_counter()
        # spoken addresses ("saket dot munda at the rate gmail dot com") become
        # written ones before anything plans with them
        request = spoken_email.normalize(str((params.arguments or {}).get("request") or "").strip())
        said = spoken_email.normalize(_last_user_text(params.context)) or request
        # The planner plans from the user's own words. The model's restatement
        # is added only to resolve a reference ("send it") — a 4B planner given
        # a paraphrase as well planned a dentist booking as a note (replay).
        needs_ref = bool(_REFERENCE.search(said.lower()))
        outcome = f"{said} (meaning: {request})" if needs_ref and request and request.lower() != said.lower() else said
        turn: dict = {"said": said, "request": request, "t_tool_call": t0}

        async def speak(text: str) -> None:
            await params.llm.push_frame(TTSSpeakFrame(text=text, append_to_context=False))

        if not _user_spoke_last(params.context):
            # Step 9 replay: the startup "greet the user" instruction made the
            # model call use_tools on its own and read a calendar nobody asked
            # about. The agent acts only on something the user said.
            turn["error"] = "refused: no user request behind this tool call"
            await params.result_callback({"status": "ignored", "rule": "The user asked for nothing. "
                                          "Do not call use_tools unless the user's latest message asks."},
                                         properties=_props(run_llm=False))
            self._report(turn)
            return

        ack = models.acknowledgement(said)
        await speak(ack)
        turn["ack"], turn["t_ack_pushed"] = ack, time.perf_counter()
        self._event({"type": "ack", "text": ack})

        self.broker.stopped = False
        self.verified_tools = frozenset()       # a new run: nothing is done yet
        self.running = True
        self._n += 1
        try:
            rt = await self.runtime()

            async def approver(req: dict) -> dict:
                if self.broker.stopped:      # "stop" already said no to this run
                    ans = {"approved": False, "source": "voice:stop", "verdict": "stopped"}
                    turn.setdefault("approvals", []).append({"tool": req.get("tool"), "answer": ans})
                    return ans
                spoken = req.get("spoken") or f"I'm about to run {req.get('tool')}. Shall I go ahead?"
                self._show(approval_view(req))
                await speak(spoken)
                ans = await self.broker.ask(req, self._timeout)
                verdict = ans.get("verdict")
                if not ans.get("approved"):
                    # one no ends the run's asking: later gated steps are refused
                    # without another question (step 9 replay: a declined delete
                    # went on to ask twice more and waited out two timeouts)
                    self.broker.stopped = True
                    await speak({"unclear": SPOKEN_UNCLEAR, "timeout": SPOKEN_TIMEOUT,
                                 "stopped": SPOKEN_STOPPED}.get(verdict, SPOKEN_DECLINED))
                turn.setdefault("approvals", []).append(
                    {"tool": req.get("tool"), "spoken": spoken, "answer": ans})
                return ans

            res = await rt.run(outcome, approver=approver, on_event=self._event,
                               emit_ack=False, thread_id=f"{self._session}-{self._n}")
        except Exception as e:  # MCP spawn / planner server down: say so, keep the session
            turn["error"] = f"{type(e).__name__}: {e}"
            self.running = False
            await speak(SPOKEN_FAILED)
            await params.result_callback({"status": "failed", "error": turn["error"],
                                          "rule": "Nothing was done. Do not claim otherwise."},
                                         properties=_props(run_llm=False))
            self._report(turn)
            return
        self.running = False

        self.verified_tools = frozenset(verified_mutations(res))
        if self.verified_tools:
            self.last_verified_mutation_at = time.time()
        turn.update(status=res.status, planId=res.plan_id, t_graph_done=time.perf_counter(),
                    plan=[{"tool": st["tool"], "args": st.get("args")} for st in res.plan],
                    steps=[{"tool": r["tool"], "status": r["status"], "error": r.get("error")}
                           for r in res.step_results])
        self._show(self.provenance_view(res))

        payload = voice_result(res)
        # every step refused and already said aloud -> nothing new to say
        all_refused = res.step_results and all(r["status"] == "denied" for r in res.step_results) \
            and turn.get("approvals")
        turn["noFollowUp"] = bool(all_refused)
        await params.result_callback(payload, properties=_props(run_llm=not all_refused))
        self._report(turn)

    def _report(self, turn: dict) -> None:
        if self._on_turn is not None:
            try:
                self._on_turn(turn)
            except Exception:
                pass


def _props(*, run_llm: bool):
    from pipecat.frames.frames import FunctionCallResultProperties

    return FunctionCallResultProperties(run_llm=run_llm)


def _user_spoke_last(context) -> bool:
    """True if a user message comes after the last assistant text reply — the
    tool call answers something the user just said."""
    for m in reversed(list(getattr(context, "messages", []) or [])):
        if not isinstance(m, dict):
            continue
        if m.get("role") == "user":
            return True
        if m.get("role") == "assistant" and m.get("content") and not m.get("tool_calls"):
            return False
    return False


def _last_user_text(context) -> str:
    for m in reversed(list(getattr(context, "messages", []) or [])):
        if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str):
            return m["content"].strip()
    return ""


def _default_runtime():
    from engine.agent.graph import deterministic_report
    from engine.agent.runner import AgentRuntime

    # The conversation model says the result (it reads `voice_result`), so the
    # graph's report stays the model-free deterministic one — no second model
    # call between the tools finishing and the first spoken word.
    return AgentRuntime(reporter=deterministic_report)


def register(llm, bridge: VoiceAgentBridge) -> None:
    """Register `use_tools` on the pipeline's LLM stage, async."""
    llm.register_function(TOOL_NAME, bridge.handle, cancel_on_interruption=False)
