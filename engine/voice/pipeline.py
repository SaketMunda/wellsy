"""Build and run the streaming voice pipeline.

    transport.input()
      -> HalfDuplexGate     (step 4c: drops mic audio while the bot speaks + a
                            decay tail so VAD/STT never hear the playback;
                            InterruptionFrame/ESC always pass. Default on.)
      -> SeamSTT           (transcribes every VAD-gated utterance)
      -> SelfEchoFilter    (step 4c: drops any transcript that fuzzy-matches
                            something the bot just said — see EchoTextTap below)
      -> WakeGate          (asleep: only a wake phrase passes)
      -> IntentGate        (deterministic stop/wake/sleep/help — INVARIANTS #3;
                            describe_scene / query_object -> capture + verify a
                            frame, attach to context, run the VLM)
      -> user_aggregator
      -> LLM/VLM           (streaming SeamLLMService; qwen2.5:3b text by default,
                            non-reasoning; a vision turn flips it to the VL model
                            (qwen3-vl:2b-instruct / WELLSY_VLM_MODEL) and back. If
                            no VL model is pulled the gate says so, no image sent)
      -> ProvenanceLogger  (vision turns: one provenance line per answer with the
                            step-3 capture provenance folded in; drops the image)
      -> SeamTTS           (sentence-chunked; first audio before the LLM finishes)
      -> EchoTextTap       (step 4c: records each spoken sentence into the
                            rolling window SelfEchoFilter reads)
      -> transport.output()
      -> assistant_aggregator

VAD (Silero v5) and semantic turn detection (Smart Turn v3) are Pipecat
defaults in 1.8.x — the fixed 600 ms silence tail of the old build is gone; the
per-turn saving is what `metrics.py` measures. Open-air on speakers is
half-duplex by default (the HalfDuplexGate); spoken barge-in during playback
needs the wake-gated mode or AEC — see `engine/voice/duplex.py` /
`engine/voice/aec.py` and `.claude/rebuild/step4c-results.md`. ESC is the
deterministic instant stop and is never gated.
"""

from __future__ import annotations

import asyncio
import os
import sys

from engine.voice.config import load_voice_config
from engine.voice.duplex import (
    AsrWakeProbe,
    SelfEchoWindow,
    build_echo_text_tap,
    build_half_duplex_gate,
    build_self_echo_filter,
)
from engine.voice.intent_gate import build_intent_gate, build_provenance_logger
from engine.voice.vision import VisionPending
from engine.voice.wake import WakeState, build_wake_gate

# Default LLM is qwen2.5:3b (non-reasoning — step 4b). qwen3 overrides get
# `think:false` via extra_body in adapters.build_llm(); that build ignores it
# today, but this prompt stays model-agnostic.
#
# Identity matters (owner feedback 2026-09-04): the base models default to a
# "I'm a text-only AI, I have no camera, I can't move" persona. WELLSY is not
# that — she runs locally, sees through a camera and the screen, speaks aloud,
# and has a visible presence (an orb) she can reposition. She must never deny a
# capability she has.
SYSTEM_PROMPT = (
    "You are WELLSY — a local, private AI that lives on this machine, in the "
    "spirit of JARVIS. You are not a text chatbot. You hear the user through a "
    "microphone and speak back aloud. You can see: a live camera of the room and "
    "the screen, on demand. You have a visible presence on screen — a glowing orb "
    "— and you can move it to any corner when asked. You can run tools: calendar, "
    "mail drafts, reminders, notes, files, and web search.\n"
    "Because of this: never say you are 'text-based', never say you cannot see or "
    "have no camera, never say you cannot move. If the user asks what you see, "
    "answer from the camera or screen. If they ask you to move, it is already "
    "being handled — just acknowledge briefly.\n"
    "You are speaking aloud: reply in one or two short spoken sentences. No lists, "
    "no markdown, no emoji. If you genuinely do not know something, say so plainly."
)

AUDIO_IN_SR = 16000   # Silero VAD + Smart Turn v3 + Whisper all want 16 kHz
AUDIO_OUT_SR = 24000  # Kokoro native rate


