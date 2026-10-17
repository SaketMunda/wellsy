# WELLSY Rebuild — Session Index

**Master session context: `.claude/stack-teardown.md` (the audit and every
decision), `spec/phase1-acceptance.md` (the definition of done),
`.claude/rebuild/INVARIANTS.md` (the rules).**

This directory holds one self-contained prompt per rebuild step. Each is written
to be executed in a **fresh session** with no memory of the master session.
Every prompt therefore repeats the context it needs — that redundancy is
deliberate, not sloppy.

## How to use

1. Open a new session in this repo.
2. Paste or reference the step's prompt file.
3. The step is done when its own acceptance criteria pass **and** the scenarios
   it claims from `spec/phase1-acceptance.md` pass.
4. Come back to the master session with the results before starting the next
   step. Steps have ordering dependencies.

## Steps

| # | File | Delivers | Depends on |
|---|---|---|---|
| 1 | `step1-repo-reset.md` | New `engine/` package, perception core ported, `src/` deleted, rename complete | — |
| 2 | `step2-backend-abstraction.md` | Portable inference interfaces + backends + cross-platform benchmark harness | 1 |
| 3 | `step3-capture-layer.md` | Camera + screen capture with degenerate-capture verification. **Fixes the wallpaper defect.** | 1 |
| 4 | `step4-voice-path.md` | Streaming voice on Pipecat: Silero VAD, Smart Turn, streaming ASR/TTS, real barge-in | 2, 3 |
| 4b | `step4b-live-verification.md` | **Owner at the machine.** A8-granted, A14 live, acoustic latency, wake tuning. Wires capture into the VLM path. | 3, 4 |
| 4c | `step4c-echo-and-duplex.md` | **Regression + open-air audio.** Half-duplex gate, self-transcript rejection, wake-gated barge-in, AEC, audio hardware spec | 4 |
| 5 | `step5-agent-runtime.md` | LangGraph runtime, MCP tools, policy gate, audit log, **two model roles** | 2 |
| 5b | `step5b-model-selection.md` | Planner / VLM / fast / TTS chosen on measured numbers; re-derives the hardware sizing | 4, 4b, 5 |
| 6 | `step6-native-interface.md` | **Presence orb + Iron Man HUD.** Native Qt Quick, in-process, no webview. The interface renders measured state only. | 4, 4b, 5 |
| 6b | `step6b-consolidation.md` | **Merge, don't design.** Land step 6 on top of 5b, resolve the model-default collision, fix the red duplex test, re-measure. | 4c, 5b, 6 |
| 5c | `step5c-model-rebaseline.md` | **The 2026 set, measured.** Qwen3.5 / Gemma 4 / YOLOE-26 against the incumbents; the one-model collapse test; closes 5b's owed D3; re-derives §1 + §7 a third time | 5b, 6b |
| 6c | `step6c-live-verification.md` | **Owner at the machine.** The first live `wellsy run`. Device-timestamped §1. Orb on video. Measure, don't fix. | 6b |
| 7 | `step7-memory-context.md` | Memory substrate, provenance-aware writes, context engine | 5b, **5c** |
| 8 | `step8-system1-decisions.md` | **System-One decision layer.** Jev-hosted primary + local fallback; typed calibrated decisions; intent without a parser per capability; the egress log | 5c, 9 |
| 9 | `step9-assistant-convergence.md` | **The shipping blocker.** The agent becomes the brain of the voice loop — every tool reachable by speaking. Spoken approvals, read-back, HUD from the runtime. | 5c, 6c |
| 10 | *not yet written* | **Expressive TTS** — the standing ask. Bench-off per `.claude/v2-roadmap.md`; the rebuild shipped the Kokoro fallback. | 5c |

**Numbers are topics, not execution order** (4c and 5b already interleave).
Current order:

> **6c → 5c → 9 → 8 → 7 → 10**

6c first because it needs no code and closes the oldest owed acceptance. 5c
second because step 7's context engine and step 9's routing are both designed
*against* a model's context window and latency — building either on the outgoing
set is how the 33-second planner nearly became step 6's loading animation.

**9 before 8**, reordered 2026-10-12 for shipping speed: convergence is what
turns two demos into a product, and it can route on the planner's own
tool-calling. Step 8 then makes that routing cheap and supplies the confidence
number — an optimisation of a working thing rather than a prerequisite for it.

Step 10 is deliberately **not written yet** — its candidate set depends on what
headroom 5c leaves.

