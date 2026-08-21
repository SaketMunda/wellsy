# Day 10 results

Everything below is measured on this machine, this session, real hardware
(real camera, real microphone, real speakers) unless explicitly marked
synthetic. Zero LLM in this loop — every answer below is deterministic
pattern-matching and grounded track data, not model output.

## The measurement table

| # | Metric | Result | Conditions |
|---|--------|--------|------------|
| 1 | Wake/press → first spoken word, p50/p95 | **Not cleanly measured this session — an honest instrumentation gap, not a missing feature.** `query_loop.py` computed `wakeToAnswerMs`/`pressToAnswerMs` but the first live test's process was interrupted before those lines printed; the print statements were added mid-session (see below) for the next run. One real success surfaced a **partial** number: T3-internal processing (intent → forced-look → describe → TTS-start, i.e. *after* the command was already transcribed) took **119.1ms**. The silence-tail wait (0.8s, by design) and STT transcription time are real, additional, unmeasured cost on top of that. | Real mic, real camera, real speakers, `--t3` |
| 2 | Breakdown: VAD, STT, forced T1, describeScene, TTS first-audio | **Partial.** Forced-T1: 33.4ms (row 3). Intent parse + describeScene + TTS-handoff, combined: 119.1ms (row 1). VAD and STT stage timings were not isolated this session — `query_loop.py` doesn't yet time them separately, only the whole `_record_utterance`/`transcribe` calls. Carried to Day 11. | Real hardware |
| 3 | Forced-fresh-T1 cost (Part 0.1) | **33.4ms** real inference, **71.2ms** wall-clock round trip (thread hand-off included) | Real camera, real YOLOE detector, `verify_preemption.py`, `engine/clips/preemption-verify.jsonl` |
| 4 | Preemption visible in JSONL during a query | **Yes.** During the 60 frames (~2s) the seam was held `active`, exactly one `inferenceMs` was non-null (the forced look, 33.4ms) and zero others — ambient T1 genuinely paused, not just throttled. See `engine/clips/preemption-verify.jsonl` and the excerpt below. | Real camera, real detector |
| 5 | Idle CPU with mic + VAD always on | Main engine process (capture+detect+T1+T3 threads, one PID): **11.5%** during startup settling, dropping to **1.9–2.3%** of one core at steady state (`--synthetic`, no real motion, wake-phrase listener + VAD running). Not directly comparable to Day 9's "main+capture, 6–13%" framing — this number is the main PID alone, not summed with the separate capture subprocess. | `--synthetic --t3`, `ps` sampling |
| 6 | Wake-phrase false accepts / false rejects | **Not run to the stated bar (10 min / 20 utterances) this session.** What was captured live, real hardware, real speech: 3 wake attempts, 2 matched ("hey yap" heard as "App." → matched "yappy" at 0.75; "hey yo" heard inside a longer sentence → matched at 0.77), 1 produced a full successful query end-to-end. Zero observed false accepts during the ~30s this ran, but that is far too short a window to claim the bar is met. **A real, live collision was found instead: "yap" is repeatedly transcribed as "app"** — see decisions.md D39. Carried forward: the acceptance-bar test itself, and a wake-word rename (user's call, deferred this session). | Real mic, real speakers, live human speech |
| 7 | Audio confirmed audible on real speakers | **Yes — by a human, finally, after nine days.** First attempt: silence (default output was an HT-S20R soundbar that was off). Second attempt, same device, powered on: confirmed heard. | `say -v Samantha`, real speakers (HT-S20R) |
| 8 | τ verdict (Part 0.3) | **Changed, with evidence — not yet retuned.** Real walk test (third attempt, after two coordination misses — see below) produced 89 real T1 ticks with per-tick box movement mean 55.7px, p95 252.5px, max 707.2px, over a mean 225ms inter-tick gap. τ=70ms resolves the mean case within one tick interval but cannot close the p95/max jumps before the next real update lands. See decisions.md D34 (amended). | Real camera, real walk, `engine/clips/tau-walk.jsonl` |

Row 3/4 is the thesis, proven with real data. Row 7 was nine days overdue and is now closed. Row 1/2/6 are the honest gaps — real partial evidence, not a fabricated number.

## Part 0 — the six items

### 0.1 — Forced fresh T1 on query: shipped and proven (the blocker)
`engine/tiers.py`'s `PreemptionSeam` gained `request_fresh_look()` /
`poll_force_request()` / `deliver_fresh_look()` — a real, working hand-off
between `main.py`'s capture loop and T3's calling thread, not the inert
flag it was through Day 9. `verify_preemption.py` proves it against real
camera + real detector: one forced look, 33.4ms of real inference, and
zero other detections for the ~2s the seam stayed held. See decisions.md
D36.

Real JSONL excerpt (`engine/clips/preemption-verify.jsonl`), around the
preempt point:
```
{"t": 1.922, "gated": true, "preemptionActive": false, "forced": false, "inferenceMs": 33.63}
{"t": 3.013, "gated": true, "preemptionActive": true,  "forced": true,  "inferenceMs": 33.43}
{"t": 5.058, "gated": true, "preemptionActive": false, "forced": false, "inferenceMs": null}
```
Between `t=3.013` (the forced look) and `t=5.058` (the first frame after
release), 60 frames passed with `preemptionActive: true` and **zero**
non-forced `inferenceMs` values — ambient sensing paused for the duration,
exactly as designed.

### 0.2 — Audio hardware check: both halves closed, the hard way
- **Mic:** the first attempt returned all-zero samples (`rms: 0.0`) —
  turned out to be a permission gap specific to the process tree this
  session runs under (VS Code / the Claude Code native binary), not a real
  silence. Confirmed working from **Terminal.app** instead: `max: 0.178,
  rms: 0.024` — real, non-silent audio, permission dialog granted there.
- **Speakers:** confirmed audible by a human (row 7) — after discovering
  the default output device (an HT-S20R soundbar) was off. Both outcomes —
  the initial silent failure and the working retry — are part of the
  finding, not edited out.
- **Mic contention (Chrome `getUserMedia` vs. Python):** **not verified
  this session** — a genuine carried-forward gap, not an assumption dressed
  up as a finding. The brief's own recommendation (Python owns the mic
  exclusively; browser mic path becomes browser-only-mode legacy) is
  adopted as the working default because it's what Day 10 actually built
  (T3 lives entirely in the engine, D37) — but the actual dual-open test
  `scripts/camera-dual-test.mjs` did for video was not repeated for audio.
  Also worth naming honestly: **the process running this session does not
  have reliable mic access itself** (see row 5's context and the mic
  permission story above) — every real audio test this session had to be
  run by the project owner directly in Terminal.app, not by the agent.

