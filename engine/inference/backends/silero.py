"""VAD backend — Silero VAD v5, ONNX.

Portable by construction: onnxruntime runs on Linux/Windows/macOS/mobile/
embedded, and the model is ~2.3 MB. This is the real VAD path for step 4
(`stack-teardown.md` §5). Silero v5 ONNX I/O:

    input  float32 [batch, samples]   — 512 samples per call at 16 kHz
    state  float32 [2, batch, 128]    — carried between calls
    sr     int64   scalar             — 16000
    ->
    output float32 [batch, 1]         — P(speech)
    stateN float32 [2, batch, 128]

Weight file: ``$WELLSY_WEIGHTS_DIR/silero_vad.onnx`` (default
``~/.cache/wellsy/weights``). Fetch once with::

    curl -sL -o ~/.cache/wellsy/weights/silero_vad.onnx \\
      https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx
"""

from __future__ import annotations

import importlib.util
from typing import Any, Iterator

import numpy as np

from engine.inference.base import (
    WEIGHTS_DIR,
    BackendCapabilities,
    BackendUnavailable,
    SpeechProb,
    detect_accelerator,
    platform_tag,
)

WEIGHT = WEIGHTS_DIR / "silero_vad.onnx"
SAMPLE_RATE = 16000
FRAME = 512
VERIFIED = "2026-09-01"  # snakers4/silero-vad master, v5 onnx


def _providers() -> list[str]:
    import onnxruntime as ort

    have = set(ort.get_available_providers())
    order = [
        "CUDAExecutionProvider",
        "CoreMLExecutionProvider",
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    ]
    return [p for p in order if p in have] or ["CPUExecutionProvider"]


class SileroVad:
    NAME = "silero"
    MODALITY = "vad"

    def __init__(self, *, threshold: float = 0.5) -> None:
        if importlib.util.find_spec("onnxruntime") is None:
            raise BackendUnavailable("onnxruntime not installed")
        if not WEIGHT.exists():
            raise BackendUnavailable(f"missing weight {WEIGHT} — see module docstring for the fetch line")
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.inter_op_num_threads = 1
        so.intra_op_num_threads = 1
        self._sess = ort.InferenceSession(str(WEIGHT), sess_options=so, providers=_providers())
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._sr = np.array(SAMPLE_RATE, dtype=np.int64)
        self.threshold = threshold
        self.capabilities = BackendCapabilities(
            modality="vad",
            name=self.NAME,
            platform=platform_tag(),
            accelerator=detect_accelerator(),
            streams=True,
            version="silero-vad v5 (onnx)",
            verified=VERIFIED,
            max_context=None,
            resident_mb=None,
            detail={"sample_rate": SAMPLE_RATE, "frame": FRAME},
        )

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("onnxruntime") is not None and WEIGHT.exists()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)

    def stream(self, frames: Iterator[Any]) -> Iterator[SpeechProb]:
        t = 0.0
        for frame in frames:
            x = np.asarray(frame, dtype=np.float32).reshape(-1)
            if x.size < FRAME:
                x = np.pad(x, (0, FRAME - x.size))
            elif x.size > FRAME:
                x = x[:FRAME]
            out, self._state = self._sess.run(
                ["output", "stateN"],
                {"input": x.reshape(1, FRAME), "state": self._state, "sr": self._sr},
            )
            p = float(np.asarray(out).reshape(-1)[0])
            yield SpeechProb(prob=p, t=t, is_speech=p >= self.threshold)
            t += FRAME / SAMPLE_RATE
