"""`wellsy bench --modality llm` — the per-slot model bench-off.

`.claude/rebuild/step5b-model-selection.md` Deliverable 1. The old
`wellsy bench --modality llm` reported **one** composite `openai_http` row
(whatever `WELLSY_LLM_MODEL` happened to be). That hides exactly the decision
step 5b exists to make: *which* model fills each role.

This module runs a **named candidate set per slot** (`planner`, `fast`, `vlm`)
against the local OpenAI-compatible server and emits a comparison table:

    cold-load s, TTFT p50/p95, tokens/sec, resident MB, and
    **thinking-token count per turn** — the metric that caught `qwen3:4b`
    (step 4/5). It lives in the harness now, not in a session's notes.

Measurement rule (INVARIANTS "measured, not estimated" / §1): n >= 20 warm
trials, the cold turn recorded separately, p50 and p95, and the method string
written into every row. TTFT here is time from request send to the first
`content` **or** `thinking` token off the wire.

    wellsy bench --modality llm                 # every slot, every candidate
    wellsy bench --modality llm --slot planner  # one slot
    wellsy bench --modality llm --trials 30
    wellsy bench --modality llm --candidate qwen3:4b-instruct-2507-q4_K_M

The candidate sets are literals below — edit them, don't pass models by hand.
Sizes/licences and the reasoning behind each pick: `.claude/rebuild/step5b-research.md` §2-4.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterator

import httpx

from engine.inference import base
from engine.inference.bench import RESULTS_DIR, _commit, pct

DEFAULT_BASE_URL = os.environ.get("WELLSY_LLM_BASE_URL", "http://localhost:11434/v1")
VERIFIED = "2026-09-03"


# --------------------------------------------------------------------------- #
# candidate sets — step 5b research §2-4, lean set approved by the owner       #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Candidate:
    slot: str                       # "planner" | "fast" | "vlm"
    model: str                      # server model id
    note: str                       # why it is in the running
    think: Any = None               # None | False | "low" | "medium" | "high"
                                    #   passed as Ollama `think`; None omits it
    incumbent: bool = False


CANDIDATES: list[Candidate] = [
    # --- planner: needs a >=3-step tool plan under the schema, TTFT ~3-4 s ----
    Candidate("planner", "qwen3:4b-instruct-2507-q4_K_M",
              "non-reasoning by construction — the likely answer", think=None),
    Candidate("planner", "qwen3:4b-thinking-2507-q4_K_M",
              "always reasons; probe think:low/high for a bounded prefix", think=None),
    Candidate("planner", "qwen3:4b-thinking-2507-q4_K_M",
              "same model, think='low' — does the server bound it?", think="low"),
    Candidate("planner", "qwen3:4b",
              "hybrid incumbent-adjacent; carries the 33 s TTFT number", think=None,
              incumbent=True),
    # --- fast: TTFT < 1 s, >= 30 tok/s, short replies + the ack line ---------
    Candidate("fast", "qwen2.5:3b", "incumbent / interim — the number to beat",
              think=None, incumbent=True),
    Candidate("fast", "qwen3:4b-instruct-2507-q4_K_M",
              "current same-class; if TTFT < 1 s it unifies fast+planner", think=None),
    Candidate("fast", "qwen3:1.7b", "smaller/faster — does quality survive?", think=None),
    # --- vlm: text+image turn for a TTFT/token-count number. The authoritative
    #     legibility + resolution sweep is Deliverable 3 (real vision path). ---
    Candidate("vlm", "qwen3-vl:2b-instruct-q4_K_M",
              "lightest non-reasoning VLM; Orin-friendly", think=None),
    Candidate("vlm", "qwen2.5vl:3b", "step-5 interim VLM — baseline to beat",
              think=None, incumbent=True),
]


# --------------------------------------------------------------------------- #
# workloads                                                                    #
# --------------------------------------------------------------------------- #

_TOOL_CATALOG = (
    "calendar_list_events, calendar_get_event, calendar_create_event, "
    "calendar_move_event, reminders_create, reminders_list, mail_search, "
    "mail_get_message, mail_create_draft, mail_send_draft, notes_create, "
    "notes_search, contacts_search, fs_list_dir, fs_read_file, fs_write_file"
)

_PLAN_SYSTEM = (
    "You are WELLSY's planner. Given a request, emit ONLY a JSON object "
    '{"steps": [{"tool": <name>, "args": {...}}, ...]} using these tools: '
    + _TOOL_CATALOG
    + ". No prose, no markdown fence. Today is 2026-09-03 (Thursday)."
)
_PLAN_USER = (
    "Move my 3pm meeting today to the same time on Monday, then draft a short "
    "email to Alex telling them about the new time, then add a reminder to "
    "confirm Alex replied on Friday afternoon."
)

_CHAT_USER = (
    "In one sentence, suggest a good time this evening for a 20-minute walk "
    "and why."
)

_VLM_USER = "What text do you see in this image? List it verbatim."


def _messages(slot: str) -> list[dict[str, Any]]:
    if slot == "planner":
        return [{"role": "system", "content": _PLAN_SYSTEM},
                {"role": "user", "content": _PLAN_USER}]
    if slot == "fast":
        return [{"role": "user", "content": _CHAT_USER}]
    if slot == "vlm":
        return [{"role": "user", "content": _VLM_USER}]
    raise KeyError(slot)


def _vlm_image_data_uri() -> str:
    """A 768x768 PNG with a few lines of small text — enough for a token-count
    and TTFT number. Real screen-text legibility is Deliverable 3."""
    import base64 as _b64

    import cv2  # already a dep (perception)
    import numpy as np

    img = np.full((768, 768, 3), 245, dtype=np.uint8)
    lines = [
        "WELLSY vision bench",
        "Meeting: 3:00 PM - Design review",
        "Room 4B  .  invite: alex@example.com",
        "Action: move to Monday, notify Alex",
        "small print: the quick brown fox 12345",
    ]
    y = 120
    for i, ln in enumerate(lines):
        scale = 0.9 if i < 4 else 0.5
        cv2.putText(img, ln, (40, y), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (20, 20, 20), 1, cv2.LINE_AA)
        y += 110 if i < 4 else 60
    ok, buf = cv2.imencode(".png", img)
    return "data:image/png;base64," + _b64.b64encode(buf.tobytes()).decode()


# --------------------------------------------------------------------------- #
# one streamed turn against the server                                         #
# --------------------------------------------------------------------------- #


@dataclass
class TurnResult:
    ttft_s: float | None
    wall_s: float
    content_chars: int
    think_chars: int
    eval_count: int | None          # total output tokens (server-reported)
    eval_s: float | None            # generation time (server-reported)
    load_s: float | None            # cold model-load time (server-reported)
    prompt_tokens: int | None
    ok: bool
    detail: str = ""
    content_text: str = ""          # full assembled answer (for the plan-JSON check)

    @property
    def think_tokens_est(self) -> float | None:
        """Char-proportional split of the server's real `eval_count`. Method is
        recorded in the row; the metric only has to catch a model burning a
        thousand-token reasoning prefix, and this does that reproducibly."""
        if self.eval_count is None:
            return None
        total = self.content_chars + self.think_chars
        if total == 0:
            return 0.0
        return round(self.eval_count * self.think_chars / total, 1)

    @property
    def tok_per_s(self) -> float | None:
        if self.eval_count and self.eval_s:
            return round(self.eval_count / self.eval_s, 1)
        return None


_KNOWN_TOOLS = {t.strip() for t in _TOOL_CATALOG.replace(",", " ").split()}


def plan_is_valid(text: str) -> bool:
    """The planner workload asks for `{"steps":[{"tool","args"}...]}` and nothing
    else. Valid == parseable JSON, >= 3 steps, every `tool` in the catalog. This
    is the structured-output-reliability signal (step 5b D2); the full graph
    drive is the results doc's job."""
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("{"):]
    try:
        obj = json.loads(s[s.find("{"): s.rfind("}") + 1])
    except (json.JSONDecodeError, ValueError):
        return False
    steps = obj.get("steps") or obj.get("plan") or []
    if not isinstance(steps, list) or len(steps) < 3:
        return False
    return all(isinstance(st, dict) and st.get("tool") in _KNOWN_TOOLS for st in steps)


