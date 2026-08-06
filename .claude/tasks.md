# Tasks

## Day 1 — COMPLETE ✅
- [x] Inspect repo (empty — greenfield)
- [x] Choose stack: Vite + React + TS, TF.js, browser-only
- [x] Scaffold project, install `@tensorflow/tfjs` + `@tensorflow-models/coco-ssd`
- [x] `useCamera` — getUserMedia, status states, cleanup on unmount
- [x] `useDetector` — model load, rAF detect loop, ref-based frame output, FPS
- [x] `drawHud` — brackets, labels, crosshair, frame corners, scanline, tracking line
- [x] `HudCanvas` — independent draw loop, DPR-correct sizing
- [x] `describeScene` — pure detections → English, pluralisation, change-diffing
- [x] `useNarrator` — stability gate, cooldown, speech synthesis, log
- [x] `StatusPanel` — telemetry + narration log
- [x] HUD styling
- [x] Typecheck + production build clean
- [x] Verify in headless Chrome with fake camera device
- [x] **Fix: mirrored label text** (mirror coords, not canvas)
- [x] `.claude/` workspace populated

## Day 1 — carried forward
- [ ] **Verify on a real webcam** — raise one hand, confirm the box tracks the
      correct side of the screen (confirms the mirror fix on an asymmetric scene)
- [ ] Confirm speech audio works in a real browser (headless has no voices)
- [ ] Record the demo video

## Day 2 — tracking
- [ ] `src/vision/tracker.ts` — IoU matcher, pure function
- [ ] `Track` type: `id`, `ageMs`, `missedFrames` alongside label/score/bbox
- [ ] Exponential position smoothing (α ≈ 0.4)
- [ ] Keep tracks alive ~5 missed frames
- [ ] HUD: show track ID + age
- [ ] Narrator: switch to track enter/exit events
- [ ] Capture a jitter before/after clip for content

## Day 3 — narration
- [ ] Tune `STABLE_MS` / `COOLDOWN_MS` against real footage
- [ ] Spatial language from bbox position ("on your left")
- [ ] Salience ranking (size, centrality, novelty)
- [ ] Event narration from Day 2 tracks
- [ ] Decide: rule-based vs LLM for scene description

## Day 4 — HUD polish
- [ ] Lock-on acquire animation
- [ ] Confidence ring / distance estimate
- [ ] Primary-target treatment
- [ ] On-frame subtitle track
- [ ] Keyboard shortcuts

## Day 5 — performance
- [ ] WebGPU backend + fallback, **measured**
- [ ] Adaptive frame skipping on static scenes
- [ ] Decouple detection resolution from display resolution
- [ ] Latency breakdown panel
- [ ] Before/after benchmark table

## Day 6 — robustness
- [ ] Rear camera + portrait + touch controls
- [ ] Handle: permission denied, no camera, model load failure
- [ ] Pause detection when tab is backgrounded
- [ ] Unit tests for `describeScene` and `tracker`
- [ ] Low-light behaviour documented honestly

## Day 7 — ship
- [ ] Deploy static build to a public URL
- [ ] README with GIF + honest capability/limitation list
- [ ] Final 60–90s demo recording
- [ ] Series wrap-up write-up

## Known issues
- Boxes jitter (no temporal tracking) → Day 2
- Narration timing values are untuned guesses → Day 3
- Bundle is ~1.3MB (TF.js) — code-split or lazy-load the model → Day 5/7
- `object-fit: cover` will crop if a camera reports a non-16:9 aspect → Day 6
