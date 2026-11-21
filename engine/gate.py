"""The approval gate: WELLSY's own code (PLAN.md §2.3), on top of deepagents' pause.

It also holds the brain's questions: `ask_user` (a choice between options, each with
its source, e.g. which support address) pauses the same way, and the user's pick, by
voice or click, goes back to the brain as the tool's answer.

deepagents (LangChain's HumanInTheLoopMiddleware, `interrupt_on`) stops the brain
before a risky tool runs and resumes it with a decision. This module decides which
tools are risky, holds each paused action until the user answers, and logs it.

  * Which tools: a tool is risky unless its maker marks it read-only. Composio tags
    every tool (`readOnlyHint`, `createHint`, `destructiveHint`, ...), so a send, a
    create, a delete or an update all pause, in every app, with no per-app list.
    `[approval] always` adds tools by name (e.g. a browser's purchase click, Phase 3).
  * The answer: a spoken yes/no (the voice model's `answer_approval` tool) or a click
    on the panel. The first answer wins; later ones are ignored.
  * Silence is a no: an unanswered action is rejected after `[approval] timeout_secs`.
  * Every request and every decision, with who decided and how long it took, goes to
    `runs/actions.jsonl`.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import dataclass, field

from engine import runs

ASK_USER = "ask_user"   # the brain's question tool (engine/brain.py); its pause is a choice, not a yes

# Arguments shown first on the approval card and in the spoken read-back, when present.
_KEY_ARGS = ("recipient_email", "to", "recipients", "attendees", "cc", "bcc", "subject", "summary",
             "title", "start_datetime", "start", "end_datetime", "end", "timezone", "body", "message",
             "description", "item", "price", "quantity", "url")


@dataclass
class Pending:
    """One action waiting for the user's yes, or one question waiting for a pick."""
    id: str
    task_id: str
    label: str            # the task's label, as the user knows it
    tool: str
    args: dict
    title: str            # "Gmail: send email"
    fields: list[tuple[str, str]]     # the read-back, (name, value), key fields first
    created: float = field(default_factory=time.monotonic)
    future: asyncio.Future | None = None
    asked_at: float | None = None     # when the voice was handed the read-back to ask

    @property
    def kind(self) -> str:
        return "choose" if self.tool == ASK_USER else "approve"

    @property
    def options(self) -> list[dict]:
        return [o if isinstance(o, dict) else {"value": str(o)} for o in self.args.get("options") or []]

    def pick(self, said: str) -> str:
        """The option the user's answer names: by its value, or by position ("the
        second one", "2"); otherwise their own words."""
        said_l = said.lower().strip()
        for o in self.options:
            if said_l and (said_l in o["value"].lower() or o["value"].lower() in said_l):
                return o["value"]
        said_w = said_l.replace(".", " ").replace(",", " ").split()
        ordinals = (("first", "1", "one"), ("second", "2", "two"), ("third", "3", "three"),
                    ("fourth", "4", "four"), ("fifth", "5", "five"))
        # Later positions first: "the second one" says "one" too.
        for i in reversed(range(min(len(ordinals), len(self.options)))):
            if any(w in said_w for w in ordinals[i]):
                return self.options[i]["value"]
        return said.strip()

    def readback(self) -> str:
        """One line the voice can read back before asking."""
        if self.kind == "choose":
            return f"{self.args.get('question', '')} Options: " + "; ".join(
                f"{i + 1}. {o['value']}" for i, o in enumerate(self.options))
        parts = [f"{k}: {v}" for k, v in self.fields[:4]]
        return f"{self.title}. " + "; ".join(parts)

    def view(self) -> dict:
        if self.kind == "choose":
            return {"id": self.id, "kind": "choose", "title": str(self.args.get("question", "")),
                    "options": [{"value": o.get("value", ""), "note": o.get("note", ""),
                                 "source": o.get("source", "")} for o in self.options]}
        return {"id": self.id, "kind": "approve", "title": self.title, "tool": self.tool,
                "fields": [{"name": k, "value": v} for k, v in self.fields]}



def said_yes(text: str, settings: dict) -> bool:
    """True if the user's own words are a yes: a yes phrase and no no-phrase. The
    voice model's own `approved=true` is never enough on its own: Gemini 3.8 Live
    approved twice with nobody speaking (eval, 2026-11-06)."""
    a = settings.get("approval", {})
    words = " " + " ".join("".join(c.lower() if c.isalnum() or c == "'" else " " for c in text).split()) + " "
    hit = lambda phrases: any(f" {p.lower()} " in words for p in phrases)
    return hit(a.get("yes_words", ["yes"])) and not hit(a.get("no_words", ["no"]))


