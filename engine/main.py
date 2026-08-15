"""Day 7 Python skeleton: camera -> motion gate -> JSON lines on stdout.

No model, no tracker, no HUD, no WebSocket — see .claude/day7-prompt.md.
This exists to prove three things before anything expensive is built on top:
1. Camera access works from Python on this machine (macOS permission dialog
   included).
2. The motion gate is genuinely cheap (~1ms/frame, measured below).
3. Process boundaries hold: capture runs in its own process, handing frames
   to this one across a latest-wins queue of depth 1 (decisions.md D29).

Usage:
    uv run main.py                 # real camera, runs until Ctrl+C
    uv run main.py --seconds 60    # real camera, stops after 60s
    uv run main.py --synthetic     # no camera required — exercises the
                                    # same pipeline against a generated
                                    # moving frame, for machines/sessions
                                    # where the camera isn't available
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from multiprocessing import Event, Process, Queue

from capture import capture_worker
from motion import motion_gate, to_gate_gray

# How much history the gated-fraction readout (stderr) is computed over.
STATS_WINDOW_SECONDS = 60


def emit(
    t_wall: float,
    motion: float,
    gated: bool,
    capture_ms: float,
    gate_ms: float,
    stats: deque[tuple[float, bool]],
) -> None:
    record = {
        "t": round(t_wall, 3),
        "motion": round(motion, 4),
        "gated": gated,
        "captureMs": round(capture_ms, 2),
        "gateMs": round(gate_ms, 2),
    }
    print(json.dumps(record), flush=True)

    stats.append((t_wall, gated))
    while stats and t_wall - stats[0][0] > STATS_WINDOW_SECONDS:
        stats.popleft()
    if len(stats) % 30 == 0 and len(stats) > 0:
        fraction = sum(1 for _, g in stats if g) / len(stats)
        window_s = t_wall - stats[0][0]
        print(f"[gated-fraction] {fraction:.1%} over last {window_s:.0f}s ({len(stats)} frames)", file=sys.stderr, flush=True)


def run_camera(seconds: float | None, camera_index: int, synthetic: bool) -> None:
    frame_queue: Queue = Queue(maxsize=1)
    stop_event = Event()
    proc = Process(target=capture_worker, args=(frame_queue, stop_event, camera_index, synthetic), daemon=True)
    proc.start()

    prev_gray = None
    stats: deque[tuple[float, bool]] = deque()
    start = time.monotonic()
    try:
        while seconds is None or (time.monotonic() - start) < seconds:
            try:
                item = frame_queue.get(timeout=2.0)
            except Exception:
                print("[warn] no frame in 2s — camera process may be stuck or waiting on permission", file=sys.stderr, flush=True)
                continue

            if item[0] == "error":
                print(f"[error] {item[1]}", file=sys.stderr, flush=True)
                break

            t_wall, frame, capture_ms = item
            t1 = time.monotonic()
            gray = to_gate_gray(frame)
            motion, gated = motion_gate(prev_gray, gray)
            gate_ms = (time.monotonic() - t1) * 1000
            prev_gray = gray

            emit(t_wall, motion, gated, capture_ms, gate_ms, stats)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        proc.join(timeout=2.0)
        if proc.is_alive():
            proc.terminate()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=None, help="stop after N seconds (default: run until Ctrl+C)")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--synthetic", action="store_true", help="skip the real camera, use a generated moving frame")
    args = parser.parse_args()
    run_camera(args.seconds, args.camera_index, args.synthetic)


if __name__ == "__main__":
    main()
