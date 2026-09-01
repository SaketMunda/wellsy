"""Capture-latency benchmark — `.claude/rebuild/step3-capture-layer.md`
acceptance 6. p50/p95 over >= 20 trials, cold vs warm reported separately
(INVARIANTS.md measurement rule). Prior recorded baseline: 203.9 ms for a
1920x1080 capture.

    uv run python bench/capture_bench.py --trials 30

Measures every screen backend that can actually return frames here, plus the
one-shot camera path. A backend that refuses (e.g. ScreenCaptureKit without the
TCC grant) is reported as refused with its message, not silently skipped.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time

from engine.capture.base import CaptureError
from engine.capture.screen import all_candidates


def pct(vals: list[float], p: float) -> float:
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1))))]


def bench_backend(be, trials: int) -> None:
    print(f"\n=== screen backend: {be.name}  (available={be.available()}) ===")
    if not be.available():
        print("  unavailable on this machine — skipped")
        return
    try:
        cold_t0 = time.perf_counter()
        frames = be.capture()
        cold_ms = (time.perf_counter() - cold_t0) * 1000
    except CaptureError as e:
        print(f"  REFUSED: {e.reason}")
        print(f"  (this is the correct behaviour without the grant; latency not measurable here)")
        return
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR: {type(e).__name__}: {e}")
        return

    dims = ", ".join(f"[{f.label}]" for f in frames)
    print(f"  {len(frames)} display(s): {dims}")
    print(f"  cold capture: {cold_ms:.1f} ms")

    warm: list[float] = []
    for _ in range(trials):
        t0 = time.perf_counter()
        be.capture()
        warm.append((time.perf_counter() - t0) * 1000)
    print(
        f"  warm x{trials}: p50 {pct(warm,50):.1f} ms  p95 {pct(warm,95):.1f} ms  "
        f"min {min(warm):.1f}  max {max(warm):.1f}  mean {statistics.mean(warm):.1f}"
    )


def bench_camera(trials: int, camera_index: int) -> None:
    from engine.capture.camera import capture_camera

    print(f"\n=== camera one-shot (index {camera_index}) ===")
    try:
        t0 = time.perf_counter()
        r = capture_camera(camera_index)
        cold = (time.perf_counter() - t0) * 1000
    except CaptureError as e:
        print(f"  REFUSED: {e.reason}")
        return
    f = r.frames[0]
    print(f"  frame {f.width}x{f.height}; cold (open+grab) {cold:.1f} ms")
    warm = []
    for _ in range(trials):
        t0 = time.perf_counter()
        capture_camera(camera_index)
        warm.append((time.perf_counter() - t0) * 1000)
    print(f"  warm x{trials} (reopen+grab): p50 {pct(warm,50):.1f} ms  p95 {pct(warm,95):.1f} ms")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--camera", action="store_true", help="also benchmark the one-shot camera path")
    ap.add_argument("--camera-index", type=int, default=0)
    args = ap.parse_args()

    print(f"platform: {sys.platform}")
    for be in all_candidates():
        bench_backend(be, args.trials)
    if args.camera:
        bench_camera(args.trials, args.camera_index)


if __name__ == "__main__":
    main()