def describe(tool: str, args: dict) -> tuple[str, list[tuple[str, str]]]:
    """A human title and the arguments as display fields, key ones first."""
    app, _, verb = tool.partition("_")
    title = f"{app.capitalize()}: {verb.replace('_', ' ').lower()}" if verb else tool.replace("_", " ")
    keys = [k for k in _KEY_ARGS if k in args] + sorted(k for k in args if k not in _KEY_ARGS)
    fields = []
    for k in keys:
        v = args[k]
        if v in (None, "", [], {}):
            continue
        text = ", ".join(map(str, v)) if isinstance(v, list) else str(v)
        fields.append((k.replace("_", " "), text if len(text) <= 600 else text[:600] + "…"))
    return title, fields


class Gate:
    """Holds paused actions until the user answers. One per voice session; all
    methods run on the session's event loop (use `answer_threadsafe` from the UI)."""

    def __init__(self, settings: dict, *, on_change=None):
        a = settings.get("approval", {})
        self.timeout = float(a.get("timeout_secs", 45))
        self.on_change = on_change          # called after any pending action opens or closes
        self.pending: dict[str, Pending] = {}
        self._ids = itertools.count(1)
        self.loop: asyncio.AbstractEventLoop | None = None

    async def ask(self, *, task_id: str, label: str, tool: str, args: dict) -> dict:
        """Wait for the user's decision on one action. Returns
        {"approved": bool, "source": "voice" | "click" | "timeout" | "cancelled"}."""
        self.loop = asyncio.get_running_loop()
        title, fields = describe(tool, args)
        p = Pending(id=f"a{next(self._ids)}", task_id=task_id, label=label, tool=tool, args=args,
                    title=title, fields=fields, future=self.loop.create_future())
        self.pending[p.id] = p
        runs.log("actions", {"event": "approval_requested", "approval_id": p.id, "task_id": task_id,
                             "label": label, "tool": tool, "args": args})
        self._changed()
        try:
            decision = await asyncio.wait_for(asyncio.shield(p.future), self.timeout)
        except asyncio.TimeoutError:
            decision = {"approved": False, "source": "timeout"}
        except asyncio.CancelledError:
            decision = {"approved": False, "source": "cancelled"}
            self._close(p, decision)
            raise
        self._close(p, decision)
        return decision

    def answer(self, approval_id: str, approved: bool, source: str, heard: str = "", choice: str = "") -> bool:
        """Resolve one pending action (or question: `choice`). False if it is gone or
        already answered."""
        p = self.pending.get(approval_id)
        if p is None or p.future is None or p.future.done():
            return False
        p.future.set_result({"approved": bool(approved), "source": source,
                             **({"heard": heard} if heard else {}), **({"choice": choice} if choice else {})})
        return True

    def answer_threadsafe(self, approval_id: str, approved: bool, source: str = "click") -> None:
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.answer, approval_id, approved, source)

    def waiting(self) -> list[Pending]:
        """Actions still waiting for an answer (an answered one closes on the next tick)."""
        return [p for p in self.pending.values() if p.future is not None and not p.future.done()]

    def for_task(self, task_id: str) -> list[Pending]:
        return [p for p in self.waiting() if p.task_id == task_id]

    def _close(self, p: Pending, decision: dict) -> None:
        if self.pending.pop(p.id, None) is None:
            return
        runs.log("actions", {"event": "approval_decided", "approval_id": p.id, "task_id": p.task_id,
                             "label": p.label, "tool": p.tool, "approved": decision["approved"],
                             "source": decision["source"], "heard": decision.get("heard", ""),
                             **({"choice": decision["choice"]} if decision.get("choice") else {}),
                             "secs": round(time.monotonic() - p.created, 2)})
        self._changed()

    def _changed(self) -> None:
        if self.on_change:
            self.on_change()


def risky_tools(tools: list, read_only: set[str], settings: dict) -> set[str]:
    """Names of the tools that need a yes: every tool from an app (Composio) that its
    maker does not tag read-only, plus `[approval] always`. WELLSY's own tools (search,
    answer, deepagents' in-memory files and todos) never touch the outside world."""
    always = set(settings.get("approval", {}).get("always", []))
    out = set()
    for t in tools:
        app = (getattr(t, "metadata", None) or {}).get("wellsy_source") == "composio"
        if (app and t.name not in read_only) or t.name in always:
            out.add(t.name)
    return out
