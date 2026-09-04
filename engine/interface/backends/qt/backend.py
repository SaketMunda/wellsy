"""The Qt Quick Presence/HUD backend — GPU scene graph, in the engine's own
process, no IPC to the runtime (teardown D54).

Framework verified current before adoption (INVARIANTS #8): PySide6 / Qt
**6.11.2**, released 2026-08-18 (6.11.1 was 2026-05-13, 6.10.3 the prior line).
Verified 2026-09-03 against pypi.org/pypi/PySide6/json. What was rejected and
why is in `.claude/rebuild/step6-results.md`.

Import is lazy: `pip install wellsy` does not pull Qt. `pip install
wellsy[interface]` does. Headless paths never import this module.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from engine.interface.capability import PresenceCapability, probe
from engine.interface.state import StateSnapshot

_QML_DIR = Path(__file__).resolve().parent
_STATE_PATH = Path.home() / ".cache" / "wellsy" / "interface.json"

# how much of the grip / caption band sits below the square orb area
_GRIP_BAND = 40
_MARGIN = 24  # gap from the screen edge when snapped to a corner

CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right",
           "left", "right", "center")
_ALIASES = {
    "tl": "top-left", "tr": "top-right", "bl": "bottom-left", "br": "bottom-right",
    "topleft": "top-left", "topright": "top-right",
    "bottomleft": "bottom-left", "bottomright": "bottom-right",
    "left corner": "bottom-left", "right corner": "bottom-right",
    "lower-left": "bottom-left", "lower-right": "bottom-right",
    "upper-left": "top-left", "upper-right": "top-right",
    "middle": "center", "centre": "center",
}


def normalize_corner(name: str) -> str | None:
    if not name:
        return None
    raw = name.strip().lower()
    said_corner = "corner" in raw
    k = raw
    for junk in ("move ", "put ", "go ", "it ", "yourself ", "to ", "the ",
                 "please ", "over ", "into ", "bottom-most ", "top-most ",
                 " of the screen", " of screen", " corner", " side", "-hand"):
        k = k.replace(junk, "")
    k = k.strip().replace("_", "-").replace(" ", "-")
    while "--" in k:
        k = k.replace("--", "-")
    if k in CORNERS and not (said_corner and k in ("left", "right")):
        return k
    if k in _ALIASES:
        return _ALIASES[k]
    if k in ("top", "up"):
        return "top-right"
    if k in ("bottom", "down"):
        return "bottom-right"
    # "left/right corner" with no vertical hint -> the bottom corner (desktop-widget default)
    if said_corner and k == "left":
        return "bottom-left"
    if said_corner and k == "right":
        return "bottom-right"
    # tolerate reversed order: "right-bottom" -> "bottom-right"
    parts = set(k.split("-"))
    if parts <= {"top", "bottom", "left", "right"} and len(parts) == 2:
        vert = "top" if "top" in parts else "bottom"
        horiz = "left" if "left" in parts else "right"
        return f"{vert}-{horiz}"
    return None


def _load_state() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text())
    except Exception:
        return {}


def _save_state(**kw) -> None:
    """Persist window placement. A key set to None is removed (e.g. a manual
    drag clears any saved corner snap)."""
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        cur = _load_state()
        for k, v in kw.items():
            if v is None:
                cur.pop(k, None)
            else:
                cur[k] = v
        _STATE_PATH.write_text(json.dumps(cur))
    except Exception:
        pass


class QtPresenceBackend:
    name = "qt"

    def __init__(self, *, on_approval=None, on_escape=None, on_hotkey=None,
                 size: int | None = None, fraction: float | None = None,
                 corner: str | None = None):
        self.cap: PresenceCapability = probe()
        self._on_approval = on_approval
        self._on_escape = on_escape
        self._on_hotkey = on_hotkey
        self._app = None
        self._view = None
        self._bridge = None

        st = _load_state()
        env_size = os.environ.get("WELLSY_ORB_SIZE")
        # explicit size only (flag/env); the auto default is re-derived every
        # launch so it tracks a screen/display change and is never poisoned by a
        # stale persisted value.
        self._req_size = size or (int(env_size) if env_size else None)
        self._fraction = fraction or float(os.environ.get("WELLSY_ORB_FRACTION", 0) or 0) or 0.25
        self._corner = normalize_corner(corner or os.environ.get("WELLSY_ORB_CORNER", "")) \
            or st.get("corner")
        self._edge = 400  # resolved in start() from the screen

    # -- lifecycle --------------------------------------------------------- #

    def start(self) -> None:
        if self.cap.platform == "linux" and self.cap.session == "wayland" and not self.cap.degraded:
            from engine.interface.backends.qt import linux_layershell
            linux_layershell.init_before_qapplication()

        from PySide6.QtCore import Qt, QUrl
        from PySide6.QtGui import QColor, QGuiApplication
        from PySide6.QtQuick import QQuickView

        from engine.interface.backends.qt import pointcloud  # noqa: F401  (registers Wellsy.Orb)

        self._app = QGuiApplication.instance() or QGuiApplication(sys.argv or ["wellsy"])

        # orb edge ≈ 25% of the screen width by default (owner's ask), clamped so
        # it is neither a speck nor a takeover. Explicit --size / env wins.
        scr = self._app.primaryScreen()
        avail = scr.availableGeometry() if scr else None
        base = avail.width() if avail else 1440
        self._edge = int(self._req_size or max(300, min(720, round(base * self._fraction))))

        from engine.interface.backends.qt._bridge import Bridge
        self._bridge = Bridge(
            on_drag=self._drag, on_persist=self._persist,
            on_approval=self._on_approval, on_escape=self._on_escape,
            on_corner=self.move_to_corner,
        )

        view = QQuickView()
        view.setColor(QColor(0, 0, 0, 0))
        view.setDefaultAlphaBuffer(True)
        view.rootContext().setContextProperty("bridge", self._bridge)

        flags = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                 | Qt.NoDropShadowWindowHint)
        if self.cap.click_through:
            flags |= Qt.WindowTransparentForInput
        view.setFlags(flags)
        view.setResizeMode(QQuickView.SizeRootObjectToView)
        view.setSource(QUrl.fromLocalFile(str(_QML_DIR / "Presence.qml")))
        if view.status() == QQuickView.Error:
            errs = "; ".join(e.toString() for e in view.errors())
            raise RuntimeError(f"Presence.qml failed to load: {errs}")

        view.resize(self._edge, self._edge + _GRIP_BAND)
        self._view = view

        st = _load_state()
        if self._corner:
            self._place(self._corner)
        elif "x" in st and "y" in st:
            view.setPosition(int(st["x"]), int(st["y"]))
        else:
            self._place("bottom-right")

        view.show()
        self._apply_platform(view)

        if os.environ.get("WELLSY_ORB_PRINT_CAP") == "1":
            print(self.cap.summary(), file=sys.stderr)

    def _apply_platform(self, view) -> None:
        if self.cap.platform == "macos":
            from engine.interface.backends.qt import macos_panel
            ok = macos_panel.apply(int(view.winId()))
            if not ok:
                self.cap = self.cap.__class__(**{**self.cap.__dict__,
                                                 "all_spaces": False, "degraded": True,
                                                 "reason": "NSPanel shim unavailable (pyobjc missing) — "
                                                           "orb will drop on fullscreen/Space switch.",
                                                 "fallback": "install wellsy[interface] with pyobjc, or accept the drop."})
        elif self.cap.platform == "linux" and self.cap.session == "wayland" and not self.cap.degraded:
            from engine.interface.backends.qt import linux_layershell
            linux_layershell.apply(view)

    # -- placement ------------------------------------------------------- #

    def _place(self, corner: str) -> None:
        """Position the window against `corner` of the screen's available area."""
        if self._view is None or self._app is None:
            return
        scr = self._view.screen() or self._app.primaryScreen()
        g = scr.availableGeometry()
        w = self._view.width() or self._edge
        h = self._view.height() or (self._edge + _GRIP_BAND)
        m = _MARGIN
        xr = g.x() + g.width() - w - m
        yb = g.y() + g.height() - h - m
        xc = g.x() + (g.width() - w) // 2
        yc = g.y() + (g.height() - h) // 2
        pos = {
            "top-left": (g.x() + m, g.y() + m),
            "top-right": (xr, g.y() + m),
            "bottom-left": (g.x() + m, yb),
            "bottom-right": (xr, yb),
            "left": (g.x() + m, yc),
            "right": (xr, yc),
            "center": (xc, yc),
        }.get(corner, (xr, yb))
        self._view.setPosition(*pos)

    def move_to_corner(self, name: str) -> bool:
        """Public: snap the orb to a named corner (voice/text command target).
        Accepts 'left', 'right', 'top-left', 'bottom right', 'centre', … ."""
        c = normalize_corner(name)
        if c is None:
            return False
        self._corner = c
        self._place(c)
        p = self._view.position()
        _save_state(corner=c, x=p.x(), y=p.y())
        return True

    # -- state / hud --------------------------------------------------- #

    def render(self, snap: StateSnapshot) -> None:
        if self._bridge is not None:
            self._bridge.update(snap.state.value, snap.reactive_amplitude, snap.because)

    def show_hud(self, view: dict) -> None:
        if self._bridge is not None:
            self._bridge.showHud(view)

    def hide_hud(self) -> None:
        if self._bridge is not None:
            self._bridge.hideHud()

    def stop(self) -> None:
        if self._view is not None:
            from PySide6.QtCore import QUrl

            self._view.setSource(QUrl())
            self._view.close()
            self._view = None
        if self._app is not None:
            self._app.quit()

    def exec_(self) -> int:
        return int(self._app.exec())

    def process_events(self) -> None:
        if self._app is not None:
            self._app.processEvents()

    # -- drag / persist ---------------------------------------------- #

    def _drag(self, dx: float, dy: float) -> None:
        if self._view is not None:
            p = self._view.position()
            self._view.setPosition(p.x() + int(dx), p.y() + int(dy))

    def _persist(self) -> None:
        if self._view is not None:
            p = self._view.position()
            _save_state(x=p.x(), y=p.y(), corner=None)  # a manual drag clears the corner snap
