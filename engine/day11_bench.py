"""Day 11 measurement harness (day11-prompt.md Part 4, row 1/2) — NOT part
of the shipped engine, same category as `verify_preemption.py`. Captures a
real camera frame once and fires it at Ollama's `qwen3-vl:8b` repeatedly
with `stream=True` to get a genuine first-token latency, not just total
response time — `llm.py`'s shipped `Llm.respond()` stays non-streaming
(unchanged shape from D40) since the query loop only needs the final text,
but the measurement itself needs streaming to answer day11-prompt.md's
actual question ("is first-token latency comfortably inside ~1.5s").

    uv run python day11_bench.py --n 12
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request

import cv2

from llm import MODEL_NAME, OLLAMA_URL, SYSTEM_PROMPT, TEMPERATURE, _encode_jpeg_b64


def timed_query(image_b64: str, question: str, model: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question, "images": [image_b64]},
    ]
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "options": {"temperature": TEMPERATURE},
        "stream": True,
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})

    t0 = time.monotonic()
    first_token_at = None
    chunks: list[str] = []
    with urllib.request.urlopen(req, timeout=60) as resp:
        for line in resp:
            if not line.strip():
                continue
            obj = json.loads(line)
            content = obj.get("message", {}).get("content", "")
            if content and first_token_at is None:
                first_token_at = time.monotonic()
            if content:
                chunks.append(content)
            if obj.get("done"):
                break
    t1 = time.monotonic()
    return {
        "firstTokenMs": round((first_token_at - t0) * 1000, 1) if first_token_at else None,
        "totalMs": round((t1 - t0) * 1000, 1),
        "answer": "".join(chunks).strip(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=12)
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--question", default="what do you see in this image?")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.camera_index, cv2.CAP_AVFOUNDATION)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit("camera did not open")
    image_b64 = _encode_jpeg_b64(frame)

    print(f"[bench] warming up ({args.model})...")
    t0 = time.monotonic()
    warm = timed_query(image_b64, args.question, args.model)
    cold_ms = round((time.monotonic() - t0) * 1000, 1)
    print(f"[bench] cold call: {cold_ms}ms total (includes Ollama's model load into memory), answer={warm['answer']!r}")

    results = []
    for i in range(args.n):
        r = timed_query(image_b64, args.question, args.model)
        print(f"[bench] {i+1}/{args.n}: firstToken={r['firstTokenMs']}ms total={r['totalMs']}ms")
        results.append(r)

    first_tokens = [r["firstTokenMs"] for r in results if r["firstTokenMs"] is not None]
    totals = [r["totalMs"] for r in results]

    def pct(vals, p):
        vals = sorted(vals)
        idx = min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1))))
        return vals[idx]

    print(f"\n[bench] n={len(results)}")
    print(f"[bench] first-token p50={pct(first_tokens, 50)}ms p95={pct(first_tokens, 95)}ms")
    print(f"[bench] total       p50={pct(totals, 50)}ms p95={pct(totals, 95)}ms")


if __name__ == "__main__":
    main()
