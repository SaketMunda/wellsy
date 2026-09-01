# Step 4b — measurement runbook (owner at the machine)

The code prerequisite is done and committed on `rebuild/step4b-vlm-wiring`
(`e0a1d0f`): the step-3 capture layer is wired into the VLM path, and
`wellsy voice --measure-acoustic` is the at-the-device latency rig. This file
is the sequence to take the five measurements.

## Permission state for *this* process tree (VS Code → claude → zsh → python)

```
[ OK ]      camera
[ OK ]      microphone
[ MISSING ] screen recording   → grant to "Code", then FULLY QUIT + REOPEN VS Code
```

`wellsy doctor` prints the current state. **A8-granted and the ScreenCaptureKit
latency number cannot be taken until Screen Recording is granted to this app and
the app is restarted** — the restart kills the session that granted nothing, so
those two run in a fresh session (or a plain Terminal.app that already has all
three grants). Everything else is mic-only and can run now.

Set the VL model for any run that exercises a vision turn:

```bash
export WELLSY_LLM_MODEL=qwen3-vl:4b
```

(Text/deterministic turns still work on that model, just slower — that is why
the §1 text rows were measured separately on `qwen3:4b` / `qwen2.5:3b`.)

---

## 1. A8 — screen grounding, both halves

### Revoked half — DONE (verified this session, no restart needed)

Through the new wiring, with Screen Recording missing:

- `wellsy screen` → `REFUSED: Screen Recording permission is not granted for this process`
- `engine.voice.vision.capture_for_intent("what's on my screen")` → raises
  `CaptureError`, spoken: *"I can't see your screen — screen recording
  permission isn't granted for this process."* **No wallpaper / desktop / menu
  bar description is produced.** Nothing reaches the model.

Re-confirm in the live voice path (optional, still revoked):

```bash
wellsy voice --awake
# say: "what's on my screen"
# expect: the spoken refusal above. NOT a description of anything.
```

### Granted half — needs the restart

1. System Settings → Privacy & Security → Screen Recording → enable **Code**.
2. Quit VS Code completely (⌘Q) and reopen. Open a new terminal.
3. `wellsy doctor` → camera / microphone / screen recording all `OK`.
4. Open **two or more windows, at least one with legible text** (e.g. a code
   file and a browser article).
5. Capture check:
   ```bash
   wellsy screen --save ~/wellsy-a8
   # expect: {"verified": true, "captureVerifiedBy": "...", "displays": [...]}
   # open ~/wellsy-a8/display_0.png — it must show the real windows, not the desktop
   ```
6. Live grounding:
   ```bash
   WELLSY_LLM_MODEL=qwen3-vl:4b wellsy voice --awake
   # say: "what's on my screen"       → must name real window contents
   # say: "read me the text on screen" → must read text genuinely visible
   ```
   **Pass:** describes actual window contents and reads back on-screen text.
   **Hard fail:** any answer about a wallpaper.
7. ScreenCaptureKit capture latency, p50/p95, n ≥ 20:
   ```bash
   uv run python bench/capture_bench.py --trials 30
   # the `screencapturekit` backend section now produces numbers instead of REFUSED
   ```

Record the granted-half transcript, the SCK latency block, and confirm the
revoked half still refuses **after** the wiring (step 1 above already shows it
does).

---

## 2 + 3 + 4. Acoustic §1 table, A14 barge-in, `stop` wall-clock — one session

All three come from one live run with the observer:

```bash
WELLSY_LLM_MODEL=qwen3-vl:4b wellsy voice --measure-acoustic
```

Speak the script below. Leave ~2 s between turns. When done, Ctrl+C — a summary
prints and `spec/results/voice-acoustic-<date>.json` is written with every raw
turn.

**Protocol notes:**
- Run **without `--awake`** so the wake phrase is in the path (the §1 row is
  "wake word → first audible word"). Say each item as **one breath** —
  `"hey wellsy, what can you do"` — so onset is stamped at the wake word and it
  is one speech segment, not two turns. Adding `--awake` skips the wake phrase
  *and* fires a startup greeting; if you use it, discard that first greeting
  turn.
- The observer resets its open turn on every `UserStartedSpeakingFrame`; a pause
  mid-utterance splits it into two turns (the first with no audio). Keep each
  utterance continuous.

