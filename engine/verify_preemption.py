"""Day 10 verification harness for Part 0.1 / Part 1's preemption claim —
NOT part of the shipped engine. Runs the real camera + real detector with
the real PreemptionSeam, and from a side thread (standing in for T3, minus
audio) calls `request_fresh_look()` partway through, exactly the way
query_loop.py's `handle_command` does. Writes one JSONL line per captured
frame so day10-results.md can show, from real data, that: (a) the forced
look appears with a real, measured inferenceMs; (b) T1's own-schedule
detection produces zero further inferenceMs values for the duration the
seam is held active.

    uv run python verify_preemption.py --seconds 12 --preempt-at 4 --hold 2
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from multiprocessing import Event, Process, Queue
from pathlib import Path

from capture import capture_worker
from motion import motion_gate, to_gate_gray
from tiers import PreemptionSeam

DETECT_HZ = 8.0
DETECT_INTERVAL_S = 1.0 / DETECT_HZ
MOTION_HOLD_SECONDS = 1.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=12.0)
    parser.add_argument("--preempt-at", type=float, default=4.0, help="seconds after start to fire request_fresh_look()")
    parser.add_argument("--hold", type=float, default=2.0, help="how long to keep the seam active after the forced look, simulating TTS speaking the answer")
    parser.add_argument("--out", default=str(Path(__file__).parent / "clips" / "preemption-verify.jsonl"))
    args = parser.parse_args()

    import detector
    from tracker import Tracker

    print("[setup] loading detector...", file=sys.stderr, flush=True)
    model = detector.load_model()
    prompts = detector.load_prompts()
    detector.set_prompts(model, prompts)
    tracker = Tracker(frame_rate=int(DETECT_HZ))
    print(f"[setup] ready, prompts={prompts}", file=sys.stderr, flush=True)

    preemption = PreemptionSeam()
    forced_look_ms: list[float] = []

    def t3_side_thread() -> None:
        time.sleep(args.preempt_at)
        preemption.request()
        t0 = time.monotonic()
        result = preemption.request_fresh_look()
        dt = (time.monotonic() - t0) * 1000
        if result:
            forced_look_ms.append(result[1])
            print(f"[t3-sim] forced look delivered in {dt:.1f}ms wall, inferenceMs={result[1]:.1f}", file=sys.stderr, flush=True)
        else:
            print("[t3-sim] forced look TIMED OUT", file=sys.stderr, flush=True)
        time.sleep(args.hold)
        preemption.release()
        print("[t3-sim] released", file=sys.stderr, flush=True)

    threading.Thread(target=t3_side_thread, daemon=True).start()

    frame_queue: Queue = Queue(maxsize=1)
    stop_event = Event()
    proc = Process(target=capture_worker, args=(frame_queue, stop_event, 0, False, False), daemon=True)
    proc.start()

    prev_gray = None
    last_motion_time = None
    last_detect_time = 0.0
    last_tracks: list[dict] = []
    bootstrapped = False
    start = time.monotonic()

    out_path = args.out
    with open(out_path, "w") as f:
        try:
            while (time.monotonic() - start) < args.seconds:
                try:
                    item = frame_queue.get(timeout=2.0)
                except Exception:
                    continue
                if item[0] == "error":
                    print(f"[error] {item[1]}", file=sys.stderr, flush=True)
                    break
                t_wall, frame, capture_ms = item
                now = time.monotonic()

                gray = to_gate_gray(frame)
                motion, gated = motion_gate(prev_gray, gray)
                prev_gray = gray
                if not gated:
                    last_motion_time = now

                inference_ms = None
                forced = False
                if preemption.poll_force_request():
                    ti = time.monotonic()
                    detections = detector.predict(model, frame)
                    last_tracks = tracker.update(detections, now=t_wall)
                    inference_ms = (time.monotonic() - ti) * 1000
                    last_detect_time = now
                    bootstrapped = True
                    forced = True
                    preemption.deliver_fresh_look(last_tracks, inference_ms)
                elif not preemption.active:
                    held_open = last_motion_time is not None and (now - last_motion_time) < MOTION_HOLD_SECONDS
                    t1_active = (not gated) or held_open or not bootstrapped
                    due = (now - last_detect_time) >= DETECT_INTERVAL_S
                    if t1_active and due:
                        ti = time.monotonic()
                        detections = detector.predict(model, frame)
                        last_tracks = tracker.update(detections, now=t_wall)
                        inference_ms = (time.monotonic() - ti) * 1000
                        last_detect_time = now
                        bootstrapped = True

                f.write(json.dumps({
                    "t": round(now - start, 3),
                    "gated": gated,
                    "preemptionActive": preemption.active,
                    "forced": forced,
                    "inferenceMs": round(inference_ms, 2) if inference_ms is not None else None,
                }) + "\n")
                f.flush()
        finally:
            stop_event.set()
            proc.join(timeout=2.0)
            if proc.is_alive():
                proc.terminate()

    print(f"[done] wrote {out_path}, forced_look_ms={forced_look_ms}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
