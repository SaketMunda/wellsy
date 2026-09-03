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
| 7 | `step7-memory-context.md` | Memory substrate, provenance-aware writes, context engine | 5b |

Later phases — proactive engine, autonomy levels, communication modes, the
ambient interface — are not yet written as prompts. They are scoped in
`.claude/roadmap-phase1.md` and will be rewritten against reality once step 6
lands.

## Decisions already made — do not relitigate in a step session

| ID | Decision |
|---|---|
| D46 | Name is **WELLSY**. Wake phrase retuned accordingly. |
| D47 | `src/` (browser HUD) is **deleted**, not frozen. |
| D49 | **Cascaded streaming**, not full-duplex S2S. An agent needs a text seam for tools, permissions, memory and audit. PersonaPlex returns later as an optional conversation mode. |
| D51 | Production target #1 is **Linux / ARM64 / CUDA** (Jetson-class), because the endgame is a humanoid body. macOS is a development convenience. |
| D53 | Agent runtime is **LangGraph** — its `interrupt()` primitive *is* the approval gate. |
| D54 | Interface is a **client of the runtime**, not the product. Phase 1 scope: control surface, approvals, audit viewer, perception state. Native (PySide6 + Qt Quick), never a webview. The ambient showpiece is deferred. |

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

## Status as of 2026-09-01

Steps 1-5 merged to `master` (step 4b included). Tree clean.

Ratified deviations: package `wellsy/` -> `engine/`; LLM backend is
`openai_http` (OpenAI-compatible streaming - covers Ollama, llama-server, vLLM,
SGLang) rather than in-process llama-cpp-python; ASR is faster-whisper `base.en`
after Qwen3-ASR was rejected on measured numbers; Pipecat's bundled
Silero + Smart Turn v3 over the step-2 wrappers; MCP servers authored in-house
(FastMCP/stdio) after the community macOS servers failed invariant #8; `mcp`
held at `<2` by langchain-mcp-adapters 0.3.2.

**The blocking item is model selection, not the next feature.** The planner
(`qwen3:4b`, 33 s TTFT) is unshippable, the VLM row misses at 3.0 s against a
2.5 s budget, and the fast slot and TTS were both adopted with their bench-offs
deferred. `step5b-model-selection.md` closes all four and re-derives the §7
hardware sizing, which is currently arithmetic over models that are being
replaced. Hardware is **not** being bought yet - that is the last step, after everything
is verified. 5b still matters for the planner's 33 s, which step 6's UI will
put on screen as a 33-second "thinking" animation. 5b and step 6 touch no
common files and can run in parallel.

Open debt carried forward beyond 5b's scope:
- A8-granted half and the ScreenCaptureKit latency row - needs Screen Recording
  granted to the editor's process tree and a full restart.
- A3-A6 live against a real Calendar / Mail account (`osascript` backend).
- faster-whisper `base.en` is English-only.
- An in-process LLM backend must be validated before embodiment bring-up.
- Linux/CUDA path is code-complete and **unexecuted**.
- `InMemorySaver` -> `SqliteSaver` for cross-process resume.
- Intermittent `recursive_mutex lock failed` at pytest teardown when pipecat
  (anyio) and agent (stdio MCP) tests run in one process; exit code stays 0.