def _warm(stt, tts) -> None:
    """Run one throwaway ASR + TTS inference so turn 1 is not the cold turn.
    Cold faster-whisper is ~1.3 s vs ~0.26 s warm; cold Kokoro TTFA ~0.76 s vs
    ~0.05 s. The LLM warms on its first real call (`keep_alive: -1` then pins
    it). Skippable with WELLSY_VOICE_NO_WARM=1."""
    import numpy as np

    try:
        list(stt._asr.stream(iter([np.zeros(16000, dtype=np.float32)])))
    except Exception:
        pass
    try:
        for _ in tts._tts.stream(iter(["ready"])):
            break
    except Exception:
        pass


def build(*, start_awake: bool = False, on_decision=None, observers=None,
          handle_sigint: bool = True, on_move=None):
    """Construct (worker, runner, wake_state, context). `observers` are Pipecat
    observers attached to the worker (e.g. `acoustic.LatencyObserver`)."""
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

    if os.environ.get("WELLSY_VOICE_NO_WARM") != "1":
        _warm(stt, tts)

    wake_state = WakeState(awake=start_awake)
    wake_gate = build_wake_gate(wake_state, cfg_provider)

    context = LLMContext(messages=[{"role": "system", "content": SYSTEM_PROMPT}])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    # Vision turns (describe_scene / query_object): IntentGate captures + verifies
    # a frame and appends it to `context`; the provenance logger, after the LLM,
    # writes the answer line with the capture provenance folded in and drops the
    # image from context (step 3 "on-demand only").
    vision_pending = VisionPending()
    intent_gate = build_intent_gate(
        wake_state, context=context, pending=vision_pending, on_decision=on_decision,
        on_move=on_move, llm=llm,
    )
    prov_logger = build_provenance_logger(vision_pending, context=context, llm=llm)

    # --- step 4c: open-air audio -------------------------------------------- #
    cfg = cfg_holder["cfg"]
    echo_window = SelfEchoWindow(ttl_s=cfg.self_echo_ttl_s)
    echo_tap = build_echo_text_tap(echo_window)
    self_echo_filter = (
        build_self_echo_filter(echo_window, threshold=cfg.self_echo_threshold)
        if cfg.self_echo_reject
        else None
    )

    mode = cfg.barge_in_mode if cfg.half_duplex else "full"
    wake_probe = None
    if mode == "wake_gated":
        wake_probe = AsrWakeProbe(
            stt._asr, cfg.wake_phrases, sample_rate=AUDIO_IN_SR,
            threshold=max(cfg.wake_threshold, 0.85),
        )
    half_duplex_gate = build_half_duplex_gate(
        tail_ms=cfg.half_duplex_tail_ms, mode=mode, wake_probe=wake_probe
    )

    stages = [transport.input(), half_duplex_gate, stt]
    if self_echo_filter is not None:
        stages.append(self_echo_filter)
    stages += [wake_gate, intent_gate, user_aggregator, llm, prov_logger, tts, echo_tap,
               transport.output(), assistant_aggregator]
    pipeline = Pipeline(stages)

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=AUDIO_IN_SR,
            audio_out_sample_rate=AUDIO_OUT_SR,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=list(observers or []),
        idle_timeout_secs=None,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )
    runner = WorkerRunner(handle_sigint=handle_sigint)
    return worker, runner, wake_state, context


async def _esc_watch(worker) -> None:
    """Raw-tty ESC -> deterministic instant stop (the old build's 114 ms path).
    No-op when stdin is not a tty.

    Uses `loop.add_reader`, not a blocking `stdin.read` on the default executor:
    that read cannot be cancelled, so on shutdown `asyncio.run` would block
    forever in `shutdown_default_executor()` waiting for a keystroke — the orb
    then hangs the process and Ctrl+C only gets you `zsh: suspended`
    (owner log 2026-09-04)."""
    if not sys.stdin.isatty():
        return
    try:
        import termios
        import tty
    except ImportError:
        return  # non-POSIX (Windows console) — ESC stop is a convenience, not the safety path

    import os

    from pipecat.frames.frames import InterruptionFrame

    loop = asyncio.get_running_loop()
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    done = asyncio.Event()

    def _on_readable() -> None:
        try:
            ch = os.read(fd, 64)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            done.set()
            return
        if not ch:                       # EOF (stdin closed)
            done.set()
            return
        if b"\x1b" in ch or b"q" in ch:
            loop.create_task(worker.queue_frames([InterruptionFrame()]))

    try:
        tty.setcbreak(fd)
        loop.add_reader(fd, _on_readable)
        await done.wait()                # until cancelled at shutdown
    except asyncio.CancelledError:
        pass
    finally:
        try:
            loop.remove_reader(fd)
        except Exception:
            pass
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


