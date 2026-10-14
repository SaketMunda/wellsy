"""Append-only prefix reuse — step 5c Deliverable 6, the follow-up to
`llm_context_sweep.py`.

The sweep's warm turn *edits* the final user message, which forces a rollback;
a hybrid recurrent model (Qwen3.5: 24 Gated DeltaNet + 8 attention layers)
cannot roll its recurrent state back and re-processes. A real conversation is
append-only: old prompt + the model's own reply + a new user turn. This
measures that pattern: turn 1 (cold, fills the history), then three appended
turns, first-content time and server prompt_eval_duration (the real
re-evaluation cost; prompt_eval_count reports the whole prompt) for each.

    uv run python bench/llm_append_reuse.py --model qwen3.5:4b-q4_K_M --think false --ctx 32768
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm_context_sweep as sweep  # noqa: E402

from engine.inference import llm_bench  # noqa: E402

FOLLOW_UPS = ["Also add a note titled 'Alex follow-up'.",
              "Actually make the reminder Friday 5pm instead.",
              "Read me back the full plan."]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--think", default="none")
    ap.add_argument("--ctx", type=int, action="append", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    think = None if args.think == "none" else False
    rows = []
    with httpx.Client(timeout=1800) as c:
        for ctx in args.ctx:
            c.post(sweep.ROOT + "/api/chat", json={"model": args.model, "messages": [], "keep_alive": 0})
            msgs = [{"role": "system", "content": llm_bench._PLAN_SYSTEM},
                    {"role": "user", "content": "Earlier context:\n" + sweep.filler(int(ctx * 0.6))},
                    {"role": "assistant", "content": "Noted."},
                    {"role": "user", "content": llm_bench._PLAN_USER}]
            turns = []
            r = sweep.chat(c, args.model, msgs, think=think, num_ctx=ctx, num_predict=300)
            turns.append({"turn": 0, "firstContentS": round(r["firstContentS"] or 0, 2),
                          "promptTokens": r["promptTokens"], "prefillS": round(r["prefillS"] or 0, 2)})
            for i, q in enumerate(FOLLOW_UPS, 1):
                msgs = msgs + [{"role": "assistant", "content": r["text"]}, {"role": "user", "content": q}]
                r = sweep.chat(c, args.model, msgs, think=think, num_ctx=ctx, num_predict=300)
                turns.append({"turn": i, "firstContentS": round(r["firstContentS"] or 0, 2),
                              "promptTokens": r["promptTokens"], "prefillS": round(r["prefillS"] or 0, 2)})
            row = {"model": args.model, "numCtx": ctx, "turns": turns}
            rows.append(row)
            print(json.dumps(row), flush=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "run", "method": "turn 0 cold with a history of 0.6*ctx; "
                            "turns 1-3 append the model's reply + a new user turn (no edits); "
                            "promptTokens = server prompt_eval_count (whole prompt; on Ollama "
                            "0.40.3 it includes cached tokens); prefillS = server "
                            "prompt_eval_duration — the actual re-evaluation cost"}) + "\n")
        for r in rows:
            f.write(json.dumps({"kind": "result", **r}) + "\n")


if __name__ == "__main__":
    main()
