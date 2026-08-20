"""Day 8 engine loop: camera -> motion gate (T0) -> detect+track (T1) ->
JSON lines on stdout. T2/T3 exist as wired stubs (tiers.py) — see
.claude/day8-prompt.md and decisions.md D28-D32.

Usage:
    uv run main.py                 # real camera, runs until Ctrl+C
    uv run main.py --seconds 60    # real camera, stops after 60s
    uv run main.py --synthetic     # no camera required — exercises the
                                    # same pipeline against a generated
                                    # moving frame, for machines/sessions
                                    # where the camera isn't available
    uv run main.py --no-detect     # T0 only, Day 7 behavior — for isolating
                                    # motion-gate cost from detection cost
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from multiprocessing import Event, Process, Queue
from pathlib import Path

from bridge import Bridge
from capture import capture_worker
from motion import motion_gate, to_gate_gray

# How much history the gated-fraction readout (stderr) is computed over.
STATS_WINDOW_SECONDS = 60

# T1 rate cap — 8Hz, not 60Hz: detection is the expensive tier, and D15's
# render-time interpolation (browser build, hudState.ts) already proves
# 8Hz *looks* smooth once boxes are interpolated on Day 9. Running faster
# would burn CPU nothing downstream benefits from.
DETECT_HZ = 8.0
DETECT_INTERVAL_S = 1.0 / DETECT_HZ

# Hysteresis: keep T1 warm for this long after the last real motion before
# letting it go idle. Without this, someone pausing mid-gesture freezes
# mid-gesture the instant T0 gates the frame — see day8-prompt.md's
# explicit correctness trap.
MOTION_HOLD_SECONDS = 1.0

PROMPTS_PATH = Path(__file__).parent / "prompts.txt"


def emit(
    t_wall: float,
    motion: float,
    gated: bool,
    capture_ms: float,
    gate_ms: float,
    tracks: list[dict],
    detections: list[dict],
    inference_ms: float | None,
    stats: deque[tuple[float, bool]],
) -> None:
    record = {
        "t": round(t_wall, 3),
        "motion": round(motion, 4),
        "gated": gated,
        "captureMs": round(capture_ms, 2),
        "gateMs": round(gate_ms, 2),
        "detections": detections,
        "tracks": tracks,
        "inferenceMs": round(inference_ms, 2) if inference_ms is not None else None,
    }
    print(json.dumps(record), flush=True)

    stats.append((t_wall, gated))
    while stats and t_wall - stats[0][0] > STATS_WINDOW_SECONDS:
        stats.popleft()
    if len(stats) % 30 == 0 and len(stats) > 0:
        fraction = sum(1 for _, g in stats if g) / len(stats)
        window_s = t_wall - stats[0][0]
        print(f"[gated-fraction] {fraction:.1%} over last {window_s:.0f}s ({len(stats)} frames)", file=sys.stderr, flush=True)


def run_camera(
    seconds: float | None,
    camera_index: int,
    synthetic: bool,
    detect: bool,
    synthetic_intermittent: bool = False,
    ws_port: int | None = 8765,
) -> None:
    frame_queue: Queue = Queue(maxsize=1)
    stop_event = Event()
    proc = Process(
        target=capture_worker,
        args=(frame_queue, stop_event, camera_index, synthetic, synthetic_intermittent),
        daemon=True,
    )
    proc.start()

    bridge = None
    if ws_port is not None:
        bridge = Bridge(ws_port)
        bridge.start()

    model = None
    tracker = None
    prompts: list[str] = []
    prompts_mtime = None
    if detect:
        import detector
        from tracker import Tracker

        print("[setup] loading detector...", file=sys.stderr, flush=True)
        t0 = time.monotonic()
        model = detector.load_model()
        prompts = detector.load_prompts(PROMPTS_PATH)
        prompts_mtime = PROMPTS_PATH.stat().st_mtime if PROMPTS_PATH.exists() else None
        detector.set_prompts(model, prompts)
        tracker = Tracker(frame_rate=int(DETECT_HZ))
        print(f"[setup] detector ready in {time.monotonic() - t0:.1f}s, prompts={prompts}", file=sys.stderr, flush=True)

    prev_gray = None
    stats: deque[tuple[float, bool]] = deque()
    last_motion_time = None  # None = no real motion observed yet
    last_detect_time = 0.0
    last_tracks: list[dict] = []  # T1's last output — held across gated/rate-limited frames
    last_detections: list[dict] = []
    last_broadcast_time = 0.0  # throttles the bridge to ~DETECT_HZ independent of capture
    # rate — day9-prompt.md is explicit that the client should see ~8Hz of
    # messages, not however fast the camera captures (up to 60Hz on a real
    # camera, ~30Hz synthetic). stdout's emit() stays per-capture-frame,
    # unchanged from Day 8; only the bridge is throttled.
    bootstrapped = False  # forces exactly one T1 run on the first frame, gate or no gate,
    # so a scene with zero motion since startup still gets an initial look —
    # after that, only real motion (+ hysteresis) reopens T1. Without this
    # distinct flag, "no motion observed yet" is indistinguishable from
    # "motion observed, currently still", and T1 either never runs on a
    # static-from-the-start scene or runs forever on one — see decisions.md D31.
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
            now = time.monotonic()

            t1 = time.monotonic()
            gray = to_gate_gray(frame)
            motion, gated = motion_gate(prev_gray, gray)
            gate_ms = (time.monotonic() - t1) * 1000
            prev_gray = gray

            if not gated:
                last_motion_time = now

            inference_ms = None
            if detect:
                held_open = last_motion_time is not None and (now - last_motion_time) < MOTION_HOLD_SECONDS
                t1_active = (not gated) or held_open or not bootstrapped
                due = (now - last_detect_time) >= DETECT_INTERVAL_S

                if t1_active and due:
                    bootstrapped = True
                    if prompts_mtime is not None and PROMPTS_PATH.exists():
                        mtime = PROMPTS_PATH.stat().st_mtime
                        if mtime != prompts_mtime:
                            prompts = detector.load_prompts(PROMPTS_PATH)
                            detector.set_prompts(model, prompts)
                            prompts_mtime = mtime
                            print(f"[prompts] reloaded: {prompts}", file=sys.stderr, flush=True)

                    ti = time.monotonic()
                    last_detections = detector.predict(model, frame)
                    last_tracks = tracker.update(last_detections, now=t_wall)
                    inference_ms = (time.monotonic() - ti) * 1000
                    last_detect_time = now
                # else: T1 didn't run this frame — last_tracks/last_detections
                # from the previous run are re-emitted below, on purpose. A
                # still room must keep showing what was last seen, not go
                # empty (day8-prompt.md's explicit correctness trap).

            emit(t_wall, motion, gated, capture_ms, gate_ms, last_tracks, last_detections, inference_ms, stats)

            if bridge is not None and (now - last_broadcast_time) >= DETECT_INTERVAL_S:
                last_broadcast_time = now
                # Separate payload from emit()'s stdout record on purpose —
                # stdout stays byte-compatible with Day 8 (day9-prompt.md's
                # verification rule), and the bridge is free to carry the
                # extra fields (sourceWidth/sourceHeight) the client needs
                # for the coordinate contract (day9-prompt.md Part 1)
                # without the two wire formats needing to agree.
                bridge.broadcast({
                    "t": round(t_wall, 3),
                    "motion": round(motion, 4),
                    "gated": gated,
                    "captureMs": round(capture_ms, 2),
                    "gateMs": round(gate_ms, 2),
                    "detections": last_detections,
                    "tracks": last_tracks,
                    "inferenceMs": round(inference_ms, 2) if inference_ms is not None else None,
                    "sourceWidth": frame.shape[1],
                    "sourceHeight": frame.shape[0],
                })
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        proc.join(timeout=2.0)
        if proc.is_alive():
            proc.terminate()
        if bridge is not None:
            bridge.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=None, help="stop after N seconds (default: run until Ctrl+C)")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--synthetic", action="store_true", help="skip the real camera, use a generated moving frame")
    parser.add_argument("--no-detect", action="store_true", help="T0 only (Day 7 behavior) — isolates motion-gate cost")
    parser.add_argument(
        "--synthetic-intermittent",
        action="store_true",
        help="staged enter/hold-still-20s/move-again clip, for the intermittent-motion test (day8-prompt.md) when a real camera clip isn't available",
    )
    parser.add_argument("--ws-port", type=int, default=8765, help="WebSocket bridge port, localhost only (day9-prompt.md)")
    parser.add_argument("--no-ws", action="store_true", help="disable the WebSocket bridge — stdout JSONL only, Day 8 behavior")
    args = parser.parse_args()
    run_camera(
        args.seconds,
        args.camera_index,
        args.synthetic or args.synthetic_intermittent,
        detect=not args.no_detect,
        synthetic_intermittent=args.synthetic_intermittent,
        ws_port=None if args.no_ws else args.ws_port,
    )


if __name__ == "__main__":
    main()
