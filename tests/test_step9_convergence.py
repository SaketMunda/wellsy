"""Step 9 — the agent is the brain of the voice loop.

What is proved here without a model or a microphone (the live numbers are in
`.claude/rebuild/step9-results.md`):

  * the request shape: `reasoning_effort:"none"` on every request, one model;
  * spoken approval is a fixed grammar, and anything unclear is a no;
  * the read-back is heard before commit, with dates in words, and a date the
    user didn't say is caught — and forces an approval on a step the policy
    would otherwise run silently;
  * deny, end to end: graph -> interrupt -> spoken question -> spoken "no"
    -> audit denial line -> nothing written -> refusal spoken;
  * the ack never claims an action, and ClaimGuard refuses a completed-action
    claim that no verified mutation backs;
  * IntentGate answers a pending approval deterministically and never forwards
    the answer to the model; `stop` denies;
  * the orb's agent states come from graph events;
  * checkpoints are durable: a second runtime resumes an interrupted plan.
"""

from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from engine.agent import audit, models, readback
from engine.agent.graph import deterministic_report
from engine.honesty.approval import parse_approval


def run(coro):
    return asyncio.run(coro)


def _iso(days, hour, minute=0):
    d = dt.date.today() + dt.timedelta(days=days)
    return dt.datetime.combine(d, dt.time(hour, minute)).isoformat()


def _plan(*steps):
    def planner(outcome, catalog):
        return {"plan": list(steps)}
    return planner


# --------------------------------------------------------------------------- #
# request shape (5c §1.3, §9)                                                  #
# --------------------------------------------------------------------------- #

def test_every_request_turns_reasoning_off_on_one_model(monkeypatch):
    monkeypatch.delenv("WELLSY_FAST_MODEL", raising=False)
    monkeypatch.delenv("WELLSY_PLANNER_MODEL", raising=False)
    assert models.model_name("fast") == models.model_name("planner") == "qwen3.5:4b-q4_K_M"
    for role in ("fast", "planner"):
        m = models.get_model(role)
        assert m.extra_body["reasoning_effort"] == "none"
        assert "think" not in m.extra_body                 # ignored on /v1 (5c §1.3)
        assert "chat_template_kwargs" not in m.extra_body

    from engine.voice import adapters

    monkeypatch.setattr(adapters, "_resolve_ollama_model", lambda b, m: m)
    monkeypatch.setattr(adapters, "_model_has_vision", lambda b, m: True)
    monkeypatch.delenv("WELLSY_LLM_MODEL", raising=False)
    llm = adapters.build_llm(system_instruction="sys")
    assert llm.model == "qwen3.5:4b-q4_K_M"
    eb = llm._settings.extra["extra_body"]
    assert eb["reasoning_effort"] == "none" and "think" not in eb
    llm.use_vlm(True)
    assert llm._settings.model == "qwen3.5:4b-q4_K_M"     # no model flip
    assert llm.on_vlm()


def test_fit_messages_trims_with_headroom_and_never_orphans_a_tool_result():
    from engine.voice.adapters import CONTEXT_BUDGET_TOKENS, _estimate_tokens, fit_messages

    msgs = []
    for i in range(30):
        msgs += [{"role": "user", "content": "question " * 40},
                 {"role": "assistant", "tool_calls": [{"id": f"c{i}", "function": {"name": "use_tools"}}]},
                 {"role": "tool", "tool_call_id": f"c{i}", "content": "result " * 40}]
    out = fit_messages(msgs)
    assert out[-1] is msgs[-1]
    assert out[0]["role"] == "user"                       # never starts on a tool fragment
    assert sum(_estimate_tokens(m) for m in out) <= 0.6 * CONTEXT_BUDGET_TOKENS + 200
    # once trimmed, the next appended turn fits without another edit
    again = fit_messages(out + [{"role": "user", "content": "one more"}])
    assert len(again) == len(out) + 1


# --------------------------------------------------------------------------- #
# spoken approval grammar                                                      #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text,verdict", [
    ("yes", "yes"), ("Yeah, go ahead.", "yes"), ("Yes please.", "yes"),
    ("Wellsy, do it", "yes"), ("okay", "yes"), ("Yes, send it.", "yes"),
    ("no", "no"), ("Nope.", "no"), ("yes, no wait", "no"), ("Don't.", "no"),
    ("hold on", "no"), ("cancel that", "no"),
    ("what time is it", "unclear"), ("yes but tomorrow", "unclear"),
    ("thank you", "unclear"), ("right now", "unclear"), ("", "unclear"),
    ("maybe", "unclear"),
])
def test_parse_approval(text, verdict):
    assert parse_approval(text) == verdict


