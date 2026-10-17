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
# of 4096. Step 9: 3000 left ~1750 for history once the system prompt and the
# tool schema were reserved, so a session trimmed every ~3 agentic turns and
# each trim cost a Qwen3.5 re-prefill (delivery 2.0-2.8 s after a trim vs
# 0.9-1.5 s without; spec/results/step9-replay-rows-*). The estimate runs 5-10 %
# above the server's real prompt_tokens (measured on 5 live requests), and the
# longest reply is a ~70-token tool call, so 3500 keeps a safe margin. Above
# 4096 Ollama truncates silently (5,200 tokens in -> 2,050 counted, 0.40.5).
# `WELLSY_LLM_NUM_CTX` tells WELLSY the window the server really runs (Ollama's
# default 4096, or OLLAMA_CONTEXT_LENGTH); the request is fitted to it minus
# ~600 tokens for the reply and the estimate's error.
SERVER_NUM_CTX = int(os.environ.get("WELLSY_LLM_NUM_CTX", "4096"))
CONTEXT_BUDGET_TOKENS = SERVER_NUM_CTX - 596
IMAGE_TOKENS = 700                # one <=1024 px frame (qwen3-vl 1056 tok / 2 imgs; qwen3.5 ~600) + margin
# Front-trimming the history is an edit, and on Qwen3.5 (24 of 32 layers are
# recurrent) any edit to earlier history costs a re-prefill from the last
# checkpoint — 1.2 s at 4K (5c §6). Trimming to exactly the budget would pay
# that on every turn once a session is long; trimming to 60 % pays it once
# per several turns.
TRIM_TO_FRACTION = 0.6


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
    if isinstance(m, dict) and m.get("tool_calls"):
        return len(str(m["tool_calls"])) // 3 + 4
    return 4


def _role(m: Any) -> str | None:
    return m.get("role") if isinstance(m, dict) else None


def fit_messages(msgs: list, budget: int = CONTEXT_BUDGET_TOKENS,
                 reserve: int = 0) -> list:
    """Drop the oldest turns (never a leading system prompt, never the newest
    message) until the estimate fits `budget - reserve`; once trimming starts,
    trim to `TRIM_TO_FRACTION` of it so the next turns append instead of
    editing again. A cut never starts on a tool result or an assistant
    tool-call fragment — the server rejects an orphaned tool message.
    `reserve` is what the request carries outside the messages (the system
    instruction and the tool schemas)."""
    head = [m for m in msgs[:1] if _role(m) == "system"]
    body = list(msgs[len(head):])
    limit = budget - reserve
    total = sum(_estimate_tokens(m) for m in head + body)
    if total <= limit:
        return head + body
    target = int(limit * TRIM_TO_FRACTION)
    while total > target and len(body) > 1:
        total -= _estimate_tokens(body.pop(0))
    while len(body) > 1 and (_role(body[0]) == "tool" or (
            _role(body[0]) == "assistant" and isinstance(body[0], dict) and body[0].get("tool_calls"))):
        body.pop(0)
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
    """The one LLM stage of the voice loop, on one resident model.

    Step 9 collapse (5c §3): `qwen3.5:4b` serves text, vision and the agent's
    roles, so the two-model flip of step 6 increment 6 is gone. What a vision
    turn keeps is its *shape*: `IntentGate` calls `use_vlm(True)` right before
    it emits the image `LLMRunFrame`; the request then carries only
    `VLM_SYSTEM_PROMPT` plus the images (no history, no tools, 90 tokens), and
    `ProvenanceLogger` calls `use_vlm(False)` when the answer ends. The images
    never enter a request built from the main conversation, so that
    conversation stays append-only on the server's prefix cache.

    `vlm_ok` is False when the model is not pulled or has no vision
    capability — `use_vlm(True)` is then a no-op and the gate refuses the
    vision turn honestly (never sends an image a text-only model 400s on)."""

    def __init__(self, *, model: str, vlm_ok: bool, **kw) -> None:
        super().__init__(**kw)
        self.model = model
        self.vlm_ok = bool(vlm_ok)
        self._vision_turn = False
        # set by the pipeline: drop image messages / disarm the vision turn
        self.on_failure = None
        self._text_max_tokens = self._settings.max_completion_tokens

    def use_vlm(self, on: bool) -> None:
        """Enter / leave a vision turn. Same model either way."""
        self._vision_turn = bool(on and self.vlm_ok)
        self._settings.max_completion_tokens = (
            VLM_MAX_TOKENS if self._vision_turn else self._text_max_tokens
        )

    def on_vlm(self) -> bool:
        return self._vision_turn

    def build_chat_completion_params(self, params_from_context) -> dict:
        """`developer` messages go out as `system`. Ollama's Qwen3.5 template
        drops the developer role: measured 2026-10-17 on 0.40.5, a tool result
        delivered as pipecat's async developer message was ignored 3/3 ("I'll
        let you know when results are in"); the same payload as `system` was
        read correctly 3/3. That also silently dropped the step-6c sleep note
        and the greeting instruction. Done on the outgoing request only — the
        stored context is never edited (an edit costs a re-prefill on Qwen3.5)."""
        params = super().build_chat_completion_params(params_from_context)
        msgs = params.get("messages")
        if isinstance(msgs, list) and any(isinstance(m, dict) and m.get("role") == "developer" for m in msgs):
            params["messages"] = [{**m, "role": "system"} if isinstance(m, dict) and m.get("role") == "developer"
                                  else m for m in msgs]
        dump = os.environ.get("WELLSY_DUMP_REQUESTS")
        if dump:                       # measurement harness only: the exact request
            import json as _json

            with open(dump, "a") as f:
                f.write(_json.dumps({k: v for k, v in params.items() if k != "stream_options"},
                                    default=str) + "\n")
        return params

    def _reserve_tokens(self, context) -> int:
        n = len(str(self._settings.system_instruction or "")) // 3
        tools = getattr(context, "tools", None)
        standard = getattr(tools, "standard_tools", None) or []
        for t in standard:
            n += len(str(getattr(t, "description", ""))) // 3 + 60
        return n

    async def _process_context(self, context):
        if self._vision_turn:
            from pipecat.processors.aggregators.llm_context import LLMContext

            msgs = list(context.messages)
            imgs: list = []
            while msgs and message_has_image(msgs[-1]):
                imgs.insert(0, msgs.pop())
            vlm_ctx = LLMContext(messages=imgs)          # no history, no tools
            saved = self._settings.system_instruction
            self._settings.system_instruction = VLM_SYSTEM_PROMPT
            try:
                await super()._process_context(vlm_ctx)
            finally:
                self._settings.system_instruction = saved
            return
        # A text request never carries an image (step 6c third live run: a
        # vision turn cut short by the next utterance left its frames in
        # context and the request 500'd). Images exist only for the vision
        # turn that asked for them.
        if any(message_has_image(m) for m in context.messages):
            context.transform_messages(strip_image_messages)
        fitted = fit_messages(list(context.messages), reserve=self._reserve_tokens(context))
        if len(fitted) != len(context.messages):
            context.set_messages(fitted)
        await super()._process_context(context)

    async def push_error_frame(self, error, force_treat_as_permanent: bool = False):
        """A failed completion is one bad request, not a dead service. pipecat
        classes a 400 as INVALID_REQUEST — permanent — and the worker then ends
        the whole session (step 6c live run; increment 6 hit the same class
        from another trigger). Reclassify it, recover the context, leave the
        vision turn, and say so out loud instead of going silent. Auth failures
        stay permanent."""
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


