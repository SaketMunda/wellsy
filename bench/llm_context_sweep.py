"""Planner context sweep — step 5c Deliverables 5 and 6.

5b measured everything at ctx 4096 and flagged it: "re-measure at the context
the agent actually runs". Step 7 cannot choose between aggressive retrieval and
large provenance-tagged context blocks until this exists.

For each (model, num_ctx):
  * resident: `ollama ps` size AND the runner process RSS (`ollama ps`
    under-reports some architectures — measured on gemma4 in 5c), loaded
    with nothing but a one-token prompt;
  * a filled planner turn: the 5b planner prompt preceded by a realistic prior
    transcript filling ~`fill` of the window, with one fact (Alex's address)
    planted near the start. Records cold prefill (server
    `prompt_eval_duration`), first-content-token time, a warm follow-up turn
    that reuses the cached prefix, plan-JSON validity, and whether the planted
    address made it into the plan's mail args (recall at depth).

    uv run python bench/llm_context_sweep.py --model qwen3.5:4b-q4_K_M --think false \\
        --ctx 4096 --ctx 16384 --ctx 32768 --ctx 65536 --ctx 131072
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import date
from pathlib import Path

import httpx

from engine.inference import llm_bench

ROOT = "http://localhost:11434"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "spec" / "results"
NEEDLE = "alex.rivera@northwind-labs.example"


def filler(n_tokens: int) -> str:
    """A prior-session transcript: tool calls and results like the agent's own
    history. This JSON-heavy text measured ~2.2 chars/token on Qwen3/3.5
    (5c: 8090 chars -> ~3530 tokens); 2.1 is the sizing heuristic. The
    server's real prompt_eval_count is what gets recorded, and a short prompt
    is flagged — Ollama silently drops overflowing messages, no error."""
    head = (f"[memory] Contact card: Alex Rivera, email {NEEDLE}, prefers short "
            "emails, works at Northwind Labs.\n")
    lines = [head]
    i = 0
    while sum(len(x) for x in lines) < n_tokens * 2.1:
        lines.append(
            f"[turn {i}] tool=calendar_list_events args={{\"day\": \"2026-08-{(i % 28) + 1:02d}\"}} "
            f"-> [{{\"title\": \"Standup {i}\", \"start\": \"09:{i % 60:02d}\", \"room\": \"B{i % 7}\"}}, "
            f"{{\"title\": \"Review {i}\", \"start\": \"15:00\", \"attendees\": [\"sam\", \"lee\"]}}]\n"
        )
        i += 1
    return "".join(lines)


def runner_rss_mb() -> float | None:
    try:
        pid = subprocess.run(["pgrep", "-f", "llama-server|ollama runner"], capture_output=True,
                             text=True).stdout.split()
        if not pid:
            return None
        rss = subprocess.run(["ps", "-o", "rss=", "-p", pid[-1]], capture_output=True,
                             text=True).stdout.strip()
        return round(int(rss) / 1024, 1)
    except Exception:
        return None


def ps(client: httpx.Client, model: str) -> dict:
    for m in client.get(ROOT + "/api/ps").json().get("models", []):
        if m.get("name") == model:
            return {"psMb": round(m["size"] / 2**20, 1), "runner": m.get("runner"),
                    "contextLength": m.get("context_length")}
    return {}


def chat(client, model, messages, *, think, num_ctx, num_predict=400) -> dict:
    payload = {"model": model, "messages": messages, "stream": True, "keep_alive": -1,
               "options": {"temperature": 0.0, "num_ctx": num_ctx, "num_predict": num_predict}}
    if think is not None:
        payload["think"] = think
    t0 = time.monotonic()
    first = None
    parts, done = [], {}
    with client.stream("POST", ROOT + "/api/chat", json=payload) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            obj = json.loads(line)
            c = (obj.get("message") or {}).get("content") or ""
            if c and first is None:
                first = time.monotonic() - t0
            parts.append(c)
            if obj.get("done"):
                done = obj
    return {"firstContentS": first, "wallS": time.monotonic() - t0, "text": "".join(parts),
            "promptTokens": done.get("prompt_eval_count"),
            "prefillS": (done.get("prompt_eval_duration") or 0) / 1e9 or None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--think", default="none", help="none|false")
    ap.add_argument("--ctx", type=int, action="append", required=True)
    ap.add_argument("--fill", type=float, default=0.75, help="fraction of ctx to fill")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    think = None if args.think == "none" else False

    rows = []
    with httpx.Client(timeout=1800) as client:
        for ctx in args.ctx:
            client.post(ROOT + "/api/chat", json={"model": args.model, "messages": [], "keep_alive": 0})
            time.sleep(1.5)
            chat(client, args.model, [{"role": "user", "content": "hi"}], think=think,
                 num_ctx=ctx, num_predict=1)
            row = {"kind": "result", "model": args.model, "think": think, "numCtx": ctx,
                   **ps(client, args.model), "runnerRssMb": runner_rss_mb()}

            hist = filler(int(ctx * args.fill) - 400)
            msgs = [{"role": "system", "content": llm_bench._PLAN_SYSTEM},
                    {"role": "user", "content": "Earlier context:\n" + hist},
                    {"role": "assistant", "content": "Noted."},
                    {"role": "user", "content": llm_bench._PLAN_USER}]
            cold = chat(client, args.model, msgs, think=think, num_ctx=ctx)
            warm_msgs = msgs[:-1] + [{"role": "user", "content": llm_bench._PLAN_USER + " Thanks."}]
            warm = chat(client, args.model, warm_msgs, think=think, num_ctx=ctx)
            row.update({
                "promptTokens": cold["promptTokens"],
                "coldPrefillS": round(cold["prefillS"] or 0, 2),
                "coldFirstContentS": round(cold["firstContentS"] or 0, 2),
                "coldTurnS": round(cold["wallS"], 2),
                "warmPrefixReuseFirstContentS": round(warm["firstContentS"] or 0, 2),
                "warmPrefillTokens": warm["promptTokens"],
                "targetPromptTokens": int(ctx * args.fill),
                "truncated": (cold["promptTokens"] or 0) < 0.8 * int(ctx * args.fill),
                "planValid": llm_bench.plan_is_valid(cold["text"]),
                "needleRecalled": NEEDLE in cold["text"],
                "rssAfterFillMb": runner_rss_mb(),
                **{f"after_{k}": v for k, v in ps(client, args.model).items() if k == "psMb"},
            })
            rows.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != "kind"}), flush=True)

    out = Path(args.out) if args.out else RESULTS_DIR / (
        f"llm-context-sweep-{date.today()}-{args.model.replace(':', '_')}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "run", "fill": args.fill, "needle": NEEDLE,
                            "method": ("unload, load at num_ctx with a 1-token turn -> "
                                       "ollama ps + runner RSS; then a planner turn after a "
                                       "transcript filling `fill` of ctx with the needle at "
                                       "the top; cold prefill = server prompt_eval_duration; "
                                       "warm = same prefix, new last turn (prefix cache)")}) + "\n")
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
