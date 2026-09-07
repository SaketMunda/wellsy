"""WELLSY's native interface — step 6.

Two modes, one process:

  * **Presence** — a borderless, click-through, always-on-top orb. The only
    thing on screen 99% of the time. Reacts to *measured* runtime signal.
  * **HUD** — panels that unfold from the orb when there is real content to
    show (the plan, an approval prompt, a captured frame, the audit trail).

Architecture (INVARIANTS #6 extended to pixels, #13, #14; teardown D54):

  runtime seams ─▶ SignalBus ─▶ derive_state() ─▶ PresenceBackend
   (voice observer,  (depth-1     (pure; measured-   (qt | headless;
    agent on_event,   latest-wins) only)              platform shims
    intent decision)                                  behind a seam)

The bus is the single source of animated truth. There is deliberately **no code
path** from a timer to a listening/speaking amplitude — see
`tests/test_interface_state.py`. The UI runs in the engine's own process; there
is no IPC to the runtime.
"""

from engine.interface.signals import Channel, SignalBus
from engine.interface.state import OrbState, StateSnapshot, derive_state
from engine.interface.taps import agent_event_sink, intent_decision_sink

__all__ = [
    "Channel", "SignalBus", "OrbState", "StateSnapshot", "derive_state",
    "agent_event_sink", "intent_decision_sink",
]
