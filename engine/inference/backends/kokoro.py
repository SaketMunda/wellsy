"""TTS backend — Kokoro-82M, ONNX.

The portable *fast baseline* TTS for the streaming voice path (`stack-teardown.md`
§5): Kokoro is the "fast-but-flat" target, chosen over Chatterbox (which was
adopted mid-Day-11 with no latency budget and measured RTF 1.1x-3.3x — slower
than realtime). An expressive, instructable model (Qwen3-TTS) is a later day; the
seam here does not change when it lands.

Portable by construction: `kokoro-onnx` runs onnxruntime on
Linux/Windows/macOS, ~82M params, 24 kHz output. Phonemisation is done by
`espeak-ng` (a system package, like PortAudio for the audio device).

Weights (INVARIANTS #1 — the one sanctioned path outside the repo):

    $WELLSY_WEIGHTS_DIR/kokoro-v1.0.onnx     (~325 MB)
    $WELLSY_WEIGHTS_DIR/voices-v1.0.bin      (~28 MB)

Fetch once::

    curl -sL -o ~/.cache/wellsy/weights/kokoro-v1.0.onnx \\
      https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
    curl -sL -o ~/.cache/wellsy/weights/voices-v1.0.bin \\
      https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

`WELLSY_TTS_VOICE` overrides the default voice; `WELLSY_TTS_SPEED` the rate.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Iterator

import numpy as np

from engine.inference.base import (
    WEIGHTS_DIR,
    BackendCapabilities,
    BackendUnavailable,
    PcmChunk,
    detect_accelerator,
    platform_tag,
)

MODEL = WEIGHTS_DIR / "kokoro-v1.0.onnx"
VOICES = WEIGHTS_DIR / "voices-v1.0.bin"
SAMPLE_RATE = 24000
VERIFIED = "2026-09-01"  # kokoro-onnx 0.6.1, model-files-v1.0
DEFAULT_VOICE = "af_heart"
DEFAULT_LANG = "en-us"


class KokoroTts:
    NAME = "kokoro"
    MODALITY = "tts"
    SAMPLE_RATE = SAMPLE_RATE

    def __init__(
        self,
        *,
        voice: str | None = None,
        speed: float | None = None,
        lang: str = DEFAULT_LANG,
    ) -> None:
        if importlib.util.find_spec("kokoro_onnx") is None:
            raise BackendUnavailable("kokoro-onnx not installed — `uv sync` with the voice deps")
        for f in (MODEL, VOICES):
            if not f.exists():
                raise BackendUnavailable(f"missing weight {f} — see module docstring for the fetch lines")

        from kokoro_onnx import Kokoro

        self.voice = voice or os.environ.get("WELLSY_TTS_VOICE") or DEFAULT_VOICE
        self.speed = float(speed if speed is not None else os.environ.get("WELLSY_TTS_SPEED", 1.0))
        self.lang = lang
        # kokoro-onnx builds its own onnxruntime session; it honours ORT's
        # provider auto-selection, so CUDA/CoreML/CPU are picked up with no
        # code here.
        self._k = Kokoro(str(MODEL), str(VOICES))

        self.capabilities = BackendCapabilities(
            modality="tts",
            name=self.NAME,
            platform=platform_tag(),
            accelerator=detect_accelerator(),
            streams=True,
            version="kokoro-onnx 0.6.1 / model-files-v1.0",
            verified=VERIFIED,
            max_context=None,
            resident_mb=None,
            detail={"sample_rate": SAMPLE_RATE, "voice": self.voice, "speed": self.speed},
        )

    @classmethod
    def is_available(cls) -> bool:
        return (
            importlib.util.find_spec("kokoro_onnx") is not None
            and MODEL.exists()
            and VOICES.exists()
        )

    def close(self) -> None:
        """Release the ORT session + espeak-ng backend before interpreter
        shutdown. Without this, kokoro-onnx's phonemiser and the ONNX session
        are still live at teardown and their C-level destructors race
        (``recursive_mutex lock failed`` on macOS). Harnesses call this."""
        import gc

        self._k = None
        gc.collect()

    def stream(self, text_chunks: Iterator[str]) -> Iterator[PcmChunk]:
        """One `PcmChunk` per non-empty text chunk. The caller sentence-chunks
        the LLM token stream, so each chunk here is a clause/sentence and the
        first audio is emitted after synthesising only the first one — nothing
        waits for the whole answer."""

        for chunk in text_chunks:
            text = (chunk or "").strip()
            if not text:
                continue
            samples, sr = self._k.create(
                text, voice=self.voice, speed=self.speed, lang=self.lang, trim=True
            )
            pcm = np.asarray(samples, dtype=np.float32).reshape(-1)
            if pcm.size:
                yield PcmChunk(pcm=pcm, sample_rate=int(sr or SAMPLE_RATE))
