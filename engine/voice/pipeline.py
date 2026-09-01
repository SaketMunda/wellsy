"""Build and run the streaming voice pipeline.

    transport.input()
      -> SeamSTT           (transcribes every VAD-gated utterance)
      -> WakeGate          (asleep: only a wake phrase passes)
      -> IntentGate        (deterministic stop/wake/sleep/help — INVARIANTS #3)
      -> user_aggregator
      -> LLM               (streaming, text-only qwen3:4b by default)
      -> SeamTTS           (sentence-chunked; first audio before the LLM finishes)
      -> transport.output()
      -> assistant_aggregator

VAD (Silero v5) and semantic turn detection (Smart Turn v3) are Pipecat
defaults in 1.8.x — the fixed 600 ms silence tail of the old build is gone; the
per-turn saving is what `metrics.py` measures. Barge-in is on by default while
the bot is speaking; ESC is the deterministic instant stop.
"""

from __future__ import annotations

import asyncio
import os
import sys

from engine.voice.config import load_voice_config
from engine.voice.intent_gate import build_intent_gate
from engine.voice.wake import WakeState, build_wake_gate

# `/no_think` keeps qwen3 from spending seconds on reasoning tokens before the
# first answer token — the voice path cannot afford it (see model-inventory.md).
SYSTEM_PROMPT = (
    "/no_think You are WELLSY, a local voice assistant. You are speaking aloud, so "
    "answer in one or two short spoken sentences. No lists, no markdown, no emoji. "
    "If you do not know, say so plainly."
)

AUDIO_IN_SR = 16000   # Silero VAD + Smart Turn v3 + Whisper all want 16 kHz
AUDIO_OUT_SR = 24000  # Kokoro native rate


def build(*, start_awake: bool = False, on_decision=None):
    """Construct (worker, runner, wake_state, kickoff-coro-factory)."""
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
        LLMUserAggregatorParams,
    )
    from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
    from pipecat.workers.runner import WorkerRunner

    from engine.voice.adapters import SeamSTTService, SeamTTSService, build_llm

    cfg_holder = {"cfg": load_voice_config()}

    def cfg_provider():
        if cfg_holder["cfg"].stale():
            cfg_holder["cfg"] = load_voice_config()
        return cfg_holder["cfg"]

    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=AUDIO_IN_SR,
            audio_out_sample_rate=AUDIO_OUT_SR,
        )
    )

    stt = SeamSTTService(sample_rate=AUDIO_IN_SR)
    tts = SeamTTSService(sample_rate=AUDIO_OUT_SR)
    llm = build_llm()

    wake_state = WakeState(awake=start_awake)
    wake_gate = build_wake_gate(wake_state, cfg_provider)
    intent_gate = build_intent_gate(wake_state, on_decision=on_decision)

    context = LLMContext(messages=[{"role": "system", "content": SYSTEM_PROMPT}])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            wake_gate,
            intent_gate,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=AUDIO_IN_SR,
            audio_out_sample_rate=AUDIO_OUT_SR,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=None,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )
    runner = WorkerRunner(handle_sigint=True)
    return worker, runner, wake_state, context


async def _esc_watch(worker) -> None:
    """Raw-tty ESC -> deterministic instant stop (the old build's 114 ms path).
    No-op when stdin is not a tty."""
    if not sys.stdin.isatty():
        return
    try:
        import termios
        import tty
    except ImportError:
        return  # non-POSIX (Windows console) — ESC stop is a convenience, not the safety path

    from pipecat.frames.frames import InterruptionFrame

    loop = asyncio.get_running_loop()
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            ch = await loop.run_in_executor(None, sys.stdin.read, 1)
            if not ch:
                await asyncio.sleep(0.05)
                continue
            if ch == "\x1b" or ch == "q":
                await worker.queue_frames([InterruptionFrame()])
    except asyncio.CancelledError:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


async def run(*, start_awake: bool = False, on_decision=None) -> None:
    from pipecat.frames.frames import LLMRunFrame

    worker, runner, wake_state, context = build(
        start_awake=start_awake, on_decision=on_decision
    )
    await runner.add_workers(worker)

    esc = asyncio.create_task(_esc_watch(worker))
    try:
        if start_awake:
            context.add_message({"role": "developer", "content": "Greet the user in one short sentence."})
            await worker.queue_frames([LLMRunFrame()])
        await runner.run()
    finally:
        esc.cancel()


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="wellsy voice", description=__doc__)
    ap.add_argument("--awake", action="store_true", help="start awake (skip the wake phrase)")
    ap.add_argument("--measure", action="store_true", help="run the §1 latency harness instead of a live session")
    ap.add_argument("--profile-cpu", metavar="SECONDS", type=float, default=None,
                    help="sample idle CPU for N seconds and exit")
    ap.add_argument("--trials", type=int, default=20, help="warm trials per path for --measure")
    args = ap.parse_args(argv)

    if args.measure or args.profile_cpu is not None:
        from engine.voice import metrics

        return metrics.main(args)

    try:
        asyncio.run(run(start_awake=args.awake))
    except KeyboardInterrupt:
        pass
    return 0
