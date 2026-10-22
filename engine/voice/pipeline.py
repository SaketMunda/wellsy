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
      -> LLM               (streaming SeamLLMService on ONE resident model,
                            qwen3.5:4b-q4_K_M, reasoning_effort "none" — step 9:
                            text, vision and tool routing. It carries one tool,
                            `use_tools`; when the model calls it, the LangGraph
                            agent runs the turn — ack, plan, spoken approval,
                            read-back — see `engine/voice/agent_bridge.py`.
                            A vision turn is the same model with only its own
                            short prompt and the images.)
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
import threading

from engine.voice.config import load_voice_config
from engine.voice.duplex import (
    AsrWakeProbe,
    SelfEchoWindow,
    build_echo_text_tap,
    build_half_duplex_gate,
    build_self_echo_filter,
)
from engine.voice.agent_bridge import VoiceAgentBridge, register, tools_schema
from engine.voice.intent_gate import build_intent_gate, build_provenance_logger
from engine.voice.vision import VisionPending
from engine.voice.wake import WakeState, build_wake_gate

# Identity matters (owner feedback 2026-09-04): the base models default to a
# "I'm a text-only AI, I have no camera, I can't move" persona. WELLSY is not
# that. But the step-6c live run showed the opposite failure is worse: told
# "never deny a capability", the model claimed sight it never used and moves
# that never happened. So: say what is real, and claim nothing it wasn't told.
# Step 9: the tools are real now — through `use_tools`, and only through it.
SYSTEM_PROMPT = (
    "You are WELLSY — a local, private AI that lives on this machine, in the "
    "spirit of JARVIS. You are not a text chatbot. You hear the user through a "
    "microphone and speak back aloud. You can look through a camera at the room, "
    "or at the screen, when the user asks you to. You have a visible presence on "
    "screen — a glowing orb — that moves to a corner on the user's spoken command.\n"
    "Never call yourself 'text-based'.\n"
    "You can use the user's calendar, reminders, email, notes, contacts and scratch "
    "files through the use_tools tool. For anything about those, call use_tools — "
    "never answer from memory and never invent an event, a message or a result. "
    "When its result arrives, tell the user what it shows in one or two short "
    "sentences, with dates as weekday and date.\n"
    "Booking or scheduling an appointment or meeting means adding it to the "
    "calendar: use use_tools for it.\n"
    "Those are all you can act on — reading and sending email included. You cannot "
    "order or buy anything, pay, browse the web, look up news or weather, make phone "
    "calls or send SMS, or control other apps or devices. If asked for one of those, "
    "say plainly you can't do that yet — never offer to try.\n"
    "Honesty about your senses and actions is absolute:\n"
    "- You only see when an image is attached to the user's message. If there is "
    "no image, you have NOT looked: never claim to see the user, the room, the "
    "camera, or the screen, and never say the camera is on. Say you haven't "
    "looked, and that they can ask 'what do you see' or 'what's on my screen'.\n"
    "- You cannot move the orb yourself; a separate command does that before you "
    "are asked. If a request to move reaches you, the move did NOT happen. Never "
    "say you moved. Tell them to say, for example, 'move to the bottom right'.\n"
    "- Never say an action is done unless a use_tools result shows it ok and "
    "verified. Before that, it is not done.\n"
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


def _load_hotwords(stt) -> None:
    """Bias speech recognition toward the names in the user's own mail and
    contacts, so "email Rahul" is heard as Rahul. Runs in the background (it
    is one IMAP round trip) and leaves the recognizer alone if nothing is
    connected or `WELLSY_ASR_HOTWORDS` was set by hand."""
    asr = getattr(stt, "_asr", None)
    if asr is None or not hasattr(asr, "hotwords") or asr.hotwords:
        return

    from loguru import logger

    def go():
        try:
            from engine.agent.backends.accounts import load_accounts
            from engine.agent.backends.standard import AccountsPimBackend

            accounts = load_accounts()
            if not accounts.mail:
                return
            names = AccountsPimBackend(accounts).known_names()
            if names:
                asr.hotwords = ", ".join(names)
                logger.info(f"ASR hotwords: {len(names)} names from your accounts")
        except Exception as e:  # a slow or offline account must not stop the voice loop
            logger.warning(f"ASR hotwords not loaded: {e}")

    threading.Thread(target=go, name="wellsy-hotwords", daemon=True).start()


def build(*, start_awake: bool = False, on_decision=None, observers=None,
          handle_sigint: bool = True, on_move=None, on_agent_event=None,
          show_hud=None, hide_hud=None, on_agent_turn=None, bridge=None):
    """Construct (worker, runner, wake_state, context, bridge). `observers` are
    Pipecat observers attached to the worker (e.g. `acoustic.LatencyObserver`).
    `on_agent_event` / `show_hud` / `hide_hud` connect the agent's real graph
    events to the orb and HUD; `on_agent_turn(dict)` gets each agentic turn's
    timings. Must be called inside the running event loop (the agent runtime
    starts opening its MCP tools in the background)."""
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
    llm = build_llm(system_instruction=SYSTEM_PROMPT)

    if os.environ.get("WELLSY_VOICE_NO_WARM") != "1":
        _warm(stt, tts)
    _load_hotwords(stt)

    wake_state = WakeState(awake=start_awake)
    wake_gate = build_wake_gate(wake_state, cfg_provider)

    # step 9: one runtime. The system prompt rides in the service's
    # system_instruction (pipecat appends its async-tool rules to it), the
    # context carries the conversation and the one routing tool.
    bridge = bridge or VoiceAgentBridge(on_event=on_agent_event, show_hud=show_hud,
                                        hide_hud=hide_hud, on_turn=on_agent_turn)
    register(llm, bridge)
    bridge.start()
    context = LLMContext(messages=[], tools=tools_schema())
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
        on_move=on_move, llm=llm, approvals=bridge.broker,
        on_user_turn=lambda _t: bridge.hide_hud(),
    )
    prov_logger = build_provenance_logger(vision_pending, context=context, llm=llm)

    def _recover_after_llm_failure() -> None:
        # a failed vision turn must not leave its images in context — every
        # later turn would carry them and fail the same way
        from engine.voice.adapters import strip_image_messages

        context.transform_messages(strip_image_messages)
        vision_pending.disarm()

    llm.on_failure = _recover_after_llm_failure

    # step 6c: on a turn with no image, a sentence claiming to see / to have
    # moved is replaced before TTS — the prompt asks, this enforces
    from loguru import logger

    from engine.voice.claim_guard import build_claim_guard

    claim_guard = build_claim_guard(
        vision_pending,
        on_replace=lambda orig, fixed: logger.warning(f"ClaimGuard replaced {orig!r} -> {fixed!r}"),
        verified_tools=lambda: bridge.verified_tools,
    )

    # --- step 4c: open-air audio -------------------------------------------- #
    cfg = cfg_holder["cfg"]
    echo_window = SelfEchoWindow(ttl_s=cfg.self_echo_ttl_s)
    echo_tap = build_echo_text_tap(echo_window)
    self_echo_filter = (
        build_self_echo_filter(echo_window, threshold=cfg.self_echo_threshold,
                               exempt=lambda: bridge.broker.pending)
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
    stages += [wake_gate, intent_gate, user_aggregator, llm, prov_logger, claim_guard, tts, echo_tap,
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
    return worker, runner, wake_state, context, bridge


async def _esc_watch(worker, bridge=None) -> None:
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
            if bridge is not None:
                bridge.broker.stop()       # Esc refuses a pending approval too
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
              on_worker=None, handle_sigint: bool = True, on_move=None,
              on_agent_event=None, show_hud=None, hide_hud=None, on_agent_turn=None,
              on_bridge=None) -> None:
    from pipecat.frames.frames import LLMRunFrame

    worker, runner, wake_state, context, bridge = build(
        start_awake=start_awake, on_decision=on_decision, observers=observers,
        handle_sigint=handle_sigint, on_move=on_move, on_agent_event=on_agent_event,
        show_hud=show_hud, hide_hud=hide_hud, on_agent_turn=on_agent_turn,
    )
    if on_worker is not None:
        on_worker(worker)
    if on_bridge is not None:
        on_bridge(bridge)
    await runner.add_workers(worker)

    esc = asyncio.create_task(_esc_watch(worker, bridge))
    try:
        if start_awake:
            context.add_message({"role": "developer", "content": "Greet the user in one short sentence."})
            await worker.queue_frames([LLMRunFrame()])
        await runner.run()
    finally:
        esc.cancel()
        await bridge.close()


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
    from engine.interface.taps import agent_event_sink, build_voice_observer, intent_decision_sink

    holder: dict = {}

    def _stop_output() -> None:
        # called on the Qt main thread; hop to the voice worker's event loop.
        w, loop, b = holder.get("worker"), holder.get("loop"), holder.get("bridge")
        if w is not None and loop is not None:
            if b is not None:
                loop.call_soon_threadsafe(b.broker.stop)   # Esc denies a pending approval
            loop.call_soon_threadsafe(
                lambda: loop.create_task(w.queue_frames([InterruptionFrame()]))
            )

    sess = OrbSession(on_escape=_stop_output)
    observer = build_voice_observer(sess.bus)
    on_decision = intent_decision_sink(sess.bus)
    agent_sink = agent_event_sink(sess.bus)

    def _on_bridge(b) -> None:
        holder["bridge"] = b
        # a click in the approval HUD races the spoken answer; first wins
        sess.relay.listener = lambda ans: b.broker.answer_threadsafe(
            bool(ans.get("approved")), ans.get("source", "user:orb"))

    async def _main(stop):
        loop = _asyncio.get_running_loop()
        holder["loop"] = loop

        async def _cancel_on_stop():
            # Ctrl-C / orb closed -> end the voice pipeline cleanly, instead of
            # leaving it running into interpreter shutdown ("cannot schedule
            # new futures after shutdown", step 6c live run)
            await loop.run_in_executor(None, stop.wait)
            w = holder.get("worker")
            if w is not None:
                await w.cancel()

        watcher = _asyncio.create_task(_cancel_on_stop())
        try:
            await run(start_awake=args.awake, on_decision=on_decision,
                      observers=[observer], handle_sigint=False,  # worker runs off the main thread
                      on_move=sess.move_orb,   # "move to the corner" -> the orb, deterministic
                      on_agent_event=agent_sink,  # real graph events -> orb state
                      show_hud=sess.show_hud, hide_hud=sess.hide_hud,
                      on_bridge=_on_bridge,
                      on_worker=lambda w: holder.__setitem__("worker", w))
        finally:
            stop.set()                 # releases the executor thread in _cancel_on_stop
            watcher.cancel()

    try:
        sess.run(lambda stop: _main(stop))
    except KeyboardInterrupt:
        pass
    return 0