### 0.3 — τ walk test: run for real, on the third try
Two attempts wasted a full 20s recording each because the camera wasn't
pointed at a person — a coordination miss between the remote session and
whoever needed to be in frame, not a code or hardware bug. The third
attempt, done right, is real evidence — see row 8 and decisions.md D34.

### 0.4 — Clip-overwrite bug: fixed
`engine/clips/record_and_analyze.py` now writes
`real_clip_<timestamp>.mp4` instead of a fixed `real_clip.mp4` — two lines,
per the brief. The existing `real_clip.mp4` from Day 9 is untouched.

### 0.5 — `debug_window.py`'s window: not confirmed this session either
Still the same shape of open item Day 9 left it in — needs a genuine
interactive-terminal launch to confirm the `cv2.imshow` window is visible,
which this session's process model (detached background execution) can't
provide any better than Day 9's could. Carried forward again, honestly,
rather than re-claimed as fixed without checking.

### 0.6 — Owed shots: not taken this session
Both the re-taken live HUD screenshot into `.claude/day10-images/` and the
microphone-in-frame shot were cut for time — the session's remaining
budget went to closing 0.1–0.3 and Parts 1–3 for real rather than spending
it on screenshots. Carried forward.

## Part 1 — T3 the query loop

`engine/intent.py` and `engine/scene.py` port `parseIntent.ts` and
`describeScene.ts`/`queryObject` to Python. All 20 shared `parseIntent`
cases (`spec/intent-cases.json`) pass in both `npm run test` and
`uv run pytest` — verified by actually running both suites, not assumed.
10 additional `describeScene`/`queryObject` cases ported natively into
`engine/test_scene.py`. `engine/query_loop.py` is the real T3 loop: mic →
VAD (`engine/vad.py`, energy-gate) → Moonshine STT (`engine/stt.py`,
loaded once, ~1.4s load / ~7ms warm silent-audio call) → `parse_intent` →
preemption → forced T1 → `describe_scene`/`query_object` → `say` (TTS,
`engine/tts.py`) → speakers.

