# Step 4 — Streaming voice path, turn detection, and real barge-in

**Read first:** `.claude/rebuild/INVARIANTS.md` (#3, #4, #7, #14),
`.claude/stack-teardown.md` §2, §5, §12.1, `spec/phase1-acceptance.md` §1 and
**A14**. **Depends on steps 2 and 3.**

## This is the step where the product stops feeling broken

Everything before this is scaffolding. This is the first step the owner will
*feel*, and the previous build failed precisely here. Read the diagnosis:

The old path was three fully-buffered stages in series, so their latencies
**added** rather than overlapping:

| Stage | Measured | Fault |
|---|---|---|
| STT (Moonshine base ONNX) | ~1.35–1.40 s warm | Batch. No partials. |
| LLM (Qwen3-VL-4B via Ollama) | first token 1,693 ms, full 2,201 ms | Not streaming — 508 ms discarded per turn |
| TTS (Chatterbox Turbo, MPS) | **RTF 1.1x–3.3x** | Slower than realtime; whole clip generated before the first sample plays |
| Turn end | fixed 600 ms silence tail | Flat tax on every turn |
| VAD | hand-rolled RMS, adaptive floor | Floor could latch on room noise and classify everything as speech indefinitely |

Result: 4.5–6 s to first audible word, and the owner's verdict was *"STT didn't
understand things what I say. TTS too much latency."* Both complaints were
correct.

**The architectural fix is that nothing waits for a complete buffer.** Audio
streams into ASR, ASR partials stream into the LLM, LLM tokens are
sentence-chunked into TTS, and TTS PCM streams to the device — all overlapping.

## Deliverable 1 — Pipecat pipeline

Adopt **Pipecat** rather than hand-rolling. The previous `query_loop.py` was 777
lines — 21% of the codebase — of exactly this, and it is the single largest
reason for the rebuild. Pipecat provides the streaming frame pipeline, turn
detection, and barge-in as first-class primitives. It is Python and
cross-platform, satisfying invariant #14.

Components (verify each is current per invariant #8 — do not install from these
names on trust):

| Role | Choice |
|---|---|
| VAD | Silero VAD (ONNX, portable) |
| Turn detection | Pipecat Smart Turn v3 — **semantic** end-of-turn, local, no GPU required |
| ASR | streaming backend from step 2 |
| LLM/VLM | streaming backend from step 2 |
| TTS | streaming backend from step 2 |

**Invariant #3 is non-negotiable and survives this migration.** `parse_intent`
becomes a `FrameProcessor` positioned so that `stop`, `wake`, and `sleep` are
resolved **deterministically by regex before any model sees the transcript**. An
LLM must never decide whether "stop" stops. If Pipecat's structure fights this,
the seam is wrong — fix the seam, do not relax the invariant.

## Deliverable 2 — kill the fixed silence tail

The 600 ms tail is a flat tax on every single turn and cannot distinguish "I am
thinking" from "I am finished." Replace it with semantic turn detection.
Measure and report the per-turn saving.

## Deliverable 3 — real barge-in

VAD stays live **during** TTS playback, with mid-stream cancellation. The
existing `stop` path already cancels at 114 ms — extend that same path to
detected speech.

Budget from `spec/phase1-acceptance.md` §1: user speech onset → output silent in
**< 200 ms p50 / < 350 ms p95**. The interrupted turn is recorded as
*interrupted*, never as delivered — an audit and honesty concern, not cosmetics.

## Deliverable 4 — the measurement that has been owed since Day 9

**Wake word → first audible word has never been cleanly captured.** It has been
open for two build days, blocked on macOS microphone permission being granted
per process tree. Step 3's `wellsy doctor` should have resolved that blocker.

Measure it properly: **timestamp at the first PCM sample written to the output
device** — not at TTS invocation, not at generation completion. p50 and p95 over
≥ 20 trials, cold and warm reported separately, for all three paths in §1.

**This step does not pass without this number.**

## Deliverable 5 — wake phrase retuning

The name was changed to WELLSY because the previous single-syllable wake word transcribed as "app" and
repeatedly mis-triggered. "Wellsy" has a soft `/w/` onset and a medial `/s/`.
Step 1 left a `TODO(step4)` on the difflib fuzzy-match threshold (was `0.72`).

**Tune it against recorded audio, not intuition.** Capture ≥ 30 real utterances
of the wake phrase plus ≥ 30 near-misses and non-wake speech, then pick the
threshold from the measured false-accept / false-reject curve. Commit the
recordings under `spec/fixtures/wake/` so the choice is reproducible.

## Acceptance

1. Every latency target in `spec/phase1-acceptance.md` §1 met, measured as
   specified. Report the full table.
2. **A14 (barge-in) passes**, verified live, including no clipped first word on
   the interrupting utterance.
3. `stop` still cancels within 150 ms p50 via the deterministic path.
4. Streaming is real, not simulated: prove with timestamps that TTS emits its
   first PCM sample before the LLM has finished generating.
5. Perception fast path unregressed — still within 20 ms p50 / 35 ms p95.
   Voice work has previously caused a CPU regression here (Chatterbox: ~18%
   average, 44% spikes, never profiled). **Profile idle CPU and report it.**
6. Wake false-accept and false-reject rates reported from the fixture set.
7. `query_loop.py`, `vad.py`, `stt.py`, `tts.py` are gone and not partially
   resurrected.

## Do not

- Do not hand-roll streaming, turn detection, or barge-in. That is what the
  deleted 777 lines were.
- Do not adopt a TTS model without measuring its RTF on real hardware first.
  Chatterbox was adopted mid-Day-11 with no latency budget and turned out to be
  slower than realtime. Measure before committing.
- Do not let an LLM into the `stop`/`wake`/`sleep` path.
- Do not report a latency you did not measure at the audio device.

## Report back

The §1 latency table, the A14 result, idle CPU profile, wake threshold curve,
and — honestly — anything that is still slower than the budget, rather than a
rounded number that clears it.
