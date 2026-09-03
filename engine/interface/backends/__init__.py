"""Runtime backend selection for the interface (INVARIANTS #14).

    select_backend()            # auto: qt if importable + a display, else headless
    select_backend("headless")  # force
    select_backend("qt")        # force (raises if PySide6 missing)
"""

from __future__ import annotations

import os

from engine.interface.backends.headless import HeadlessBackend


def _qt_importable() -> bool:
    try:
        import PySide6  # noqa: F401
        return True
    except Exception:
        return False


def _has_display() -> bool:
    if os.name == "nt":
        return True
    import platform
    if platform.system() == "Darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def select_backend(kind: str | None = None, **kw):
    kind = kind or os.environ.get("WELLSY_ORB_BACKEND") or "auto"

    if kind == "headless":
        return HeadlessBackend()
    if kind == "qt":
        from engine.interface.backends.qt.backend import QtPresenceBackend
        return QtPresenceBackend(**kw)

    # auto
    if _qt_importable() and _has_display():
        try:
            from engine.interface.backends.qt.backend import QtPresenceBackend
            return QtPresenceBackend(**kw)
        except Exception:
            return HeadlessBackend()
    return HeadlessBackend()