**Method the rig uses (stated in the output):** all marks are on the Pipecat
pipeline clock. "First word" = the first `TTSAudioRawFrame` handed to
`transport.output()` for the device write (sub-audio-buffer, ~10–20 ms, ahead of
the PortAudio write itself). Onset = `VADUserStartedSpeakingFrame`. Cold = the
first turn of each path; warm = the rest.

### Script

Do a cold run first (fresh process = trial 0 of each path is the cold number),
then keep going for the warm sample.

**Deterministic path (target < 800 / < 1200 ms)** — no model in the path.
Say each ≥ 20 times, varying which:

- "what can you do"
- "are you there"
- "thanks"

**LLM path (target < 1500 / < 2500 ms)** — ≥ 20 turns:

- "what's the capital of France"
- "how many days in a leap year"
- "say something short"

> Note: on `qwen3-vl:4b` (and `qwen3:4b`) the LLM row will miss the budget
> because that build runs a reasoning pass every turn — this is the known step-4
> finding, not the pipeline. If you want the honest pipeline number for this
> row too, run a second `--measure-acoustic` session with
> `WELLSY_LLM_MODEL=qwen2.5:3b` and no vision turns.

**VLM path (target < 2500 / < 3500 ms)** — ≥ 20 turns, camera pointed at the
room:

- "what do you see"
- "do you see a laptop"
- "what's in front of you"

(For screen VLM turns you need the granted session from §1; add ≥ 20 of
"what's on my screen" there and run `--measure-acoustic` in that session too.)

### A14 — barge-in (target < 200 / < 350 ms p50/p95)

≥ 20 times: trigger a long answer, then **speak over it** after ~1 s:

- say "list the planets" (or "count slowly to twenty") — wait for it to start —
  then say "what time is it"

**Pass:** the summary's `barge_in` p50/p95 within budget; every interrupted turn
appears with `interrupted: true` in the JSON (`interrupted_turns_recorded`
equals your barge-in count); the interrupting utterance is transcribed in full
with no clipped first word (check the `transcript` field of the barge-in turn).

### `stop` — wall-clock (target < 150 / < 250 ms p50/p95)

≥ 20 times: trigger a long answer, then say **"stop"**:

- "count slowly to twenty" — wait for audio — "stop"

The summary's `stop` block is onset-of-"stop" → output silent, at the device.
This is the acoustic counterpart to the wired `InterruptionFrame` / ESC path.

### Report

The `wake_to_first_word` table (cold + p50 + p95 per path), the `barge_in`
block, the `stop` block, and the **composed-vs-acoustic gap**: put the acoustic
p50/p95 next to the `metrics.py --measure` composed numbers in
`spec/results/voice-latency-2026-09-01-*.json`. If acoustic is materially worse,
that gap is a finding.

---

## 5. Wake fixtures + threshold tune

Needs an interactive terminal (it prompts you to press Enter and speak). Do this
in the real room at the real mic distance.

```bash
wellsy record-wake        # ≥ 20 "wellsy", 12 "hey wellsy", 15 near-miss, 18 chatter
# near-misses to include: "well", "wells", "welsey", "wellness", plus ordinary
# speech with none of them
wellsy tune-wake --write  # sweeps the difflib threshold against the recordings
```

`tune-wake` prints the FA/FR curve, writes `spec/results/wake-tune-<date>.json`,
and (`--write`) sets `wake_threshold` in `engine/config/voice.json` from the
measured curve — **not** the bootstrap 0.72. Commit `spec/fixtures/wake/` so the
choice is reproducible.

### Report

The FA/FR curve, the chosen threshold, and the FA/FR rates at it.

---

## Two cheap extras (while you're there)

- **60 s real-camera run:** `wellsy --seconds 60 --debug` — confirm tracks in
  the JSONL and no crash. Confirmation, not a gate (detector bench already
  passes at 13.49 ms p50).
- **Mic contention:** start `wellsy voice --awake`, then start any other audio
  capture app. Confirm both can hold the mic, or record that they cannot.

---

## What lands where

| Measurement | File |
|---|---|
| Acoustic §1 + A14 + stop | `spec/results/voice-acoustic-<date>.json` |
| SCK capture latency | stdout of `bench/capture_bench.py` → paste into `step4b-results.md` |
| Wake tune curve | `spec/results/wake-tune-<date>.json` + `spec/fixtures/wake/` |
| A8 granted transcript | `step4b-results.md` |

Then update `spec/results/` and put the acoustic table into
`.claude/system-state.md` (currently pre-rebuild) with its measurement method
beside it, per step4b acceptance #5.
