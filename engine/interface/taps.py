"""Adapters that carry real runtime signal onto the SignalBus.

Nothing here generates a value; each tap forwards something the runtime already
produced:

  * `VoiceOrbObserver` — a Pipecat observer. VAD-gated mic RMS -> vad_amplitude
    (only between UserStarted/UserStopped, so it is genuinely VAD-gated); output
    PCM RMS -> tts_amplitude; wake latch from the intent gate.
  * `agent_event_sink(bus)` — pass as `run_agent(on_event=...)`. Maps the
    graph's lifecycle events to agent_phase / approval / refusal.
  * `intent_decision_sink(bus)` — pass as the voice pipeline `on_decision`.
"""

from __future__ import annotations

import math
from typing import Any

from engine.interface.signals import SignalBus


# --------------------------------------------------------------------------- #
# agent runtime (engine/agent/runner.py emits these dicts)                     #
# --------------------------------------------------------------------------- #

def agent_event_sink(bus: SignalBus):
    def sink(ev: dict[str, Any]) -> None:
        t = ev.get("type")
        if t in ("plan_start", "ack"):
            bus.set_agent_phase("planning")
        elif t == "approval_request":
            bus.set_approval_pending(True)
        elif t == "approval_answer":
            bus.set_approval_pending(False)
            ans = ev.get("answer") or {}
            approved = ans.get("approved") if isinstance(ans, dict) else bool(ans)
            if not approved:
                bus.mark_refusal("approval declined")
            bus.set_agent_phase("acting")
        elif t == "step_start":
            bus.set_agent_phase("acting")
        elif t == "step_denied":
            bus.mark_refusal(str(ev.get("reason", "tool denied")))
        elif t == "done":
            bus.set_agent_phase("idle")
    return sink


# --------------------------------------------------------------------------- #
# intent gate (voice pipeline on_decision(decision, transcript))              #
# --------------------------------------------------------------------------- #

def intent_decision_sink(bus: SignalBus):
    def sink(decision, transcript: str) -> None:
        action = getattr(decision, "action", str(decision))
        bus.set_intent(action)
        if action in ("wake",):
            bus.set_wake(True)
        elif action in ("sleep",):
            bus.set_wake(False)
        elif action == "refuse":
            bus.mark_refusal("intent refused")
    return sink


# --------------------------------------------------------------------------- #
# voice pipeline observer                                                      #
# --------------------------------------------------------------------------- #

def _pcm_rms(audio: bytes) -> float:
    """RMS of little-endian int16 PCM, normalised to 0..1. Pure measurement."""
    if not audio:
        return 0.0
    try:
        import numpy as np

        x = np.frombuffer(audio, dtype="<i2").astype("float32") / 32768.0
        if x.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(x * x)))
    except Exception:
        # numpy-free fallback
        n = len(audio) // 2
        if n == 0:
            return 0.0
        acc = 0.0
        for i in range(0, n * 2, 2):
            v = int.from_bytes(audio[i:i + 2], "little", signed=True) / 32768.0
            acc += v * v
        return math.sqrt(acc / n)


def build_voice_observer(bus: SignalBus):
    """Returns a Pipecat `BaseObserver` subclass instance, or raises
    ImportError if pipecat is not installed (headless test paths never call
    this)."""
    from pipecat.frames.frames import (
        BotStoppedSpeakingFrame,
        InputAudioRawFrame,
        InterruptionFrame,
        TTSAudioRawFrame,
        UserStartedSpeakingFrame,
        UserStoppedSpeakingFrame,
        VADUserStartedSpeakingFrame,
        VADUserStoppedSpeakingFrame,
    )
    from pipecat.observers.base_observer import BaseObserver, FramePushed
    from pipecat.processors.frame_processor import FrameDirection

    class VoiceOrbObserver(BaseObserver):
        def __init__(self) -> None:
            super().__init__()
            self._vad_open = False

        async def on_push_frame(self, data: "FramePushed") -> None:
            f = data.frame
            if isinstance(f, (VADUserStartedSpeakingFrame, UserStartedSpeakingFrame)):
                self._vad_open = True
                return
            if isinstance(f, (VADUserStoppedSpeakingFrame, UserStoppedSpeakingFrame)):
                self._vad_open = False
                bus.channel("vad_amplitude").clear()
                return
            if isinstance(f, InputAudioRawFrame) and self._vad_open:
                # measured mic energy, and only while VAD says speech is live
                bus.push_vad_amplitude(min(1.0, _pcm_rms(f.audio) * 4.0))
                return
            if isinstance(f, TTSAudioRawFrame) and data.direction == FrameDirection.DOWNSTREAM:
                bus.push_tts_amplitude(min(1.0, _pcm_rms(f.audio) * 4.0))
                return
            if isinstance(f, (BotStoppedSpeakingFrame, InterruptionFrame)):
                bus.channel("tts_amplitude").clear()
                return

    return VoiceOrbObserver()
