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
| 5 | `step5-agent-runtime.md` | LangGraph runtime, MCP tools, policy gate, audit log | 2 |
| 6 | `step6-memory-context.md` | Memory substrate, provenance-aware writes, context engine | 5 |

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
