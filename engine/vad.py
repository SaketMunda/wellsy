"""T0 for audio: "is anyone speaking" — the exact symmetry day10-prompt.md
calls out with vision's motion.py: no neural net, a ~ms-cost check that
gates whether anything more expensive (STT) runs at all. Never run STT on
silence.

An adaptive RMS-energy gate, not Silero VAD. webrtcvad (the other "small,
CPU, chunked" option the brief names) is unmaintained and its wheel imports
`pkg_resources`, which recent setuptools no longer ships on Python 3.13 —
confirmed broken in this environment, not assumed. Silero itself is a real
model with a real load cost; an energy gate is the same *shape* of solution
as motion.py (a cheap statistic against a floor, not a model) and needs no
extra weights or network fetch. Revisit if push-to-talk's fallback role
stops being sufficient and false-trigger rate on real background noise
turns out to matter more than this measures.
"""

from __future__ import annotations

import numpy as np

FRAME_MS = 30
SAMPLE_RATE = 16000
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)

# Multiplier above the rolling noise floor before a frame counts as speech.
# First-guess constant, same caveat as tracker.ts's alpha/tau values — not
# tuned against a real noise-floor distribution yet.
SPEECH_RATIO = 2.5
NOISE_FLOOR_DECAY = 0.98  # per-frame EMA toward the current frame's RMS when it's below the current floor


class EnergyVad:
    """Chunked, stateful. Feed it consecutive `FRAME_SAMPLES`-length int16
    frames; `is_speech` updates a rolling noise floor and reports whether
    the current frame is above it."""

    def __init__(self) -> None:
        self._floor = 50.0  # int16-scale RMS starting guess, adapts fast

    def is_speech(self, frame: np.ndarray) -> bool:
        rms = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)) + 1e-6)
        speech = rms > self._floor * SPEECH_RATIO
        if not speech:
            self._floor = self._floor * NOISE_FLOOR_DECAY + rms * (1 - NOISE_FLOOR_DECAY)
        return speech

    @property
    def floor(self) -> float:
        return self._floor
