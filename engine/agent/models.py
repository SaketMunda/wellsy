"""Two model roles, not one model (step 5 Deliverable 2b).

Step 4 measured the shared LLM row at 3957 ms p50 against a 1500 ms target with
`qwen3:4b`, because that build runs a reasoning pass every turn and no flag
disables it (re-verified by curl, step 4b). Reasoning is poison on the
conversational hot path and genuinely useful in the planner. So:

| Role     | Model                              | Reasoning | Budget                         |
|----------|------------------------------------|-----------|--------------------------------|
| fast     | WELLSY_FAST_MODEL   (qwen2.5:3b*)  | off       | §1: < 1500 ms p50 to first word|
| planner  | WELLSY_PLANNER_MODEL (qwen3:4b)    | on        | 3-4 s ok — the fast path spoke |

*`qwen2.5:3b` is an INTERIM default carried from step 4b, not the answer. It is
a 2024-era model; adopting it because it happened to be installed is the
stale-tech failure mode INVARIANTS #8 exists to stop. Deliverable 2b's bench-off
of current non-reasoning instruct models for the fast slot is recorded debt in
`.claude/rebuild/step5-results.md` — do it and record the losing numbers before
this default is blessed.

The acknowledge-then-deliver rule: when a request needs the planner, the fast
path emits an acknowledgement ("let me check your calendar") within the §1
budget while the planner runs behind it. `acknowledgement()` is deterministic —
no model in the ack path, so it cannot itself blow the budget.
"""

from __future__ import annotations

import os
import re
from typing import Any, Literal

Role = Literal["fast", "planner"]

_DEFAULTS = {
    "fast": ("WELLSY_FAST_MODEL", "qwen2.5:3b"),
    "planner": ("WELLSY_PLANNER_MODEL", "qwen3:4b"),
}


def model_name(role: Role) -> str:
    env, default = _DEFAULTS[role]
    return os.environ.get(env, default)


def base_url() -> str:
    return os.environ.get("WELLSY_LLM_BASE_URL", "http://localhost:11434/v1")


def get_model(role: Role, *, temperature: float = 0.0, **kwargs: Any):
    """A `langchain_openai.ChatOpenAI` bound to the local OpenAI-compatible
    endpoint. `planner` keeps reasoning on; `fast` asks the server to skip it
    (Ollama honours neither `think` today — step 4b — so `fast` also just uses a
    non-reasoning model, which is the real fix)."""
    from langchain_openai import ChatOpenAI

    extra_body: dict[str, Any] = {"keep_alive": -1}
    if role == "fast":
        extra_body["think"] = False
        extra_body["chat_template_kwargs"] = {"enable_thinking": False}

    return ChatOpenAI(
        model=model_name(role),
        base_url=base_url(),
        api_key=os.environ.get("WELLSY_LLM_API_KEY", "ollama"),
        temperature=temperature,
        # 120 s: the planner (reasoning) can take tens of seconds on a cold
        # model — the acknowledge-then-deliver rule is what hides that from the
        # user, not a tight client timeout. Step 4b: qwen3 burns a reasoning
        # pass no flag disables.
        timeout=float(os.environ.get("WELLSY_LLM_TIMEOUT", "120")),
        max_retries=1,
        extra_body=extra_body,
        **kwargs,
    )


# --- routing (deterministic, no model) --------------------------------------

_TRIVIAL = re.compile(
    r"^\s*(hi|hey|hello|thanks|thank you|ok|okay|got it|never mind|nvm)\b", re.I
)
# A bare single read with no conjunction and no scheduling verb is a lookup the
# planner still handles, but it's the kind of thing a fast path *could* answer;
# kept here for when the fast slot is wired into `voice`.
_MULTISTEP = re.compile(
    r"\b(and then|and also|after that|prepare|organi[sz]e|plan|research|book|"
    r"schedule|reschedule|move|draft|reply|send|summari[sz]e|find .* and)\b", re.I
)


def should_plan(text: str) -> bool:
    """True if this outcome needs the planner + tools. Trivial greetings don't."""
    if _TRIVIAL.match(text or ""):
        return False
    return True


_ACK_BY_KEYWORD = [
    (re.compile(r"\bcalendar|meeting|schedule|reschedul|event\b", re.I),
     "Let me check your calendar."),
    (re.compile(r"\bmail|email|reply|inbox|message\b", re.I),
     "Let me look at your mail."),
    (re.compile(r"\bremind|reminder|task\b", re.I),
     "Let me check your reminders."),
    (re.compile(r"\bcontact|phone number|address\b", re.I),
     "Let me look that contact up."),
    (re.compile(r"\bnote|notes\b", re.I), "Let me check your notes."),
    (re.compile(r"\bfile|folder|document|scratch\b", re.I),
     "Let me look at those files."),
    (re.compile(r"\bprepare|brief|prep\b", re.I),
     "Let me pull that together — one moment."),
]


def acknowledgement(text: str) -> str:
    """The line the fast path speaks immediately while the planner runs behind
    it. Deterministic; emitted inside the §1 budget."""
    for pat, ack in _ACK_BY_KEYWORD:
        if pat.search(text or ""):
            return ack
    return "On it — one moment."
