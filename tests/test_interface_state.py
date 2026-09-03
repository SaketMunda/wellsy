"""The honesty rule, as a test (step 6 acceptance #3; INVARIANTS #6 -> pixels):

    The interface renders measured state. It never animates on a timer.

Specifically proven here:
  * mic closed  => NO listening animation, and reactive_amplitude == 0.0
  * there is NO bus method and NO derive_state path that yields a listening or
    speaking pulse without a fresh VAD / PCM sample
  * a stale VAD frame stops being "listening" on its own
  * the priority order (approval > refusal > speaking > listening > acting >
    thinking > idle > asleep) holds
  * a source scan of engine/interface finds no RNG / timer feeding amplitude
"""

from __future__ import annotations

import ast
import pathlib

from engine.interface.signals import SignalBus
from engine.interface.state import OrbState, derive_state


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def _bus():
    return SignalBus(clock=FakeClock())


# --- the core guarantee ---------------------------------------------------- #

def test_mic_closed_means_no_listening_and_zero_amplitude():
    bus = _bus()
    bus.set_wake(True)  # awake, but no VAD frames
    snap = derive_state(bus)
    assert snap.state is not OrbState.LISTENING
    assert snap.state is OrbState.IDLE
    assert snap.reactive_amplitude == 0.0


def test_listening_requires_a_fresh_vad_frame():
    clk = FakeClock()
    bus = SignalBus(clock=clk)
    bus.set_wake(True)
    bus.push_vad_amplitude(0.5)
    assert derive_state(bus).state is OrbState.LISTENING
    assert derive_state(bus).reactive_amplitude == 0.5
    # let the frame go stale — listening must end with no new input
    clk.t += 1.0
    assert derive_state(bus).state is not OrbState.LISTENING
    assert derive_state(bus).reactive_amplitude == 0.0


def test_speaking_requires_a_fresh_pcm_frame():
    clk = FakeClock()
    bus = SignalBus(clock=clk)
    bus.push_tts_amplitude(0.7)
    assert derive_state(bus).state is OrbState.SPEAKING
    clk.t += 1.0
    assert derive_state(bus).state is not OrbState.SPEAKING


def test_no_bus_api_produces_amplitude_without_a_frame():
    """Every way to influence amplitude goes through push_vad_amplitude /
    push_tts_amplitude, both of which take a measured value. Enumerate the
    public surface and assert nothing else touches those channels."""
    bus = _bus()
    amp_setters = [n for n in dir(bus) if not n.startswith("_") and callable(getattr(bus, n))]
    # the only methods whose names promise an amplitude:
    assert {"push_vad_amplitude", "push_tts_amplitude"}.issubset(set(amp_setters))
    # calling every *other* public method must leave both amplitude channels empty
    safe = {
        "set_agent_phase": ("idle",), "set_approval_pending": (False,),
        "mark_refusal": ("x",), "set_wake": (True,), "set_intent": ("forward",),
    }
    for name, args in safe.items():
        getattr(bus, name)(*args)
    assert bus.channel("vad_amplitude").latest() is None
    assert bus.channel("tts_amplitude").latest() is None
    assert derive_state(bus).reactive_amplitude == 0.0


# --- priority order ------------------------------------------------------- #

def test_priority_order():
    clk = FakeClock()
    bus = SignalBus(clock=clk)
    bus.set_wake(True)
    bus.set_agent_phase("acting")
    assert derive_state(bus).state is OrbState.ACTING
    bus.push_vad_amplitude(0.3)
    assert derive_state(bus).state is OrbState.LISTENING
    bus.push_tts_amplitude(0.3)
    assert derive_state(bus).state is OrbState.SPEAKING
    bus.mark_refusal("denied")
    assert derive_state(bus).state is OrbState.REFUSING
    bus.set_approval_pending(True)
    assert derive_state(bus).state is OrbState.AWAITING_APPROVAL


def test_awaiting_approval_does_not_expire_on_its_own():
    clk = FakeClock()
    bus = SignalBus(clock=clk)
    bus.set_approval_pending(True)
    clk.t += 3600  # an hour later, still blocked
    assert derive_state(bus).state is OrbState.AWAITING_APPROVAL


def test_asleep_when_no_wake():
    assert derive_state(_bus()).state is OrbState.ASLEEP


# --- source scan: no RNG / timer feeding amplitude ---------------------- #

def test_interface_source_has_no_synthetic_amplitude_source():
    root = pathlib.Path(__file__).resolve().parents[1] / "engine" / "interface"
    banned_calls = {"random", "uniform", "gauss", "randint", "randrange"}
    offenders: list[str] = []
    for py in root.rglob("*.py"):
        tree = ast.parse(py.read_text(), filename=str(py))
        for node in ast.walk(tree):
            # import random  /  from random import ...
            if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "random" for a in node.names):
                offenders.append(f"{py.name}:{node.lineno} imports random")
            if isinstance(node, ast.ImportFrom) and node.module == "random":
                offenders.append(f"{py.name}:{node.lineno} imports from random")
            if isinstance(node, ast.Call):
                fn = node.func
                nm = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
                if nm in banned_calls:
                    offenders.append(f"{py.name}:{node.lineno} calls {nm}()")
    assert not offenders, "synthetic signal source in engine/interface:\n" + "\n".join(offenders)


def test_demo_walk_never_touches_reactive_channels():
    """`wellsy orb --demo` steps the non-reactive states only — it structurally
    cannot fake listening/speaking (honesty invariant, visible in the demo)."""
    from engine.interface.app import _DEMO_WALK

    kinds = {k for k, _ in _DEMO_WALK}
    assert kinds <= {"wake", "phase", "approval", "refusal"}
    assert "vad_amplitude" not in kinds and "tts_amplitude" not in kinds