**A real end-to-end success, captured live:**
```
[t3] wake match: 'That's your word. Do you see? Hey. Hey. Hey.' ~ 'hey yo' (0.77)
[t3] wake: 'What do you see?' -> describe_scene -> 'two things: a person and a glasses.' (119.1ms)
```
Full log: `engine/clips/t3-live-test-1.txt`.

## Part 2 — silence is the default

Shipped: `query_loop.py`'s `ambient_enabled` defaults `False`;
`engine/ambient.py` only speaks when it's `True` (set by the `wake`
intent, mirroring the browser build's original wake/sleep semantics). Not
built: the browser-side HUD visual mode indicator — the bridge payload
now carries `ambientEnabled` (see `main.py`'s broadcast dict), but no
`src/hud/` code reads it yet. `src/hud/` stays a zero-line diff for Day 10
too, on purpose — see decisions.md D38 for why this was cut rather than
half-built.

## Part 3 — wake phrases

`engine/wake_phrases.txt` ships `hey yap` / `yappy` / `hey yo`, hot-reloaded
on mtime change. `--enable-yo` adds bare `yo`, off by default. **Real,
live finding: "yap" collides with "app" in Moonshine's transcription** —
reported to the project owner during this session; a replacement wake word
was discussed (candidates: "Hey Jarvis", matching the episode's own hook;
"Hey Vision") but **deferred to a future session, owner's explicit call**.
The current phrase list stays live and does work (see the "hey yo" success
above) — this is a real, camera-worthy finding, not a blocker. Full
reasoning and the transcription evidence: decisions.md D39.

## What was cut

- The wake-phrase acceptance bar (10 min false-accept window, 20-utterance
  false-reject count) — only a handful of live utterances were tried this
  session, not the full protocol.
- Row 1/2's full latency breakdown — the instrumentation existed but a
  clean full run (with the logging fix in place) wasn't completed before
  this document was written; the fix ships, the number doesn't yet.
- Mic-contention dual-open test (Chrome + Python simultaneously) for
  audio, the audio equivalent of `camera-dual-test.mjs`.
- `debug_window.py` on-screen confirmation (0.5) and both owed screenshots
  (0.6) — carried forward from Day 9 essentially unchanged.
- The browser-side ambient-mode HUD indicator (Part 2's "the HUD must make
  the mode visible" — the data exists on the wire, nothing reads it yet).
- The wake-word rename itself (D39) — a real replacement phrase, chosen
  and shipped.

## What Day 11 inherits

- **The query loop works, end to end, on real hardware, with zero LLM.**
  That's the load-bearing fact for Day 11: the LLM gets bolted onto a path
  that has already been proven to work deterministically, with a partial
  but real latency baseline (119.1ms for the intent→TTS-start segment
  alone) to compare against once the full wake-to-answer number is
  captured.
- **The forced-fresh-T1 cost (33.4ms) is real and small** — Day 11 adding
  an LLM call in the middle of this loop should budget against that
  number, not against zero.
- **"yap" needs a new name before more wake-word work is worth doing** —
  every phrase built around it inherits the same STT collision.
- **The instrumentation gap (row 1/2) should be the first five minutes of
  Day 11**, not a recurring apology — the fix already shipped
  (`query_loop.py`'s breakdown-dict logging), it just needs one clean run.
