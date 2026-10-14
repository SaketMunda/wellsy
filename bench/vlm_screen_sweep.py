"""VLM resolution sweep on a real dense screenshot — step 5b's owed D3, closed
in step 5c Deliverable 3.

The image goes through the real encoder the voice loop uses
(`engine.voice.vision._to_jpeg`, `MAX_EDGE_PX` set per row), so the model sees
the exact JPEG bytes `IntentGate` would append. The transport is Ollama's native
`/api/chat` rather than the pipeline's `/v1` client, because only the native
endpoint returns `prompt_eval_count` / `prompt_eval_duration` — the vision-token
count and the image-prefill time this sweep exists to measure.

5b's VLM row was prompt-cache-inflated (identical image every turn). Here every
warm trial perturbs one pixel before encoding, so each turn is a new image to
the server: the honest cost of "a new screen question with the model resident".

Per (model, edge): cold load s + cold first-content s (model unloaded first),
then n warm trials: first-content-token p50/p95, image-prefill p50/p95
(server `prompt_eval_duration`), prompt tokens. Then three transcriptions at
the model's default sampling (as production sends), each scored against owner-checkable ground-truth strings read off the
screenshot (case-insensitive, whitespace-normalised substring match).

    uv run python bench/vlm_screen_sweep.py runs/step5c/screens/display_1.png \\
        --model qwen3-vl:2b-instruct-q4_K_M --model qwen3.5:4b-q4_K_M
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import time
from datetime import date
from pathlib import Path

import cv2
import httpx

from engine.voice import vision

ROOT = "http://localhost:11434"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "spec" / "results"
QUESTION = "What's on my screen right now? Answer in one short sentence."
TRANSCRIBE = ("Transcribe every piece of visible text on this screen verbatim, top to "
              "bottom, left to right. Plain text only.")

# Read off runs/step5c/screens/display_1.png by eye (step 5c). Ordered roughly
# large -> small; the last ones are status-bar / file-tree size UI text.
GROUND_TRUTH = [
    "Chatbot with Memory",
    "LangGraph Memory Store",
    "cognitive function that allows people to store, retrieve, and use information",
    "semantic memory",
    "in the hot path",
    "langchain_openai langgraph langchain_core",
    "memory_store.ipynb",
    "memory_agent.ipynb",
    "memoryschema_collection.ipynb",
    "memoryschema_profile.ipynb",
    "requirements.txt",
    "lca-lc-foundations",
    "Clear All Outputs",
    "Select Kernel",
    "Python 3.13.0",
    "Debug Console",
    "History restored",
    "Cell 1 of 1",
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("`", "")).strip().lower()


def legibility(text: str) -> tuple[int, list[str]]:
    t = _norm(text)
    missed = [g for g in GROUND_TRUTH if _norm(g) not in t]
    return len(GROUND_TRUTH) - len(missed), missed


def pct(vals: list[float], p: float) -> float:
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1))))]


def encode(frame, edge: int, tick: int) -> tuple[str, tuple[int, int]]:
    """Through the real encoder. The perturbation is a 16x16 corner block
    applied *after* the downscale: a single source pixel is averaged away by
    INTER_AREA and quantised away by JPEG q85, which left most "new" images
    byte-identical and server-cached in the first 5c attempt."""
    vision.MAX_EDGE_PX = edge
    f = vision._downscale(frame).copy()
    f[:16, :16] = ((tick * 37) % 256, (tick * 91) % 256, (tick * 13) % 256)
    jpeg = vision._to_jpeg(f)          # already at edge: _downscale is a no-op here
    return base64.b64encode(jpeg).decode(), f.shape[1::-1]


def turn(client: httpx.Client, model: str, prompt: str, img: str, *, think, num_ctx: int,
         num_predict: int) -> dict:
    # No temperature: production (`adapters.build_llm`) sends none, so the
    # model's own defaults apply. Greedy decoding loops on dense UI ("Update\n"
    # x1500 in the first 5c attempt) and is not what the user gets.
    payload = {"model": model, "stream": True, "keep_alive": -1,
               "messages": [{"role": "user", "content": prompt, "images": [img]}],
               "options": {"num_ctx": num_ctx, "num_predict": num_predict}}
    if think is not None:
        payload["think"] = think
    t0 = time.monotonic()
    first = None
    parts: list[str] = []
    think_chars = 0
    done: dict = {}
    with client.stream("POST", ROOT + "/api/chat", json=payload) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            obj = json.loads(line)
            msg = obj.get("message") or {}
            c = msg.get("content") or ""
            think_chars += len(msg.get("thinking") or "")
            if c and first is None:
                first = time.monotonic() - t0
            parts.append(c)
            if obj.get("done"):
                done = obj
    return {"firstContentS": first, "wallS": time.monotonic() - t0, "text": "".join(parts),
            "thinkChars": think_chars,
            "promptTokens": done.get("prompt_eval_count"),
            "prefillS": (done.get("prompt_eval_duration") or 0) / 1e9 or None,
            "loadS": (done.get("load_duration") or 0) / 1e9 or None,
            "evalCount": done.get("eval_count")}


def unload(client: httpx.Client, model: str) -> None:
    client.post(ROOT + "/api/chat", json={"model": model, "messages": [], "keep_alive": 0})
    time.sleep(1.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("screenshot")
    ap.add_argument("--model", action="append", required=True)
    ap.add_argument("--edge", type=int, action="append", default=None,
                    help="longest edge px (default: native 1920, 1024, 768, 512)")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    frame = cv2.imread(args.screenshot)
    if frame is None:
        raise SystemExit(f"cannot read {args.screenshot}")
    edges = args.edge or [max(frame.shape[:2]), 1024, 768, 512]
    rows = []
    tick = 0
    with httpx.Client(timeout=600) as client:
        for model in args.model:
            # Qwen3.5 thinks by default (its card); the voice path must send
            # think=false. Models without a think path get no flag.
            show = client.post(ROOT + "/api/show", json={"model": model}).json()
            think = False if "thinking" in (show.get("capabilities") or []) else None
            for edge in edges:
                unload(client, model)
                img, size = encode(frame, edge, tick); tick += 1
                cold = turn(client, model, QUESTION, img, think=think,
                            num_ctx=args.num_ctx, num_predict=48)
                first, prefill, wall, ptoks = [], [], [], []
                think_chars = 0
                for _ in range(args.trials):
                    img, _ = encode(frame, edge, tick); tick += 1
                    t = turn(client, model, QUESTION, img, think=think,
                             num_ctx=args.num_ctx, num_predict=48)
                    if t["firstContentS"] is not None:
                        first.append(t["firstContentS"] * 1000)
                    if t["prefillS"]:
                        prefill.append(t["prefillS"] * 1000)
                    wall.append(t["wallS"] * 1000)
                    ptoks.append(t["promptTokens"] or 0)
                    think_chars += t["thinkChars"]
                scores, trs = [], []
                for _ in range(3):   # sampled decoding: three reads, all reported
                    img, _ = encode(frame, edge, tick); tick += 1
                    tr = turn(client, model, TRANSCRIBE, img, think=think,
                              num_ctx=args.num_ctx, num_predict=1500)
                    trs.append(tr)
                    scores.append(legibility(tr["text"]))
                hit, missed = max(scores, key=lambda x: x[0])
                row = {
                    "kind": "result", "model": model, "think": think, "edge": edge,
                    "sentSize": list(size), "trials": len(first),
                    "coldLoadS": round(cold["loadS"] or 0, 2),
                    "coldFirstContentS": round(cold["firstContentS"] or 0, 2),
                    "firstContentP50Ms": round(pct(first, 50), 1) if first else None,
                    "firstContentP95Ms": round(pct(first, 95), 1) if first else None,
                    "imagePrefillP50Ms": round(pct(prefill, 50), 1) if prefill else None,
                    "imagePrefillP95Ms": round(pct(prefill, 95), 1) if prefill else None,
                    "promptTokens": sorted(ptoks)[len(ptoks) // 2] if ptoks else None,
                    "thinkCharsWarm": think_chars,
                    "legibility": f"{hit}/{len(GROUND_TRUTH)}",
                    "legibilityRuns": [h for h, _ in scores], "missedBest": missed,
                    "transcriptionThinkChars": sum(t["thinkChars"] for t in trs),
                    "transcriptions": [t["text"] for t in trs],
                    "sampleAnswer": cold["text"],
                }
                rows.append(row)
                print(f"{model:30s} {edge:5d}px sent {size[0]}x{size[1]}  tok {row['promptTokens']}  "
                      f"cold load {row['coldLoadS']} s / first {row['coldFirstContentS']} s  "
                      f"warm first {row['firstContentP50Ms']}/{row['firstContentP95Ms']} ms  "
                      f"prefill {row['imagePrefillP50Ms']}/{row['imagePrefillP95Ms']} ms  "
                      f"legible {row['legibilityRuns']}/{len(GROUND_TRUTH)}", flush=True)

    out = Path(args.out) if args.out else RESULTS_DIR / f"vlm-screen-sweep-{date.today()}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write(json.dumps({
            "kind": "run", "screenshot": Path(args.screenshot).name,
            "native": list(frame.shape[1::-1]), "numCtx": args.num_ctx, "question": QUESTION,
            "method": ("vision._to_jpeg (q85, MAX_EDGE_PX=edge) -> Ollama /api/chat images; "
                       "model unloaded before the cold turn; warm trials perturb a 16px block "
                       "after downscale so every turn is a new image; model-default sampling "
                       "(as production); firstContent = request -> first content "
                       "token; imagePrefill = server prompt_eval_duration; p50/p95 "
                       "nearest-rank; legibility = ground-truth substrings, 3 sampled "
                       "transcriptions each reported"),
            "groundTruth": GROUND_TRUTH}) + "\n")
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
