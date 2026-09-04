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


def build_llm():
    """Pipecat `OpenAILLMService` on the local server. Default
    `qwen3:4b-instruct-2507-q4_K_M` (step 5b): non-reasoning by construction —
    the `-instruct` build has no `<think>` path, so it sidesteps the Ollama
    0.33.2 problem where every hybrid/thinking `qwen3*` build burns ~78 s/turn
    on a reasoning pass that no flag or `think:"low"` level disables (all
    measured, `.claude/rebuild/step5b-results.md` §2). 21 ms warm TTFT — the
    honest pipeline number, same model the agent's fast+planner roles use.
    Override with `WELLSY_LLM_MODEL` (e.g. `qwen3-vl:2b-instruct-q4_K_M` for
    image turns) / `WELLSY_LLM_BASE_URL`."""

    from pipecat.services.openai.llm import OpenAILLMService

    base_url = os.environ.get("WELLSY_LLM_BASE_URL", "http://localhost:11434/v1")
    model = os.environ.get("WELLSY_LLM_MODEL", "qwen3:4b-instruct-2507-q4_K_M")
    # `keep_alive: -1` pins the model resident so the ~10-16 s cold reload does
    # not tax every idle-gap turn. `think` / `enable_thinking` are still sent so
    # a qwen3 override behaves as well as that build allows (it currently
    # ignores them — step 4b finding).
    extra_body = {
        "keep_alive": -1,
        "think": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    return OpenAILLMService(
        api_key=os.environ.get("WELLSY_LLM_API_KEY", "ollama"),
        base_url=base_url,
        settings=OpenAILLMService.Settings(model=model, extra={"extra_body": extra_body}),
    )
