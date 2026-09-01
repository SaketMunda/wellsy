"""Perception no-regression benchmark — acceptance criterion 3 of
`.claude/rebuild/step1-repo-reset.md`.

Recorded baseline (M4 Pro, 24 GB, torch 2.6.0, `.claude/day11-results.md`
row 4 + `.claude/decisions.md` D-TTS-swap):
  - fast path (motion gate + YOLOE detect + ByteTrack update), p50 16.81 ms
  - steady-state YOLOE inference (predict only), 21.8-22.2 ms

Budget it must stay inside (`spec/phase1-acceptance.md` §1):
  - perception fast path p50 < 20 ms, p95 < 35 ms

Not part of the shipped package — same category as the old `verify_preemption.py`.

    uv run python bench/detector_bench.py --trials 30
"""

from __future__ import annotations

import argparse
import statistics
import time

import numpy as np
import torch

from wellsy.perception import detector
from wellsy.perception.capture import make_synthetic_frame
from wellsy.perception.motion import motion_gate, to_gate_gray
from wellsy.perception.tracker import Tracker


def pct(vals: list[float], p: float) -> float:
    vals = sorted(vals)
    idx = min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1))))
    return vals[idx]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=30, help="measured trials (>= 20 for acceptance)")
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--device", default="mps")
    ap.add_argument(
        "--camera",
        action="store_true",
        help="grab one real camera frame and fire it repeatedly — matches the "
        "recorded baseline's methodology (a real scene with real objects). "
        "Default is synthetic frames, for camera-less CI.",
    )
    ap.add_argument("--camera-index", type=int, default=0)
    args = ap.parse_args()

    print(f"[bench] torch {torch.__version__}  device={args.device}  "
          f"mps={torch.backends.mps.is_available()}  cuda={torch.cuda.is_available()}")

    model = detector.load_model(device=args.device)
    prompts = detector.load_prompts()
    detector.set_prompts(model, prompts)
    print(f"[bench] prompts={prompts}")

    n_frames = args.warmup + args.trials + 1
    if args.camera:
        import cv2

        cap = cv2.VideoCapture(args.camera_index, cv2.CAP_AVFOUNDATION)
        ok, real = cap.read()
        cap.release()
        if not ok:
            raise SystemExit("camera did not open — check camera permission for this process")
        print(f"[bench] real camera frame {real.shape[1]}x{real.shape[0]}, fired repeatedly")
        # Same frame every trial (the recorded 21.8-22.2 ms methodology). A
        # 1px tick keeps the motion gate and ByteTrack from trivially short-
        # circuiting on pixel-identical input.
        frames = []
        for i in range(n_frames):
            f = real.copy()
            f[0, 0] = (i % 256, 0, 0)
            frames.append(f)
    else:
        # Distinct frames so the motion gate sees real change and ByteTrack
        # has something to match frame-to-frame.
        frames = [make_synthetic_frame(i / 12.0) for i in range(n_frames)]

    # --- cold call (first inference pays the Metal kernel compile) ---
    t0 = time.monotonic()
    detector.predict(model, frames[0], device=args.device)
    cold_ms = (time.monotonic() - t0) * 1000
    print(f"[bench] cold inference: {cold_ms:.1f} ms (kernel compile, excluded from p50/p95)")

    for i in range(1, args.warmup + 1):
        detector.predict(model, frames[i], device=args.device)

    infer_ms: list[float] = []
    fastpath_ms: list[float] = []
    tracker = Tracker(frame_rate=8)
    prev_gray = to_gate_gray(frames[args.warmup])
    for i in range(args.warmup + 1, args.warmup + 1 + args.trials):
        frame = frames[i]

        t_fp = time.monotonic()
        gray = to_gate_gray(frame)
        motion_gate(prev_gray, gray)
        prev_gray = gray
        t_inf = time.monotonic()
        dets = detector.predict(model, frame, device=args.device)
        infer_ms.append((time.monotonic() - t_inf) * 1000)
        tracker.update(dets, now=time.time())
        fastpath_ms.append((time.monotonic() - t_fp) * 1000)

    n = len(infer_ms)
    print(f"\n[bench] n={n}")
    print(f"[bench] YOLOE inference   p50={pct(infer_ms,50):.2f} ms  p95={pct(infer_ms,95):.2f} ms  "
          f"mean={statistics.mean(infer_ms):.2f} ms")
    print(f"[bench] fast path (T0+T1) p50={pct(fastpath_ms,50):.2f} ms  p95={pct(fastpath_ms,95):.2f} ms  "
          f"mean={statistics.mean(fastpath_ms):.2f} ms")

    p50, p95 = pct(fastpath_ms, 50), pct(fastpath_ms, 95)
    ok = p50 < 20.0 and p95 < 35.0
    print(f"\n[bench] acceptance (fast path p50 < 20 ms, p95 < 35 ms): {'PASS' if ok else 'FAIL'}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
