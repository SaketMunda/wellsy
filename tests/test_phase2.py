"""Phase 2: the approval gate (real deepagents pause/resume, scripted model), the
voice link's spoken and clicked approvals, silence, the action log, and the panel.
No network: the model and the app are stand-ins; deepagents and LangGraph are real."""

import asyncio

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from engine import brain, gate, runs
from engine import settings as cfg


@pytest.fixture
def settings():
    s = cfg.load()
    return {**s, "preset": "value", "brain": "", "approval": {**s.get("approval", {}), "timeout_secs": 0.5}}


@pytest.fixture(autouse=True)
def tmp_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "RUNS", tmp_path)
    return tmp_path


SENT: list[dict] = []


@tool("GMAIL_SEND_EMAIL")
def send_email(recipient_email: str, subject: str, body: str) -> str:
    """Send an email."""
    SENT.append({"to": recipient_email, "subject": subject})
    return '{"successful": true}'


@tool("GMAIL_FETCH_EMAILS")
def fetch_emails(query: str = "") -> str:
    """Read emails."""
    return '{"messages": []}'


@tool("tavily_search")
def fake_search(query: str) -> str:
    """Search the web."""
    return '{"results": []}'


send_email.metadata = {"wellsy_source": "composio"}
fetch_emails.metadata = {"wellsy_source": "composio"}

EMAIL = {"recipient_email": "help@railway.example", "subject": "Is my app back?", "body": "Hi, when is my app back?"}


class ScriptedModel(GenericFakeChatModel):
    """Replays fixed AI turns; deepagents binds tools, which a script ignores."""

    def bind_tools(self, tools, **kw):
        return self


def script():
    return ScriptedModel(messages=iter([
        AIMessage(content="", tool_calls=[{"name": "GMAIL_SEND_EMAIL", "args": EMAIL, "id": "s1"}]),
        AIMessage(content="", tool_calls=[{"name": "answer", "id": "a1", "args": {
            "spoken": "Done.", "answer": "Handled the email.",
            "candidates": [{"value": "help@railway.example", "source": "https://railway.example/support"}]}}]),
    ]))


@pytest.fixture
def fake_brain(monkeypatch):
    SENT.clear()
    monkeypatch.setattr(brain, "chat_model", lambda spec: script())
    monkeypatch.setattr(brain, "search_tool", lambda s: fake_search)
    monkeypatch.setattr(brain, "app_tools", lambda s: ([send_email, fetch_emails], {"GMAIL_FETCH_EMAILS"}))


def test_only_app_tools_not_tagged_read_only_need_a_yes(settings):
    risky = gate.risky_tools([fake_search, send_email, fetch_emails, brain.answer_tool],
                             {"GMAIL_FETCH_EMAILS"}, settings)
    assert risky == {"GMAIL_SEND_EMAIL"}
    assert gate.risky_tools([fake_search], set(), {"approval": {"always": ["tavily_search"]}}) == {"tavily_search"}


@pytest.mark.parametrize("approved, sent", [(True, 1), (False, 0)])
def test_send_waits_for_the_decision_and_runs_only_on_yes(settings, fake_brain, approved, sent):
    asked = []

    async def on_approval(tool_name, args):
        asked.append((tool_name, args))
        assert SENT == []                       # nothing has been sent while it waits
        return {"approved": approved, "source": "voice"}

    res = asyncio.run(brain.run("email railway support", settings, on_approval=on_approval, task_id="t1"))
    assert asked == [("GMAIL_SEND_EMAIL", EMAIL)]
    assert len(SENT) == sent and res.status == "done"
    assert res.approvals == [{"tool": "GMAIL_SEND_EMAIL", "approved": approved, "source": "voice"}]
    assert res.display["candidates"][0]["value"] == "help@railway.example"
    tool_log = [r for r in runs.read("actions") if r["event"] == "tool"]
    assert tool_log[0]["tool"] == "GMAIL_SEND_EMAIL" and tool_log[0]["gated"] is True
    assert tool_log[0]["status"] == ("done" if approved else "refused")


