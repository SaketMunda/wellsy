"""Side-by-side detector comparison on one recorded clip — step 5c Deliverable 4.

Step 6c's perception baseline ran the detector on 1.8 % of frames because the
T0 motion gate stayed closed while the owner put on glasses or held up a phone.
A comparison through that gate measures the gate twice. This script removes
both confounds: every detector sees the **identical frames** of one clip, and
T1 runs on every 8 Hz tick (the live `DETECT_HZ` cadence), gate ignored.

T0 is still computed and timed per frame (INVARIANTS #5); its decision is
recorded beside each tick but never consulted.

Per detector it writes: load s, cold first call ms, warm detect+track p50/p95
(nearest-rank), and for every label on the prompt list the ticks it was seen on
plus its score range — so D30's named misses (glasses, cell phone in hand) are
read straight off the table.

Not part of the shipped package (same category as `detector_bench.py`).

    uv run wellsy --seconds 60 --record runs/step5c/clip.mp4     # owner records once
    uv run python bench/detector_clip_compare.py runs/step5c/clip.mp4 \\
        --detector yoloe-11s-seg.pt --detector yoloe-26s-seg.pt
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

import cv2

from engine.perception import detector
from engine.perception.motion import motion_gate, to_gate_gray
from engine.perception.tracker import Tracker

DETECT_HZ = 8.0  # engine/cli.py DETECT_HZ — the live T1 cadence
RESULTS_DIR = Path(__file__).resolve().parent.parent / "spec" / "results"


def pct(vals: list[float], p: float) -> float:
    vals = sorted(vals)
    idx = min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1))))
    return vals[idx]


def read_ticks(clip: Path) -> tuple[list[tuple[float, object]], float, int]:
    """Every frame on the 8 Hz grid, by clip timestamp — identical for every
    detector. Returns (ticks, fps, total_frames)."""
    cap = cv2.VideoCapture(str(clip))
    if not cap.isOpened():
        raise SystemExit(f"clip did not open: {clip}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    ticks: list[tuple[float, object]] = []
    next_t = 0.0
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        if t + 1e-9 >= next_t:
            ticks.append((t, frame))
            next_t += 1.0 / DETECT_HZ
        i += 1
    cap.release()
    return ticks, fps, i


def run_detector(name: str, ticks, prompts: list[str]) -> dict:
    t0 = time.monotonic()
    model = detector.load_model(name=name)
    detector.set_prompts(model, prompts)
    load_s = time.monotonic() - t0
    tracker = Tracker(frame_rate=int(DETECT_HZ))

    prev_gray = None
    gate_ms: list[float] = []
    t0_open = 0
    infer_ms: list[float] = []
    per_tick: list[dict] = []
    for t, frame in ticks:
        tg = time.monotonic()
        gray = to_gate_gray(frame)
        _, gated = motion_gate(prev_gray, gray)
        gate_ms.append((time.monotonic() - tg) * 1000)
        prev_gray = gray
        t0_open += 0 if gated else 1

        ti = time.monotonic()
        dets = detector.predict(model, frame)
        tracker.update(dets, now=t)
        infer_ms.append((time.monotonic() - ti) * 1000)
        per_tick.append({"t": round(t, 3), "t0Gated": gated,
                         "labels": [[d["label"], d["score"]] for d in dets]})

    labels: dict[str, dict] = {}
    for tick in per_tick:
        seen: set[str] = set()
        for label, score in tick["labels"]:
            e = labels.setdefault(label, {"ticks": 0, "min": 1.0, "max": 0.0, "first": tick["t"]})
            if label not in seen:          # distinct ticks, not boxes
                e["ticks"] += 1
                seen.add(label)
            e["min"] = min(e["min"], score)
            e["max"] = max(e["max"], score)
            e["last"] = tick["t"]
    warm = infer_ms[1:]
    return {
        "kind": "result", "detector": name, "ticks": len(ticks),
        "loadS": round(load_s, 2), "coldFirstCallMs": round(infer_ms[0], 2),
        "warmP50Ms": round(pct(warm, 50), 2) if warm else None,
        "warmP95Ms": round(pct(warm, 95), 2) if warm else None,
        "t0GateMsP50": round(pct(gate_ms, 50), 2),
        "t0WouldHaveOpened": t0_open,
        "labels": labels, "perTick": per_tick,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--detector", action="append", required=True,
                    help="weights; pass more than once for a side-by-side")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    clip = Path(args.clip).resolve()
    ticks, fps, n = read_ticks(clip)
    prompts = detector.load_prompts()
    print(f"[compare] {clip.name}: {n} frames @ {fps:.1f} fps -> {len(ticks)} ticks at "
          f"{DETECT_HZ:g} Hz; prompts={prompts}")

    rows = [run_detector(name, ticks, prompts) for name in args.detector]
    for r in rows:
        print(f"\n[{r['detector']}] load {r['loadS']} s · cold {r['coldFirstCallMs']} ms · "
              f"warm detect+track p50 {r['warmP50Ms']} / p95 {r['warmP95Ms']} ms "
              f"(n={r['ticks'] - 1}) · T0 would have opened on {r['t0WouldHaveOpened']}/{r['ticks']}")
        for label, e in sorted(r["labels"].items(), key=lambda kv: -kv[1]["ticks"]):
            print(f"    {label:22s} {e['ticks']:4d}/{r['ticks']} ticks  "
                  f"score {e['min']:.2f}-{e['max']:.2f}  {e['first']:.1f}-{e['last']:.1f}s")

    out = Path(args.out) if args.out else (
        RESULTS_DIR / f"detector-clip-compare-{date.today().isoformat()}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "run", "clip": str(clip), "fps": fps, "frames": n,
                            "detectHz": DETECT_HZ, "prompts": prompts,
                            "method": "identical clip frames on the 8 Hz grid; T1 every "
                                      "tick (T0 timed, decision ignored); warm = ticks[1:]; "
                                      "p50/p95 nearest-rank; detect+track wall ms"}) + "\n")
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"\n[compare] wrote {out}")


if __name__ == "__main__":
    main()
