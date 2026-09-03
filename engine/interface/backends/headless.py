"""The no-GPU backend — the humanoid endgame has no monitor, CI has no display,
and a server has neither. It renders state transitions as JSON lines on stderr,
same honesty rules, zero pixels.

It is also the reference for what a backend must not do: it cannot invent a
number because it is handed a `StateSnapshot` and nothing else.
"""

from __future__ import annotations

import json
import sys
import time

from engine.interface.state import StateSnapshot


class HeadlessBackend:
    name = "headless"

    def __init__(self, *, stream=sys.stderr) -> None:
        self._stream = stream
        self._last_state = None
        self._last_emit = 0.0

    def start(self) -> None:
        self._log({"event": "presence_start", "backend": self.name})

    def render(self, snap: StateSnapshot) -> None:
        now = time.monotonic()
        changed = snap.state != self._last_state
        # throttle: on change immediately, otherwise at most 2 Hz for amplitude
        if not changed and (now - self._last_emit) < 0.5:
            return
        self._last_state = snap.state
        self._last_emit = now
        self._log({
            "event": "state",
            "state": snap.state.value,
            "reactiveAmplitude": round(snap.reactive_amplitude, 3),
            "because": snap.because,
        })

    def show_hud(self, view: dict) -> None:
        self._log({"event": "hud_show", "kind": view.get("kind")})

    def hide_hud(self) -> None:
        self._log({"event": "hud_hide"})

    def stop(self) -> None:
        self._log({"event": "presence_stop"})

    def _log(self, obj: dict) -> None:
        print(json.dumps(obj), file=self._stream, flush=True)
