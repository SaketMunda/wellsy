"""Step 4c acceptance #6 — the regression test that would have caught this.

Playback is routed back into the input path (a fake STT that turns mic audio
into the bot's *own* words, exactly as laptop speakers did on 2026-09-02), and
we assert **no self-transcript reaches the LLM**.

Nothing in the step-4 suite caught the loop because every step-4 number came
from a file-injection harness with no speaker in the room. This puts the speaker
in the room, in software: the half-duplex gate (layer 1) and the self-echo
filter (layer 2) are each shown to stop it on their own.
"""

from __future__ import annotations

import asyncio

from engine.voice.duplex import (
    SelfEchoWindow,
    build_echo_text_tap,
    build_half_duplex_gate,
    build_self_echo_filter,
)

BOT_LINE = "I can't share deeds as I don't have physical access to your files."
# what the speakers fed back through STT, per the live log
ECHO_FRAGMENTS = ["I can't share deep.", "I can't share her.", "I can't share."]


def _build_fake_stt(transcripts):
    """A stand-in STT: each InputAudioRawFrame becomes the next TranscriptionFrame
    in `transcripts` (the bot's own words, as the room fed them back)."""
    from pipecat.frames.frames import Frame, InputAudioRawFrame, TranscriptionFrame
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    pending = list(transcripts)

    class FakeSTT(FrameProcessor):
        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)
            if isinstance(frame, InputAudioRawFrame) and pending:
                text = pending.pop(0)
                await self.push_frame(
                    TranscriptionFrame(text, "", "t", finalized=True), direction
                )
                return
            await self.push_frame(frame, direction)

    return FakeSTT()


def _audio(n=320):
    from pipecat.frames.frames import InputAudioRawFrame

    return InputAudioRawFrame(audio=b"\x00\x01" * n, sample_rate=16000, num_channels=1)


async def _run(mode: str, *, self_echo: bool, extra_user: str | None = None):
    from pipecat.frames.frames import BotStartedSpeakingFrame, TTSTextFrame, TranscriptionFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.tests.utils import run_test

    fed = list(ECHO_FRAGMENTS)
    if extra_user is not None:
        fed.append(extra_user)

    window = SelfEchoWindow(ttl_s=60.0)
    gate = build_half_duplex_gate(tail_ms=50, mode=mode)
    tap = build_echo_text_tap(window)
    stt = _build_fake_stt(fed)
    stages = [gate, tap, stt]
    if self_echo:
        stages.append(build_self_echo_filter(window, threshold=0.8))
    pipeline = Pipeline(stages)

    frames_in = [
        BotStartedSpeakingFrame(),
        TTSTextFrame(BOT_LINE, aggregated_by="sentence"),   # the bot says its line -> window
        _audio(), _audio(), _audio(),    # the room feeds that line back as mic audio
    ]
    if extra_user is not None:
        frames_in.append(_audio())       # a genuine, different user utterance

    down, _up = await run_test(pipeline, frames_to_send=frames_in)
    return [f.text for f in down if isinstance(f, TranscriptionFrame)]


def test_half_duplex_gate_alone_stops_the_loop():
    # layer 1: mic audio is dropped at the gate during playback, so the fake STT
    # never even sees it -> no transcript at all.
    leaked = asyncio.run(_run("mute", self_echo=False))
    assert leaked == [], f"self-transcript leaked past the half-duplex gate: {leaked}"


def test_self_echo_filter_alone_stops_the_loop():
    # layer 2: gate disabled (mode="full", the step-4 behaviour). The fake STT
    # produces the bot's own words, but the self-echo filter drops every one.
    leaked = asyncio.run(_run("full", self_echo=True))
    assert leaked == [], f"self-transcript leaked past the self-echo filter: {leaked}"


def test_both_layers_off_the_loop_is_reproduced():
    # the regression itself: no gate, no filter -> the bot's words reach the LLM.
    leaked = asyncio.run(_run("full", self_echo=False))
    assert leaked == ECHO_FRAGMENTS[:3], leaked


def test_genuine_user_speech_still_reaches_the_llm():
    # the fixes must not make the assistant deaf to a real follow-up spoken
    # after the bot stops. mode="full" + filter on: only the echo is dropped.
    leaked = asyncio.run(_run("full", self_echo=True, extra_user="what time is it"))
    assert "what time is it" in leaked
    assert not any(frag in leaked for frag in ECHO_FRAGMENTS[:3])