# --------------------------------------------------------------------------- #
# read-back before commit                                                      #
# --------------------------------------------------------------------------- #

NOW = dt.datetime(2026, 10, 17, 10, 0)          # a Saturday


def test_spoken_when_names_weekday_and_date():
    s = readback.spoken_when(dt.datetime(2026, 10, 19, 15, 0), dt.datetime(2026, 10, 19, 16, 30), NOW)
    assert s == "Monday, October 19 from 3 PM to 4:30 PM"


def test_monday_rendered_as_sunday_is_caught():
    # the 5b finding: "Monday" planned as a Sunday
    w = readback.date_warnings("Set up a call with Dana on Monday at 3pm",
                               {"start": "2026-10-18T15:00:00"}, NOW)
    assert any("you said Monday, but I have Sunday, October 18" in x for x in w)


def test_tomorrow_wrong_time_and_past_dates_are_caught():
    assert readback.date_warnings("remind me tomorrow", {"due": "2026-10-19T09:00:00"}, NOW)
    w = readback.date_warnings("tomorrow at 3 pm", {"start": "2026-10-18T13:00:00"}, NOW)
    assert any("you said 3 PM, but I have 1 PM" in x for x in w)
    assert any("already passed" in x
               for x in readback.date_warnings("book it", {"start": "2026-07-01T09:00:00"}, NOW))
    assert readback.date_warnings("tomorrow at 3pm", {"start": "2026-10-18T15:00:00"}, NOW) == []
    assert readback.date_warnings("no date said", {"start": "2026-10-20T15:00:00"}, NOW) == []


def test_date_check_reads_only_what_the_user_said():
    w = readback.date_warnings("remind me tomorrow at 6 pm (meaning: remind on Sunday)",
                               {"due": "2026-10-18T18:00:00"}, NOW)
    assert w == []
    w = readback.date_warnings("remind me tomorrow at 6 pm (meaning: Monday)",
                               {"due": "2026-10-19T18:00:00"}, NOW)
    assert w == ["you said tomorrow, but I have Monday, October 19"]


def test_planner_gets_a_day_table_not_arithmetic():
    from engine.agent.graph import day_table

    t = day_table(dt.date(2026, 10, 17))
    assert "today: Saturday 2026-10-17" in t and "tomorrow: Sunday 2026-10-18" in t
    assert "this Monday: Monday 2026-10-19" in t and "next Saturday: Saturday 2026-10-24" in t


def test_create_event_read_back_handles_minute_precision_offsets(agent_env):
    from engine.agent.runner import auto_approver, run_agent

    start = (dt.datetime.now().astimezone() + dt.timedelta(days=2)).replace(
        hour=15, minute=0, second=0, microsecond=0)
    res = run(run_agent("add it", approver=auto_approver,
                        planner=_plan({"tool": "pim.calendar_create_event", "args": {
                            "title": "Offset", "start": start.isoformat(timespec="minutes"),
                            "end": (start + dt.timedelta(hours=1)).isoformat(timespec="minutes")},
                            "why": "x"}),
                        reporter=deterministic_report, use_models=False))
    assert res.step_results[0]["status"] == "ok", res.step_results[0]["readBack"]


def test_preview_is_the_spoken_question_with_resolved_values():
    async def lookup(tool, args):
        return {"subject": "Re: integration timeline", "to": ["dana.kim@partner.example"]}

    pv = run(readback.preview("pim.mail_send_draft", {"draft_id": "d1"}, "send it", lookup, NOW))
    # the address is spelled out — that is where speech recognition goes wrong
    assert pv["spoken"] == ("I'm about to send the email “Re: integration timeline” to "
                            "d a n a dot k i m, at partner dot example. Shall I go ahead?")
    pv = run(readback.preview("pim.calendar_create_event",
                              {"title": "Dentist", "start": "2026-10-18T15:00:00",
                               "end": "2026-10-18T16:00:00"}, "dentist on monday at 3pm", None, NOW))
    assert pv["spoken"].startswith("Careful: you said Monday, but I have Sunday, October 18. ")
    assert "add “Dentist” to your calendar, Sunday, October 18 from 3 PM to 4 PM" in pv["spoken"]