VOICE_TEMPERATURE = 0.7
VOICE_TOP_P = 0.8


def _model_has_vision(base_url: str, model: str) -> bool:
    """`/api/show` capabilities include "vision". Any failure -> False, and the
    vision path then refuses honestly instead of sending an image."""
    import json as _json
    import urllib.request

    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3].rstrip("/")
    try:
        req = urllib.request.Request(root + "/api/show", _json.dumps({"model": model}).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1.5) as r:
            return "vision" in (_json.loads(r.read()).get("capabilities") or [])
    except Exception:
        return False


def build_llm(*, system_instruction: str | None = None):
    """A `SeamLLMService` on the local server: one OpenAI-compatible LLM stage,
    one resident model for text, vision and tool routing.

    Default `qwen3.5:4b-q4_K_M` (step 9, measured in 5c): natively multimodal,
    so a vision turn is the same model with a different request. It thinks by
    default, and on `/v1` only `reasoning_effort:"none"` turns that off — the
    `think:false` / `chat_template_kwargs` this used to send are ignored there
    (5c §1.3; re-verified on Ollama 0.40.5). Pinned GGUF tag, never bare.

    The name is resolved against what is actually pulled (a quant suffix is
    fine); if it is missing or has no vision capability, vision turns say so
    plainly rather than crash. Override with `WELLSY_LLM_MODEL` /
    `WELLSY_LLM_BASE_URL`."""
    from engine.agent.models import DEFAULT_MODEL, REQUEST_EXTRA_BODY

    base_url = os.environ.get("WELLSY_LLM_BASE_URL", "http://localhost:11434/v1")
    requested = os.environ.get("WELLSY_LLM_MODEL", DEFAULT_MODEL)
    model = _resolve_ollama_model(base_url, requested) or requested
    vlm_ok = _model_has_vision(base_url, model)
    # `keep_alive: -1` pins the model resident so the cold reload does not tax
    # every idle-gap turn; `reasoning_effort: "none"` is the off-switch.
    return SeamLLMService(
        api_key=os.environ.get("WELLSY_LLM_API_KEY", "ollama"),
        base_url=base_url,
        settings=SeamLLMService.Settings(
            model=model, system_instruction=system_instruction,
            # Qwen3.5 card, "Instruct (or non-thinking) mode for general tasks":
            # temperature 0.7, top_p 0.8, top_k 20, presence_penalty 1.5
            # (verified 2026-10-17). Ollama's defaults are the THINKING-mode
            # row (1.0 / 0.95); top_k and presence_penalty already match.
            temperature=VOICE_TEMPERATURE, top_p=VOICE_TOP_P,
            extra={"extra_body": dict(REQUEST_EXTRA_BODY)},
        ),
        model=model, vlm_ok=vlm_ok,
    )
