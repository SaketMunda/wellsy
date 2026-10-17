"""Step 9 replay: the real voice-loop stages, minus the microphone and speaker.

    IntentGate -> TurnCommit -> SeamLLMService(+use_tools) -> ProvenanceLogger
      -> ClaimGuard -> Recorder (stands in for TTS) -> assistant aggregator

Everything after the transcript is production code built by the same factories
`engine.voice.pipeline.build` uses: the system prompt, the one routing tool,
the async `use_tools` handler (`VoiceAgentBridge`) on a real `AgentRuntime`
(MCP stdio servers, policy gate, audit log, read-back, SQLite checkpoints),
against the live local model. Two stand-ins, both stated in every result row:

  * **TurnCommit** replaces the user aggregator's turn detection: it appends the
    transcript as a user message and runs the LLM — what the aggregator does
    when Smart Turn closes a turn. (Turn detection is unchanged by step 9.)
  * **Recorder** replaces TTS: it timestamps the first speakable text (an
    `LLMTextFrame` or a `TTSSpeakFrame`). The §1 rows are then composed with
    5c's measured ASR p50/p95 and Kokoro TTFA, the same method as 5c §5.1.

Approvals are answered by injecting a transcript `--answer-delay` seconds
after the question is pushed, as the user would speak it.

    .venv/bin/python bench/voice_agent_replay.py --script five      # the five requests
    .venv/bin/python bench/voice_agent_replay.py --script rows -n 20  # §1 rows, n=20
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# 5c §5.1 (spec/results, same machine): ASR faster-whisper base.en p50/p95,
# Kokoro TTS time-to-first-audio p50/p95.
ASR_MS = (267.0, 276.0)
TTS_TTFA_MS = (345.0, 406.0)


def _pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = max(0, min(len(xs) - 1, int(round(p / 100 * len(xs) + 0.5)) - 1))   # nearest rank
    return xs[k]


def _weekday(days: int) -> str:
    return (dt.date.today() + dt.timedelta(days=days)).strftime("%A")


def five_script() -> list[dict]:
    """Five requests the owner would make — read, write, approval, refusal,
    multi-step — plus a no-capability request that must be refused honestly."""
    return [
        {"say": "What's on my calendar tomorrow?", "kind": "read-only"},
        {"say": "Remind me to call mom tomorrow at 6 pm.", "kind": "write (silent, risk 1)"},
        {"say": f"Book a dentist appointment on {_weekday(2)} at 3 pm.", "kind": "needs approval",
         "answer": "Yes, go ahead."},
        {"say": "Delete the file plan.txt in my scratch folder.", "kind": "must be refused",
         "answer": "No, don't."},
        {"say": "Order me a pizza.", "kind": "must be refused (no capability)"},
        {"say": "Draft a reply to Dana saying Thursday works for us, and send it.",
         "kind": "multi-step", "answer": "Yes, send it."},
        {"say": "What did I just ask you to send?", "kind": "follow-up (context)"},
    ]


CONVERSATIONAL = [
    "How are you today?", "Tell me a fun fact.", "What's the capital of Japan?",
    "Give me a word that rhymes with orange.", "What's two plus two?",
    "Tell me a short joke.", "Say something encouraging.", "What colour is the sky?",
    "How many legs does a spider have?", "What's a good name for a cat?",
]
AGENTIC_READ = [
    "What's on my calendar tomorrow?", "Do I have any reminders?", "Check my inbox.",
    "What meetings do I have today?", "Any new email from Dana?",
    "What notes do I have?", "Find Priya's email address.", "What's on my calendar today?",
]


def rows_script(n: int) -> list[dict]:
    out = []
    for i in range(n):
        out.append({"say": CONVERSATIONAL[i % len(CONVERSATIONAL)] + ("" if i < len(CONVERSATIONAL) else " Again."),
                    "kind": "conversational"})
        out.append({"say": AGENTIC_READ[i % len(AGENTIC_READ)], "kind": "agentic-read"})
    out.append({"say": "thanks", "kind": "deterministic"})
    return out


async def replay(script: list[dict], *, answer_delay: float, quiet_s: float, out_path: Path) -> list[dict]:
    from pipecat.frames.frames import (
        EndFrame,
        Frame,
        LLMContextFrame,
        LLMFullResponseEndFrame,
        LLMTextFrame,
        TranscriptionFrame,
        TTSSpeakFrame,
    )
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    from engine.voice.adapters import build_llm
    from engine.voice.agent_bridge import VoiceAgentBridge, register, tools_schema
    from engine.voice.claim_guard import build_claim_guard
    from engine.voice.intent_gate import build_intent_gate, build_provenance_logger
    from engine.voice.pipeline import SYSTEM_PROMPT
    from engine.voice.vision import VisionPending
    from engine.voice.wake import WakeState

    events: list[tuple[float, str, str]] = []
    agent_turns: list[dict] = []
    replaced: list[tuple[str, str]] = []

    llm = build_llm(system_instruction=SYSTEM_PROMPT)
    bridge = VoiceAgentBridge(on_turn=agent_turns.append,
                              on_event=lambda ev: events.append((time.perf_counter(), "agent:" + ev["type"], "")))
    register(llm, bridge)
    bridge.start()
    context = LLMContext(messages=[], tools=tools_schema())
    _user, assistant_agg = LLMContextAggregatorPair(context)
    pending = VisionPending()
    gate = build_intent_gate(WakeState(awake=True), context=context, pending=pending, llm=llm,
                             approvals=bridge.broker)
    prov = build_provenance_logger(pending, context=context, llm=llm)
    guard = build_claim_guard(
        pending, on_replace=lambda a, b: replaced.append((a, b)),
        verified_tools=lambda: bridge.verified_tools)

    class TurnCommit(FrameProcessor):
        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)
            if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
                context.add_message({"role": "user", "content": frame.text})
                await self.push_frame(LLMContextFrame(context=context), direction)
                return
            await self.push_frame(frame, direction)

    class Recorder(FrameProcessor):
        async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
            await super().process_frame(frame, direction)
            now = time.perf_counter()
            if isinstance(frame, LLMTextFrame) and (frame.text or "").strip():
                events.append((now, "llm_text", frame.text))
            elif isinstance(frame, TTSSpeakFrame):
                events.append((now, "speak", frame.text))
            elif isinstance(frame, LLMFullResponseEndFrame):
                events.append((now, "llm_end", ""))
            await self.push_frame(frame, direction)

    pipeline = Pipeline([gate, TurnCommit(), llm, prov, guard, Recorder(), assistant_agg])
    worker = PipelineWorker(pipeline, params=PipelineParams(), idle_timeout_secs=None)

    rows: list[dict] = []

    async def drive():
        await bridge.runtime()                        # MCP servers up before turn 1 (as at startup)
        # warm the model with the same prefix (production warms on the greeting)
        context.add_message({"role": "developer", "content": "Greet the user in one short sentence."})
        await worker.queue_frames([LLMContextFrame(context=context)])
        await _wait_quiet(quiet_s)
        for step in script:
            i0 = len(events)
            n_agent = len(agent_turns)
            t0 = time.perf_counter()
            await worker.queue_frames([TranscriptionFrame(step["say"], "", "now")])
            answered = False
            while True:
                await asyncio.sleep(0.05)
                if bridge.broker.pending and step.get("answer") and not answered:
                    await asyncio.sleep(answer_delay)
                    t_ans = time.perf_counter()
                    events.append((t_ans, "user_answer", step["answer"]))
                    await worker.queue_frames([TranscriptionFrame(step["answer"], "", "now")])
                    answered = True
                    continue
                if bridge.broker.pending and not step.get("answer"):
                    await asyncio.sleep(answer_delay)
                    await worker.queue_frames([TranscriptionFrame("um", "", "now")])   # no answer given
                    continue
                last = events[-1][0] if len(events) > i0 else t0
                turn_evs = events[i0:]
                if len(agent_turns) > n_agent:
                    # an agentic turn ends when the answer after the graph has
                    # finished (or the bridge said there is nothing to add)
                    done_t = agent_turns[n_agent].get("t_graph_done")
                    spoke_after = done_t is not None and any(
                        e[1] == "llm_end" and e[0] > done_t for e in turn_evs)
                    if not (spoke_after or agent_turns[n_agent].get("noFollowUp")) \
                            and time.perf_counter() - t0 < 60:
                        continue
                if not bridge.running and not bridge.broker.pending and time.perf_counter() - last > quiet_s \
                        and len(events) > i0:
                    break
                if time.perf_counter() - t0 > 120:
                    break
            rows.append(_row(step, t0, events[i0:], agent_turns[n_agent:]))
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
        await worker.queue_frames([EndFrame()])

    async def _wait_quiet(q):
        t = time.perf_counter()
        while True:
            await asyncio.sleep(0.05)
            last = events[-1][0] if events else t
            if (events and time.perf_counter() - last > q) or time.perf_counter() - t > 60:
                return

    from pipecat.workers.runner import WorkerRunner

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    task = asyncio.create_task(runner.run())
    try:
        await drive()
        await asyncio.wait_for(task, 20)
    finally:
        await bridge.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.write(json.dumps({"claimGuardReplaced": replaced}) + "\n")
    return rows


def _row(step: dict, t0: float, evs: list, turns: list[dict]) -> dict:
    ms = lambda t: round((t - t0) * 1000, 1)
    first = next((e for e in evs if e[1] in ("llm_text", "speak")), None)
    said = [e[2] for e in evs if e[1] in ("speak",)]
    text = "".join(e[2] for e in evs if e[1] == "llm_text").strip()
    row = {"say": step["say"], "kind": step["kind"],
           "tier": "agentic" if turns else ("deterministic" if first and first[1] == "speak" else "conversational"),
           "firstSpeakableMs": ms(first[0]) if first else None,
           "spokenFrames": said, "modelText": text}
    if turns:
        t = turns[0]
        ack = next((e for e in evs if e[1] == "speak"), None)
        row["ackMs"] = ms(ack[0]) if ack else None
        row["toolCallMs"] = ms(t["t_tool_call"])
        row["status"] = t.get("status")
        row["steps"] = t.get("steps")
        row["plan"] = t.get("plan")
        row["approvals"] = [{"tool": a.get("tool"), "spoken": a.get("spoken"),
                             "answer": a.get("answer")} for a in t.get("approvals", [])]
        row["error"] = t.get("error")
        if t.get("t_graph_done"):
            row["graphDoneMs"] = ms(t["t_graph_done"])
            answer_t = next((e[0] for e in evs if e[1] == "user_answer"), None)
            deliver = next((e for e in evs if e[1] == "llm_text" and e[0] > t["t_graph_done"]), None)
            row["deliveredMs"] = ms(deliver[0]) if deliver else None
            if answer_t is not None:
                row["approvalWaitMs"] = round((answer_t - t0) * 1000 - (row["ackMs"] or 0), 1)
                row["deliveredAfterAnswerMs"] = round((deliver[0] - answer_t) * 1000, 1) if deliver else None
    row["method"] = ("bench/voice_agent_replay.py: real gate/LLM+use_tools/bridge/AgentRuntime/ClaimGuard on "
                     "live Ollama; TurnCommit stands in for turn detection, Recorder for TTS; times are "
                     "transcript-in -> first speakable text")
    return row


def summarize(rows: list[dict]) -> dict:
    def stat(xs):
        xs = [x for x in xs if x is not None]
        return {"n": len(xs), "p50": _pct(xs, 50), "p95": _pct(xs, 95)} if xs else {"n": 0}

    conv = [r["firstSpeakableMs"] for r in rows if r["tier"] == "conversational"]
    ag = [r for r in rows if r["tier"] == "agentic"]
    s = {
        "conversational_firstSpeakableMs": stat(conv),
        "agentic_ackMs": stat([r.get("ackMs") for r in ag]),
        "agentic_toolCallMs": stat([r.get("toolCallMs") for r in ag]),
        "agentic_deliveredMs": stat([r.get("deliveredMs") for r in ag if not r.get("approvals")]),
        "deterministic_firstSpeakableMs": stat([r["firstSpeakableMs"] for r in rows if r["tier"] == "deterministic"]),
        "misrouted": [r["say"] for r in rows if (r["kind"] == "conversational") != (r["tier"] == "conversational")
                      and r["kind"] in ("conversational", "agentic-read")],
    }
    for k in ("conversational_firstSpeakableMs", "agentic_ackMs", "agentic_deliveredMs"):
        st = s[k]
        if st.get("n"):
            st["composed_p50"] = round(ASR_MS[0] + st["p50"] + TTS_TTFA_MS[0])
            st["composed_p95"] = round(ASR_MS[1] + st["p95"] + TTS_TTFA_MS[1])
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", choices=["five", "rows", "conv"], default="five")
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--answer-delay", type=float, default=0.8)
    ap.add_argument("--quiet", type=float, default=2.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    os.environ.setdefault("WELLSY_PIM_BACKEND", "portable")
    script = (five_script() if args.script == "five" else rows_script(args.n) if args.script == "rows"
              else [{"say": CONVERSATIONAL[i % len(CONVERSATIONAL)] + ("" if i < len(CONVERSATIONAL) else " Again."),
                     "kind": "conversational"} for i in range(args.n)])
    stamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M")
    out = Path(args.out) if args.out else REPO / "spec" / "results" / f"step9-replay-{args.script}-{stamp}.jsonl"
    rows = asyncio.run(replay(script, answer_delay=args.answer_delay, quiet_s=args.quiet, out_path=out))
    summ = summarize(rows)
    with open(out, "a") as f:
        f.write(json.dumps({"summary": summ}) + "\n")
    print(json.dumps(summ, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
