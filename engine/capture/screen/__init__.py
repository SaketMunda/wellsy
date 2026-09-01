"""Screen backend selection — the only module that decides which platform
path runs. Per invariant #14 the platform packages live in the sibling modules
here and nothing above `engine/capture/screen/` imports them.

Selection order (native first, portable mss as the tested fallback everywhere):

    macOS   -> ScreenCaptureKit   -> mss
    Linux   -> PipeWire portal *  -> mss   (* not implemented yet; mss covers X11)
    Windows -> Windows.Graphics.Capture *  -> mss   (* not implemented yet)

Override with `WELLSY_SCREEN_BACKEND={screencapturekit|mss|pipewire-portal|
windows-graphics-capture}`.
"""

from __future__ import annotations

import os
import sys

from engine.capture.base import ScreenBackend
from engine.capture.screen.portable import PortableScreenBackend

_ENV = "WELLSY_SCREEN_BACKEND"


def _native_for_platform() -> ScreenBackend | None:
    if sys.platform == "darwin":
        from engine.capture.screen.macos import MacOSScreenBackend

        return MacOSScreenBackend()
    if sys.platform.startswith("linux"):
        from engine.capture.screen.linux import LinuxScreenBackend

        return LinuxScreenBackend()
    if sys.platform.startswith("win"):
        from engine.capture.screen.windows import WindowsScreenBackend

        return WindowsScreenBackend()
    return None


def _by_name(name: str) -> ScreenBackend:
    name = name.strip().lower()
    if name in ("mss", "portable"):
        return PortableScreenBackend()
    if name in ("screencapturekit", "sck", "macos"):
        from engine.capture.screen.macos import MacOSScreenBackend

        return MacOSScreenBackend()
    if name in ("pipewire-portal", "linux"):
        from engine.capture.screen.linux import LinuxScreenBackend

        return LinuxScreenBackend()
    if name in ("windows-graphics-capture", "wgc", "windows"):
        from engine.capture.screen.windows import WindowsScreenBackend

        return WindowsScreenBackend()
    raise ValueError(f"unknown {_ENV}={name!r}")


def select_backend() -> ScreenBackend:
    override = os.environ.get(_ENV)
    if override:
        return _by_name(override)
    native = _native_for_platform()
    if native is not None and native.available():
        return native
    return PortableScreenBackend()


def all_candidates() -> list[ScreenBackend]:
    """Every backend that could run here, native first — for `wellsy doctor`."""
    out: list[ScreenBackend] = []
    native = _native_for_platform()
    if native is not None:
        out.append(native)
    out.append(PortableScreenBackend())
    return out