async def run(*, start_awake: bool = False, on_decision=None, observers=None,
              on_worker=None, handle_sigint: bool = True, on_move=None) -> None:
    from pipecat.frames.frames import LLMRunFrame

    worker, runner, wake_state, context = build(
        start_awake=start_awake, on_decision=on_decision, observers=observers,
        handle_sigint=handle_sigint, on_move=on_move,
    )
    if on_worker is not None:
        on_worker(worker)
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
    ap.add_argument("--orb", action="store_true",
                    help="show the Presence orb, pulsing to the live VAD / TTS amplitude; Esc stops output")
    ap.add_argument("--measure", action="store_true", help="run the §1 latency harness (component-composed) instead of a live session")
    ap.add_argument("--measure-acoustic", action="store_true",
                    help="live session with the at-the-device latency observer; Ctrl+C writes the acoustic §1 table")
    ap.add_argument("--profile-cpu", metavar="SECONDS", type=float, default=None,
                    help="sample idle CPU for N seconds and exit")
    ap.add_argument("--trials", type=int, default=20, help="warm trials per path for --measure")
    args = ap.parse_args(argv)

    if args.measure or args.profile_cpu is not None:
        from engine.voice import metrics

        return metrics.main(args)

    if args.measure_acoustic:
        from engine.voice import acoustic

        obs = acoustic.LatencyObserver()
        try:
            asyncio.run(run(start_awake=args.awake, on_decision=obs.on_decision, observers=[obs]))
        except KeyboardInterrupt:
            pass
        acoustic.print_summary(obs)
        if obs.turns:
            print(f"\nwrote {acoustic.write_results(obs)}")
        else:
            print("\nno turns captured — nothing written")
        return 0

    if args.orb:
        return _run_with_orb(args)

    try:
        asyncio.run(run(start_awake=args.awake))
    except KeyboardInterrupt:
        pass
    return 0


def _run_with_orb(args) -> int:
    """Live voice session behind the Presence orb. The orb pulses to the
    measured VAD amplitude while you speak and the measured output PCM
    amplitude while it speaks — nothing synthetic (INVARIANTS #6). Esc routes
    to the deterministic InterruptionFrame stop."""
    import asyncio as _asyncio

    from pipecat.frames.frames import InterruptionFrame

    from engine.interface.session import OrbSession
    from engine.interface.taps import build_voice_observer, intent_decision_sink

    holder: dict = {}

    def _stop_output() -> None:
        # called on the Qt main thread; hop to the voice worker's event loop.
        w, loop = holder.get("worker"), holder.get("loop")
        if w is not None and loop is not None:
            loop.call_soon_threadsafe(
                lambda: loop.create_task(w.queue_frames([InterruptionFrame()]))
            )

    sess = OrbSession(on_escape=_stop_output)
    observer = build_voice_observer(sess.bus)
    on_decision = intent_decision_sink(sess.bus)

    async def _main():
        holder["loop"] = _asyncio.get_running_loop()
        await run(start_awake=args.awake, on_decision=on_decision,
                  observers=[observer], handle_sigint=False,  # worker runs off the main thread
                  on_move=sess.move_orb,   # "move to the corner" -> the orb, deterministic
                  on_worker=lambda w: holder.__setitem__("worker", w))

    try:
        sess.run(lambda _stop: _main())
    except KeyboardInterrupt:
        pass
    return 0
