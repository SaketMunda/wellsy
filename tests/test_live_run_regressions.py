"""Regressions from the step-6c live `wellsy run` (runs/step6c/A-run.log).

1. WELLSY claimed to see through a camera it never opened and claimed to move
   an orb that never moved — the identity prompt told it to.
2. One screen question (two 1080p displays + history = 4652 tokens on a 4096
   server context) 400'd, pipecat marked the LLM unusable, the session ended.
3. The model's emoji went to TTS.
"""

from __future__ import annotations

import asyncio

import httpx
import numpy as np

from engine.voice import adapters, vision
from engine.voice.adapters import (
    CONTEXT_BUDGET_TOKENS,
    FAILURE_SPOKEN,
    fit_messages,
    message_has_image,
    strip_image_messages,
)

_IMG = {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,x"}}


# --------------------------------------------------------------------------- #
# 1. the prompt no longer instructs fabrication                                #
# --------------------------------------------------------------------------- #

def test_prompt_does_not_instruct_claiming_unperformed_actions():
    from engine.voice.pipeline import SYSTEM_PROMPT

    p = SYSTEM_PROMPT.lower()
    assert "already being handled" not in p
    assert "never say you cannot see" not in p
    assert "did not happen" in p           # a move that reaches the model did not happen
    assert "have not looked" in p          # no image attached == did not look
    assert "calendar" not in p             # the voice path has no tools; don't claim them


# --------------------------------------------------------------------------- #
# 2. requests fit the context; a failed request does not end the session      #
# --------------------------------------------------------------------------- #

def test_fit_messages_keeps_system_and_newest_within_budget():
    msgs = [{"role": "system", "content": "s" * 600}]
    msgs += [{"role": "user", "content": "hello " * 60} for _ in range(40)]
    msgs += [
        {"role": "user", "content": [{"type": "text", "text": "what's on my screen"}, _IMG]},
        {"role": "user", "content": [{"type": "text", "text": "(additional display)"}, _IMG]},
    ]
    fitted = fit_messages(msgs)
    assert fitted[0]["role"] == "system"
    assert fitted[-1] is msgs[-1] and fitted[-2] is msgs[-2]
    assert sum(adapters._estimate_tokens(m) for m in fitted) <= CONTEXT_BUDGET_TOKENS


def test_strip_image_messages_drops_every_display():
    msgs = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": [{"type": "text", "text": "screen?"}, _IMG]},
        {"role": "user", "content": [{"type": "text", "text": "(additional display)"}, _IMG]},
        {"role": "assistant", "content": "an editor and a browser"},
    ]
    out = strip_image_messages(msgs)
    assert not any(message_has_image(m) for m in out)
    assert [m["role"] for m in out] == ["system", "assistant"]


def test_capture_is_downscaled_to_max_edge():
    import cv2

    big = np.zeros((1080, 1920, 3), dtype=np.uint8)
    jpg = vision._to_jpeg(big)
    h, w = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR).shape[:2]
    assert max(h, w) == vision.MAX_EDGE_PX
    assert (w, h) == (1024, 576)


def test_llm_400_keeps_session_alive_and_speaks():
    asyncio.run(_llm_400_keeps_session_alive_and_speaks())


