"""Linux/Wayland Presence via wlr-layer-shell (LayerShellQt) — the platform
backend for KWin / sway / Hyprland. GNOME/mutter does not implement
layer-shell; `capability.probe()` detects that and the app reports it rather
than rendering an orb that sinks. This file is in a sanctioned backend dir.
"""

from __future__ import annotations


def available() -> bool:
    try:
        import LayerShellQt  # noqa: F401
        return True
    except Exception:
        return False


def apply(window) -> bool:
    """Put `window` (a QWindow) on the overlay layer: above normal windows, no
    keyboard focus, zero exclusive zone, anchored so it does not reserve space.
    Returns False if LayerShellQt is missing."""
    try:
        from LayerShellQt import Window as LSWindow
    except Exception:
        return False

    ls = LSWindow.get(window)
    ls.setLayer(LSWindow.LayerOverlay)
    ls.setKeyboardInteractivity(LSWindow.KeyboardInteractivityNone)
    ls.setExclusiveZone(0)
    ls.setScope("wellsy-presence")
    # anchor to a corner without stretching -> a small floating surface
    ls.setAnchors(LSWindow.AnchorTop | LSWindow.AnchorRight)
    return True


def init_before_qapplication() -> None:
    """LayerShellQt must be initialised before the QGuiApplication is created."""
    try:
        from LayerShellQt import Shell

        Shell.useLayerShell()
    except Exception:
        pass