def test_approval_request_carries_the_read_back(agent_env):
    from engine.agent.runner import run_agent

    seen = []
    res = run(run_agent(
        "Move my design review to " + dt.date.fromordinal(
            dt.date.today().toordinal() + 3).strftime("%A"),
        approver=lambda req: (seen.append(req), {"approved": False, "source": "test"})[1],
        planner=_plan({"tool": "pim.calendar_move_event",
                       "args": {"event_id": "evt-review", "new_start": _iso(3, 15),
                                "new_end": _iso(3, 16)}, "why": "move"}),
        reporter=deterministic_report, use_models=False))
    req = seen[0]
    assert req["spoken"].startswith("I'm about to move “")       # the event's real title, looked up
    assert "Shall I go ahead?" in req["spoken"]
    assert req["preview"]["dateWarnings"] == []
    assert res.step_results[0]["status"] == "denied"


def test_date_mismatch_forces_approval_on_a_silent_step(agent_env):
    from engine.agent.runner import run_agent

    # reminders_create is risk 1 -> runs silently. With a date the user didn't
    # say, it must ask first.
    wrong_day = (dt.date.today() + dt.timedelta(days=2))
    said_day = (dt.date.today() + dt.timedelta(days=3)).strftime("%A")
    seen = []
    res = run(run_agent(
        f"Remind me to call mom on {said_day}",
        approver=lambda req: (seen.append(req), {"approved": False, "source": "voice:no"})[1],
        planner=_plan({"tool": "pim.reminders_create",
                       "args": {"title": "Call mom", "due": dt.datetime.combine(
                           wrong_day, dt.time(9)).isoformat()}, "why": "remind"}),
        reporter=deterministic_report, use_models=False))
    assert seen, "a mismatched date must not commit silently"
    assert seen[0]["spoken"].startswith(f"Careful: you said {said_day}")
    assert res.step_results[0]["status"] == "denied"

    # and with the right date it still runs silently (autonomy rule unchanged)
    seen.clear()
    res = run(run_agent(
        f"Remind me to call mom on {said_day}",
        approver=lambda req: (seen.append(req), {"approved": False, "source": "x"})[1],
        planner=_plan({"tool": "pim.reminders_create",
                       "args": {"title": "Call mom", "due": dt.datetime.combine(
                           wrong_day + dt.timedelta(days=1), dt.time(9)).isoformat()},
                       "why": "remind"}),
        reporter=deterministic_report, use_models=False))
    assert not seen and res.step_results[0]["status"] == "ok"


def test_said_send_completes_a_draft_only_plan():
    from engine.agent.graph import complete_plan

    draft = [{"tool": "pim.contacts_search", "args": {}}, {"tool": "pim.mail_create_draft", "args": {}}]
    out = complete_plan("Draft a reply to Dana saying Thursday works, and send it.", draft)
    assert out[-1] == {"tool": "pim.mail_send_draft", "args": {"draft_id": "$2.id"},
                       "why": "you asked to send it (added: the plan drafted but did not send)"}
    assert complete_plan("Draft a reply to Dana but don't send it", draft) == draft
    assert complete_plan("Draft a reply to Dana", draft) == draft


def test_step_references_thread_ids_and_block_on_failure(agent_env):
    from engine.agent.backends import get_pim_backend
    from engine.agent.graph import UnresolvedRef, resolve_refs
    from engine.agent.runner import auto_approver, run_agent

    ok = [{"status": "ok", "result": {"id": "d-1"}}, {"status": "ok", "result": [{"id": "e-9"}]}]
    assert resolve_refs({"draft_id": "$1.id", "x": ["$s2.id"], "y": "$notaref"}, ok) == \
        {"draft_id": "d-1", "x": ["e-9"], "y": "$notaref"}
    with pytest.raises(UnresolvedRef):
        resolve_refs({"draft_id": "$1.id"}, [{"status": "denied"}])

    # draft -> send, the id threaded by reference (replay finding: "<from_create>")
    res = run(run_agent("Draft a reply to Dana and send it", approver=auto_approver,
                        planner=_plan(
                            {"tool": "pim.mail_create_draft",
                             "args": {"to": ["dana.kim@partner.example"], "subject": "Re: timeline",
                                      "body": "Thursday works."}, "why": "draft"},
                            {"tool": "pim.mail_send_draft", "args": {"draft_id": "$1.id"}, "why": "send"}),
                        reporter=deterministic_report, use_models=False))
    assert [r["status"] for r in res.step_results] == ["ok", "ok"]
    assert any(m.subject == "Re: timeline" for m in get_pim_backend().list_sent())


