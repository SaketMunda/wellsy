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
import os
import sys
import time
from collections import deque
from multiprocessing import Event, Process, Queue
from pathlib import Path

# Redirect STT's HF Hub weights cache into the single recorded cache
# exception (~/.cache/yap-engine/weights, D30) before anything imports
# moonshine_onnx — day10-prompt.md's boundary rule says this cache dir
# "does not get extended today," which means new model caches route through
# it, not that no new caches may exist.
os.environ.setdefault("HF_HOME", str(Path.home() / ".cache" / "yap-engine" / "weights" / "hf"))

from bridge import Bridge
from capture import capture_worker
from motion import motion_gate, to_gate_gray
from tiers import PreemptionSeam

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
    enable_t3: bool = False,
    enable_yo: bool = False,
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

    preemption = PreemptionSeam()
    query_loop = None
    if enable_t3:
        if not detect:
            print("[warn] --t3 requires detection; ignoring (pass without --no-detect)", file=sys.stderr, flush=True)
        else:
            print("[setup] loading STT...", file=sys.stderr, flush=True)
            t0 = time.monotonic()
            from query_loop import QueryLoop
            from stt import Stt

            stt = Stt()
            print(f"[setup] STT ready in {time.monotonic() - t0:.1f}s", file=sys.stderr, flush=True)

            print("[setup] checking Ollama...", file=sys.stderr, flush=True)
            t0 = time.monotonic()
            from llm import Llm

            llm = Llm()
            print(f"[setup] Ollama reachable, using {llm._model_name} ({time.monotonic() - t0:.1f}s)", file=sys.stderr, flush=True)

            query_loop = QueryLoop(preemption, stt, llm=llm, enable_yo=enable_yo)
            query_loop.start()

    ambient = None
    if query_loop is not None:
        from ambient import AmbientNarrator

        ambient = AmbientNarrator(query_loop)

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
                # day10-prompt.md Part 0.1: a query forces a fresh T1 look,
                # synchronously, before describeScene reads anything —
                # regardless of the motion gate. This runs even while T3
                # has preempted ambient sensing below, because it's the
                # forced look T3 is specifically waiting on.
                if preemption.poll_force_request():
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
                    bootstrapped = True
                    preemption.deliver_fresh_look(last_tracks, inference_ms)

                # T3 preempts T1 (day10-prompt.md Part 1): while a query is
                # in flight, ambient sensing's own-schedule detection pauses
                # entirely — the JSONL should show no new inferenceMs values
                # here for the duration of the query except the forced one
                # above. T0 (the gate computed above, every frame
                # regardless) is unaffected — "do not gate the gate."
                elif not preemption.active:
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

            if ambient is not None:
                ambient.update(last_tracks)

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
                    # Part 2 (decisions.md D38): silence is the default —
                    # the HUD must be able to show whether ambient
                    # narration could speak unprompted right now.
                    "ambientEnabled": query_loop.ambient_enabled if query_loop is not None else False,
                    # decisions.md D40's ecosystem follow-up: T3's voice
                    # loop (mic, STT, LLM, TTS) runs entirely in this
                    # process with zero visibility in the browser — this
                    # is what lets the HUD show captions for what's
                    # actually being said, instead of nothing.
                    "voice": query_loop.last_exchange if query_loop is not None else None,
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
        if query_loop is not None:
            query_loop.stop()


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
    parser.add_argument("--t3", action="store_true", help="enable the Day 10 query loop: mic, wake phrase, push-to-talk, TTS (day10-prompt.md)")
    parser.add_argument("--enable-yo", action="store_true", help="add bare 'yo' to the wake phrase list, off by default per decisions.md D39")
    args = parser.parse_args()
    run_camera(
        args.seconds,
        args.camera_index,
        args.synthetic or args.synthetic_intermittent,
        detect=not args.no_detect,
        synthetic_intermittent=args.synthetic_intermittent,
        ws_port=None if args.no_ws else args.ws_port,
        enable_t3=args.t3,
        enable_yo=args.enable_yo,
    )


if __name__ == "__main__":
    main()
