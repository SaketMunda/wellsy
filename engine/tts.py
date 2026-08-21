"""Local TTS for the engine's T3 loop.

**Deviation from the day10-prompt.md's "Kokoro/Piper" suggestion, recorded
here per house rules ("no dependency added without a line in decisions.md
saying why" — the inverse also applies to a dependency deliberately NOT
added):** this uses macOS's built-in `say`, not a Python neural-TTS
package. Reasoning: Day 10's hardest, most overdue requirement is "audio
confirmed audible on real speakers by a human" (nine days open) plus a real
measured wake/press-to-first-word latency. `say` is zero-dependency,
zero-download, on-device, and has been shipping speech on this exact
machine for years — it cannot fail to produce audio the way a freshly
wired ONNX/PyTorch TTS stack still might (see decisions.md D13's Kokoro
bundler saga for how much that risk is not hypothetical). It is not neural
and not expressive — a real quality regression from the browser build's
Kokoro-82M voice. `say` is also a subprocess, which happens to be exactly
what "stop must interrupt mid-word" needs (SIGTERM kills speech instantly;
an in-process neural TTS streaming to a sound device would need its own
interrupt plumbing). Piper (`pip install piper-tts`, real ONNX neural
voices, still fully local) is the documented upgrade path once voice
quality matters more than closing the audibility gap — decisions.md D39.
"""

from __future__ import annotations

import subprocess
import threading
import time

VOICE = "Samantha"


class SpeechHandle:
    """One in-flight `say` invocation. `stop()` is idempotent and safe to
    call from a different thread than the one that started speech — this is
    exactly the push-to-talk-interrupts-playback requirement from
    day10-prompt.md's feedback-trap section."""

    def __init__(self, proc: subprocess.Popen, text: str) -> None:
        self._proc = proc
        self.text = text
        self.started_at = time.monotonic()
        self._first_audio_at: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        self._proc.wait()

    def stop(self) -> None:
        with self._lock:
            if self._proc.poll() is None:
                self._proc.terminate()

    @property
    def speaking(self) -> bool:
        return self._proc.poll() is None


def speak(text: str, voice: str = VOICE) -> SpeechHandle:
    """Starts `say` immediately, non-blocking. `say` begins producing audio
    within a handful of ms of process start (no model load), so
    `started_at` doubles as a good first-audio proxy for the latency table
    — see day10-results.md row 2's breakdown."""
    proc = subprocess.Popen(
        ["say", "-v", voice, text],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return SpeechHandle(proc, text)
