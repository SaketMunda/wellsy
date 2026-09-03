"""The orb state machine — INVARIANTS #6, extended to pixels.

    > The interface renders measured state. It never animates on a timer.

`derive_state()` is a pure function of the `SignalBus` at an instant. Every
branch reads a channel that a real runtime seam pushed. There is no argument
for a synthetic waveform, no `random`, no phase accumulator. The one always-on
motion the orb has — a slow breathing envelope at rest — represents a real fact
("the pipeline is up") and carries **zero amplitude**; the reactive amplitude
that makes the orb pulse is `0.0` unless a fresh VAD or TTS sample exists.

State priority (highest first) — the ordering is itself a safety statement:

  AWAITING_APPROVAL  the gate is blocked on a human. Must stop and wait.
  REFUSING           a denial / failed verification just happened. Not an answer.
  SPEAKING           output PCM is flowing.
  LISTENING          live VAD frames are arriving.
  ACTING             a tool is executing.
  THINKING           the planner is running.
  IDLE               awake, nothing happening — "alive and breathing".
  ASLEEP             no wake.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from engine.interface.signals import SignalBus


class OrbState(str, Enum):
    ASLEEP = "asleep"
    IDLE = "idle"                       # awake, at rest
    LISTENING = "listening"
    THINKING = "thinking"
    ACTING = "acting"
    AWAITING_APPROVAL = "awaiting_approval"
    REFUSING = "refusing"
    SPEAKING = "speaking"


@dataclass(frozen=True)
class StateSnapshot:
    state: OrbState
    # The quantity the shader displaces the surface by. 0.0 for every
    # non-reactive state — a still mic is a still orb.
    reactive_amplitude: float
    # Why this state, in one phrase, from real signal — shown in the HUD, never
    # invented.
    because: str


def derive_state(bus: SignalBus, now: float | None = None) -> StateSnapshot:
    if now is None:
        now = bus.clock()

    approval = bus.channel("approval")
    if approval.latest() is not None and approval.value_or(None, now) == "pending":
        return StateSnapshot(OrbState.AWAITING_APPROVAL, 0.0,
                             "policy gate interrupt() is unanswered")

    refusal = bus.channel("refusal")
    if refusal.fresh(now):
        return StateSnapshot(OrbState.REFUSING, 0.0,
                             f"refusal: {refusal.latest().value}")

    tts = bus.channel("tts_amplitude")
    if tts.fresh(now):
        return StateSnapshot(OrbState.SPEAKING, _clamp(tts.value_or(0.0, now)),
                             "output PCM at the device")

    vad = bus.channel("vad_amplitude")
    if vad.fresh(now):
        return StateSnapshot(OrbState.LISTENING, _clamp(vad.value_or(0.0, now)),
                             "live VAD frames")

    phase = bus.channel("agent_phase").value_or("idle", now)
    if phase == "acting":
        return StateSnapshot(OrbState.ACTING, 0.0, "a tool is executing")
    if phase == "planning":
        return StateSnapshot(OrbState.THINKING, 0.0, "the planner is running")

    if bus.channel("wake").value_or(False, now):
        return StateSnapshot(OrbState.IDLE, 0.0, "awake, idle")

    return StateSnapshot(OrbState.ASLEEP, 0.0, "no wake")


def _clamp(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)