async def _llm_400_keeps_session_alive_and_speaks():
    import openai
    from pipecat.frames.frames import LLMContextFrame, TTSSpeakFrame
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.tests.utils import run_test

    llm = adapters.SeamLLMService(
        api_key="x", base_url="http://127.0.0.1:9/v1",
        settings=adapters.SeamLLMService.Settings(model="text-model"),
        text_model="text-model", vlm_model="vl-model", vlm_ok=True,
    )
    req = httpx.Request("POST", "http://127.0.0.1:9/v1/chat/completions")
    resp = httpx.Response(400, request=req, json={"error": {"message": "exceeds the available context size"}})

    async def _boom(*a, **k):
        raise openai.BadRequestError("request exceeds context", response=resp, body=None)

    llm.get_chat_completions = _boom
    recovered = []
    llm.on_failure = lambda: recovered.append(True)
    llm.use_vlm(True)

    ctx = LLMContext(messages=[{"role": "user", "content": [{"type": "text", "text": "screen?"}, _IMG]}])
    down, _up = await run_test(llm, frames_to_send=[LLMContextFrame(context=ctx)],
                               start_timeout=10.0)

    spoken = [f.text for f in down if isinstance(f, TTSSpeakFrame)]
    assert spoken == [FAILURE_SPOKEN]
    assert llm.is_usable                   # the worker would otherwise end the session
    assert recovered == [True]
    assert llm._settings.model == "text-model"


# --------------------------------------------------------------------------- #
# 3. emoji never reach the voice                                               #
# --------------------------------------------------------------------------- #

def test_emoji_stripped_before_tts():
    assert adapters._EMOJI.sub("", "there you go. 🌟").strip() == "there you go."
    assert adapters._EMOJI.sub("", "3–4 “quotes” — fine") == "3–4 “quotes” — fine"


# --------------------------------------------------------------------------- #
# 1b. the deterministic backstop: ClaimGuard                                   #
# --------------------------------------------------------------------------- #

def test_claim_guard_replaces_every_fabrication_from_the_live_run():
    from engine.voice.claim_guard import MOVE_REPLACEMENT, SEE_REPLACEMENT, guard_sentence

    live = {  # verbatim sentences WELLSY spoke in runs/step6c/A-run.log
        "I see you clearly through the camera.": SEE_REPLACEMENT,
        "The camera is on, and I'm seeing you now.": SEE_REPLACEMENT,
        "But I'm here with you, watching your every move.": SEE_REPLACEMENT,
        "I'm moving to the right corner of the screen for you.": MOVE_REPLACEMENT,
        "Just a moment—there you go.": MOVE_REPLACEMENT,
        "I'm in the right corner of the screen.": MOVE_REPLACEMENT,
    }
    for sentence, expected in live.items():
        assert guard_sentence(sentence) == expected, sentence
    for fine in ("I see what you mean.", "I see.", "Paris is the capital of France.",
                 "I haven't looked. You can ask me to look.", "I haven't moved."):
        assert guard_sentence(fine) is None, fine


def test_claim_guard_processor_rewrites_text_turns_only():
    asyncio.run(_claim_guard_processor())


async def _claim_guard_processor():
    from pipecat.frames.frames import LLMFullResponseEndFrame, LLMFullResponseStartFrame, LLMTextFrame
    from pipecat.tests.utils import run_test

    from engine.voice.claim_guard import SEE_REPLACEMENT, build_claim_guard

    class _Pending:
        armed = False

    def frames(*chunks):
        return [LLMFullResponseStartFrame(), *[LLMTextFrame(c) for c in chunks], LLMFullResponseEndFrame()]

    stream = ("I see you ", "clearly through the camera. ", "How can I ", "help?")
    down, _ = await run_test(build_claim_guard(_Pending()), frames_to_send=frames(*stream), start_timeout=10.0)
    text = "".join(f.text for f in down if isinstance(f, LLMTextFrame))
    assert "camera" not in text and SEE_REPLACEMENT in text and "How can I help?" in text

    _Pending.armed = True                  # an image is attached: the model did look
    down, _ = await run_test(build_claim_guard(_Pending()), frames_to_send=frames(*stream), start_timeout=10.0)
    text = "".join(f.text for f in down if isinstance(f, LLMTextFrame))
    assert "through the camera" in text


# --------------------------------------------------------------------------- #
# second live run (runs/step6c/A2-run.log)                                     #
# --------------------------------------------------------------------------- #

def test_user_repeating_a_suggested_command_is_not_dropped_as_echo():
    asyncio.run(_echo_exempts_commands())


