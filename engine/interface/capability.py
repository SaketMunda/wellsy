"""Honest capability probing for Presence mode (INVARIANTS #13: a probe reported
honestly is acceptable; a silent degradation is not).

The hard case is GNOME/Wayland: `xdg-shell` gives an app no control over its own
toplevel placement, and mutter does not implement `wlr-layer-shell`. So on that
combination the orb cannot be truly unmanaged-always-on-top. We detect it and
say so, rather than render an orb that sinks behind other windows.
"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class PresenceCapability:
    platform: str                # "macos" | "linux" | "windows"
    session: str                 # "quartz" | "wayland" | "x11" | "win32" | "unknown"
    compositor: str | None       # best-effort, linux only
    always_on_top: bool          # can we stay above other windows reliably
    click_through: bool          # can input pass through
    unmanaged: bool              # no titlebar / taskbar / dock entry
    all_spaces: bool             # visible across Spaces / virtual desktops / fullscreen
    degraded: bool               # something below full Presence — must be surfaced
    reason: str                  # human-readable explanation of any gap
    fallback: str                # what the app will do instead

    def summary(self) -> str:
        head = "Presence: full" if not self.degraded else "Presence: DEGRADED"
        return (f"{head}  [{self.platform}/{self.session}"
                + (f", {self.compositor}" if self.compositor else "")
                + f"]\n  always-on-top={self.always_on_top} click-through={self.click_through} "
                f"unmanaged={self.unmanaged} all-spaces={self.all_spaces}\n  {self.reason}"
                + (f"\n  fallback: {self.fallback}" if self.degraded else ""))


def probe() -> PresenceCapability:
    sysname = platform.system()
    if sysname == "Darwin":
        return _macos()
    if sysname == "Windows":
        return _windows()
    return _linux()


def _macos() -> PresenceCapability:
    # Qt Tool|StaysOnTop|TranslucentBackground|TransparentForInput gets most of
    # the way; the Spaces / fullscreen-auxiliary behaviour needs the NSPanel
    # shim (backends/qt/macos_panel.py). Both are expected present on a normal
    # desktop session.
    return PresenceCapability(
        platform="macos", session="quartz", compositor=None,
        always_on_top=True, click_through=True, unmanaged=True, all_spaces=True,
        degraded=False,
        reason="NSPanel .floating level + canJoinAllSpaces|fullScreenAuxiliary via the macOS shim.",
        fallback="",
    )


def _windows() -> PresenceCapability:
    return PresenceCapability(
        platform="windows", session="win32", compositor=None,
        always_on_top=True, click_through=True, unmanaged=True, all_spaces=True,
        degraded=False,
        reason="WS_EX_LAYERED|WS_EX_TRANSPARENT|WS_EX_TOOLWINDOW, topmost. "
               "Implemented; on-device execution may be deferred (step6-results.md).",
        fallback="",
    )


def _linux() -> PresenceCapability:
    session = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
    wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or session == "wayland"
    x11 = bool(os.environ.get("DISPLAY")) and not wayland
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "").lower()
    compositor = desktop or None

    if x11:
        return PresenceCapability(
            platform="linux", session="x11", compositor=compositor,
            always_on_top=True, click_through=True, unmanaged=True, all_spaces=True,
            degraded=False,
            reason="X11: override-redirect / _NET_WM_STATE_ABOVE + input shape. Full Presence.",
            fallback="",
        )

    if wayland:
        is_gnome = "gnome" in desktop or "mutter" in desktop
        has_layershell = _layershell_available()
        if is_gnome or not has_layershell:
            why = ("GNOME/mutter does not implement wlr-layer-shell, and xdg-shell "
                   "gives no toplevel placement control"
                   if is_gnome else
                   "LayerShellQt / wlr-layer-shell not available on this compositor")
            return PresenceCapability(
                platform="linux", session="wayland", compositor=compositor,
                always_on_top=False, click_through=False, unmanaged=False, all_spaces=False,
                degraded=True,
                reason=f"Presence cannot be unmanaged-always-on-top here: {why}.",
                fallback="run an X11 session for full Presence, or accept a normal "
                         "managed always-visible window (no click-through, may lose focus stacking).",
            )
        return PresenceCapability(
            platform="linux", session="wayland", compositor=compositor,
            always_on_top=True, click_through=True, unmanaged=True, all_spaces=True,
            degraded=False,
            reason="wlr-layer-shell via LayerShellQt: overlay layer, no keyboard focus, "
                   "exclusive-zone 0. Full Presence on KWin/sway/Hyprland.",
            fallback="",
        )

    return PresenceCapability(
        platform="linux", session="unknown", compositor=compositor,
        always_on_top=False, click_through=False, unmanaged=False, all_spaces=False,
        degraded=True,
        reason="No X11 DISPLAY and no WAYLAND_DISPLAY — headless or unrecognised session.",
        fallback="headless backend (state to stdout); no orb.",
    )


def _layershell_available() -> bool:
    try:
        import LayerShellQt  # noqa: F401
        return True
    except Exception:
        # the Qt plugin can also be present without the python shim
        return shutil.which("qt6-layer-shell") is not None
