"""Capture layer — the single entry point perception/voice code uses to get
pixels for a model.

    from engine.capture import capture_screen, capture_camera

`capture_screen()` captures every attached display through the platform's
native backend (mss fallback), then runs the degenerate-capture verification
in `verify.py`. It **raises `CaptureError` rather than return an unverified
frame** — the wallpaper defect (`stack-teardown.md` §1) is a `raise`, never a
silent bad answer. Screen capture is on-demand only, exactly once per routed
question — there is deliberately no continuous-capture API here (a privacy
property of the product).
"""

from __future__ import annotations

from engine.capture.base import (
    CaptureError,
    CaptureResult,
    DisplayFrame,
    Permission,
    ScreenBackend,
    WindowInfo,
)
from engine.capture.camera import capture_camera
from engine.capture.screen import select_backend
from engine.capture.verify import verify_screen

__all__ = [
    "CaptureError",
    "CaptureResult",
    "DisplayFrame",
    "Permission",
    "ScreenBackend",
    "WindowInfo",
    "capture_camera",
    "capture_screen",
    "select_backend",
    "verify_screen",
]


def capture_screen() -> CaptureResult:
    """Capture and verify every display. Raises `CaptureError` (with a spoken
    remedy) if the capture cannot be confirmed non-degenerate."""
    backend = select_backend()
    frames = backend.capture()  # native backends raise here on denied permission
    return verify_screen(frames, backend)
