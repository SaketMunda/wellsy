# Day 2 POC — narration latency, verified

## The claim being verified

The Day 2 script says narration used to be chained to the 60fps detect loop
and needed two fixes: **events, not frames**, and **decouple + rate-limit**.
This session's job was to check whether that fix already exists in the
codebase (it does — shipped as part of the narrator-personality work) and
remove anything that still contradicted it.

## What works, verified

1. **Detection still runs untouched at its own rate** — `src/vision/useDetector.ts`
   drives a `requestAnimationFrame` loop independent of narration.
2. **Narration never reads the raw per-frame stream.** `src/narration/useNarrator.ts`
   runs its own `setInterval(..., SAMPLE_MS)` (250ms), requires the scene to
   hold unchanged for `STABLE_MS` (900ms) before treating it as "settled", and
   only then feeds it to `createEventTracker().update(...)` in
   `src/narration/events.ts`.
3. **Events, not frames.** The tracker turns a settled scene into structured
   `NarrationEvent`s (`appear` / `disappear` / `count_change` / `still_present`)
   — no opinions, just facts about what changed since the previous settled
   scene.
4. **Rate limit.** `useNarrator` will not speak more than once per
   `config.min_seconds_between_lines` (default **4 seconds**,
   `src/narration/config.ts:18`). When multiple events queue up inside one
   window, `byInterest` (`appear` > `disappear` > `count_change` >
   `still_present`) picks the most interesting as the primary line and folds a
   second one in as an aside — nothing is dropped silently, but nothing is
   read out sixty times a second either.
5. **No gap found.** Grepped and read `useNarrator.ts` end to end — every code
   path that reaches `generateLine`/`speak` goes through the sampler → stable
   check → event tracker → rate limit chain. There is no code path left that
   fires narration per raw detection frame.

## Verification method

- **Read** `src/narration/events.ts`, `src/narration/useNarrator.ts`,
  `src/narration/config.ts` end to end (not just this prompt's summary of
  them).
- **Unit tests**: `npm run test` — 23 tests pass, including
  `describe('event tracker', ...)` in `src/narration/narrator.test.ts`, which
  directly exercises `createEventTracker` for truthful appear/count_change/
  disappear emission, idle escalation, and idle-clock reset on count change.
- **Live run**: headless Chrome (Puppeteer) against `npm run dev`, camera
  started with a synthetic fake-device video, narration on, "boring mode" on.
  Observed for 2 minutes:
  ```
  FPS:        60.0–60.4
  Inference:  11 ms
  Console errors: none
  ```

## What is NOT verified from the live run — stated plainly

- **An actual narration line firing end-to-end.** The synthetic fake-camera
  pattern flickers between 0 and 1 detected targets roughly every 5 seconds —
  it never holds still for the full 900ms `STABLE_MS` window, so no scene ever
  "settles" and the log stayed empty for the full 2-minute observation. This
  is the same limitation Day 1 already noted for the stability gate: the
  synthetic device is too noisy to hold a stable scene. It's also indirect
  confirmation the stability gate is doing its job — a jittery input produces
  zero spoken lines, not sixty.
- **Speech audio.** Headless Chrome has no voices, same caveat as Day 1.
- **Real-scene rate-limit behavior** (one line roughly every 4+ seconds under
  actual movement) needs a real webcam with real appear/disappear/count-change
  events — first thing to check when recording.

## First real-webcam check to run

Start the camera, turn narration + boring mode on, move a few objects in and
out of frame over 20–30 seconds. Confirm: the narration log grows roughly once
every 4+ seconds despite more happening than that, and each styled line's
"boring" counterpart is a literal `appear`/`disappear`/`count_change` line
naming a real object.

## Running it

```bash
npm install
npm run dev
# open http://localhost:5183 (or whatever port Vite picks) and click "Start camera"
```

## Deliberately not done on Day 2

- No literal "broken" narrator to demo against — the `src/demo/` staged
  failure layer was deleted (see `.claude/progress-log.md`); the before/after
  story is told through the code history and the telemetry, not a
  reconstructed regression.
- Narration timing (`STABLE_MS`, `min_seconds_between_lines`) is still
  untuned against real footage — that's Day 4's job.
