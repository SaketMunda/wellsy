"""Three-arm comparison on D30's named misses — step 5c Deliverable 4 (amended
2026-10-14).

Arms, all on the same 28 frames of the recorded clip (one every 2 s of clip
time, frame i where i % 60 == 30):

  1. `yoloe-11s-seg.pt` — closed-vocabulary label "glasses" / "cell phone"
  2. `yoloe-26s-seg.pt` — same
  3. `yoloe-26s` localizes `person` only -> crop -> a closed yes/no question to
     a **local** VLM; P(yes) from the first-token logprobs (Ollama 0.40.3
     `logprobs`/`top_logprobs`). No pixel leaves the machine (INVARIANTS #2).

Ground truth was labelled **by eye** from contact sheets of exactly these
frames, independent of every arm. Positive = the object is visibly worn / held.
Frames with nobody in view are negatives for both questions.

    uv run python bench/detector_crop_decide.py runs/step5c/clip.mp4
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import time
from pathlib import Path

import cv2
import httpx

from engine.perception import detector
from engine.voice import vision

ROOT = "http://localhost:11434"
RESULTS = Path(__file__).resolve().parent.parent / "spec" / "results" / "detector-crop-decide-5c.jsonl"

# clip seconds (frame // 30) -> truth, labelled by eye in step 5c
GLASSES = {t: (11 <= t <= 49) for t in range(1, 57, 2)}
PHONE = {t: (29 <= t <= 47) for t in range(1, 57, 2)}
QUESTIONS = {
    "glasses": "Is this person wearing eyeglasses? Answer yes or no.",
    "phone": "Is this person holding a mobile phone in their hand? Answer yes or no.",
}
VLMS = [("qwen3.5:4b-q4_K_M", False), ("qwen3-vl:2b-instruct-q4_K_M", None)]


def p_yes(logprobs: list | None) -> float | None:
    """P(yes) renormalised over yes/no variants of the first token."""
    if not logprobs:
        return None
    yes = no = 0.0
    for alt in logprobs[0].get("top_logprobs", []):
        tok = alt["token"].strip().lower()
        if tok == "yes":
            yes += math.exp(alt["logprob"])
        elif tok == "no":
            no += math.exp(alt["logprob"])
    return yes / (yes + no) if yes + no else None


def ask(client: httpx.Client, model: str, think, jpeg: bytes, q: str) -> tuple[float | None, float]:
    payload = {"model": model, "stream": False, "keep_alive": -1, "logprobs": True,
               "top_logprobs": 10, "options": {"num_predict": 1, "temperature": 0.0},
               "messages": [{"role": "user", "content": q,
                             "images": [base64.b64encode(jpeg).decode()]}]}
    if think is not None:
        payload["think"] = think
    t0 = time.monotonic()
    r = client.post(ROOT + "/api/chat", json=payload).json()
    return p_yes(r.get("logprobs")), (time.monotonic() - t0) * 1000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    args = ap.parse_args()

    cap = cv2.VideoCapture(str(Path(args.clip).resolve()))
    frames: dict[int, object] = {}
    i = 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % 60 == 30:
            frames[i // 30] = f
        i += 1
    frames = {t: f for t, f in frames.items() if t in GLASSES}

    prompts = detector.load_prompts()
    rows: list[dict] = []
    person_boxes: dict[int, list] = {}
    for name in ["yoloe-11s-seg.pt", "yoloe-26s-seg.pt"]:
        m = detector.load_model(name=name)
        detector.set_prompts(m, prompts)
        detector.predict(m, next(iter(frames.values())))  # warm
        for t, f in frames.items():
            dets = detector.predict(m, f)
            labels = {d["label"] for d in dets}
            rows.append({"arm": name, "t": t, "glasses": "glasses" in labels,
                         "phone": "cell phone" in labels})
            if name.startswith("yoloe-26"):
                people = [d for d in dets if d["label"] in ("person", "a human person")]
                person_boxes[t] = max(people, key=lambda d: d["score"])["bbox"] if people else None

    with httpx.Client(timeout=300) as client:
        for model, think in VLMS:
            for t, f in frames.items():
                box = person_boxes[t]
                row = {"arm": f"yoloe-26s person crop -> {model}", "t": t}
                if box is None:     # nothing to ask about: a "no" for both questions
                    row.update({"glasses": False, "phone": False, "pGlasses": None,
                                "pPhone": None, "ms": []})
                    rows.append(row)
                    continue
                x, y, w, h = box
                H, W = f.shape[:2]
                px, py = 0.15 * w, 0.15 * h
                crop = f[max(0, int(y - py)):min(H, int(y + h + py)),
                         max(0, int(x - px)):min(W, int(x + w + px))]
                jpeg = vision._to_jpeg(crop)
                pg, mg = ask(client, model, think, jpeg, QUESTIONS["glasses"])
                pp, mp = ask(client, model, think, jpeg, QUESTIONS["phone"])
                row.update({"pGlasses": pg, "pPhone": pp, "glasses": (pg or 0) >= 0.5,
                            "phone": (pp or 0) >= 0.5, "ms": [round(mg, 1), round(mp, 1)]})
                rows.append(row)
            client.post(ROOT + "/api/chat", json={"model": model, "messages": [], "keep_alive": 0})

    summary = []
    for arm in dict.fromkeys(r["arm"] for r in rows):
        rs = [r for r in rows if r["arm"] == arm]
        out = {"arm": arm}
        for key, truth in (("glasses", GLASSES), ("phone", PHONE)):
            tp = sum(1 for r in rs if r[key] and truth[r["t"]])
            fp = sum(1 for r in rs if r[key] and not truth[r["t"]])
            fn = sum(1 for r in rs if not r[key] and truth[r["t"]])
            tn = sum(1 for r in rs if not r[key] and not truth[r["t"]])
            out[key] = {"tp": tp, "fp": fp, "fn": fn, "tn": tn}
        ms = sorted(x for r in rs for x in r.get("ms", []))
        if ms:
            out["callMsP50"] = ms[len(ms) // 2]
            out["callMsP95"] = ms[min(len(ms) - 1, int(round(0.95 * (len(ms) - 1))))]
            out["calls"] = len(ms)
        summary.append(out)
        print(json.dumps(out))

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "run", "frames": sorted(frames),
                             "method": "28 frames (one per 2 s of clip time); truth by eye; "
                                       "arms 1-2 = detector label present (>= 0.35); arm 3 = "
                                       "yoloe-26s best person box +15% pad -> vision._to_jpeg -> "
                                       "local VLM, 1 token, P(yes) from top_logprobs, threshold "
                                       "0.5; no person -> no; call ms = one question, model "
                                       "resident"}) + "\n")
        for s in summary:
            fh.write(json.dumps({"kind": "summary", **s}) + "\n")
        for r in rows:
            fh.write(json.dumps({"kind": "frame", **r}) + "\n")
    print(f"wrote {RESULTS}")


if __name__ == "__main__":
    main()
