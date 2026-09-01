"""Windows screen backend — Windows.Graphics.Capture. **Scaffold: unexecuted —
no Windows machine is available yet.**

What this needs to run first time on Windows:

- `Windows.Graphics.Capture` via `winrt` (`winsdk` / `pywinrt`):
  `GraphicsCaptureItem.TryCreateFromMonitor` per monitor, a `Direct3D11`
  capture frame pool, one `TryGetNextFrame`, then copy the surface to a CPU
  bitmap. `windows-capture` on PyPI wraps this if a dependency is acceptable.
- Windows has no per-app screen-capture consent prompt (any process can
  capture the desktop), so `permission()` is GRANTED and `verify.py` relies on
  the window-count and content signals. The one caveat is the yellow capture
  border WGC draws by default — disable it with
  `IsBorderRequired = false` (needs Windows 11 build 22621+).
- Multi-display: enumerate monitors with `EnumDisplayMonitors`; label by
  device name and mark the one with `MONITORINFOF_PRIMARY` as primary.
- DXcam is faster but is **banned from the core by invariant #14** (it is a
  single-vendor, Windows-only path with no portable fallback); it could only
  ever be an opt-in accelerated backend, never the interface.

Until a box exists, `available()` is False and the registry falls back to
`PortableScreenBackend` (mss), which uses the Windows DWM path today.
"""

from __future__ import annotations

from engine.capture.base import CaptureError, DisplayFrame, Permission, WindowInfo

_IMPORT_ERROR = "windows screen backend not implemented (no Windows target machine yet)"


class WindowsScreenBackend:
    name = "windows-graphics-capture"

    def available(self) -> bool:
        return False

    def permission(self) -> Permission:
        return Permission.UNKNOWN

    def request_permission(self) -> Permission:
        return Permission.UNKNOWN

    def list_windows(self) -> list[WindowInfo]:
        return []

    def capture(self) -> list[DisplayFrame]:
        raise CaptureError(
            "Windows screen capture is not implemented yet; the portable mss "
            "backend covers Windows in the meantime.",
            remedy="Implement the Windows.Graphics.Capture path.",
        )
