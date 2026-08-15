"""Frame-differencing motion gate — T0 in the tier scheduler
(v2-architecture-research.md §2a). No model, no tracker: this is the ~1ms
check that decides whether anything more expensive should run at all.

Pure function, same discipline as tracker.ts/drawHud.ts in the browser build
(architecture.md's purity rule) — given the same two frames it returns the
same answer, no I/O, no state.
"""

from __future__ import annotations

import cv2
import numpy as np

# Frames are downscaled before differencing — the gate only needs to answer
# "did enough change", not localize it, so full resolution buys nothing but
# CPU. 160x120 keeps the per-frame cost near the ~1ms target on this machine.
GATE_WIDTH = 160
GATE_HEIGHT = 120

# Mean per-pixel absolute difference (0..255) below this is "nothing moved".
# First-guess constant, like D11's alpha=0.4 or D15's tau=70ms — not tuned
# against real footage yet. Revisit once a real still room is measured.
MOTION_THRESHOLD = 4.0


def to_gate_gray(frame_bgr: np.ndarray) -> np.ndarray:
    small = cv2.resize(frame_bgr, (GATE_WIDTH, GATE_HEIGHT), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)


def motion_gate(prev_gray: np.ndarray | None, curr_gray: np.ndarray) -> tuple[float, bool]:
    """Returns (motion, gated). `motion` is the mean absolute pixel
    difference against the previous gated-resolution grayscale frame,
    normalized to 0..1. `gated=True` means downstream work (T1 detection)
    should be skipped for this frame — see v2-architecture-research.md §2a.
    """
    if prev_gray is None:
        return 0.0, True  # nothing to compare against yet — first frame is always gated
    diff = cv2.absdiff(prev_gray, curr_gray)
    mean_diff = float(np.mean(diff))
    motion = mean_diff / 255.0
    gated = mean_diff < MOTION_THRESHOLD
    return motion, gated
