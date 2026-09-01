"""WELLSY perception loop: camera -> motion gate (T0) -> detect+track (T1) ->
JSON lines on stdout. No voice path, no bridge — those are rebuilt in later
steps as clients of the runtime.

This is the Day 8 `engine/main.py` loop with the browser bridge, the T3 query
loop, ambient narration and the person-greeter removed. The perception
behaviour (motion hysteresis, the one forced bootstrap detection, re-emitting
the last tracks on gated frames) is carried over unchanged — see
`.claude/day8-prompt.md` and `.claude/decisions.md` D28-D32.

Usage:
    wellsy                       # real camera, runs until Ctrl+C
    wellsy --seconds 60          # real camera, stops after 60s
    wellsy --synthetic           # no camera — generated moving frame
    wellsy --no-detect           # T0 only — isolates motion-gate cost
    wellsy bench                  # cross-platform inference benchmark (LLM / ASR / TTS / VAD)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from multiprocessing import Event, Process, Queue
from pathlib import Path

from engine.perception.capture import capture_worker
from engine.perception.motion import motion_gate, to_gate_gray
from engine.runtime.tiers import PreemptionSeam

# How much history the gated-fraction readout (stderr) is computed over.
STATS_WINDOW_SECONDS = 60

# T1 rate cap — 8Hz, not 60Hz: detection is the expensive tier and nothing
# downstream benefits from running it faster (decisions.md D15).
DETECT_HZ = 8.0
DETECT_INTERVAL_S = 1.0 / DETECT_HZ

# Hysteresis: keep T1 warm for this long after the last real motion before
# letting it go idle, so someone pausing mid-gesture doesn't freeze the
# instant T0 gates the frame (day8-prompt.md's explicit correctness trap).
MOTION_HOLD_SECONDS = 1.0

PROMPTS_PATH = Path(__file__).resolve().parent / "config" / "prompts.txt"


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
    quiet: bool = False,
) -> None:
    if not quiet:
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
        print(
            f"[gated-fraction] {fraction:.1%} over last {window_s:.0f}s ({len(stats)} frames)",
            file=sys.stderr,
            flush=True,
        )


def run_camera(
    seconds: float | None,
    camera_index: int,
    synthetic: bool,
    detect: bool,
    synthetic_intermittent: bool = False,
    quiet: bool = True,
) -> None:
    frame_queue: Queue = Queue(maxsize=1)
    stop_event = Event()
    proc = Process(
        target=capture_worker,
        args=(frame_queue, stop_event, camera_index, synthetic, synthetic_intermittent),
        daemon=True,
    )
    proc.start()

    model = None
    tracker = None
    prompts: list[str] = []
    prompts_mtime = None
    if detect:
        from engine.perception import detector
        from engine.perception.tracker import Tracker

        print("[setup] loading detector...", file=sys.stderr, flush=True)
        t0 = time.monotonic()
        model = detector.load_model()
        prompts = detector.load_prompts(PROMPTS_PATH)
        prompts_mtime = PROMPTS_PATH.stat().st_mtime if PROMPTS_PATH.exists() else None
        detector.set_prompts(model, prompts)
        tracker = Tracker(frame_rate=int(DETECT_HZ))
        print(
            f"[setup] detector ready in {time.monotonic() - t0:.1f}s, prompts={prompts}",
            file=sys.stderr,
            flush=True,
        )

    # PreemptionSeam is constructed but has no query-path caller yet — it comes
    # back in step 4/5. T1 here always runs on its own 8Hz schedule.
    preemption = PreemptionSeam()

    prev_gray = None
    stats: deque[tuple[float, bool]] = deque()
    last_motion_time = None
    last_detect_time = 0.0
    last_tracks: list[dict] = []
    last_detections: list[dict] = []
    bootstrapped = False
    start = time.monotonic()
    try:
        while seconds is None or (time.monotonic() - start) < seconds:
            try:
                item = frame_queue.get(timeout=2.0)
            except Exception:
                print(
                    "[warn] no frame in 2s — camera process may be stuck or waiting on permission",
                    file=sys.stderr,
                    flush=True,
                )
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
            if detect and not preemption.active:
                if prompts_mtime is not None and PROMPTS_PATH.exists():
                    mtime = PROMPTS_PATH.stat().st_mtime
                    if mtime != prompts_mtime:
                        prompts = detector.load_prompts(PROMPTS_PATH)
                        detector.set_prompts(model, prompts)
                        prompts_mtime = mtime
                        print(f"[prompts] reloaded: {prompts}", file=sys.stderr, flush=True)

                held_open = (
                    last_motion_time is not None
                    and (now - last_motion_time) < MOTION_HOLD_SECONDS
                )
                t1_active = (not gated) or held_open or not bootstrapped
                due = (now - last_detect_time) >= DETECT_INTERVAL_S

                if t1_active and due:
                    bootstrapped = True
                    ti = time.monotonic()
                    last_detections = detector.predict(model, frame)
                    last_tracks = tracker.update(last_detections, now=t_wall)
                    inference_ms = (time.monotonic() - ti) * 1000
                    last_detect_time = now
                # else: T1 didn't run — last_tracks/last_detections from the
                # previous run are re-emitted below on purpose. A still room
                # keeps showing what was last seen, not go empty.

            emit(
                t_wall,
                motion,
                gated,
                capture_ms,
                gate_ms,
                last_tracks,
                last_detections,
                inference_ms,
                stats,
                quiet=quiet,
            )
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        proc.join(timeout=2.0)
        if proc.is_alive():
            proc.terminate()


def _run_bench(argv: list[str]) -> None:
    from engine.inference.bench import main as bench_main

    raise SystemExit(bench_main(argv))


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "bench":
        return _run_bench(sys.argv[2:])
    parser = argparse.ArgumentParser(prog="wellsy", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seconds", type=float, default=None, help="stop after N seconds (default: run until Ctrl+C)")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--synthetic", action="store_true", help="skip the real camera, use a generated moving frame")
    parser.add_argument("--no-detect", action="store_true", help="T0 only — isolates motion-gate cost from detection cost")
    parser.add_argument(
        "--synthetic-intermittent",
        action="store_true",
        help="staged enter/hold-still-20s/move-again clip, for the intermittent-motion test when a real camera clip isn't available",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="print the per-frame JSONL on stdout (one line per camera frame) — off by default",
    )
    args = parser.parse_args()
    run_camera(
        args.seconds,
        args.camera_index,
        args.synthetic or args.synthetic_intermittent,
        detect=not args.no_detect,
        synthetic_intermittent=args.synthetic_intermittent,
        quiet=not args.debug,
    )


if __name__ == "__main__":
    main()