Later phases — proactive engine, autonomy levels, communication modes, the
ambient interface — are scoped in `.claude/roadmap-phase1.md`.

## Decisions already made — do not relitigate in a step session

| ID | Decision |
|---|---|
| D46 | Name is **WELLSY**. Wake phrase retuned accordingly. |
| D47 | `src/` (browser HUD) is **deleted**, not frozen. |
| D49 | **Cascaded streaming**, not full-duplex S2S. An agent needs a text seam for tools, permissions, memory and audit. PersonaPlex returns later as an optional conversation mode. |
| D51 | Production target #1 is **Linux / ARM64 / CUDA** (Jetson-class), because the endgame is a humanoid body. macOS is a development convenience. |
| D53 | Agent runtime is **LangGraph** — its `interrupt()` primitive *is* the approval gate. |
| D54 | Interface is a **client of the runtime**, not the product. Phase 1 scope: control surface, approvals, audit viewer, perception state. Native (PySide6 + Qt Quick), never a webview. The ambient showpiece is deferred. |
| D55 | ~~Jev rejected for the core~~ **AMENDED 2026-10-12 by owner override: online APIs are permitted.** Jev becomes step 8's primary backend; a local backend stays as the proven fallback (a body with no network must still decide), `stop` stays local on its 617 ms budget, and the egress log is built now even though the guardrail is deferred. Original reasoning and the accepted costs are both in `decisions.md`. |
| D55-orig | *(superseded)* **Jev was rejected for the core** — hosted API only, no weights, no rationale returned, and the `state` payload is exactly the personal data that may never leave the device. Its *System-One pattern* is adopted locally (step 8). `GLiFormer` does not verify; nothing from that source chain enters the tree. |

## Hardware — deferred, deliberately

The owner will provision a Linux/NVIDIA box when the program nears shipping.
The configuration cannot be specified responsibly yet, because it is determined
by decisions not made until step 5:

- final model sizes for brain, VLM, ASR and TTS,
- whether the brain runs resident or is loaded on demand,
- whether a Jetson-class target constrains the desktop build (it should — see
  `stack-teardown.md` §12.2: a Unitree G1 EDU carries a Jetson Orin NX with
  ~16 GB, **less** than the 24 GB M4 Pro this is developed on).

**Action for the master session:** produce a specification with measured VRAM
and throughput requirements at the end of step 5, not before. Sizing a box
against guesses is how the current stack ended up wrong.

## Status as of 2026-10-12

**`master` @ `57c11bc`. Tree clean. 190 tests green. Last commit 2026-09-07 —
five weeks idle.**

Merged: steps 1-6 plus 4b, 4c, 5b, 6b. The shipped stack:

| Slot | Running | Measured |
|---|---|---|
| Detector (T1) | `yoloe-11s-seg.pt`, open-vocab, PyTorch/MPS | 13.49 / 23.95 ms fast path |
| Planner + fast (unified) | `qwen3:4b-instruct-2507-q4_K_M` | 32 ms warm TTFT, 3.99 s full plan, 20/20 plan-valid |
| VLM | `qwen3-vl:2b-instruct-q4_K_M` | ~1.8 s first-capture |
| Co-resident | both pinned `keep_alive:-1` | **5.2 GB** -> Orin NX 16 GB fits |
| Interface | PySide6 / Qt Quick particle orb | 0.62 % asleep, 2.84 % p95 acting |
| Agent | LangGraph >=1.2.11, 24 tools, policy gate, audit log | — |
| Voice | composed wake -> first word | 615 ms p50 (n=20) |

Ratified deviations (unchanged): package `wellsy/` -> `engine/`; LLM backend is
`openai_http` (OpenAI-compatible streaming - Ollama, llama-server, vLLM, SGLang)
rather than in-process llama-cpp-python; ASR is faster-whisper `base.en` after
Qwen3-ASR was rejected on measured numbers; Pipecat's bundled Silero + Smart
Turn v3 over the step-2 wrappers; MCP servers authored in-house (FastMCP/stdio)
after the community macOS servers failed invariant #8; `mcp` held at `<2` by
langchain-mcp-adapters 0.3.2.

### The two things blocking everything else

**1. Nothing has ever been run live.** Every latency number in this repo came
from a file-injection or component-compose harness. `wellsy run` has never been
exercised by a human with a microphone and a speaker. That is how the step-4
echo regression shipped — the harness had no speaker in the room. **Step 6c.**

