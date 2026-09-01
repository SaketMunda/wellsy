# Step 4b — Live verification session (owner at the machine)

**Read first:** `.claude/rebuild/INVARIANTS.md`, `spec/phase1-acceptance.md` §1
and **A8, A14**, `.claude/rebuild/step3-results.md`, `.claude/rebuild/step4-results.md`.
**Depends on steps 3 and 4 (both merged to `master`).**

## Why this is its own session

Five acceptance items are outstanding across steps 3 and 4. Every one of them is
blocked on the same condition and none of them is blocked on code:

> **The owner must be physically at the machine, in an interactive session,
> with microphone *and* Screen Recording granted to this process tree.**

macOS TCC is granted **per process tree** — a terminal, an IDE's integrated
terminal, and a packaged app each need their own grant. This has blocked the
wake→first-word measurement since Day 9 of the previous build. It ends here.

**Run this session in a terminal the owner can grant permissions to, and grant
them before starting.** `wellsy doctor` reports what is missing.

## Prerequisite (code, do this first)

**Wire the step-3 capture layer into the VLM path.** `describe_scene` and
`query_object` currently forward to the text LLM, so the §1 VLM row cannot be
measured and A8-granted cannot be exercised end to end.

- Camera frames and verified screen captures reach the VLM backend as images.
- `CaptureResult.provenance()` folds into `honesty/provenance.log_answer()` —
  step 3 left this explicitly owed.
- **An unverified capture never reaches the model** (step 3's whole point).

## The five measurements

### 1. A8 — screen grounding, granted half
Two or more windows open, at least one with legible text.
**Pass:** describes real window contents and reads back text genuinely on
screen. **Any answer about a wallpaper is a hard fail.**
Also re-run the revoked half to confirm it still refuses after the VLM wiring.
Measure ScreenCaptureKit capture latency, p50/p95, n ≥ 20 — unmeasurable until
now.

### 2. A14 — barge-in, live
Trigger a long spoken answer, then speak over it.
**Pass:** output silent within **200 ms p50 / 350 ms p95** measured from speech
onset; the interrupting utterance captured in full with **no clipped first
word**; the interrupted turn recorded as *interrupted*, never as delivered.

### 3. `stop` — wall-clock
Deterministic path, target **< 150 ms p50 / < 250 ms p95**. The
`InterruptionFrame` / ESC path is wired; this is the acoustic number.

### 4. True mic→speaker end-to-end
The step-4 table is **component-composed**, not acoustic. Measure the real path:
**first PCM sample written to the output device**, timestamped from wake-word
onset. p50/p95, n ≥ 20, cold and warm separate. All three §1 rows —
deterministic, LLM, VLM.

Report the composed-vs-acoustic gap. If the acoustic number is materially worse,
that gap is a finding, not a rounding error.

### 5. Wake fixtures and threshold tune
`wellsy record-wake` — **≥ 30 wake utterances and ≥ 30 non-wake**, owner
speaking, in the real room at the real mic distance. Include the known-hard
near-misses: "well", "wells", "welsey", "wellness", plus ordinary speech
containing none of them.

Then `wellsy tune-wake --write`. **Pick the threshold from the measured
false-accept / false-reject curve, not intuition** — the bootstrap 0.72 is a
guess and `wake.py` cannot currently separate "well" (0.80) from "welsey"
(0.83), which is exactly why it is tuned against recordings.

Commit `spec/fixtures/wake/` so the choice is reproducible.

## While the owner is there — two cheap extras

- **60 s real-camera run.** Step 1 verified `--help`, tests and a synthetic run,
  but never a fresh real-camera run (perception code was byte-identical and the
  detector bench passes at 13.49 ms p50, so this is confirmation, not a gate).
- **Microphone contention.** Confirm the voice path and any other audio
  consumer can coexist, or document that they cannot.

## Acceptance

1. A8 passes **both** halves, granted and revoked, with the VLM actually wired.
2. A14 passes live, with the wall number.
3. All three §1 rows have **acoustic** p50/p95, n ≥ 20 — not composed.
4. Wake threshold chosen from a committed fixture set; FA/FR rates reported.
5. `spec/results/` updated; `system-state.md` carries the acoustic table with
   its measurement method beside it.

## Do not

- Do not report a composed number as an acoustic one.
- Do not tune the wake threshold by ear.
- Do not let an unverified capture reach the model to make A8 pass.
- Do not mock a permission state. Revoke it for real.

## Report back

The acoustic §1 table, both A8 halves, the A14 wall number, the FA/FR curve and
chosen threshold, and the composed-vs-acoustic gap.
