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
import re
from typing import Any, AsyncGenerator

import numpy as np

from pipecat.frames.frames import Frame, TranscriptionFrame, TTSAudioRawFrame
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.settings import STTSettings, TTSSettings
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.services.tts_service import TTSService
from pipecat.utils.time import time_now_iso8601

from engine.inference import registry

# The model emits emoji despite the prompt (step 6c live run: "there you go. 🌟");
# they never reach the voice. Nor does markdown — the VL model answers in
# bullet lists ("- A code editor ...") despite being asked not to.
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF\uFE0F\u200D]+"
)
_MARKDOWN = re.compile(r"(?m)^\s*(?:[-*•]|\d+\.|#+)\s+|\*\*|__|`")

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
        text = _MARKDOWN.sub("", _EMOJI.sub("", text or "")).strip()
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


# The local server runs every model at a 4096-token context (Ollama's default;
# the OpenAI-compatible endpoint ignores a per-request `num_ctx` — verified
# against Ollama 0.40.3 on 2026-10-13: a 6012-token prompt 400s with or without
# `options.num_ctx`). So the request is fitted to the window here instead of
# trusting the server. Step 6c live run: two 1080p screen captures + history =
# 4652 tokens -> 400 -> session over.
CONTEXT_BUDGET_TOKENS = 3000      # of 4096 — the rest is room for the reply
IMAGE_TOKENS = 700                # one <=1024 px frame on qwen3-vl (32 px/token) + margin


def message_has_image(m: Any) -> bool:
    content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
    return isinstance(content, list) and any(
        isinstance(p, dict) and p.get("type") == "image_url" for p in content
    )


def strip_image_messages(msgs: list) -> list:
    return [m for m in msgs if not message_has_image(m)]


def _estimate_tokens(m: Any) -> int:
    content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
    if isinstance(content, str):
        return len(content) // 3 + 4
    if isinstance(content, list):
        n = 4
        for p in content:
            if isinstance(p, dict) and p.get("type") == "image_url":
                n += IMAGE_TOKENS
            elif isinstance(p, dict):
                n += len(str(p.get("text", ""))) // 3
        return n
    return 4


def fit_messages(msgs: list, budget: int = CONTEXT_BUDGET_TOKENS) -> list:
    """Drop the oldest turns (never the system prompt, never the newest
    message) until the estimate fits `budget`."""
    head = [m for m in msgs[:1] if (m.get("role") if isinstance(m, dict) else None) == "system"]
    body = list(msgs[len(head):])
    total = sum(_estimate_tokens(m) for m in head + body)
    while total > budget and len(body) > 1:
        total -= _estimate_tokens(body.pop(0))
    return head + body


FAILURE_SPOKEN = "Sorry, that one failed on my side. Ask me again."

