"""Two model roles, one resident model (step 5 Deliverable 2b; step 9 collapse).

| Role     | Model (step 9 default)                    | Reasoning | Budget                         |
|----------|-------------------------------------------|-----------|--------------------------------|
| fast     | WELLSY_FAST_MODEL    (qwen3.5:4b-q4_K_M)  | off       | §1: < 1500 ms p50 (5c: 71 ms TTFT) |
| planner  | WELLSY_PLANNER_MODEL (qwen3.5:4b-q4_K_M)  | off       | 3-4 s ok (5c: 3.47 s full plan, 20/20) |

Step 5c (`.claude/rebuild/step5c-results.md` §2-§3) measured Qwen3.5-4B with
reasoning off as matching or beating `qwen3:4b-instruct-2507` on both budgets,
and as one model for planner + fast + vision (-2.1 GB resident). But Qwen3.5
**thinks by default** (4066 thinking tokens/turn, 0/5 valid plans), and on the
OpenAI-compatible `/v1` endpoint Ollama honours **only** `reasoning_effort:
"none"` -- the `think:false` + `chat_template_kwargs` shape every caller used
to send is ignored there (re-verified on 0.40.5, 2026-10-17: 197-221 reasoning
chars and no content vs 0 with `reasoning_effort`). So the model string and the
request shape change together, here and in `engine.voice.adapters.build_llm`.
`reasoning_effort:"none"` is harmless on the instruct incumbents (5c §1.3), so
an env override back to `qwen3:4b-instruct-2507-q4_K_M` still works.

Always a pinned GGUF tag, never a bare `qwen3.5:4b`: Ollama >= 0.40 may resolve
a bare tag to an MLX build on Apple Silicon (INVARIANTS #14, 5c §1.2).

The acknowledge-then-deliver rule: when a request needs the planner, the fast
path emits an acknowledgement ("let me check your calendar") within the §1
budget while the planner runs behind it. `acknowledgement()` is deterministic —
no model in the ack path, so it cannot itself blow the budget, and it never
claims an action has happened.
"""

from __future__ import annotations

import os
import re
from typing import Any, Literal

Role = Literal["fast", "planner"]

# Both roles resolve to ONE resident model, which is also the voice loop's text
# and vision model (step 9; measured in 5c). Split them by setting the env vars.
DEFAULT_MODEL = "qwen3.5:4b-q4_K_M"
_DEFAULTS = {
    "fast": ("WELLSY_FAST_MODEL", DEFAULT_MODEL),
    "planner": ("WELLSY_PLANNER_MODEL", DEFAULT_MODEL),
}

# The only reasoning off-switch Ollama's /v1 honours for Qwen3.5 (5c §1.3).
# Every request to the local server carries it -- voice, fast and planner.
REQUEST_EXTRA_BODY = {"keep_alive": -1, "reasoning_effort": "none"}


def model_name(role: Role) -> str:
    env, default = _DEFAULTS[role]
    return os.environ.get(env, default)


def base_url() -> str:
    return os.environ.get("WELLSY_LLM_BASE_URL", "http://localhost:11434/v1")


def get_model(role: Role, *, temperature: float = 0.0, **kwargs: Any):
    """A `langchain_openai.ChatOpenAI` bound to the local OpenAI-compatible
    endpoint. Both roles send `reasoning_effort:"none"`: the planner used to
    keep reasoning on, and on Qwen3.5 that is the 80 s / 0-of-5-valid row in
    5c §2. Its plan quality with reasoning off is the measured 20/20."""
    from langchain_openai import ChatOpenAI

    extra_body: dict[str, Any] = dict(REQUEST_EXTRA_BODY)

    return ChatOpenAI(
        model=model_name(role),
        base_url=base_url(),
        api_key=os.environ.get("WELLSY_LLM_API_KEY", "ollama"),
        temperature=temperature,
        # 120 s: a cold model load plus a full plan can take several seconds —
        # the acknowledge-then-deliver rule is what hides that from the user,
        # not a tight client timeout.
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
    (re.compile(r"\b(calendar|meeting|schedul|reschedul|event|appointment|book)", re.I),
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
