"""Camera capture, in its own process.

Runs in a separate `multiprocessing.Process` from the vision loop (main.py) —
see decisions.md D29. Never blocks a consumer: writes into a latest-wins
queue of depth 1, dropping whatever frame was there before rather than
buffering. A slow consumer sees stale-but-recent frames, never a growing
backlog.
"""

from __future__ import annotations

import time
from multiprocessing import Queue
from multiprocessing.synchronize import Event

import cv2
import numpy as np


def put_latest(q: Queue, item: object) -> None:
    """Latest-wins put: drop whatever's queued, then insert the new item.

    Never blocks. A `qsize()`-based drop check is inherently racy across
    processes, but the failure mode of losing that race is "the queue holds
    one frame instead of zero for an instant" — never unbounded growth,
    which is the actual thing D29 rules out.
    """
    try:
        while True:
            q.get_nowait()
    except Exception:
        pass
    try:
        q.put_nowait(item)
    except Exception:
        pass  # consumer's queue is momentarily full; this frame is expendable


def capture_worker(
    frame_queue: Queue,
    stop_event: Event,
    camera_index: int = 0,
    synthetic: bool = False,
    synthetic_intermittent: bool = False,
) -> None:
    """Opens the camera and pushes (timestamp, bgr_frame, capture_ms) tuples.

    `cv2.CAP_AVFOUNDATION` is explicit rather than left to OpenCV's default
    backend probing — on macOS this is also the point where the OS camera
    permission dialog fires the first time, which is exactly the thing
    day7-prompt.md wants proven now rather than discovered on Day 8.

    `synthetic=True` swaps the frame source for a generated moving frame but
    keeps everything else identical — still a real, separate process, still
    handing frames across the same latest-wins queue. This exists so the
    process-boundary and queue mechanics are provably exercised even in a
    session where a real camera can't be granted permission (see
    day7-baseline.md) — the thing under test there is the plumbing, not the
    pixels.
    """
    cap = None
    if not synthetic and not synthetic_intermittent:
        cap = cv2.VideoCapture(camera_index, cv2.CAP_AVFOUNDATION)
        if not cap.isOpened():
            frame_queue.put(("error", "camera did not open — check macOS camera permission for this process"))
            return

    frame_i = 0
    try:
        while not stop_event.is_set():
            t0 = time.monotonic()
            if synthetic_intermittent:
                frame = make_intermittent_synthetic_frame(frame_i / 30.0)
                ok = True
                time.sleep(1 / 30)
            elif synthetic:
                frame = make_synthetic_frame(frame_i / 30.0)
                ok = True
                time.sleep(1 / 30)  # a real camera paces itself; a generator doesn't, so fake the cadence
            else:
                ok, frame = cap.read()
            capture_ms = (time.monotonic() - t0) * 1000
            frame_i += 1
            if not ok:
                continue
            put_latest(frame_queue, (time.time(), frame, capture_ms))
    finally:
        if cap is not None:
            cap.release()


def make_synthetic_frame(t: float, width: int = 640, height: int = 480) -> np.ndarray:
    """A moving synthetic frame, for exercising the pipeline with no camera
    attached (e.g. this repo's CI, or a machine with the camera denied)."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    x = int((np.sin(t) * 0.5 + 0.5) * (width - 40))
    frame[:, :, 1] = 20  # faint green background so "no motion" is visible as flat gray-green
    cv2.rectangle(frame, (x, height // 2 - 20), (x + 40, height // 2 + 20), (0, 200, 255), -1)
    return frame


def make_intermittent_synthetic_frame(t: float, width: int = 640, height: int = 480) -> np.ndarray:
    """A staged stand-in for day8-prompt.md's intermittent-motion test
    ("enter, hold still 20s, move again") — used when a real camera clip
    isn't available. 0-3s: object enters (moving). 3-23s: frozen in place,
    pixel-identical frames — motion should read as exactly 0 and the gate
    should close. 23s+: moving again, to measure how fast the gate reopens.
    """
    if t < 3:
        te = t
    elif t < 23:
        te = 3.0  # frozen — same position every frame, on purpose
    else:
        te = 3.0 + (t - 23)
    # A small slow accent box (the original make_synthetic_frame shape)
    # never moves the mean-pixel-diff gate at 160x120 — measured well under
    # 1% of MOTION_THRESHOLD. This bar is deliberately large (a third of
    # frame width) and fast (te*3) so the "moving" phases actually clear
    # the gate, making this a meaningful stand-in for a real intermittent-
    # motion clip rather than a no-op.
    bar_width = width // 3
    x = int((np.sin(te * 3.0) * 0.5 + 0.5) * (width - bar_width))
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, 1] = 20
    cv2.rectangle(frame, (x, 0), (x + bar_width, height), (255, 255, 255), -1)
    return frame