def test_without_an_approver_a_send_is_refused_and_logged(settings, fake_brain):
    res = asyncio.run(brain.run("email railway support", settings, task_id="t1"))
    assert SENT == [] and res.approvals[0]["source"] == "no approver"
    assert any(r["event"] == "approval_decided" and r["approved"] is False for r in runs.read("actions"))


def test_gate_silence_is_a_no_and_is_logged(settings):
    g = gate.Gate(settings)

    async def go():
        return await g.ask(task_id="t1", label="railway email", tool="GMAIL_SEND_EMAIL", args=EMAIL)

    d = asyncio.run(go())
    assert d == {"approved": False, "source": "timeout"} and g.pending == {}
    req, dec = runs.read("actions")
    assert req["event"] == "approval_requested" and req["args"] == EMAIL
    assert dec["event"] == "approval_decided" and dec["source"] == "timeout" and dec["approved"] is False


def test_gate_first_answer_wins(settings):
    g = gate.Gate(settings)

    async def go():
        t = asyncio.create_task(g.ask(task_id="t1", label="x", tool="GMAIL_SEND_EMAIL", args=EMAIL))
        await asyncio.sleep(0.01)
        (pid,) = g.pending
        assert g.answer(pid, True, "click") is True
        assert g.answer(pid, False, "voice") is False
        return await t

    assert asyncio.run(go()) == {"approved": True, "source": "click"}


def test_readback_puts_recipient_and_subject_first():
    title, fields = gate.describe("GMAIL_SEND_EMAIL", {"body": "b", "subject": "s", "recipient_email": "a@b.c"})
    assert title == "Gmail: send email" and [k for k, _ in fields] == ["recipient email", "subject", "body"]


# --------------------------------------------------------------------------- #
# the voice link: spoken yes, click, silence, cancel while waiting             #
# --------------------------------------------------------------------------- #

class Params:
    def __init__(self, tid="call_1", **args):
        self.tool_call_id, self.arguments = tid, args
        self.results = []

    async def result_callback(self, result, *, properties=None):
        self.results.append(result)


class FakeSession:
    def __init__(self):
        from engine.interface.signals import SignalBus
        self.bus, self.views, self.on_action = SignalBus(), [], None

    def show_hud(self, view):
        self.views.append(view)


class FakeLLM:
    def __init__(self):
        self.frames = []

    async def queue_frame(self, frame):
        self.frames.append(frame)


def _link(settings):
    from engine.voice import Link
    link = Link(settings, session=FakeSession())
    link.llm = FakeLLM()
    return link


async def _until(cond, secs=2.0):
    for _ in range(int(secs / 0.01)):
        if cond():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out")


def test_spoken_yes_sends_and_the_answer_comes_back_on_the_approval_call(settings, fake_brain):
    link = _link(settings)
    d, yes = Params("call_1", task="email railway support", label="railway email"), Params("fc_2", approved=True)

    async def go():
        await link.delegate(d)                      # returns early: an action waits for a yes
        assert d.results[0]["status"] == "needs_approval" and "help@railway.example" in d.results[0]["action"]
        assert SENT == [] and link.session.bus.channel("approval").latest() is not None
        item = link.session.views[-1]["items"][0]
        assert item["approval"]["title"] == "Gmail: send email" and link.session.on_action == link.ui_action
        link.hear("Yes, go ahead.")
        await link.answer_approval(yes)

    asyncio.run(go())
    assert len(SENT) == 1 and yes.results[0]["status"] == "done" and "not_done" not in yes.results[0]
    final = link.session.views[-1]["items"][0]
    assert final["status"] == "done" and final["approval"] is None and final["actions"] == ["Gmail: send email: approved"]
    assert final["candidates"][0]["value"] == "help@railway.example"
    dec = [r for r in runs.read("actions") if r["event"] == "approval_decided"]
    assert dec[0]["source"] == "voice" and dec[0]["approved"] is True and dec[0]["heard"] == "Yes, go ahead."
    assert link.llm.frames == []                    # nothing typed into the voice: the call carried it


