"""ONNX Runtime backends for ASR and TTS — the *portable real* path, scaffolded.

Step 2's scope (agreed with the owner) is: build the seam, prove LLM + VAD
end-to-end, and leave ASR/TTS as a documented scaffold. So these two classes:

* declare themselves **unavailable** unless an explicit ONNX export is pointed
  at via env var — `is_available()` never lies and no multi-GB download happens
  behind anyone's back;
* load an `onnxruntime.InferenceSession` if a path *is* given, so the class is
  structurally real;
* raise `NotImplementedError` from `stream()` with a pointer to the follow-up
  step, because the feature/mel front-end + decode loop (Qwen3-ASR 0.6B) and the
  vocoder pipeline (Kokoro-82M / Qwen3-TTS) are that step's work.

    WELLSY_ASR_ONNX_MODEL   path to an ASR .onnx (or model dir)
    WELLSY_TTS_ONNX_MODEL   path to a TTS .onnx (or model dir)
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any, Iterator

from engine.inference.base import (
    BackendCapabilities,
    BackendUnavailable,
    Final,
    Partial,
    PcmChunk,
    detect_accelerator,
    platform_tag,
)

VERIFIED = "2026-09-01"
_DEFERRED = (
    "ONNX {kind} decode loop is deferred to the ASR/TTS wiring step "
    "(see .claude/rebuild/ and spec/model-inventory.md). "
    "Set {env} to a real export to load the session."
)


def _model_path(env: str) -> Path | None:
    raw = os.environ.get(env)
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.exists() else None


class _OnnxBase:
    NAME = "onnx"
    _ENV = ""
    MODALITY = ""

    def __init__(self) -> None:
        if importlib.util.find_spec("onnxruntime") is None:
            raise BackendUnavailable("onnxruntime not installed")
        path = _model_path(self._ENV)
        if path is None:
            raise BackendUnavailable(
                f"no model — set {self._ENV} to an ONNX export "
                f"({self.MODALITY} model wiring lands in a later step)"
            )
        import onnxruntime as ort

        self._sess = ort.InferenceSession(str(path), providers=ort.get_available_providers())
        self._path = path
        self.capabilities = BackendCapabilities(
            modality=self.MODALITY,
            name=self.NAME,
            platform=platform_tag(),
            accelerator=detect_accelerator(),
            streams=True,
            version=f"onnxruntime {getattr(ort, '__version__', '?')}",
            verified=VERIFIED,
            max_context=None,
            resident_mb=None,
            detail={"model_path": str(path)},
        )

    @classmethod
    def is_available(cls) -> bool:
        return (
            importlib.util.find_spec("onnxruntime") is not None
            and _model_path(cls._ENV) is not None
        )


class OnnxAsr(_OnnxBase):
    MODALITY = "asr"
    _ENV = "WELLSY_ASR_ONNX_MODEL"

    def stream(self, audio_chunks: Iterator[Any]) -> Iterator[Partial | Final]:
        raise NotImplementedError(_DEFERRED.format(kind="ASR", env=self._ENV))


class OnnxTts(_OnnxBase):
    MODALITY = "tts"
    _ENV = "WELLSY_TTS_ONNX_MODEL"

    def stream(self, text_chunks: Iterator[str]) -> Iterator[PcmChunk]:
        raise NotImplementedError(_DEFERRED.format(kind="TTS", env=self._ENV))
