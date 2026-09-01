"""On-demand single-frame camera capture, for a routed "what am I looking at"
query. Portable (OpenCV / `cv2.VideoCapture`) — the same source the ambient
perception loop uses in `engine/perception/capture.py`, but grabbed once
instead of streamed.

The camera has no degenerate-capture failure mode of the screen kind: OpenCV
returns `ok == False` (not a plausible-looking wrong frame) when the device is
denied or absent, so verification here is just "we got a frame with signal in
it", not the multi-signal screen gate.
"""

from __future__ import annotations

import sys
import time

import cv2
import numpy as np

from engine.capture.base import CaptureError, CaptureResult, DisplayFrame

_BACKEND = cv2.CAP_AVFOUNDATION if sys.platform == "darwin" else cv2.CAP_ANY


def capture_camera(camera_index: int = 0, *, warmup_frames: int = 3, timeout_s: float = 3.0) -> CaptureResult:
    cap = cv2.VideoCapture(camera_index, _BACKEND)
    if not cap.isOpened():
        raise CaptureError(
            f"Camera {camera_index} did not open.",
            permission="camera",
            remedy=(
                "Grant Camera permission for this process ( > System Settings > "
                "Privacy & Security > Camera on macOS), or check the device is "
                "connected. `wellsy doctor` confirms."
            ),
            spoken="I can't see through the camera — it didn't open for this process.",
        )
    try:
        deadline = time.monotonic() + timeout_s
        frame = None
        # First frames after open are often stale/black; pull a few.
        for _ in range(max(1, warmup_frames)):
            ok, f = cap.read()
            if ok and f is not None:
                frame = f
            if time.monotonic() > deadline:
                break
        if frame is None:
            raise CaptureError(
                f"Camera {camera_index} opened but returned no frame.",
                permission="camera",
                remedy="Check Camera permission for this process; another app may hold the device.",
                spoken="I can't see through the camera right now.",
            )
        if _is_blank(frame):
            raise CaptureError(
                f"Camera {camera_index} returned a blank frame (all one colour).",
                permission="camera",
                remedy="The lens may be covered, or the camera is denied and returning black.",
                spoken="The camera frame is blank — it may be covered or blocked.",
            )
        h, w = frame.shape[:2]
        df = DisplayFrame(index=0, image=frame, width=w, height=h, is_primary=True, label=f"camera {camera_index} ({w}x{h})")
        return CaptureResult(
            frames=[df],
            backend="opencv",
            verified=True,
            verified_by="frame-nonblank",
            verified_at=time.time(),
            source="camera",
        )
    finally:
        cap.release()


def _is_blank(frame: np.ndarray) -> bool:
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(g.std()) < 1.0
