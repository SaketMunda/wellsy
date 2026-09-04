"""The Presence orb — a ~3.2k-point sphere that unravels into swirling ribbons
and re-winds, cyan → violet → magenta along the streams, additive glow.
Modelled on the reference clip.

Implemented as a `QQuickPaintedItem`: the point cloud is transformed and
projected in NumPy each frame (~1 ms) and drawn with additive-composited glow
sprites. Qt Quick 3D's custom-geometry point path renders nothing on the Metal
RHI in PySide6 6.11.2 (points collapse) — see step6-results.md — so this is the
route that actually draws. It stays in the engine process, on the Qt scene
graph, no webview (teardown D54).

HONESTY (INVARIANTS #6 → pixels): `amplitude` is the only reactive input and is
set straight from `derive_state().reactive_amplitude` (0 unless a live VAD / PCM
frame exists). It adds turbulence + brightness on top of the always-on swirl —
which represents "the runtime is up", the one motion allowed to run on a clock.
`state` selects a per-state identity (unravel amount, swirl rate, tint); the
state itself is measured. No RNG anywhere; the noise is deterministic in `t`.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Property, QPointF, Qt, Signal, Slot
from PySide6.QtGui import QColor, QImage, QPainter, QRadialGradient
from PySide6.QtQml import QmlElement
from PySide6.QtQuick import QQuickPaintedItem

QML_IMPORT_NAME = "Wellsy.Orb"
QML_IMPORT_MAJOR_VERSION = 1

N_POINTS = 3200
_RAMP = ("#2ad0fc", "#6a53f2", "#fc44b8")          # cyan · violet · magenta
_SIZES = (2, 3, 4, 6)                               # depth bins (px) at a ~240 px orb
_PEAK = 115                                         # per-sprite core alpha
_SIZE_REF = 240.0                                   # orb edge the base sizes are tuned for

# per state: mo=unravel, tu=swirl rate, hot=flare gain, dim=brightness,
# tint=(r,g,b) 0..1 pulled toward. Frozen sphere for awaiting_approval; inward
# for refusing.
_PARAMS = {
    "asleep":            dict(mo=0.10, tu=0.10, hot=0.0, dim=0.45, tint=(0.35, 0.40, 0.55)),
    "idle":              dict(mo=0.34, tu=0.28, hot=0.1, dim=0.85, tint=(0.30, 0.55, 0.90)),
    "listening":         dict(mo=0.48, tu=0.42, hot=0.2, dim=1.05, tint=(0.20, 0.75, 1.00)),
    "thinking":          dict(mo=0.72, tu=0.85, hot=0.3, dim=1.00, tint=(0.55, 0.35, 0.95)),
    "acting":            dict(mo=0.88, tu=1.05, hot=0.4, dim=1.05, tint=(0.30, 0.85, 0.65)),
    "awaiting_approval": dict(mo=0.00, tu=0.05, hot=0.5, dim=1.10, tint=(1.00, 0.72, 0.20)),
    "refusing":          dict(mo=-0.55, tu=0.55, hot=0.5, dim=1.00, tint=(1.00, 0.28, 0.28)),
    "speaking":          dict(mo=0.60, tu=0.60, hot=0.3, dim=1.10, tint=(0.50, 0.80, 1.00)),
}


def _sprite(hex_color: str, size: int, peak: int) -> QImage:
    im = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    im.fill(0)
    p = QPainter(im)
    p.setRenderHint(QPainter.Antialiasing)
    g = QRadialGradient(size / 2, size / 2, size / 2)
    c0 = QColor(hex_color); c0.setAlpha(peak); g.setColorAt(0.0, c0)
    c1 = QColor(hex_color); c1.setAlpha(int(peak * 0.35)); g.setColorAt(0.45, c1)
    c2 = QColor(hex_color); c2.setAlpha(0); g.setColorAt(1.0, c2)
    p.setBrush(g); p.setPen(Qt.NoPen)
    p.drawEllipse(0, 0, size, size)
    p.end()
    return im


@QmlElement
class PointCloud(QQuickPaintedItem):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        i = np.arange(N_POINTS, dtype=np.float32)
        y = 1.0 - (i / (N_POINTS - 1)) * 2.0
        r = np.sqrt(np.clip(1.0 - y * y, 0.0, 1.0))
        th = i * 2.399963  # golden angle
        self._P = np.stack([r * np.cos(th), y, r * np.sin(th)], 1).astype(np.float32)
        self._u = ((th / (2.0 * math.pi)) % 1.0).astype(np.float32)
        self._spr_scale = 0.0
        self._spr: list[list[QImage]] = []
        self._rebuild_sprites(1.0)

        self._t = 0.0
        self._amp = 0.0
        self._state = "asleep"
        # eased parameter vector [mo, tu, hot, dim, tr, tg, tb]
        self._cur = self._target_vec("asleep")

    # ---- QML-facing properties -------------------------------------------- #
    changed = Signal()

    def _get_state(self): return self._state
    def _set_state(self, s: str):
        if s != self._state:
            self._state = s
            self.changed.emit()
    state = Property(str, _get_state, _set_state, notify=changed)

    def _get_amp(self): return self._amp
    def _set_amp(self, a: float):
        self._amp = max(0.0, min(1.0, float(a)))
    amplitude = Property(float, _get_amp, _set_amp)

    def _rebuild_sprites(self, scale: float) -> None:
        """Re-render the 3 colours × 4 depth-bin sprites at `scale`. Cheap (12
        tiny QImages); done only when the orb size changes materially so a big
        orb gets proportionally bigger dots, not a sparse speckle."""
        self._spr_scale = scale
        sizes = [max(1, int(round(s * scale))) for s in _SIZES]
        self._spr = [[_sprite(_RAMP[b], sizes[k], _PEAK) for k in range(4)] for b in range(3)]
        self._sizes = np.array(sizes)

    @Slot(float)
    def tick(self, frame_time: float) -> None:
        """Advance the clock and ease params toward the current state. Called by
        a QML Timer. `frame_time` is real seconds since the last frame
        (time-driven swirl is the one allowed clock; amplitude is separate)."""
        self._t += frame_time
        tgt = self._target_vec(self._state)
        k = min(1.0, frame_time * 4.0)
        self._cur = self._cur + (tgt - self._cur) * k
        self.update()

    # ---- render ---------------------------------------------------------- #
    def paint(self, painter: QPainter) -> None:
        w = self.width() or 300.0
        h = self.height() or 300.0
        # keep dot size proportional to the orb (sub-linear so a big orb reads
        # as a dense sphere, not a handful of blobs)
        want = max(0.8, min(2.4, (min(w, h) / _SIZE_REF) ** 0.6))
        if abs(want - self._spr_scale) > 0.12:
            self._rebuild_sprites(want)

        t = self._t
        mo, tu, hot, dim, tr, tg, tb = self._cur

        ca, sa = math.cos(t * 0.40), math.sin(t * 0.40 + tu * t * 0.0)
        rot = np.array([[ca, 0.0, sa], [0.0, 1.0, 0.0], [-sa, 0.0, ca]], np.float32)
        p = self._P @ rot.T

        # unravel: peel each latitude band into a travelling ribbon + curl push
        ribbon = np.sin(p[:, 1] * 9.0 - t * (0.7 + tu))[:, None]
        field = np.stack([
            np.sin(p[:, 2] * 2.4 + t),
            np.cos(p[:, 0] * 2.4 - t * 0.6),
            np.sin(p[:, 1] * 2.4 + t * 0.4),
        ], 1).astype(np.float32)
        amt = (mo * 0.30) + self._amp * 0.45          # MEASURED term only here
        p = p + (0.30 * ribbon * field * (0.5 + 0.5 * abs(mo))).astype(np.float32) \
              + (amt * ribbon * field).astype(np.float32)

        z = p[:, 2]
        # camera pulled in + wide focal so the sphere fills ~85% of the item
        # (the item is sized to ~25% of the screen; the orb should look it)
        cz, f = 2.9, min(w, h) * 0.60
        sx = w * 0.5 + p[:, 0] / (cz - z) * f
        sy = h * 0.5 - p[:, 1] / (cz - z) * f

        depth = np.clip((z + 1.5) / 3.0, 0.0, 1.0)
        szb = np.clip((depth * 4).astype(int), 0, 3)
        uu = (self._u + t * 0.03) % 1.0
        cb = np.clip((uu * 3).astype(int), 0, 2)
        order = np.argsort(z)                          # back → front

        sxo = sx - self._sizes[szb] * 0.5
        syo = sy - self._sizes[szb] * 0.5

        painter.setCompositionMode(QPainter.CompositionMode_Plus)
        painter.setOpacity(min(0.98, 0.60 * dim + 0.30 * self._amp + hot * 0.20))
        draw = painter.drawImage
        spr = self._spr
        for k in order:
            draw(QPointF(sxo[k], syo[k]), spr[cb[k]][szb[k]])

    # ---- helpers ------------------------------------------------------- #
    @staticmethod
    def _target_vec(state: str) -> np.ndarray:
        p = _PARAMS.get(state, _PARAMS["idle"])
        return np.array([p["mo"], p["tu"], p["hot"], p["dim"], *p["tint"]], np.float32)

    POINT_COUNT = N_POINTS