# --------------------------------------------------------------------------- #
# the bridge — deny, end to end, into the audit log                            #
# --------------------------------------------------------------------------- #

class _FakeLLM:
    def __init__(self):
        self.spoken: list[str] = []

    async def push_frame(self, frame, direction=None):
        self.spoken.append(getattr(frame, "text", ""))


class _Params:
    def __init__(self, said, request, llm):
        from pipecat.processors.aggregators.llm_context import LLMContext

        self.arguments = {"request": request}
        self.context = LLMContext(messages=[{"role": "user", "content": said}])
        self.llm = llm
        self.results: list = []

    async def result_callback(self, result, *, properties=None):
        self.results.append((result, properties))


def _bridge(planner, **kw):
    from engine.agent.runner import AgentRuntime
    from engine.voice.agent_bridge import VoiceAgentBridge

    return VoiceAgentBridge(
        runtime_factory=lambda: AgentRuntime(planner=planner, reporter=deterministic_report,
                                             use_models=False), **kw)


async def _answer_when_pending(bridge, text, delay=0.0):
    for _ in range(500):
        if bridge.broker.pending:
            await asyncio.sleep(delay)
            return bridge.broker.answer_spoken(text)
        await asyncio.sleep(0.01)
    raise AssertionError("approval never became pending")


def test_spoken_deny_end_to_end_into_audit_log(agent_env):
    from engine.agent.backends import get_pim_backend
    from engine.agent.backends.portable import PortablePimBackend

    title = "Dentist"
    planner = _plan({"tool": "pim.calendar_create_event",
                     "args": {"title": title, "start": _iso(1, 15), "end": _iso(1, 16)},
                     "why": "book"})
    events, huds = [], []
    bridge = _bridge(planner, on_event=events.append, show_hud=huds.append, hide_hud=lambda: None)
    llm = _FakeLLM()
    params = _Params("Book a dentist appointment tomorrow at 3pm", "create event Dentist", llm)

    async def go():
        answer = asyncio.create_task(_answer_when_pending(bridge, "no, don't"))
        await bridge.handle(params)
        verdict = await answer
        await bridge.close()
        return verdict

    assert run(go()) == "no"

    # heard, in order: honest ack, the read-back question, the refusal
    assert llm.spoken[0] == "Let me check your calendar."
    assert llm.spoken[1].startswith("I'm about to add “Dentist” to your calendar, ")
    assert "from 3 PM to 4 PM. Shall I go ahead?" in llm.spoken[1]
    assert llm.spoken[2] == "Okay, I won't do that."
    # the HUD opened on the approval, with the read-back
    assert any(h.get("kind") == "approval" and h.get("action", "").startswith("add") for h in huds)
    # the audit log has the denial, attributed to the spoken answer
    rows = [r for r in audit.read_all() if r["tool"] == "pim.calendar_create_event"]
    assert rows and rows[-1]["policyDecision"] == "deny"
    assert rows[-1]["approvalSource"] == "voice:no"
    # nothing was written
    PortablePimBackend()  # reload from disk
    assert not any(e.title == title for e in get_pim_backend().list_events(_iso(0, 0), _iso(3, 0)))
    # the model is told it was refused, and is not re-run (the refusal was spoken)
    result, props = params.results[-1]
    assert result["steps"][0]["status"] == "denied" and props.run_llm is False
    assert {"approval_request", "approval_answer", "step_denied", "done"} <= {e["type"] for e in events}


def test_spoken_yes_runs_and_is_verified(agent_env):
    planner = _plan({"tool": "pim.calendar_create_event",
                     "args": {"title": "Dentist", "start": _iso(1, 15), "end": _iso(1, 16)},
                     "why": "book"})
    bridge = _bridge(planner)
    llm = _FakeLLM()
    params = _Params("Book a dentist appointment tomorrow at 3pm", "create event", llm)

    async def go():
        t = asyncio.create_task(_answer_when_pending(bridge, "yes, go ahead"))
        await bridge.handle(params)
        await t
        await bridge.close()

    run(go())
    result, props = params.results[-1]
    assert result["status"] == "ok" and result["steps"][0]["verified"] is True
    assert props.run_llm is True                          # the model says the result
    assert bridge.verified_tools == {"pim.calendar_create_event"}   # the evidence ClaimGuard accepts
    rows = [r for r in audit.read_all() if r["tool"] == "pim.calendar_create_event"]
    assert rows[-1]["approvalSource"] == "voice:yes" and rows[-1]["outcome"] == "ok"


