"""Pipecat service classes that wrap the step-2 inference seam.

The seam stays the seam: these adapters own no model logic. They call
`engine.inference.registry.get_backend(...)` and translate between the
`AsrBackend` / `TtsBackend` streaming protocols and Pipecat frames. The LLM is
Pipecat's own `OpenAILLMService` pointed at the same local OpenAI-compatible
server the step-2 `openai_http` backend targets (Ollama here; llama-server /
vLLM / SGLang on Linux/CUDA) — reimplementing the context-aggregation and
tool-call plumbing would be exactly the hand-rolling step 4 forbids.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, AsyncGenerator

import numpy as np

from pipecat.frames.frames import Frame, TranscriptionFrame, TTSAudioRawFrame
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.settings import STTSettings, TTSSettings
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.services.tts_service import TTSService
from pipecat.utils.time import time_now_iso8601

from engine.inference import registry

WHISPER_SR = 16000


class SeamSTTService(SegmentedSTTService):
    """Segmented STT over any step-2 `AsrBackend` (default: `faster_whisper`).

    `SegmentedSTTService` buffers each VAD-gated utterance and calls `run_stt`
    once at end-of-turn. We take raw 16-bit PCM (``wants_wav_segments=False``)
    at the transport's input rate, hand it to the backend, and emit one
    finalized `TranscriptionFrame`.
    """

    def __init__(self, *, backend: str | None = None, sample_rate: int | None = None, **kwargs) -> None:
        kwargs.setdefault("settings", STTSettings(model=None, language=None))
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._backend_name = backend
        self._asr = registry.get_backend("asr", backend)

    @property
    def wants_wav_segments(self) -> bool:
        return False

    def can_generate_metrics(self) -> bool:
        return True

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        pcm = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        if self.sample_rate and self.sample_rate != WHISPER_SR and pcm.size:
            import soxr

            pcm = soxr.resample(pcm, self.sample_rate, WHISPER_SR)

        await self.start_processing_metrics()
        await self.start_ttfb_metrics()
        text = await asyncio.get_running_loop().run_in_executor(None, self._transcribe, pcm)
        await self.stop_ttfb_metrics()
        await self.stop_processing_metrics()

        text = (text or "").strip()
        if text:
            yield TranscriptionFrame(
                text, "", time_now_iso8601(), None, result=None, finalized=True
            )

    def _transcribe(self, pcm: np.ndarray) -> str:
        last = ""
        for out in self._asr.stream(iter([pcm])):
            last = out.text or last
        return last


class SeamTTSService(TTSService):
    """Streaming TTS over any step-2 `TtsBackend` (default: `kokoro`).

    The base aggregates the LLM token stream into sentences and calls `run_tts`
    per sentence, so the first audio is emitted after synthesising only the
    first sentence — nothing waits for the whole answer. The base also emits
    `TTSStartedFrame` / `TTSStoppedFrame` (``push_start_frame`` /
    ``push_stop_frames``).
    """

    def __init__(self, *, backend: str | None = None, sample_rate: int | None = None, **kwargs) -> None:
        self._tts = registry.get_backend("tts", backend)
        rate = sample_rate or getattr(self._tts, "SAMPLE_RATE", 24000)
        voice = getattr(getattr(self._tts, "capabilities", None), "detail", {}).get("voice")
        kwargs.setdefault("settings", TTSSettings(model=None, voice=voice, language=None))
        super().__init__(
            sample_rate=rate,
            push_start_frame=True,
            push_stop_frames=True,
            **kwargs,
        )
        self._backend_name = backend

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        text = (text or "").strip()
        if not text:
            return

        await self.start_ttfb_metrics()
        loop = asyncio.get_running_loop()
        chunks: list[np.ndarray] = await loop.run_in_executor(None, self._synth, text)

        first = True
        for pcm in chunks:
            if first:
                await self.stop_ttfb_metrics()
                first = False
            i16 = np.clip(pcm, -1.0, 1.0)
            i16 = (i16 * 32767.0).astype(np.int16)
            yield TTSAudioRawFrame(i16.tobytes(), self.sample_rate, 1)

    def _synth(self, text: str) -> list[np.ndarray]:
        out: list[np.ndarray] = []
        for chunk in self._tts.stream(iter([text])):
            pcm = np.asarray(chunk.pcm, dtype=np.float32).reshape(-1)
            if chunk.sample_rate and chunk.sample_rate != self.sample_rate and pcm.size:
                import soxr

                pcm = soxr.resample(pcm, chunk.sample_rate, self.sample_rate)
            if pcm.size:
                out.append(pcm)
        return out


class SeamLLMService(OpenAILLMService):
    """One LLM stage, two models. The pipeline has a single LLM processor
    (step 4b); `IntentGate` calls `use_vlm(True)` right before it emits the
    image `LLMRunFrame`, and `ProvenanceLogger` calls `use_vlm(False)` once the
    answer ends and the image is dropped from context. `vlm_ok` is False when no
    VL model is pulled — `use_vlm(True)` is then a no-op and the gate refuses
    the vision turn honestly (never sends an image the text model 400s on)."""

    def __init__(self, *, text_model: str, vlm_model: str, vlm_ok: bool, **kw) -> None:
        super().__init__(**kw)
        self._text_model = text_model
        self._vlm_model = vlm_model
        self.vlm_ok = bool(vlm_ok)

    def use_vlm(self, on: bool) -> None:
        target = self._vlm_model if (on and self.vlm_ok) else self._text_model
        if self._settings.model != target:
            self._settings.model = target
            self.set_full_model_name(target)


def _resolve_ollama_model(base_url: str, model: str) -> str | None:
    """Return the actual pulled tag on the local OpenAI-compatible server
    (Ollama) that satisfies `model`, or None if nothing does. Matches an exact
    tag, a ":latest" elision, or a quant suffix (`qwen3-vl:2b-instruct` ->
    `qwen3-vl:2b-instruct-q4_K_M`). Any failure -> None, and the vision path
    then degrades to an honest "my vision model isn't loaded" instead of sending
    an image to a text-only model — which 400s and, under pipecat's
    unusable-processor policy, tears the whole session down (owner log
    2026-09-04)."""
    import json as _json
    import urllib.request

    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3].rstrip("/")
    try:
        with urllib.request.urlopen(root + "/api/tags", timeout=1.5) as r:
            names = [m.get("name", "") for m in _json.loads(r.read()).get("models", [])]
    except Exception:
        return None
    if model in names:
        return model
    if f"{model}:latest" in names:
        return f"{model}:latest"
    for n in names:                              # quant suffix, shortest match first
        if n.startswith(model + "-"):
            return n
    return None


def build_llm():
    """A `SeamLLMService` on the local server — one OpenAI-compatible LLM stage
    that flips to a vision model for a single image turn and back.

    Default text model `qwen2.5:3b`: on Ollama 0.33.2 every `qwen3` / `qwen3-vl`
    build ignores `think:false` and burns 8-22 s/turn on a reasoning pass
    (re-confirmed 2026-09-01 by curl; step 4b), which blows the §1 budget the
    voice path exists to meet. `qwen2.5:3b` answers in ~50 ms TTFT with no
    reasoning — the honest pipeline number.

    Vision turns (`describe_scene` / `query_object`) need a VL model; default
    `qwen2.5vl:3b` (non-reasoning — same reason as the text model), co-resident
    with the text model. The name is resolved against what is actually pulled
    (a quant suffix is fine); if nothing matches the vision path says so plainly
    rather than crashing. Override with `WELLSY_LLM_MODEL` / `WELLSY_VLM_MODEL` /
    `WELLSY_LLM_BASE_URL`."""

    base_url = os.environ.get("WELLSY_LLM_BASE_URL", "http://localhost:11434/v1")
    model = os.environ.get("WELLSY_LLM_MODEL", "qwen2.5:3b")
    vlm_req = os.environ.get("WELLSY_VLM_MODEL", "qwen2.5vl:3b")
    vlm_resolved = _resolve_ollama_model(base_url, vlm_req)
    vlm_model = vlm_resolved or vlm_req          # a name to carry even when absent
    vlm_ok = vlm_resolved is not None
    # `keep_alive: -1` pins the model resident so the ~10-16 s cold reload does
    # not tax every idle-gap turn. `think` / `enable_thinking` are still sent so
    # a qwen3 override behaves as well as that build allows (it currently
    # ignores them — step 4b finding).
    extra_body = {
        "keep_alive": -1,
        "think": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    return SeamLLMService(
        api_key=os.environ.get("WELLSY_LLM_API_KEY", "ollama"),
        base_url=base_url,
        settings=SeamLLMService.Settings(model=model, extra={"extra_body": extra_body}),
        text_model=model, vlm_model=vlm_model, vlm_ok=vlm_ok,
    )
