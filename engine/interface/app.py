"""Wire the SignalBus to a backend and run the Presence loop.

    bus = SignalBus()
    # feed it from real seams:
    #   voice:  worker observers += [build_voice_observer(bus)]
    #           pipeline on_decision = intent_decision_sink(bus)
    #   agent:  run_agent(..., on_event=agent_event_sink(bus))
    run_presence(bus)

The loop is pure: every frame it calls `derive_state(bus)` and hands the
snapshot to the backend. It holds no animation state.
"""

from __future__ import annotations

import time

from engine.interface.backends import select_backend
from engine.interface.signals import SignalBus
from engine.interface.state import derive_state


def run_presence(bus: SignalBus, *, backend=None, hz: int = 60, stop=None, **backend_kw):
    backend = backend or select_backend(**backend_kw)
    backend.start()

    def tick() -> None:
        backend.render(derive_state(bus))

    # Qt backend owns the main-thread event loop; drive `tick` from a QTimer.
    if hasattr(backend, "exec_"):
        from PySide6.QtCore import QTimer

        timer = QTimer()
        timer.setInterval(max(1, int(1000 / hz)))
        timer.timeout.connect(tick)
        timer.start()
        try:
            return backend.exec_()
        finally:
            backend.stop()

    # headless / server loop
    period = 1.0 / hz
    try:
        while stop is None or not stop.is_set():
            tick()
            time.sleep(period)
    except KeyboardInterrupt:
        pass
    finally:
        backend.stop()
    return 0


# --------------------------------------------------------------------------- #
# demo state walk — for `wellsy orb --demo`. It steps through the NON-reactive #
# states only. It deliberately CANNOT drive listening/speaking: those need a   #
# live VAD / PCM frame, and there is no bus method that fakes one. That is the #
# honesty invariant, visible even in the demo.                                 #
# --------------------------------------------------------------------------- #

_DEMO_WALK = [
    ("wake", True), ("phase", "planning"), ("phase", "acting"),
    ("approval", True), ("approval", False), ("refusal", "demo denial"),
    ("phase", "idle"), ("wake", False),
]


def demo_drive(bus: SignalBus, *, dwell: float = 1.6, stop=None) -> None:
    import itertools

    for kind, val in itertools.cycle(_DEMO_WALK):
        if stop is not None and stop.is_set():
            return
        if kind == "wake":
            bus.set_wake(val)
        elif kind == "phase":
            bus.set_agent_phase(val)
        elif kind == "approval":
            bus.set_approval_pending(val)
        elif kind == "refusal":
            bus.mark_refusal(val)
        time.sleep(dwell)