def test_no_tool_run_without_a_user_request(agent_env):
    from pipecat.processors.aggregators.llm_context import LLMContext

    ran = []
    bridge = _bridge(lambda o, c: ran.append(o) or {"plan": []})
    llm = _FakeLLM()
    params = _Params("", "check calendar", llm)
    params.context = LLMContext(messages=[{"role": "system", "content": "Greet the user in one short sentence."}])

    async def go():
        await bridge.handle(params)
        await bridge.close()

    run(go())
    assert not ran and not llm.spoken                # no ack, no plan, nothing said
    result, props = params.results[-1]
    assert result["status"] == "ignored" and props.run_llm is False


@pytest.mark.parametrize("answer,spoken", [
    ("what time is it", "I didn't hear a clear yes, so I won't do that."),
])
def test_unclear_answer_is_a_spoken_refusal(agent_env, answer, spoken):
    planner = _plan({"tool": "pim.calendar_create_event",
                     "args": {"title": "X", "start": _iso(1, 15), "end": _iso(1, 16)}, "why": "b"})
    bridge = _bridge(planner)
    llm = _FakeLLM()

    async def go():
        t = asyncio.create_task(_answer_when_pending(bridge, answer))
        await bridge.handle(_Params("add X tomorrow at 3pm", "add X", llm))
        await t
        await bridge.close()

    run(go())
    assert llm.spoken[-1] == spoken
    assert audit.read_all()[-1]["approvalSource"] == "voice:unclear"


def test_stop_denies_pending_and_the_rest_of_the_run(agent_env):
    planner = _plan(
        {"tool": "pim.calendar_create_event",
         "args": {"title": "A", "start": _iso(1, 15), "end": _iso(1, 16)}, "why": "a"},
        {"tool": "pim.calendar_create_event",
         "args": {"title": "B", "start": _iso(1, 17), "end": _iso(1, 18)}, "why": "b"},
    )
    bridge = _bridge(planner)
    llm = _FakeLLM()
    params = _Params("add A and B tomorrow", "add A and B", llm)

    async def go():
        async def stop_when_pending():
            for _ in range(500):
                if bridge.broker.pending:
                    bridge.broker.stop()
                    return
                await asyncio.sleep(0.01)
        t = asyncio.create_task(stop_when_pending())
        await bridge.handle(params)
        await t
        await bridge.close()

    run(go())
    result, _ = params.results[-1]
    assert [s["status"] for s in result["steps"]] == ["denied", "denied"]
    assert llm.spoken.count("Stopped. I won't do that.") == 1     # asked once, then refused silently
    assert sum("Shall I go ahead?" in s for s in llm.spoken) == 1


def test_click_answers_from_another_thread(agent_env):
    import threading

    planner = _plan({"tool": "pim.calendar_create_event",
                     "args": {"title": "C", "start": _iso(1, 15), "end": _iso(1, 16)}, "why": "c"})
    bridge = _bridge(planner)

    async def go():
        async def click():
            for _ in range(500):
                if bridge.broker.pending:
                    threading.Thread(target=bridge.broker.answer_threadsafe,
                                     args=(True, "user:orb")).start()
                    return
                await asyncio.sleep(0.01)
        t = asyncio.create_task(click())
        await bridge.handle(_Params("add C tomorrow at 3pm", "add C", _FakeLLM()))
        await t
        await bridge.close()

    run(go())
    rows = [r for r in audit.read_all() if r["tool"] == "pim.calendar_create_event"]
    assert rows[-1]["approvalSource"] == "user:orb" and rows[-1]["outcome"] == "ok"


# --------------------------------------------------------------------------- #
# honesty of what is said                                                      #
# --------------------------------------------------------------------------- #

def test_ack_never_claims_an_action():
    from engine.voice.claim_guard import guard_sentence

    acks = {models.acknowledgement(t) for t in (
        "what's on my calendar", "send the email", "remind me", "find Dana's phone number",
        "make a note", "write a file", "prepare my morning", "do the thing")}
    for a in acks:
        assert a.startswith(("Let me", "On it")), a
        assert guard_sentence(a) is None, a


