# Day 12 — the rebuild. Brief for scripting.

Everything from the rebuild decision through step 5 is Day 12: steps 1, 2, 3, 4,
4b, 5. Six sessions, all merged to `master`. 62 test functions / 121 tests green.

---

## The story: one bug that turned out to be the whole architecture

**The cold open.** You asked WELLSY what was on your screen. You had windows
open. It described your wallpaper — a forest. That's the hook, and it's true.

**The investigation.** The obvious read is "the vision model is bad." It wasn't.
On macOS, `screencapture` without the Screen Recording permission **exits 0 and
writes a perfectly valid, full-resolution PNG** — containing only the desktop
wallpaper and the menu bar. Every guard in the old code checked the things that
still passed: exit code 0, file exists, file is a valid image, pixels are not
uniform. The model described a forest because it was *shown* a forest. It was
being honest. The pipeline was lying to it.

**The worse part, and say this on camera.** A previous session had already
"fixed" this bug — and recorded the wrong root cause in the code comments,
blaming a multi-monitor argument. That was a real bug, but a different one. The
fix shipped over the top of the actual defect, and the wrong explanation sat in
the codebase looking authoritative.

**The lesson that generalises:** a system that cannot tell "I saw nothing" from
"I saw a forest" will confabulate forever, and no better model fixes it.

---

## The decision: scrap ~70% and rebuild

Not because the code was ugly. Because of one structural fault:

> **Nothing streamed.** Batch speech-to-text, then a non-streaming LLM, then
> whole-clip text-to-speech — three fully-buffered stages in series. Their
> latencies *add*. 4.5-6 seconds to the first audible word. You cannot polish
> that away; the shape is wrong.

Kept: the perception core (motion gate, detector, tracker) — it was already fast
and it still benchmarks at 13.49 ms p50. Deleted: 19 modules, including the
browser HUD, the batch STT/TTS, the query loop, and the screen-capture module
that caused the forest.

---

## What got built, in order

**Step 1 — repo reset.** YAP → WELLSY. Perception core ported, everything else
deleted.

**Step 2 — a portable inference seam.** Every model sits behind one interface
(ASR / TTS / VAD / LLM), so a backend is swappable without touching callers.
Plus **invariant #14, the decision that reframed the project**: no
platform-exclusive API in the core. That banned MLX, CoreML, and Apple-only
paths — and it's enforced by a *test* that fails the build if a banned import
appears, not by a note in a document.

**Step 3 — the capture layer that cannot lie.** A capture is verified by three
independent signals before any model sees it: the OS permission preflight
(`CGPreflightScreenCaptureAccess`), a cross-check against the window list, and a
wallpaper correlation test (normalised cross-correlation against a known
desktop image). An unverified frame never reaches a model — it raises.

**Step 4 — the voice path, rebuilt streaming.** Pipecat 1.8.1. Silero VAD +
**Smart Turn v3** for semantic end-of-turn — the old fixed 600 ms silence tail is
gone entirely. Speech-to-text is faster-whisper `base.en` (CTranslate2);
text-to-speech is **Kokoro-82M** via `kokoro-onnx`. Real barge-in: you can
interrupt it mid-sentence.

**Step 4b — grounding the vision path.** Camera and screen wired through the
verified capture layer into the vision model, with provenance logged on every
answer.

**Step 5 — WELLSY becomes an agent.** LangGraph state machine: plan → policy
check → act → **verify by independent read-back** → report. 24 tools over MCP
(Model Context Protocol) across calendar, reminders, mail, notes, contacts,
files. A policy gate as a YAML sidecar, risk 0-3, where **an unannotated tool
defaults to risk 3 and fails closed**. A JSONL audit log where the pending line
is written *before* the action returns. And autonomy that is **not a switch** —
the level is recomputed from the audit log on every check, so WELLSY earns trust
by accumulating clean, read-back-verified runs, and risk-3 actions never
auto-promote at all.

---

## Numbers you can put on screen (all measured, not estimated)

| | target | measured |
|---|---|---|
| Wake → first word, deterministic | < 800 ms | **617 ms** |
| Wake → first word, fast LLM | < 1500 ms | **614 ms** |
| Speech-to-text (faster-whisper base.en) | — | **267 ms**, RTF 0.05 |
| Text-to-speech first audio (Kokoro) | — | **345 ms** |
| Perception fast path | < 20 ms | **13.49 ms** |
| Idle CPU, awake and listening | — | **1.3% of the machine** |

Measurement rule, stated once: **the clock stops at the first PCM sample written
to the output device.** Not at "model finished." What you hear is what's timed.

---

## The losses. Do not cut these.

1. **The planner model takes 33 seconds.** `qwen3:4b` runs a reasoning pass on
   every turn and *there is no way to turn it off* — six documented attempts,
   each verified by direct `curl`, all ignored. It is unshippable and it is the
   next thing being fixed.
2. **The vision path misses its budget** — 3.0 s against a 2.5 s target. Found
   the cause: at 1920×1080 a screenshot costs ~2757 vision tokens and
   prompt-processing dominates. Downscaling to 1024px took it from 9.4 s to
   3.2 s. Still a miss. Reported as a miss.
3. **Two models were adopted without their bench-off** — the fast model and the
   TTS. They clear the budget, but "it works" is not "it's the best choice,"
   and that debt is written down rather than quietly forgotten.
4. **The hardware sizing is provisional.** The target is a Unitree G1 EDU
   humanoid, whose Jetson Orin NX has **16 GB — less than this laptop's 24 GB.**
   Three model roles co-resident measure 9.0 GB, which does not fit alongside
   speech, perception and robotics middleware. But that arithmetic uses the
   models being replaced, so it gets re-derived before anything is bought.

---

## Answering the interface question, on the record

**There is no graphical interface right now.** The browser HUD was deleted in
step 1 and deliberately not replaced — the decision (D54) is that the UI is a
**client of the runtime**, native, PySide6 + Qt Quick, in the engine's own
process. That step has not been written or built yet.

So Day 12 shoots as a terminal. What is actually filmable and good:

- Ask it about your screen with the permission revoked → it **refuses out loud**:
  *"I can't see your screen — screen recording permission isn't granted."*
  Side by side with the old build confidently describing a forest. That single
  cut is the strongest thing in the episode.
- Voice conversation with barge-in — interrupt it mid-sentence, live.
- `wellsy agent "…"` → it asks for approval before it writes anything → approve
  once, deny once → `wellsy audit` shows both, including the denial.
- `wellsy autonomy` — explain that the number came from the log, not a setting.

---

## The one-line thesis

> Day 12 was not a feature. It was the day WELLSY learned the difference between
> knowing something and guessing, and stopped being allowed to guess.