def _is_ollama(base_url: str) -> bool:
    root = base_url.rsplit("/v1", 1)[0]
    try:
        return httpx.get(root + "/api/version", timeout=2.0).status_code == 200
    except Exception:
        return False


def _ollama_root(base_url: str) -> str:
    return base_url.rsplit("/v1", 1)[0]


def stream_turn(
    client: httpx.Client, base_url: str, model: str, messages: list[dict[str, Any]],
    *, think: Any, images: list[str] | None, keep_alive: Any = -1,
) -> TurnResult:
    """One streamed turn via Ollama's native `/api/chat` (gives `thinking`
    deltas and real timing stats). Falls back to `/v1/chat/completions` when the
    server is not Ollama — there reasoning tokens are best-effort."""

    if _is_ollama(base_url):
        return _stream_ollama(client, _ollama_root(base_url), model, messages,
                              think=think, images=images, keep_alive=keep_alive)
    return _stream_v1(client, base_url, model, messages, images=images)


def _stream_ollama(client, root, model, messages, *, think, images, keep_alive) -> TurnResult:
    msgs = [dict(m) for m in messages]
    if images:
        for m in reversed(msgs):
            if m.get("role") == "user":
                m["images"] = [i.split(",", 1)[1] if i.startswith("data:") else i
                               for i in images]
                break
    payload: dict[str, Any] = {
        "model": model, "messages": msgs, "stream": True,
        "keep_alive": keep_alive, "options": {"temperature": 0.0},
    }
    if think is not None:
        payload["think"] = think

    t0 = time.monotonic()
    ttft: float | None = None
    content_chars = think_chars = 0
    parts: list[str] = []
    eval_count = eval_s = load_s = prompt_tokens = None
    try:
        with client.stream("POST", root + "/api/chat", json=payload) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                obj = json.loads(line)
                msg = obj.get("message") or {}
                c = msg.get("content") or ""
                th = msg.get("thinking") or ""
                if (c or th) and ttft is None:
                    ttft = time.monotonic() - t0
                content_chars += len(c)
                think_chars += len(th)
                if c:
                    parts.append(c)
                if obj.get("done"):
                    eval_count = obj.get("eval_count")
                    eval_s = (obj.get("eval_duration") or 0) / 1e9 or None
                    load_s = (obj.get("load_duration") or 0) / 1e9 or None
                    prompt_tokens = obj.get("prompt_eval_count")
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        return TurnResult(None, time.monotonic() - t0, content_chars, think_chars,
                          None, None, None, None, ok=False, detail=repr(e))
    return TurnResult(ttft, time.monotonic() - t0, content_chars, think_chars,
                      eval_count, eval_s, load_s, prompt_tokens, ok=True,
                      content_text="".join(parts))