@pytest.mark.parametrize("sentence", [
    "I've sent it.", "I sent the email to Dana.", "Your reminder is set.",
    "It's been added to your calendar.", "The event was moved to Thursday.", "Done.",
])
def test_completed_action_claim_needs_a_verified_mutation(sentence):
    from engine.voice.claim_guard import ACTION_REPLACEMENT, guard_sentence

    assert guard_sentence(sentence) == ACTION_REPLACEMENT
    everything = {"pim.mail_send_draft", "pim.mail_create_draft", "pim.reminders_create",
                  "pim.calendar_create_event", "pim.calendar_move_event"}
    assert guard_sentence(sentence, verified=everything) is None


def test_each_claimed_verb_needs_its_own_verified_tool():
    from engine.voice.claim_guard import ACTION_REPLACEMENT, guard_sentence

    # the replay finding: a verified reminder must not vouch for a failed send
    s = "I've drafted the email saying Thursday works and sent it."
    assert guard_sentence(s, verified={"pim.reminders_create"}) == ACTION_REPLACEMENT
    assert guard_sentence(s, verified={"pim.mail_create_draft"}) == ACTION_REPLACEMENT
    assert guard_sentence(s, verified={"pim.mail_create_draft", "pim.mail_send_draft"}) is None
    assert guard_sentence("Your reminder is set.", verified={"pim.reminders_create"}) is None
    # the object named needs its own evidence: a calendar event is not a reminder
    assert guard_sentence("I also set a reminder for your call with mom.",
                          verified={"pim.calendar_create_event"}) == ACTION_REPLACEMENT
    assert guard_sentence("The dentist appointment has been added to your calendar.",
                          verified={"pim.calendar_create_event"}) is None
    # a note is not a calendar entry
    assert guard_sentence("I've scheduled your dentist appointment for Monday.",
                          verified={"pim.notes_create"}) == ACTION_REPLACEMENT


@pytest.mark.parametrize("sentence", [
    "I haven't sent it.", "I can set a reminder for you.", "Let me check your calendar.",
    "You have a standup at 9:30.", "I didn't add the event because you said no.",
    "Okay, I won't do that.",
])
def test_non_claims_pass(sentence):
    from engine.voice.claim_guard import guard_sentence

    assert guard_sentence(sentence) is None


# --------------------------------------------------------------------------- #
# IntentGate: a pending approval is answered deterministically                 #
# --------------------------------------------------------------------------- #

def test_gate_answers_pending_approval_and_forwards_nothing():
    run(_gate_answers())


async def _gate_answers():
    from pipecat.frames.frames import InterruptionFrame, TranscriptionFrame
    from pipecat.tests.utils import run_test

    from engine.voice.agent_bridge import ApprovalBroker
    from engine.voice.intent_gate import build_intent_gate
    from engine.voice.wake import WakeState

    for text, approved, interrupted in (("yes please", True, False),
                                        ("what's the weather", False, False),
                                        ("stop", False, True)):
        broker = ApprovalBroker()
        ask = asyncio.create_task(broker.ask({"tool": "x"}, timeout=10))
        await asyncio.sleep(0)
        gate = build_intent_gate(WakeState(awake=True), approvals=broker)
        down, _ = await run_test(gate, frames_to_send=[TranscriptionFrame(text, "", "now")],
                                 start_timeout=10.0)
        ans = await ask
        assert ans["approved"] is approved, text
        assert not any(isinstance(f, TranscriptionFrame) for f in down), text   # never reaches the LLM
        assert any(isinstance(f, InterruptionFrame) for f in down) is interrupted


def test_broker_timeout_is_a_refusal():
    from engine.voice.agent_bridge import ApprovalBroker

    ans = run(ApprovalBroker().ask({"tool": "x"}, timeout=0.05))
    assert ans == {"approved": False, "source": "voice:timeout", "verdict": "timeout"}


# --------------------------------------------------------------------------- #
# the orb drives from graph events                                             #
# --------------------------------------------------------------------------- #

