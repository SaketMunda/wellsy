"""ASR backend — faster-whisper (CTranslate2).

The portable ASR path for the streaming voice path. `stack-teardown.md` §5
named Qwen3-ASR 0.6B as the candidate; step 4 verified its only CPU-ONNX export
(`Daumee/Qwen3-ASR-0.6B-ONNX-CPU`) is 2.5 GB, batch-decodes on ~30 s silence
chunks, and runs at RTF ~0.32 on desktop — a ~1 s STT floor that breaks the
§1 latency budget. faster-whisper `base.en` transcribes a short command in
~150-400 ms on CPU with strong accuracy, so it is the adopted path; Smart Turn
v3 owns end-of-turn, so the lack of word-level partials costs little.

CTranslate2 runs on CPU everywhere and on CUDA where present. On Apple Silicon
there is no Metal path — it is CPU/int8 there, which is still well inside budget
for `base.en`. Portable by construction: no torch, no platform package.

Weights are pulled by `faster-whisper` on first use into
`$WELLSY_WEIGHTS_DIR/faster-whisper` (INVARIANTS #1 — the sanctioned weights
path). `WELLSY_ASR_MODEL` overrides the model id (default ``base.en``).

The `stream()` contract is honoured by buffering the utterance's audio chunks,
decoding once, and yielding a growing `Partial` per Whisper segment then one
`Final`. It is called per user turn by the voice pipeline's segmented STT
service, not for a continuous session.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any, Iterator

import numpy as np

from engine.inference.base import (
    WEIGHTS_DIR,
    BackendCapabilities,
    BackendUnavailable,
    Final,
    Partial,
    detect_accelerator,
    platform_tag,
)

SAMPLE_RATE = 16000
VERIFIED = "2026-09-01"  # faster-whisper 1.2.1
DEFAULT_MODEL = "base.en"
_DOWNLOAD_ROOT = WEIGHTS_DIR / "faster-whisper"


def _device_and_compute() -> tuple[str, str]:
    accel = detect_accelerator()
    if accel == "cuda":
        return "cuda", "float16"
    # CTranslate2 has no Metal/CoreML backend — CPU int8 on Apple Silicon and
    # anywhere else. int8 is ~2x faster than float32 with no meaningful WER cost
    # on base.en for command-length audio.
    return "cpu", "int8"


class FasterWhisperAsr:
    NAME = "faster_whisper"
    MODALITY = "asr"
    SAMPLE_RATE = SAMPLE_RATE

    def __init__(self, *, model: str | None = None, language: str | None = "en") -> None:
        if importlib.util.find_spec("faster_whisper") is None:
            raise BackendUnavailable("faster-whisper not installed — `uv sync` with the voice deps")

        from faster_whisper import WhisperModel

        self.model_id = model or os.environ.get("WELLSY_ASR_MODEL") or DEFAULT_MODEL
        self.language = language
        device, compute_type = _device_and_compute()
        _DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        try:
            self._model = WhisperModel(
                self.model_id,
                device=device,
                compute_type=compute_type,
                download_root=str(_DOWNLOAD_ROOT),
            )
        except Exception as e:  # offline + not cached, or an unsupported combo
            raise BackendUnavailable(f"faster-whisper model {self.model_id!r} unavailable: {e}") from e

        self.capabilities = BackendCapabilities(
            modality="asr",
            name=self.NAME,
            platform=platform_tag(),
            accelerator=device if device != "cpu" else "cpu",
            streams=True,
            version=f"faster-whisper 1.2.1 / {self.model_id} / {compute_type}",
            verified=VERIFIED,
            max_context=None,
            resident_mb=None,
            detail={"model": self.model_id, "device": device, "compute_type": compute_type},
        )

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    @staticmethod
    def _to_mono_f32(chunk: Any) -> np.ndarray:
        x = np.asarray(chunk, dtype=np.float32)
        if x.ndim > 1:
            x = x.mean(axis=tuple(range(1, x.ndim)))
        return x.reshape(-1)

    def transcribe(self, audio: np.ndarray) -> str:
        """One-shot helper for the wake gate (short rolling buffer)."""
        segments, _ = self._model.transcribe(
            self._to_mono_f32(audio),
            language=self.language,
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segments).strip()

    def stream(self, audio_chunks: Iterator[Any]) -> Iterator[Partial | Final]:
        buf = [self._to_mono_f32(c) for c in audio_chunks]
        audio = np.concatenate(buf) if buf else np.zeros(0, dtype=np.float32)
        if audio.size < int(0.05 * SAMPLE_RATE):
            yield Final(text="")
            return

        segments, _info = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        acc: list[str] = []
        for seg in segments:
            acc.append(seg.text.strip())
            yield Partial(text=" ".join(acc).strip(), t0=getattr(seg, "start", None), t1=getattr(seg, "end", None))
        yield Final(text=" ".join(acc).strip())