def _stream_v1(client, base_url, model, messages, *, images) -> TurnResult:
    msgs = [dict(m) for m in messages]
    if images:
        for m in reversed(msgs):
            if m.get("role") == "user":
                parts = [{"type": "text", "text": m.get("content", "")}]
                parts += [{"type": "image_url", "image_url": {"url": i}} for i in images]
                m["content"] = parts
                break
    payload = {"model": model, "messages": msgs, "stream": True,
               "temperature": 0.0, "stream_options": {"include_usage": True}}
    t0 = time.monotonic()
    ttft = None
    content_chars = think_chars = 0
    parts: list[str] = []
    eval_count = prompt_tokens = None
    try:
        with client.stream("POST", base_url + "/chat/completions", json=payload) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                obj = json.loads(data)
                if obj.get("usage"):
                    eval_count = obj["usage"].get("completion_tokens")
                    prompt_tokens = obj["usage"].get("prompt_tokens")
                ch = (obj.get("choices") or [{}])[0]
                delta = ch.get("delta") or {}
                c = delta.get("content") or ""
                th = delta.get("reasoning_content") or delta.get("reasoning") or ""
                if (c or th) and ttft is None:
                    ttft = time.monotonic() - t0
                content_chars += len(c)
                think_chars += len(th)
                if c:
                    parts.append(c)
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        return TurnResult(None, time.monotonic() - t0, content_chars, think_chars,
                          None, None, None, None, ok=False, detail=repr(e))
    return TurnResult(ttft, time.monotonic() - t0, content_chars, think_chars,
                      eval_count, None, None, prompt_tokens, ok=True,
                      content_text="".join(parts))