def test_orb_states_follow_graph_events(agent_env):
    from engine.agent.runner import run_agent
    from engine.interface.signals import SignalBus
    from engine.interface.state import OrbState, derive_state
    from engine.interface.taps import agent_event_sink

    bus = SignalBus()
    sink = agent_event_sink(bus)
    states = []

    def on_event(ev):
        sink(ev)
        states.append((ev["type"], derive_state(bus).state))

    def approver(req):
        states.append(("asking", derive_state(bus).state))
        return {"approved": False, "source": "test"}

    run(run_agent("look then add", approver=approver, on_event=on_event,
                  planner=_plan(
                      {"tool": "pim.calendar_list_events",
                       "args": {"start": _iso(0, 0)[:19], "end": _iso(2, 0)[:19]}, "why": "read"},
                      {"tool": "pim.calendar_create_event",
                       "args": {"title": "Z", "start": _iso(1, 15), "end": _iso(1, 16)}, "why": "add"}),
                  reporter=deterministic_report, use_models=False))
    got = dict((t, s) for t, s in states)
    assert got["plan_ready"] == OrbState.THINKING
    assert got["step_start"] == OrbState.ACTING
    assert got["asking"] == OrbState.AWAITING_APPROVAL
    assert got["step_denied"] == OrbState.REFUSING
    assert states[-1] == ("done", OrbState.REFUSING)     # the refusal latch outlives "done"


# --------------------------------------------------------------------------- #
# durable checkpoints: SqliteSaver                                             #
# --------------------------------------------------------------------------- #

def test_interrupted_plan_resumes_from_a_second_runtime(agent_env):
    from langgraph.types import Command

    from engine.agent.runner import AgentRuntime, checkpoint_path

    planner = _plan({"tool": "pim.calendar_create_event",
                     "args": {"title": "Durable", "start": _iso(1, 15), "end": _iso(1, 16)},
                     "why": "add"})
    cfg = {"configurable": {"thread_id": "resume-test"}}

    async def first():
        async with AgentRuntime(planner=planner, reporter=deterministic_report, use_models=False) as rt:
            out = await rt._graph.ainvoke({"outcome": "add Durable tomorrow at 3pm", "plan_id": "p1"}, cfg)
            return out["__interrupt__"][0].value

    async def second():
        async with AgentRuntime(planner=planner, reporter=deterministic_report, use_models=False) as rt:
            return await rt._graph.ainvoke(Command(resume={"approved": True, "source": "test:resume"}), cfg)

    req = run(first())                      # runtime 1 stops at the interrupt and closes
    assert req["tool"] == "pim.calendar_create_event"
    assert checkpoint_path().exists()
    out = run(second())                     # runtime 2 (new tools, new connection) resumes it
    assert out["step_results"][0]["status"] == "ok"
    assert audit.read_all()[-1]["approvalSource"] == "test:resume"


# --------------------------------------------------------------------------- #
# live-run follow-up (2026-10-22): spoken email addresses                      #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("heard,want", [
    ("The email address is sakith.munda at the rate gmail.com.", "sakith.munda@gmail.com"),
    ("the correct email address is socket. dot munda. add the rate. gmail.com", "socket.munda@gmail.com"),
    ("email saket dot munda at the rate gmail dot com saying hi", "saket.munda@gmail.com"),
    ("mail priya underscore n at outlook dot com", "priya_n@outlook.com"),
    ("send it to saket.munda@gmail.com", "saket.munda@gmail.com"),
])
def test_spoken_email_addresses_are_written(heard, want):
    from engine.honesty.spoken_email import find

    assert find(heard) == [want]


@pytest.mark.parametrize("heard", [
    "The email address of my friend is sakeeth.mundiatharitgmail.com.",   # garbled: never guessed
    "meet me at the station", "I am at home dot com later",
])
def test_non_addresses_are_left_alone(heard):
    from engine.honesty.spoken_email import normalize

    assert normalize(heard) == heard


def test_a_draft_to_an_invalid_address_never_runs(agent_env):
    from engine.agent.runner import auto_approver, run_agent

    res = run(run_agent("email my friend", approver=auto_approver,
                        planner=_plan({"tool": "pim.mail_create_draft", "args": {
                            "to": ["sakeeth.mundiatharitgmail.com"], "subject": "hi", "body": "hi"},
                            "why": "x"}),
                        reporter=deterministic_report, use_models=False))
    r = res.step_results[0]
    assert r["status"] == "error" and "not a valid email address" in r["error"]
    assert not [a for a in audit.read_all() if a["tool"] == "pim.mail_create_draft"]   # never called
