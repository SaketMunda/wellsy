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
import sys
from pathlib import Path

from engine.interface.capability import PresenceCapability, probe
from engine.interface.state import StateSnapshot

_QML_DIR = Path(__file__).resolve().parent
_STATE_PATH = Path.home() / ".cache" / "wellsy" / "interface.json"


def _load_pos() -> tuple[int, int] | None:
    try:
        d = json.loads(_STATE_PATH.read_text())
        return int(d["x"]), int(d["y"])
    except Exception:
        return None


def _save_pos(x: int, y: int) -> None:
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps({"x": x, "y": y}))
    except Exception:
        pass


class QtPresenceBackend:
    name = "qt"

    def __init__(self, *, on_approval=None, on_escape=None, on_hotkey=None):
        self.cap: PresenceCapability = probe()
        self._on_approval = on_approval          # (approved: bool) -> None
        self._on_escape = on_escape              # () -> None  (deterministic stop)
        self._on_hotkey = on_hotkey
        self._app = None
        self._view = None
        self._bridge = None

    # -- lifecycle --------------------------------------------------------- #

    def start(self) -> None:
        import os

        if self.cap.platform == "linux" and self.cap.session == "wayland" and not self.cap.degraded:
            from engine.interface.backends.qt import linux_layershell
            linux_layershell.init_before_qapplication()

        from PySide6.QtCore import Qt, QUrl
        from PySide6.QtGui import QColor, QGuiApplication
        from PySide6.QtQuick import QQuickView

        # registers the Wellsy.Orb.PointCloud QML type (the orb's particle item)
        from engine.interface.backends.qt import pointcloud  # noqa: F401

        self._app = QGuiApplication.instance() or QGuiApplication(sys.argv or ["wellsy"])

        from engine.interface.backends.qt._bridge import Bridge
        self._bridge = Bridge(
            on_drag=self._drag, on_persist=self._persist,
            on_approval=self._on_approval, on_escape=self._on_escape,
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

        pos = _load_pos()
        if pos:
            view.setPosition(*pos)
        view.resize(160, 200)
        view.show()

        self._apply_platform(view)
        self._view = view

        if os.environ.get("WELLSY_ORB_PRINT_CAP") == "1":
            print(self.cap.summary(), file=sys.stderr)

    def _apply_platform(self, view) -> None:
        if self.cap.platform == "macos":
            from engine.interface.backends.qt import macos_panel
            ok = macos_panel.apply(int(view.winId()))
            if not ok:
                # honest: we could not get panel semantics
                self.cap = self.cap.__class__(**{**self.cap.__dict__,
                                                 "all_spaces": False, "degraded": True,
                                                 "reason": "NSPanel shim unavailable (pyobjc missing) — "
                                                           "orb will drop on fullscreen/Space switch.",
                                                 "fallback": "install wellsy[interface] with pyobjc, or accept the drop."})
        elif self.cap.platform == "linux" and self.cap.session == "wayland" and not self.cap.degraded:
            from engine.interface.backends.qt import linux_layershell
            linux_layershell.apply(view)

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
            # drop the QML source first so bindings unwind before `bridge` /
            # the context go away (avoids teardown "property of null" noise)
            from PySide6.QtCore import QUrl

            self._view.setSource(QUrl())
            self._view.close()
            self._view = None
        if self._app is not None:
            self._app.quit()

    # backend owns the loop for Qt (main thread requirement)
    def exec_(self) -> int:
        return int(self._app.exec())

    def process_events(self) -> None:
        if self._app is not None:
            self._app.processEvents()

    # -- drag / persist -------------------------------------------------- #

    def _drag(self, dx: float, dy: float) -> None:
        if self._view is not None:
            p = self._view.position()
            self._view.setPosition(p.x() + int(dx), p.y() + int(dy))

    def _persist(self) -> None:
        if self._view is not None:
            p = self._view.position()
            _save_pos(p.x(), p.y())