# --------------------------------------------------------------------------- #
# per-candidate campaign                                                       #
# --------------------------------------------------------------------------- #


def _unload(client: httpx.Client, base_url: str, model: str) -> None:
    if not _is_ollama(base_url):
        return
    try:
        client.post(_ollama_root(base_url) + "/api/chat",
                    json={"model": model, "messages": [], "keep_alive": 0}, timeout=30)
        time.sleep(0.5)
    except Exception:
        pass


def _resident_mb(client: httpx.Client, base_url: str, model: str) -> float | None:
    if not _is_ollama(base_url):
        return None
    try:
        r = client.get(_ollama_root(base_url) + "/api/ps", timeout=5)
        for m in r.json().get("models", []):
            if m.get("name") == model or m.get("model") == model:
                return round(m.get("size", 0) / (1024 * 1024), 1)
    except Exception:
        pass
    return None


def bench_candidate(
    cand: Candidate, *, base_url: str, trials: int, warmup: int,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "kind": "result", "slot": cand.slot, "model": cand.model,
        "think": cand.think, "incumbent": cand.incumbent, "note": cand.note,
        "platform": base.platform_tag(), "verified": VERIFIED,
        "status": "ok", "reason": None, "trials": 0,
        "coldLoadS": None, "coldTtftS": None,
        "ttftP50Ms": None, "ttftP95Ms": None,
        "tokPerSP50": None, "thinkTokensP50": None, "thinkTokensP95": None,
        "contentTokensP50": None, "promptTokens": None, "planValidRate": None,
        "fullTurnP50Ms": None, "fullTurnP95Ms": None, "residentMb": None,
        "method": (
            "native /api/chat stream; TTFT = req->first content|thinking token; "
            "tok/s = eval_count/eval_duration; think-tokens = eval_count * "
            "think_chars/(think+content chars); n>=20 warm, cold turn separate; "
            "p50/p95 nearest-rank"
        ),
    }
    images = [_vlm_image_data_uri()] if cand.slot == "vlm" else None
    msgs = _messages(cand.slot)

    with httpx.Client(timeout=float(os.environ.get("WELLSY_LLM_TIMEOUT", "180"))) as client:
        if not _is_ollama(base_url):
            try:
                if httpx.get(base_url + "/models", timeout=3).status_code != 200:
                    row["status"] = "unavailable"
                    row["reason"] = f"no server at {base_url}"
                    return row
            except Exception as e:
                row["status"] = "unavailable"
                row["reason"] = f"no server at {base_url}: {e}"
                return row
            row["method"] = row["method"].replace("native /api/chat", "/v1 chat")

        # ---- cold ----
        _unload(client, base_url, cand.model)
        cold = stream_turn(client, base_url, cand.model, msgs,
                           think=cand.think, images=images)
        if not cold.ok:
            row["status"] = "error"
            row["reason"] = f"cold turn failed: {cold.detail}"
            return row
        row["coldLoadS"] = round(cold.load_s, 3) if cold.load_s else None
        row["coldTtftS"] = round(cold.ttft_s, 3) if cold.ttft_s else None

        for _ in range(max(0, warmup)):
            stream_turn(client, base_url, cand.model, msgs, think=cand.think, images=images)

        ttft_ms: list[float] = []
        turn_ms: list[float] = []
        toks: list[float] = []
        think_toks: list[float] = []
        content_toks: list[float] = []
        prompt_toks: list[int] = []
        plan_valid = 0
        fails = 0
        for _ in range(trials):
            t = stream_turn(client, base_url, cand.model, msgs,
                            think=cand.think, images=images)
            if not t.ok:
                fails += 1
                continue
            if cand.slot == "planner" and plan_is_valid(t.content_text):
                plan_valid += 1
            if t.ttft_s is not None:
                ttft_ms.append(t.ttft_s * 1000)
            turn_ms.append(t.wall_s * 1000)
            if t.tok_per_s is not None:
                toks.append(t.tok_per_s)
            if t.think_tokens_est is not None:
                think_toks.append(t.think_tokens_est)
                if t.eval_count is not None:
                    content_toks.append(t.eval_count - t.think_tokens_est)
            if t.prompt_tokens is not None:
                prompt_toks.append(t.prompt_tokens)

        row["residentMb"] = _resident_mb(client, base_url, cand.model)

    got = len(turn_ms)
    row["trials"] = got
    if got == 0:
        row["status"] = "error"
        row["reason"] = f"all {trials} warm trials failed"
        return row
    if fails:
        row["reason"] = f"{fails}/{trials} warm trials failed"
    if ttft_ms:
        row["ttftP50Ms"] = round(pct(ttft_ms, 50), 1)
        row["ttftP95Ms"] = round(pct(ttft_ms, 95), 1)
    row["fullTurnP50Ms"] = round(pct(turn_ms, 50), 1)
    row["fullTurnP95Ms"] = round(pct(turn_ms, 95), 1)
    if toks:
        row["tokPerSP50"] = round(pct(toks, 50), 1)
    if think_toks:
        row["thinkTokensP50"] = round(pct(think_toks, 50), 1)
        row["thinkTokensP95"] = round(pct(think_toks, 95), 1)
    if content_toks:
        row["contentTokensP50"] = round(pct(content_toks, 50), 1)
    if prompt_toks:
        row["promptTokens"] = int(statistics.median(prompt_toks))
    if cand.slot == "planner" and got:
        row["planValidRate"] = round(plan_valid / got, 2)
    return row


