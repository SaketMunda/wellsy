"""Portable reference backends for ASR and TTS.

These are **not** models. They implement the `AsrBackend` / `TtsBackend`
protocols with zero optional dependencies so that each interface has a second,
always-available backend that passes the shared conformance test on every
platform while the real ONNX models (Qwen3-ASR 0.6B, Kokoro-82M / Qwen3-TTS)
are wired in a later step.

* `ReferenceAsr` — emits a growing `Partial` per input chunk, then one `Final`.
  The text is fixed (or injected in the constructor); it is a shape, not a
  transcription.
* `ReferenceTts` — emits one `PcmChunk` of a short 180 Hz tone per text chunk,
  duration scaled to the chunk length. Deterministic, so the bench RTF number
  is meaningful as a floor.
"""

from __future__ import annotations

from typing import Any, Iterator

import numpy as np

from engine.inference.base import (
    BackendCapabilities,
    Final,
    Partial,
    PcmChunk,
    platform_tag,
)

VERIFIED = "2026-09-01"
_TTS_SR = 24000
_DEFAULT_TRANSCRIPT = "the quick brown fox jumps over the lazy dog"


class ReferenceAsr:
    NAME = "reference"
    MODALITY = "asr"

    def __init__(self, *, transcript: str = _DEFAULT_TRANSCRIPT) -> None:
        self.transcript = transcript
        self.capabilities = BackendCapabilities(
            modality="asr",
            name=self.NAME,
            platform=platform_tag(),
            accelerator="cpu",
            streams=True,
            version="wellsy-reference-asr 1",
            verified=VERIFIED,
            max_context=None,
            resident_mb=None,
            detail={"note": "fixed transcript — shape only, not a model"},
        )

    @classmethod
    def is_available(cls) -> bool:
        return True

    def stream(self, audio_chunks: Iterator[Any]) -> Iterator[Partial | Final]:
        words = self.transcript.split()
        chunks = list(audio_chunks)
        total = len(chunks) or 1
        for i in range(len(chunks)):
            k = max(1, round((i + 1) / total * len(words)))
            yield Partial(text=" ".join(words[:k]))
        yield Final(text=self.transcript)


class ReferenceTts:
    NAME = "reference"
    MODALITY = "tts"
    SAMPLE_RATE = _TTS_SR

    def __init__(self) -> None:
        self.capabilities = BackendCapabilities(
            modality="tts",
            name=self.NAME,
            platform=platform_tag(),
            accelerator="cpu",
            streams=True,
            version="wellsy-reference-tts 1",
            verified=VERIFIED,
            max_context=None,
            resident_mb=None,
            detail={"sample_rate": _TTS_SR, "note": "tone generator — shape only, not a model"},
        )

    @classmethod
    def is_available(cls) -> bool:
        return True

    def stream(self, text_chunks: Iterator[str]) -> Iterator[PcmChunk]:
        for chunk in text_chunks:
            dur = max(0.05, 0.045 * len(chunk))
            n = int(dur * _TTS_SR)
            tt = np.arange(n, dtype=np.float32) / _TTS_SR
            pcm = (0.2 * np.sin(2 * np.pi * 180.0 * tt)).astype(np.float32)
            yield PcmChunk(pcm=pcm, sample_rate=_TTS_SR)