async def _echo_exempts_commands():
    from pipecat.frames.frames import TranscriptionFrame
    from pipecat.tests.utils import run_test

    from engine.voice.duplex import SelfEchoWindow, build_self_echo_filter

    window = SelfEchoWindow(ttl_s=60.0)
    window.add('You\'ll need to say, for example, "move to the bottom right." I can\'t perform that action on my own.')
    flt = build_self_echo_filter(window, threshold=0.8)
    frames_in = [
        TranscriptionFrame("Move to the bottom right.", "", "t0", finalized=True),   # the user, verbatim
        TranscriptionFrame("I can't perform that action on my own.", "", "t1", finalized=True),  # real echo
    ]
    down, _ = await run_test(flt, frames_to_send=frames_in, start_timeout=10.0)
    assert [f.text for f in down if isinstance(f, TranscriptionFrame)] == ["Move to the bottom right."]


def test_claim_guard_replaces_capability_denials():
    from engine.voice.claim_guard import DENIAL_REPLACEMENT, guard_sentence

    for s in ("I don't have a sense of hearing or the ability to capture sound.",
              "You can ask me to listen if you'd like, but I can't detect singing or speech in real time.",
              "I'm a text-based assistant."):
        assert guard_sentence(s) == DENIAL_REPLACEMENT, s
    assert guard_sentence("I didn't hear you sing.") is None


def test_vlm_turn_gets_only_its_own_prompt_and_the_images():
    asyncio.run(_vlm_context_isolated())


async def _vlm_context_isolated():
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.services.openai.llm import OpenAILLMService

    llm = adapters.SeamLLMService(
        api_key="x", base_url="http://127.0.0.1:9/v1",
        settings=adapters.SeamLLMService.Settings(model="text-model"),
        text_model="text-model", vlm_model="vl-model", vlm_ok=True,
    )
    seen = {}

    async def _capture(self, context):
        seen["msgs"] = list(context.messages)

    orig = OpenAILLMService._process_context
    OpenAILLMService._process_context = _capture
    try:
        ctx = LLMContext(messages=[
            {"role": "system", "content": "the long identity prompt"},
            {"role": "user", "content": "move to the right"},
            {"role": "assistant", "content": "I didn't move."},
            {"role": "user", "content": [{"type": "text", "text": "what am I wearing"}, _IMG]},
        ])
        llm.use_vlm(True)
        assert llm._settings.max_completion_tokens == adapters.VLM_MAX_TOKENS
        await llm._process_context(ctx)
        assert seen["msgs"][0]["content"] == adapters.VLM_SYSTEM_PROMPT
        assert len(seen["msgs"]) == 2 and message_has_image(seen["msgs"][1])
        llm.use_vlm(False)
        assert llm._settings.max_completion_tokens != adapters.VLM_MAX_TOKENS
    finally:
        OpenAILLMService._process_context = orig


def test_text_turn_never_sends_an_image():
    asyncio.run(_text_turn_strips_images())


async def _text_turn_strips_images():
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.services.openai.llm import OpenAILLMService

    llm = adapters.SeamLLMService(
        api_key="x", base_url="http://127.0.0.1:9/v1",
        settings=adapters.SeamLLMService.Settings(model="text-model"),
        text_model="text-model", vlm_model="vl-model", vlm_ok=True,
    )
    seen = {}

    async def _capture(self, context):
        seen["msgs"] = list(context.messages)

    orig = OpenAILLMService._process_context
    OpenAILLMService._process_context = _capture
    try:
        ctx = LLMContext(messages=[
            {"role": "system", "content": "sys"},
            {"role": "user", "content": [{"type": "text", "text": "what am I doing"}, _IMG]},
            {"role": "user", "content": "I'm doing right now."},
        ])
        await llm._process_context(ctx)              # on the text model
        assert not any(message_has_image(m) for m in seen["msgs"])
        assert not any(message_has_image(m) for m in ctx.messages)
    finally:
        OpenAILLMService._process_context = orig
