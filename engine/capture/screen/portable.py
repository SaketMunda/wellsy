"""Portable screen backend — `mss`. The fallback, explicitly not the fix.

`mss` is cross-platform, but on macOS it goes through Core Graphics and so
**inherits the identical TCC failure**: with Screen Recording denied it returns
the desktop composite (menu bar + wallpaper, zero windows) and never errors.
That is exactly why `verify.py` exists and is mandatory — this backend cannot
be trusted to refuse on its own.

On macOS this backend borrows the Quartz probes from `macos.py` (both live under
`screen/`, so invariant #14 is satisfied) so `verify` still gets a real
permission signal and window list. On Linux/Windows those come back UNKNOWN /
empty and `verify` falls back to the content + window-count signals.
"""

from __future__ import annotations

import sys

import numpy as np

from engine.capture.base import CaptureError, DisplayFrame, Permission, WindowInfo

try:
    import mss  # cross-platform
    import mss.tools  # noqa: F401

    _IMPORT_ERROR: str | None = None
except Exception as exc:  # pragma: no cover
    mss = None  # type: ignore
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

_IS_MAC = sys.platform == "darwin"


def _mac():
    if not _IS_MAC:
        return None
    try:
        from engine.capture.screen import macos

        return macos if macos.available() else None
    except Exception:
        return None


class PortableScreenBackend:
    name = "mss"

    def available(self) -> bool:
        return _IMPORT_ERROR is None

    def permission(self) -> Permission:
        m = _mac()
        if m is not None:
            return m.preflight()
        # X11 / PipeWire / Windows DWM: no synchronous per-process probe here.
        return Permission.UNKNOWN

    def request_permission(self) -> Permission:
        m = _mac()
        return m.request_access() if m is not None else Permission.UNKNOWN

    def list_windows(self) -> list[WindowInfo]:
        m = _mac()
        return m.list_windows() if m is not None else []

    def capture(self) -> list[DisplayFrame]:
        if not self.available():
            raise CaptureError(f"portable screen backend unavailable: {_IMPORT_ERROR}")
        frames: list[DisplayFrame] = []
        with mss.mss() as sct:
            monitors = sct.monitors[1:]  # [0] is the union of all monitors
            if not monitors:
                raise CaptureError("mss reported zero monitors")
            for i, mon in enumerate(monitors):
                shot = sct.grab(mon)
                bgra = np.asarray(shot, dtype=np.uint8)  # mss is BGRA
                bgr = bgra[:, :, :3].copy()
                frames.append(
                    DisplayFrame(
                        index=i,
                        image=bgr,
                        width=bgr.shape[1],
                        height=bgr.shape[0],
                        is_primary=(i == 0),
                    )
                )
        return frames
