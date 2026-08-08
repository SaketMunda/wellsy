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

## Day 2 — narration latency — COMPLETE ✅
- [x] Verify `src/narration/events.ts` — settled scenes become structured
      events (appear/disappear/count_change/still_present), no opinions
- [x] Verify `src/narration/useNarrator.ts` — narration runs on its own 250ms
      sampler (`SAMPLE_MS`), gated on a 900ms stability window (`STABLE_MS`),
      never reads the raw per-frame detect loop
- [x] Verify rate limit — one line per `min_seconds_between_lines` (default
      4s, `src/narration/config.ts`), `byInterest` picks the most interesting
      event when several land in one window and folds a second in as an aside
- [x] Confirm no code path still fires narration on every detection frame —
      none found; the architecture already matched the Day 2 script
- [x] Remove `src/demo/` failure-injection layer (`controller.ts`,
      `brokenLine.ts`, `brokenTemplates.ts`, `config.ts`, `useDemoMode.ts`,
      `DemoIndicator.tsx`, `demo.test.ts`, `types.ts`) and all wiring in
      `App.tsx`, `HudCanvas.tsx`, `useNarrator.ts`, `StatusPanel.tsx`,
      `drawHud.ts`, `App.css`
- [x] Delete `.claude/ep03-cue-sheet.md`
- [x] `npx tsc -b`, `npm run build`, `npx oxlint src/`, `npm run test` all
      clean after removal
- [x] Write up Day 2 in `.claude/week-roadmap.md`, `.claude/public-notes.md`,
      `.claude/demo-script.md`, `.claude/day2-poc.md`, `.claude/progress-log.md`

### What to film for Day 2
- [ ] Cold open on the telemetry panel with narration on — read
      `SAMPLE_MS`/`STABLE_MS`/rate-limit numbers off `.claude/day2-poc.md`
- [ ] "Boring mode" toggle showing a literal event line next to its styled
      narration line — the on-camera proof it's driven by real detections
- [ ] 15–20s of moving objects in and out of frame quickly, log visibly
      capping at ~1 line/4s despite more happening than that
- [ ] Confirm speech audio out loud on the recording machine (not yet verified
      in this session — see day2-poc.md)
- [ ] Record the demo per `.claude/demo-script.md`'s Day 2 flow

## Day 3 — tracking — COMPLETE ✅
- [x] `src/vision/tracker.ts` — `updateTracks(previousTracks, detections, dtMs, nextId)`,
      IoU matcher (same-label + IoU ≥ 0.3), pure function
- [x] `Track` type in `src/vision/types.ts`: extends `Detection` with `id`,
      `ageMs`, `missedFrames`; `Frame` now carries `tracks: Track[]` alongside
      `detections`
- [x] Exponential position smoothing, α = 0.4, on matched boxes
- [x] Tracks survive up to 5 missed frames before being dropped
- [x] HUD (`drawHud.ts`): label reads `LABEL #id · age`s, e.g. `KITE #13 · 0.3s`
      — replaces the old `label score%` display
- [x] Narrator (`events.ts`/`useNarrator.ts`): `createEventTracker.update` now
      takes `Track[]` directly; appear/disappear are per-track-id, and the
      stability gate in `useNarrator.ts` compares the sorted track-id set
      instead of label counts
- [x] `count_change` retained as a type/template bank for compatibility but is
      now unreachable from the track-based path — see decisions.md
- [x] Deleted `src/narration/describeScene.ts` and `SceneState` (dead after
      the switch to track-based events — nothing imported them anymore)
- [x] `npx tsc -b`, `npm run build`, `npx oxlint src/`, `npm run test` (23
      tests, event-tracker suite rewritten for the new signature) all clean
- [x] Verified live: headless Chrome + fake camera device, see `day3-poc.md`
- [ ] Capture a jitter before/after clip for content — needs a real webcam,
      see "What to film" below

### What to film for Day 3
- [ ] Side-by-side: Day 1 HUD (bare `label score%`, visibly jittery box) vs
      Day 3 HUD (`LABEL #id · age`, smoothed box) on the same movement
- [ ] Walk out of frame and back within ~1s — confirm the id persists rather
      than resetting (needs a real webcam; the fake camera device's synthetic
      pattern doesn't hold a stable scene long enough to demonstrate this —
      see `day3-poc.md`)
- [ ] A second object of the same class entering — confirm the narration log
      says "person #2 appeared" rather than "now 2 person"
- [ ] Record the demo per `.claude/demo-script.md`'s Day 3 flow

## Day 4 — narration + local voice
- [ ] Tune `STABLE_MS` / rate limit against real footage
- [ ] Spatial language from bbox position ("on your left")
- [ ] Salience ranking (size, centrality, novelty)
- [ ] Event narration from Day 3 tracks
- [x] Decide: rule-based vs LLM for scene description — **local LLM**, no
      cloud, ever (see decisions.md D10)
- [ ] Survey tiny on-device LLM options (in-browser: WebLLM/Transformers.js
      + a small GGUF/ONNX model; check what's actually mobile-viable, not
      just desktop-viable) — pick on measured latency, not defaults
- [ ] Survey local neural TTS options (in-browser or on-device — needs to
      replace `speechSynthesis` without adding a network dependency)
- [ ] Wire local LLM into `src/narration/generateLine.ts` path as the new
      line generator, keep the template generator as a fallback/off-mode
- [ ] Wire local TTS into `src/narration/speech.ts`, same fallback pattern
- [ ] Measure and record: model load time, per-line inference latency, memory
      footprint — on both desktop and (if available) a mobile device
- [ ] Confirm zero network calls at runtime (check the network tab, not just
      the code) — this is the claim, so verify it like one

## Day 5 — HUD polish
- [ ] Lock-on acquire animation
- [ ] Confidence ring / distance estimate
- [ ] Primary-target treatment
- [ ] On-frame subtitle track
- [ ] Keyboard shortcuts

## Day 6 — performance
- [ ] WebGPU backend + fallback, **measured**
- [ ] Adaptive frame skipping on static scenes
- [ ] Decouple detection resolution from display resolution
- [ ] Latency breakdown panel
- [ ] Before/after benchmark table

## Day 7 — robustness
- [ ] Rear camera + portrait + touch controls
- [ ] Handle: permission denied, no camera, model load failure
- [ ] Pause detection when tab is backgrounded
- [ ] Unit tests for `describeScene` and `tracker`
- [ ] Low-light behaviour documented honestly

## Day 8 — ship
- [ ] Deploy static build to a public URL
- [ ] README with GIF + honest capability/limitation list
- [ ] Final 60–90s demo recording
- [ ] Series wrap-up write-up

## Known issues
- Narration timing values (`STABLE_MS`, `min_seconds_between_lines`) still need
  tuning against real footage → Day 4
- Bundle is ~1.3MB (TF.js) — code-split or lazy-load the model → Day 6/8
- `object-fit: cover` will crop if a camera reports a non-16:9 aspect → Day 7