def test_spoken_no_blocks_the_send(settings, fake_brain):
    link = _link(settings)
    d, no = Params(task="email railway support", label="railway email"), Params("fc_2", approved=False)

    async def go():
        await link.delegate(d)
        await link.answer_approval(no)

    asyncio.run(go())
    assert SENT == [] and no.results[0]["not_done"] == ["GMAIL_SEND_EMAIL (not approved)"]
    assert link.session.views[-1]["items"][0]["actions"] == ["Gmail: send email: blocked, you said no"]


def test_silence_blocks_the_send_logs_it_and_tells_the_voice(settings, fake_brain):
    from pipecat.frames.frames import LLMMessagesAppendFrame

    link = _link(settings)                          # timeout_secs = 0.5 in this fixture
    d = Params(task="email railway support", label="railway email")

    async def go():
        await link.delegate(d)
        await _until(lambda: link.llm.frames, secs=3)

    asyncio.run(go())
    assert SENT == []
    frame, = link.llm.frames
    assert isinstance(frame, LLMMessagesAppendFrame) and "no answer" in frame.messages[0]["content"]
    dec = [r for r in runs.read("actions") if r["event"] == "approval_decided"]
    assert dec[0]["source"] == "timeout" and dec[0]["approved"] is False


def test_a_click_on_approve_sends_and_the_result_reaches_the_voice(settings, fake_brain):
    link = _link(settings)
    d = Params(task="email railway support", label="railway email")

    async def go():
        await link.delegate(d)
        aid = link.session.views[-1]["items"][0]["approval"]["id"]
        link.ui_action({"type": "approve", "id": aid})      # from the Qt thread in real use
        await _until(lambda: link.llm.frames)
        late = Params("fc_3", approved=False)
        await link.answer_approval(late)                    # too late: the click won
        return late

    late = asyncio.run(go())
    assert len(SENT) == 1 and '"status": "done"' in link.llm.frames[0].messages[0]["content"]
    assert late.results == [{"status": "nothing is waiting for approval"}]


def test_cancel_while_waiting_for_a_yes_blocks_it(settings, fake_brain):
    link = _link(settings)
    d = Params(task="email railway support", label="railway email")

    async def go():
        await link.delegate(d)
        await link.cancel_task(Params("fc_4", label="railway email"))
        await _until(lambda: not link.running)

    asyncio.run(go())
    assert SENT == [] and link.gate.pending == {}
    assert link.session.views[-1]["items"][0]["status"] == "cancelled"
    dec = [r for r in runs.read("actions") if r["event"] == "approval_decided"]
    assert dec[0]["source"] == "cancelled"


@pytest.mark.parametrize("said", [None, "What's the subject again?", "Yes, but wait a second."])
def test_the_voice_model_cannot_approve_without_the_users_own_yes(settings, fake_brain, said):
    """Live eval 2026-11-06: Gemini 3.8 Live called answer_approval(approved=true) 1.3 s
    after the read-back with nobody speaking. Its flag alone must never send."""
    settings["approval"]["timeout_secs"] = 2.5           # outlasts the 1.5 s wait for a late transcript
    link = _link(settings)
    d, yes = Params(task="email railway support", label="railway email"), Params("fc_2", approved=True)

    async def go():
        link.hear("Email Railway support.")         # said before the read-back: does not count
        await link.delegate(d)
        if said:
            link.hear(said)
        await link.answer_approval(yes)
        assert yes.results[0]["status"] == "not confirmed" and link.gate.waiting()
        await _until(lambda: not link.running, secs=5)    # then silence blocks it

    asyncio.run(go())
    assert SENT == []
    dec = [r for r in runs.read("actions") if r["event"] == "approval_decided"]
    assert dec[0]["source"] == "timeout" and dec[0]["approved"] is False
    assert any(r["event"] == "approval_unconfirmed" for r in runs.read("actions"))


@pytest.mark.parametrize("text, yes", [("Yes.", True), ("yeah go ahead", True), ("Haan, send it", True),
                                       ("No.", False), ("Okay wait", False), ("Don't send it", False),
                                       ("hmm", False), ("", False)])
def test_said_yes(settings, text, yes):
    assert gate.said_yes(text, settings) is yes
