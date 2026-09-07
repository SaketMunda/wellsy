"""The QObject the QML binds to. It holds *only* values handed to it by the
backend (which got them from `derive_state`). It has no clock, no RNG, no
amplitude of its own.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot


class Bridge(QObject):
    changed = Signal()
    hudChanged = Signal()

    def __init__(self, *, on_drag, on_persist, on_approval, on_escape, on_corner=None):
        super().__init__()
        self._state = "asleep"
        self._amp = 0.0
        self._because = "no wake"
        self._hud: dict = {}
        self._hud_visible = False
        self._show_because = False
        self._on_drag = on_drag
        self._on_persist = on_persist
        self._on_approval = on_approval
        self._on_escape = on_escape
        self._on_corner = on_corner

    # ---- called from Python (backend) ---- #
    def update(self, state: str, amplitude: float, because: str) -> None:
        self._state, self._amp, self._because = state, float(amplitude), because
        self.changed.emit()

    def showHud(self, view: dict) -> None:
        self._hud = dict(view or {})
        self._hud_visible = True
        self.hudChanged.emit()

    def hideHud(self) -> None:
        self._hud_visible = False
        self.hudChanged.emit()

    # ---- properties for QML ---- #
    def _get_state(self): return self._state
    def _get_amp(self): return self._amp
    def _get_because(self): return self._because
    def _get_hud(self): return self._hud
    def _get_hud_visible(self): return self._hud_visible
    def _get_show_because(self): return self._show_because

    state = Property(str, _get_state, notify=changed)
    reactiveAmplitude = Property(float, _get_amp, notify=changed)
    because = Property(str, _get_because, notify=changed)
    hud = Property("QVariant", _get_hud, notify=hudChanged)
    hudVisible = Property(bool, _get_hud_visible, notify=hudChanged)
    showBecause = Property(bool, _get_show_because, notify=changed)

    # ---- slots invoked from QML ---- #
    @Slot(float, float)
    def dragBy(self, dx: float, dy: float) -> None:
        self._on_drag(dx, dy)

    @Slot()
    def persistPosition(self) -> None:
        self._on_persist()

    @Slot(bool)
    def answerApproval(self, approved: bool) -> None:
        if self._on_approval:
            self._on_approval(approved)
        self.hideHud()

    @Slot()
    def escape(self) -> None:
        if self._on_escape:
            self._on_escape()
        self.hideHud()

    @Slot(str, result=bool)
    def moveToCorner(self, name: str) -> bool:
        """Snap the orb to a screen corner — the target for a 'move to the
        bottom-right' voice/text command. Returns True if `name` was understood."""
        return bool(self._on_corner and self._on_corner(name))
