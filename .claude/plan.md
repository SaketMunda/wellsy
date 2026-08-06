# Plan

**Aligned with the implementation as of Day 1.**

## Strategy
Ship the smallest complete loop first, then deepen one layer per day. The loop
(camera → detect → draw → speak) existed on Day 1; every subsequent day
improves a link in that chain rather than adding a new chain.

This is deliberate: it means there is always a working demo, and every day's
change is directly visible against yesterday's.

## Layer-per-day mapping

| Day | Layer deepened | Files touched |
|---|---|---|
| 1 | The whole loop, thin | all |
| 2 | Detection → **tracking** | `vision/` (+ new `tracker.ts`) |
| 3 | **Narration** logic | `narration/` |
| 4 | **HUD** presentation | `hud/` |
| 5 | **Performance** | `vision/useDetector.ts` |
| 6 | **Robustness** + mobile | `vision/useCamera.ts`, tests |
| 7 | Deploy + docs | root |

Note the near-perfect file isolation per day — that's the payoff from the
layering rule in [architecture.md](architecture.md), and it's what makes each
day's diff explainable in public.

## Day 1 — done
See [day1-poc.md](day1-poc.md).

## Day 2 — next up, concrete
1. `src/vision/tracker.ts` — IoU-based matcher. Pure function:
   `(previousTracks, newDetections) → updatedTracks`. Keep it pure so it's
   testable and explainable.
2. Add `id`, `ageMs`, `missedFrames` to the `Detection`/`Track` type.
3. Exponential smoothing on box position (`α ≈ 0.4`) to kill jitter.
4. Keep tracks alive for ~5 missed frames before dropping.
5. HUD shows `PERSON #3 · 4.2s`.
6. Narrator switches from set-difference to track enter/exit events — strictly
   better signal, and it simplifies `useNarrator`.

**Timebox:** IoU matching only. No Kalman filter, no re-identification.

## Open questions
- **Day 3:** does narration need a real LLM for scene-level description, or is
  rule-based enough? Decide *after* seeing tuned rule-based output — the rules
  may well be enough, and a cloud call breaks the on-device story (see D1).
- **Day 5:** is WebGPU actually faster here? Measure, don't assume. A negative
  result is publishable.
- **Day 6:** does mobile need a smaller input resolution to hold framerate?
  Likely yes.

## Success criteria for the week
- [ ] Runs at ≥15 FPS on a normal laptop **and** a phone
- [ ] Boxes look locked-on, not jittery
- [ ] Narration is something you'd voluntarily leave switched on
- [ ] A stranger can open a URL and it works in under 30 seconds
- [ ] 7 days of honest, specific public content
