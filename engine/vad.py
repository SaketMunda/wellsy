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

# Real bug, found from a live log: the floor above only ever adapted on
# frames classified as *not* speech. `_floor` starts at a hardcoded 50.0 --
# if a mic's real ambient RMS is above `50.0 * SPEECH_RATIO` from frame one
# (a hotter input gain, room noise, fan noise -- never measured against
# this constant), every frame reads as speech forever, and since only a
# non-speech frame can correct the floor, it never gets the chance to: a
# permanent lockout for the rest of the process, not a transient
# misfire. The live symptom was "speech detected but transcribed nothing"
# repeating for an entire ~90s session -- what was actually being captured
# and handed to STT was continuous room noise, not silence. Fix: still
# adapt during "speech" frames, just ~200x slower (see the time-constant
# math below) -- a genuine short spoken utterance ends long before this
# budges the floor meaningfully, but sustained noise that's been
# misclassified as speech pulls the floor up and self-corrects within a
# few seconds instead of staying wrong all session.
STUCK_FLOOR_RECOVERY_DECAY = 0.995  # tau = FRAME_MS / (1 - decay) = 30ms / 0.005 = 6s

# Real bug, found from real wake_debug/*.wav evidence (query_loop.py's
# `_log_and_save_wake_debug`), not a theory: in a quiet room the adaptive
# floor above legitimately decays down toward true silence (int16 RMS in
# the 15-40 range measured from real captured buffers), and at that point
# `SPEECH_RATIO * floor` is itself so low that a fan hum, a chair creak, or
# a breath clears it -- captured wake-window buffers with peak amplitude
# of 0.004-0.023 (near-silent; a spoken word peaks 0.1-0.9 on this scale)
# were being classified as speech and handed to STT, which correctly
# transcribed them as nothing. The adaptive floor has no concept of "too
# quiet to possibly be a human talking" -- it only ever compares against
# its own recent, possibly-collapsed history. This adds a floor-independent
# absolute gate: below this RMS, it is never speech, no matter how low the
# adaptive floor has drifted. First-guess value (a quiet spoken word should
# clear this easily; a real measured "too high" report is the way to find
# out if it's wrong), same caveat as every other untuned constant here --
# but it targets the actual failure this session's real data showed,
# not a guess about what might be wrong.
MIN_ABSOLUTE_SPEECH_RMS = 300.0  # int16 scale


class EnergyVad:
    """Chunked, stateful. Feed it consecutive `FRAME_SAMPLES`-length int16
    frames; `is_speech` updates a rolling noise floor and reports whether
    the current frame is above it."""

    def __init__(self) -> None:
        self._floor = 50.0  # int16-scale RMS starting guess, adapts fast

    def is_speech(self, frame: np.ndarray) -> bool:
        rms = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)) + 1e-6)
        speech = rms > self._floor * SPEECH_RATIO and rms > MIN_ABSOLUTE_SPEECH_RMS
        decay = NOISE_FLOOR_DECAY if not speech else STUCK_FLOOR_RECOVERY_DECAY
        self._floor = self._floor * decay + rms * (1 - decay)
        return speech

    @property
    def floor(self) -> float:
        return self._floor