# --------------------------------------------------------------------------- #
# table + entry point                                                          #
# --------------------------------------------------------------------------- #

_COLS = [
    ("slot", 8), ("model", 34), ("think", 7), ("status", 9),
    ("coldLoadS", 9), ("ttftP50Ms", 10), ("ttftP95Ms", 10),
    ("tokPerSP50", 10), ("thinkTokP50", 11), ("planOK", 7),
    ("residentMb", 10), ("trials", 6),
]


def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def print_table(rows: list[dict[str, Any]]) -> None:
    hdr = "  ".join(n.ljust(w) for n, w in _COLS)
    print(hdr)
    print("-" * len(hdr))
    key = {"thinkTokP50": "thinkTokensP50", "planOK": "planValidRate"}
    for r in rows:
        cells = [(key.get(n, n)) for n, _ in _COLS]
        print("  ".join(_fmt(r.get(k)).ljust(w)[:w] for (k, (_, w)) in zip(cells, _COLS)))
        if r.get("reason"):
            print(f"    reason: {r['reason']}")


def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="wellsy bench --modality llm")
    ap.add_argument("--slot", choices=["planner", "fast", "vlm", "all"], default="all")
    ap.add_argument("--candidate", default=None, help="only this model id")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    cands = [c for c in CANDIDATES
             if (args.slot in ("all", c.slot))
             and (args.candidate is None or c.model == args.candidate)]
    if not cands:
        print("[llm-bench] no candidates match the filter")
        return 1

    print(f"[llm-bench] base_url={args.base_url}  slot={args.slot}  "
          f"trials={args.trials}  candidates={len(cands)}")
    print(f"[llm-bench] platform={base.platform_tag()}\n")

    rows = [bench_candidate(c, base_url=args.base_url, trials=args.trials,
                            warmup=args.warmup) for c in cands]
    print_table(rows)

    commit = _commit()
    out = Path(args.out) if args.out else (
        RESULTS_DIR / f"llm-bench-{date.today().isoformat()}-"
        f"{base.platform_tag().replace('/', '-')}-{commit}.jsonl"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {"kind": "run", "date": date.today().isoformat(),
            "platform": base.platform_tag(), "commit": commit,
            "baseUrl": args.base_url, "slot": args.slot, "trials": args.trials}
    with out.open("w", encoding="utf-8") as f:
        f.write(json.dumps(meta) + "\n")
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"\n[llm-bench] wrote {out}")

    return 1 if any(r["status"] == "error" for r in rows) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