**2. The model set is five weeks stale, and 5b's central finding may be
obsolete.** 5b proved across seven attempts that no flag makes a hybrid Qwen3
non-reasoning; Qwen3.5's small sizes are now reported to have reasoning off by
default, with native multimodality and 262K context against our 4096. None of it
is verified. **Step 5c** — and step 7 must not start before it, because a
context engine built for 4096 tokens is different software from one built for
262K.

### Open debt carried forward

- ~~**Live `wellsy run`** - never performed~~ -> done in step 6c
  (2026-10-13): three open-air sessions plus the recorded demo, with the
  demo-visible failures fixed (PR #15). See `step6c-results.md`.
- **Device-timestamped §1 latency** - the 615 ms is still composed, not
  measured at the output device. Step 6c did not take it (owed). Log-clock
  indication only: warm turn commit -> bot speaking 0.6-0.8 s.
- **Orb recorded in every state** (+ fullscreen, Spaces) - owed from step 6c.
- ~~**Perception scheduling: T1 runs on 1.8 % of frames.**~~ -> fixed in the
  5c follow-up (2026-10-17, `step5c-results.md` §12.1): T1 now runs at least
  every 1 s even with no motion (`T1_HEARTBEAT_S`; T0 untouched, INVARIANTS
  #5; `--heartbeat 0` restores motion-only). On the recorded clip through the
  normal loop: glasses freshly detected in 38/39 s (was 2/39), phone 18/19
  (was never); CPU cost within noise. Still open: live T1 is ~31-35 ms against
  a < 20 ms p50 budget because the GPU idles between calls at 8 Hz
  (back-to-back ~16 ms). That is a keep-warm or cadence trade, unowned.
- **Screen questions take ~4.5 s** (5c follow-up §12.2): screen capture
  261 ms plus both displays to the VLM (3.6 s first word). This misses both
  §1 VLM targets; the levers (focused display only, Qwen3.5, 768 px) are the
  owner's call.
- **Spoken barge-in** - *"Wellsy, stop"* mid-answer does not work; the ESC key
  does. AEC is a seam only, no ERLE measured (step 4c debt).
- **HUD from the agent runtime** - only the `approval` view is wired; deny has
  never been exercised end to end into the audit log.
- ~~**5b's owed D3**~~ -> closed in step 5c: 512 px reads 0-3 of 18 strings
  and saves no time on `qwen3-vl` (server floor of 1056 tokens); 1024 px
  stays. The honest new-screen first word is ~2.1 s, so the §1 VLM row misses
  p50 by ~230 ms (5b's 1.8 s was cache-inflated).
- **Qwen3.5 collapse (step 9):** `qwen3.5:4b-q4_K_M` measured as one model for
  fast + planner + VLM (−2.1 GB), but it thinks by default, and on `/v1`
  only `reasoning_effort:"none"` turns that off. The current request shapes
  would make a string-only swap silent. See `step5c-results.md` §2, §3, §9.
- Orb art pass; global hotkey; typed text into the HUD.
- A8-granted half and the ScreenCaptureKit latency row.
- A3-A6 live against a real Calendar / Mail account (`osascript` backend).
- faster-whisper `base.en` is English-only.
- An in-process LLM backend must be validated before embodiment bring-up.
- **Linux/CUDA path is code-complete and unexecuted** - and it is production
  target #1 (D51).
- `InMemorySaver` -> `SqliteSaver` for cross-process resume.
- Intermittent `recursive_mutex lock failed` at pytest teardown when pipecat
  (anyio) and agent (stdio MCP) tests run in one process; exit code stays 0.
- Dependency hygiene: opencv-python and pyav both vendor libavdevice
  (`AVFFrameReceiver` duplicate-class warning).

### Documentation warts, recorded rather than fixed

- `step7-memory-context.md` was titled `# Step 6 —` from before renumbering;
  corrected 2026-10-12.
- The D-series is split: **D1-D46 in `.claude/decisions.md`, D47-D54 in
  `.claude/stack-teardown.md` §12**, resuming at D55 in `decisions.md`.
- `day12-brief.md` is still the bug-centric draft the owner rejected. It has not
  been rewritten.
- `spec/results/voice-latency-2026-09-07-*.json` carries a stale `notes` line
  predicting the LLM row *will miss* 1500 ms; the same file measures 615 ms.
- `step6-results.md` increment 7 back-calculates warm TTFT as ~43 ms where the
  results file measures 53.5 ms.