# The VL model (2B) gets the image and nothing else. Step 6c second live run: fed
# the whole conversation, it answered "what am I wearing" with 7 sentences
# (~22 s of speech) and wandered into the earlier orb discussion; on a screen
# turn it said "I see … but I haven't looked at the screen", mixing the
# text-turn honesty rule into a turn where it had looked.
VLM_SYSTEM_PROMPT = (
    "You are WELLSY, a local assistant speaking aloud. The attached image is what "
    "you are looking at right now. Answer the user's question about it in at most "
    "two short spoken sentences, describing only what is actually visible. "
    "Talk to the user as 'you': a person in a camera image is the user, never you. "
    "If the question is about the user and no person is visible, say you don't see "
    "anyone right now — never guess what they wear or hold. "
    "No lists, no markdown, no emoji."
)
VLM_MAX_TOKENS = 90


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
        # set by the pipeline: drop image messages / disarm the vision turn
        self.on_failure = None
        self._text_max_tokens = self._settings.max_completion_tokens

    def use_vlm(self, on: bool) -> None:
        target = self._vlm_model if (on and self.vlm_ok) else self._text_model
        if self._settings.model != target:
            self._settings.model = target
            self.set_full_model_name(target)
        self._settings.max_completion_tokens = (
            VLM_MAX_TOKENS if target == self._vlm_model else self._text_max_tokens
        )

    def on_vlm(self) -> bool:
        return self.vlm_ok and self._settings.model == self._vlm_model

    async def _process_context(self, context):
        if self.on_vlm():
            from pipecat.processors.aggregators.llm_context import LLMContext

            msgs = list(context.messages)
            imgs: list = []
            while msgs and message_has_image(msgs[-1]):
                imgs.insert(0, msgs.pop())
            vlm_ctx = LLMContext(messages=[{"role": "system", "content": VLM_SYSTEM_PROMPT}, *imgs])
            await super()._process_context(vlm_ctx)
            return
        # A text-model request never carries an image (step 6c third live run:
        # a vision turn cut short by the next utterance left its frames in
        # context, the text model got them and 500'd "image input is not
        # supported"). Images exist only for the VL turn that asked for them.
        if any(message_has_image(m) for m in context.messages):
            context.transform_messages(strip_image_messages)
        fitted = fit_messages(list(context.messages))
        if len(fitted) != len(context.messages):
            context.set_messages(fitted)
        await super()._process_context(context)

    async def push_error_frame(self, error, force_treat_as_permanent: bool = False):
        """A failed completion is one bad request, not a dead service. pipecat
        classes a 400 as INVALID_REQUEST — permanent — and the worker then ends
        the whole session (step 6c live run; increment 6 hit the same class
        from another trigger). Reclassify it, recover the context, switch back
        to the text model, and say so out loud instead of going silent.
        Auth failures stay permanent."""
        from pipecat.frames.frames import TTSSpeakFrame
        from pipecat.utils.errors import ErrorCategory, classify_http_exception

        if error.category is None and error.exception is not None:
            error.category = self._classify_error(error.exception) or classify_http_exception(
                error.exception
            )
        recoverable = error.category in (None, ErrorCategory.INVALID_REQUEST,
                                         ErrorCategory.UNKNOWN, ErrorCategory.SERVER)
        if recoverable:
            error.category = ErrorCategory.APPLICATION
            force_treat_as_permanent = False
        await super().push_error_frame(error, force_treat_as_permanent=force_treat_as_permanent)
        if not recoverable:
            return
        self.use_vlm(False)
        if self.on_failure is not None:
            try:
                self.on_failure()
            except Exception:
                pass
        await self.push_frame(TTSSpeakFrame(text=FAILURE_SPOKEN, append_to_context=False))


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

    Default text model `qwen3:4b-instruct-2507-q4_K_M` (step 5b): non-reasoning
    by construction — the `-instruct` build has no `<think>` path, so it
    sidesteps the Ollama 0.33.2 problem where every hybrid/thinking `qwen3*`
    build burns ~78 s/turn on a reasoning pass that no flag or `think:"low"`
    level disables (measured, `.claude/rebuild/step5b-results.md` §2). 21 ms warm
    TTFT — the honest pipeline number, same model the agent's fast+planner roles
    use.

    Vision turns (`describe_scene` / `query_object`) need a VL model; default
    `qwen3-vl:2b-instruct-q4_K_M` (step 5b), co-resident with the text model.
    The name is resolved against what is actually pulled (a quant suffix is
    fine); if nothing matches the vision path says so plainly rather than
    crashing. Override with `WELLSY_LLM_MODEL` / `WELLSY_VLM_MODEL` /
    `WELLSY_LLM_BASE_URL`."""

    base_url = os.environ.get("WELLSY_LLM_BASE_URL", "http://localhost:11434/v1")
    model = os.environ.get("WELLSY_LLM_MODEL", "qwen3:4b-instruct-2507-q4_K_M")
    vlm_req = os.environ.get("WELLSY_VLM_MODEL", "qwen3-vl:2b-instruct-q4_K_M")
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
