"""Linux screen backend — Wayland (PipeWire via the desktop portal) with an
X11 path underneath. **Scaffold: unexecuted — no Linux machine is available
yet** (see `.claude/rebuild/step2` acceptance 6 for the same disclaimer on the
inference backends).

What this needs to run first time on the Jetson / Linux target (production
target #1, D51):

- Wayland: `xdg-desktop-portal` + a backend (`xdg-desktop-portal-gnome` /
  `-kde` / `-wlr`). Capture via the `org.freedesktop.portal.ScreenCast` API
  over D-Bus, then read frames from the returned PipeWire node (GStreamer
  `pipewiresrc`, or `python-pipewire`). The portal shows its own consent
  dialog — that dialog *is* the permission signal; a denied/cancelled request
  raises here with a remedy, it never returns a blank frame.
- X11: `mss` already works, or `python-xlib` + `XGetImage` on the root window.
  X11 has no capture-permission model, so `permission()` is GRANTED there and
  `verify.py` leans on the window-count and content signals instead.
- Multi-display: PipeWire exposes one node per output; enumerate and label by
  connector name (`DP-1`, `HDMI-A-1`).

Until a box exists, `available()` is False and the registry falls back to
`PortableScreenBackend` (mss), which covers X11 sessions today.
"""

from __future__ import annotations

from engine.capture.base import CaptureError, DisplayFrame, Permission, WindowInfo

_IMPORT_ERROR = "linux screen backend not implemented (no Linux target machine yet)"


class LinuxScreenBackend:
    name = "pipewire-portal"

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
            "Linux screen capture is not implemented yet; the portable mss "
            "backend covers X11 sessions in the meantime.",
            remedy="Run on X11 (mss works) or implement the PipeWire portal path.",
        )
