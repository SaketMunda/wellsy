"""VAD backend — RMS energy, pure NumPy.

The **portable reference** for the VAD modality: no model, no optional import,
runs identically on every platform. It is deliberately simple — a short-term
RMS level mapped through a fixed dBFS window to a 0..1 probability. It is *not*
the Day 11 energy VAD (`vad.py`, deleted): there is no adaptive floor here, so
there is nothing to latch. Silero is the real path; this exists so the VAD
interface always has a second, dependency-free backend that passes the same
conformance test.
"""

from __future__ import annotations

from typing import Any, Iterator

import numpy as np

from engine.inference.base import (
    BackendCapabilities,
    SpeechProb,
    platform_tag,
)

SAMPLE_RATE = 16000
FRAME = 512
_FLOOR_DB = -60.0   # maps to prob 0.0
_CEIL_DB = -20.0    # maps to prob 1.0
VERIFIED = "2026-09-01"


class EnergyVad:
    NAME = "energy"
    MODALITY = "vad"

    def __init__(self, *, threshold: float = 0.5) -> None:
        self.threshold = threshold
        self.capabilities = BackendCapabilities(
            modality="vad",
            name=self.NAME,
            platform=platform_tag(),
            accelerator="cpu",
            streams=True,
            version="wellsy-energy-vad 1",
            verified=VERIFIED,
            max_context=None,
            resident_mb=None,
            detail={"floor_db": _FLOOR_DB, "ceil_db": _CEIL_DB},
        )

    @classmethod
    def is_available(cls) -> bool:
        return True

    def reset(self) -> None:  # symmetry with SileroVad; nothing to carry
        pass

    def stream(self, frames: Iterator[Any]) -> Iterator[SpeechProb]:
        t = 0.0
        for frame in frames:
            x = np.asarray(frame, dtype=np.float32).reshape(-1)
            n = x.size or 1
            rms = float(np.sqrt(np.mean(x * x)) + 1e-12)
            db = 20.0 * np.log10(rms)
            p = float(np.clip((db - _FLOOR_DB) / (_CEIL_DB - _FLOOR_DB), 0.0, 1.0))
            yield SpeechProb(prob=p, t=t, is_speech=p >= self.threshold)
            t += n / SAMPLE_RATE
