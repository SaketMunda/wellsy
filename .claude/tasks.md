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
**Scope decision:** local LLM and local TTS ship together on Day 4, not split
across two days — the series is already one day over its 7-day target and
splitting would push it to 9. If the day runs long, cut in this order:
salience ranking → spatial language → timing tuning. The LLM and the TTS are
the day; everything else is trim.

- [x] Event narration from Day 3 tracks — **already shipped on Day 3** as a
      side effect of the track-based event switch (see decisions.md D12)
- [ ] Tune `STABLE_MS` / rate limit against real footage — cut, see below
- [ ] Spatial language from bbox position ("on your left") — cut, see below
- [ ] Salience ranking (size, centrality, novelty) — cut, see below
- [x] Decide: rule-based vs LLM for scene description — **local LLM**, no
      cloud, ever (see decisions.md D10)
- [x] Survey tiny on-device LLM options — WebLLM's actual prebuilt catalog
      inspected for real VRAM numbers; **Qwen2.5-0.5B-Instruct-q4f16_1-MLC**
      (944.62 MB, smallest instruct model WebLLM ships) — see decisions.md D13
- [x] Survey local neural TTS options — **Kokoro-82M** via `kokoro-js`
      (`dtype: "q8"`, ~85MB), `speechSynthesis` stays the safe default and
      fallback — see decisions.md D13
- [x] Wire local LLM into `src/narration/generateLine.ts` path — new
      `src/narration/llmLineGenerator.ts`, generate-ahead via an optional
      `prefetch()` hook so the narrator sampler never awaits it; template
      generator is the automatic fallback (not ready, rejected, unavailable)
- [x] Wire local TTS into `src/narration/speech.ts`, same fallback pattern —
      `speechSynthesis` remains the default and the automatic fallback on
      any local-tts failure
- [x] Config + UI: `line_generator_engine`/`voice_engine` toggles in
      `NarratorConfig` and `StatusPanel`, plus live load state/progress and
      latency numbers for whichever engine is active
- [x] Measure and record: model load time (cold ~45–63s, warm ~11.1s with 0
      bytes re-fetched), per-line inference latency (350–567ms), TTS load
      time (~ready alongside LLM in the same run) — see `day4-poc.md`.
      **Peak memory not measured** (no reliable sampling method in this
      environment) and **no mobile device was reachable this session** —
      both stated plainly as unverified in `day4-poc.md`, not assumed
- [x] Confirm zero network calls at runtime — verified two ways: (a) warm
      reload re-fetched 0 bytes from the model hosts, (b) network cut
      entirely mid-session (tab kept open, no reload) and the app kept
      generating new narration lines with 0 requests fired. A **full page
      reload** while offline does fail (`ERR_INTERNET_DISCONNECTED`) — this
      project has no service worker, so the HTML/JS shell itself isn't
      offline-capable; the model-caching claim is separate from that and
      holds. See `day4-poc.md`.
- [x] `npx tsc -b`, `npm run build` (main chunk unchanged at ~1.31MB; LLM and
      TTS each land in their own lazy chunk), `npx oxlint src/`,
      `npm run test` (48 tests, new fake-model-driven suites for both
      adapters) — all clean
- [x] Verified live: headless Chrome + fake camera device (Puppeteer,
      `--enable-unsafe-webgpu`), see `day4-poc.md` for the full run

### Cut this session, per the Day 4 scope decision below
`STABLE_MS`/rate-limit tuning, spatial language, and salience ranking were
all cut in favor of shipping both model swaps — the agreed order was "cut
the last one first," and none of the three were reached. Carried to Day 5+.

### What to film for Day 4
- [ ] Cold open on the network tab, empty, then start the camera — proves
      detection + template narration need zero network from the first frame
- [ ] Same scene narrated three ways, switched live: Day 1 flat English →
      Day 2 templated personality → Day 4 local-LLM line, `StatusPanel`
      visible throughout so the engine toggle and latency numbers are on
      camera, not just claimed
- [ ] The generate-ahead moment: flip to `local-llm` and immediately point
      out the log keeps producing template lines with zero stutter while the
      model downloads in the background in the network tab
- [ ] A second, cached reload — same page, same profile — landing on `LLM:
      ready` in ~11s instead of ~50s+, network tab showing no re-download
- [ ] Local TTS: show the honest state — it loads for real, then falls back
      to the system voice with a visible console warning rather than staying
      silent. Say the bug out loud; don't cut around it (decisions.md D13)
- [ ] Offline test on camera: devtools network → Offline, keep interacting
      (not reload) — narration keeps talking, network tab stays empty
- [ ] State plainly on camera: no audio has been confirmed audible from this
      machine yet (headless dev environment) — first real-speaker check is
      still owed, same as every prior day

## Day 5 — HUD polish — COMPLETE ✅
- [x] `src/hud/hudState.ts` — HUD render-state layer, `updateHudState(prev,
      frame, dtMs, frameW, frameH) -> next`, pure, same shape as
      `tracker.ts`. Per-target acquire progress, exit/fade window (memory
      the tracker itself doesn't keep — see decisions.md D14), stable
      per-id phase, render-time box interpolation (τ = 70ms, D15), primary
      selection (area × centrality, D16) with an eased `primaryProgress`
      for focus transfer
- [x] `src/hud/hudState.test.ts` — 7 unit tests: acquire progress advances
      with dt and caps; a dropped track enters exit and is released after
      `EXIT_MS`; a re-appearing id isn't treated as exiting; interpolation
      converges toward the latest box over ticks; primary picks the larger
      more-central box; `primaryProgress` eases correctly; phase is stable
      across ticks for the same id
- [x] `src/hud/theme.ts` — shared color tokens (cyan/amber/bg/panel/etc.),
      replacing the stray `CYAN`/`AMBER` hex literals and the dead
      `void CYAN;` in `drawHud.ts`. `App.css`'s `:root` mirrors it by hand
      (no CSS-from-TS build step — no new dependency, see decisions.md D14)
- [x] `drawHud.ts` rewritten: single `DrawHudOptions` object instead of an
      8-parameter positional list; consumes `HudState` instead of a raw
      `Frame`; lock-on acquire (brackets converge inward over ~300ms, label
      fades in), lose (brackets release outward + fade over ~300ms),
      per-target breathing motion (phased, not synced), primary-target
      treatment (brighter, glow reserved for primary only — see decisions.md
      D18 — leader-line callout), confidence ring (`Detection.score`, real),
      honest relative-size readout (`SIZE n% OF FRAME`, no fabricated
      distance — decisions.md D17), `prefers-reduced-motion` freezes sweeps/
      pulses/rotation but keeps state-driven fades
- [x] `HudCanvas.tsx` — owns `hudStateRef`, computes real `dtMs` per rAF
      tick (clamped to 100ms against a backgrounded-tab reflow), calls
      `updateHudState` then `drawHud`, measures and reports HUD draw-time to
      the panel at ~4Hz (same throttling pattern as `useDetector`'s stats)
- [x] `StatusPanel.tsx` — new `HUD draw` telemetry stat, warns above 8ms
- [x] `src/hud/SubtitleTrack.tsx` — DOM, not canvas (anchored to the frame,
      not a moving box); shows the latest `LogEntry`, boring-mode aware,
      auto-hides after 4.5s if nothing replaces it
- [x] `src/hud/BootSequence.tsx` — replaces the flat "Loading vision
      model…" curtain; four lines (camera/vision model/tracker/narrator),
      every line's state read from a real prop (`cameraStatus`,
      `modelStatus`, whether the narrator is actually enabled) — no fake
      progress bar, staggered CSS entrance only
- [x] `src/hud/ShortcutOverlay.tsx` + `App.tsx` keydown handler — `Space`
      start/stop, `N` narration, `B` boring mode, `V` voice, `?` overlay;
      ignores typing targets and modifier-key chords
- [x] `App.css` — subtitle/boot/shortcut styles, `prefers-reduced-motion`
      media query freezing the subtitle/boot entrance animations; existing
      900px collapse re-checked with the new elements, still usable at 375px
      (see `day5-poc.md`)
- [x] `npx tsc -b`, `npm run build`, `npx oxlint src/`, `npm run test` (55
      tests, up from 48) all clean; main chunk unchanged at ~1.31MB
- [x] Verified live: headless Chrome + fake camera device (Puppeteer,
      `--enable-unsafe-webgpu`) — see `day5-poc.md` for the full run,
      including the exit-fade caught live on camera stop/restart and the
      narrow-viewport screenshot

### What to film for Day 5
- [ ] Cold open on the boot sequence — start the camera, let each line
      (camera → vision model → tracker → narrator) report in
- [ ] Side-by-side: Day 1 HUD (`label score%`, plain rectangle) vs Day 5 HUD
      (converging brackets, confidence ring, honest size readout) on the
      same object — same model underneath, stated plainly on camera
- [ ] One target acquiring (brackets converge, ~300ms), holding (subtle
      breathing), and being lost (release + fade) — needs a real object
      entering and leaving frame; the fake-camera device's churn showed the
      lose-fade but not a clean single-object acquire/hold/lose arc (see
      `day5-poc.md`)
- [ ] Primary-target focus transferring between two objects — put two
      similarly sized objects in frame and move one closer/more central
- [ ] The subtitle track carrying a narration line with the sound off —
      the actual point of building it (no audio confirmed audible from any
      machine yet, D13)
- [ ] `?` shortcut overlay, then close it and demonstrate each shortcut live
- [ ] Close on the telemetry panel: FPS + HUD draw ms both on screen,
      proving the polish didn't cost the frame budget

## Day 6 — uncertainty + voice — COMPLETE ✅ (items 1–5, 7 of 8)
**Scope reshuffle:** the old Day 6 (WebGPU, adaptive frame skipping,
resolution decoupling) moved to **Day 7**, alongside mobile — see
week-roadmap.md for why. The real Day 6 is two complaints that are the same
complaint: wrong labels, and no way to talk back.

- [x] **Model A/B, timeboxed:** `mobilenet_v2` vs the D2 baseline
      `lite_mobilenet_v2` — measured +50% inference (~11ms → ~16-17ms), FPS
      unaffected. **Reverted**: no real-webcam scene available this session
      to confirm an accuracy gain, so a confirmed cost for an unconfirmed
      benefit was the wrong trade. Recorded as a negative result —
      decisions.md D20.
- [x] **Per-track label voting** (`src/vision/tracker.ts`) — `Track` gains
      `labelVotes`, `labelConfidence` (winning label's vote share, a
      different number from `Detection.score`), `runnerUpLabel`. Label is
      now the decayed-vote argmax, not the latest detection. **Cross-label
      matching** gated on IoU ≥ 0.5 (much stricter than same-label's 0.15)
      fixes the actual id-churn bug: a track surviving the model flipping
      `bed` → `dining table` without minting a new id. Chair/person still
      never merge on a weak overlap. 5 new tests, 11 total in
      `tracker.test.ts` — decisions.md D21.
- [x] **`UNIDENTIFIED` / hedged labels** — below `labelConfidence` 0.6, the
      HUD renders `BED / DINING TABLE ?` in the existing warn color (amber,
      reused not invented) plus a real `LBL nn%` readout; narration switches
      to a dedicated hedge template bank (`templates.ts`'s `HEDGES`); the
      LLM may only *restyle* the hedge, enforced mechanically by
      `sanitizeLlmLine` rejecting any line that doesn't hedge — decisions.md
      D22. Verified live: see day6-poc.md's screenshot.
- [x] **Push-to-talk local ASR** — `Xenova/whisper-tiny.en` via
      `@huggingface/transformers` (promoted to a direct dependency),
      `src/voice/useVoiceInput.ts` + `speechToText.ts`. Hold `T` or the mic
      button; a second, independently-handled `getUserMedia` prompt.
      **Verified working in a production build** (`npm run build && npm run
      preview`) — the exact bundler risk D13 flagged for this dependency
      family did not reproduce for Whisper. decisions.md D24.
- [x] **`parseIntent`** (`src/voice/parseIntent.ts`) — pure, deterministic,
      not the LLM. `wake` / `sleep` / `stop` / `describe_scene` /
      `query_object` / `help` / `unknown`. 8 tests. decisions.md D23.
- [x] **`describeScene` + `queryObject`** (`src/narration/describeScene.ts`)
      — pure functions of `Track[]`, grounded exactly like the pre-Day-3
      `describeScene` this revives (D12). Reports uncertain tracks as
      "unidentified," never guesses. 10 tests.
- [x] **Voice answers preempt narration** — `useNarrator.ts` gained
      `speakAnswer`/`stopAll`; an answer drops the queue, resets the
      rate-limit clock, and lands in the same log/subtitle path as ambient
      narration. `stop` cuts speech immediately regardless of narrator
      `enabled` state. decisions.md D25.
- [x] **Subtitle track shows the user's transcript** — `SubtitleTrack.tsx`
      now renders a second, visually distinct row (dimmer, italic, `>`
      prefix) above YAP's line for the last push-to-talk transcript.
- [x] **Latency breakdown panel** — capture→inference→track→draw→ASR→LLM→TTS,
      kept from the old Day 6 scope per the reshuffle below.
      `useDetector.ts` now separately times `updateTracks` (`trackMs`). No
      fabricated `capture` number — the panel says why one isn't shown.
      decisions.md D25.
- [x] `@huggingface/transformers` promoted from a transitive (`kokoro-js`)
      dependency to a direct one in `package.json` — zero new download,
      just an honest dependency graph.
- [x] `npx tsc -b`, `npm run build`, `npx oxlint src/`, `npm run test` (84
      tests, up from 55) all clean.
- [x] Verified live: headless Chrome + fake-camera device, **dev and
      production/preview builds both** — see day6-poc.md, including a
      direct synthetic-`HudState` screenshot proving the `BED / DINING
      TABLE ?` hedge renders correctly.

### Cut this session
- [ ] **Open-vocabulary relabeling (CLIP)** — item 6 of the day's own build
      order, explicitly optional ("if 6 doesn't land, the microphone is
      still mislabelled and that's fine — you'll have shipped a system that
      says UNIDENTIFIED instead of confidently saying tie"). Not started;
      the real out-of-vocabulary fix (a mic reported as `tie`) is still
      open. Carried to **Day 7 or later** — see week-roadmap.md.
- [ ] **Wake word / always-listening mode** — item 8, explicitly the
      stretch goal. Push-to-talk is a complete feature on its own per the
      day's own brief; not attempted. Carried forward, no fixed day.
- [ ] WebGPU backend, adaptive frame skipping, resolution decoupling — moved
      to **Day 7** (see week-roadmap.md) — the old Day 6 scope, reshuffled
      out before this session started per day6-prompt.md.

### What to film for Day 6
- [ ] Point the camera at a bed/table-ambiguous object (or simulate via the
      synthetic-`HudState` technique used for verification) and watch the
      label settle instead of flickering ids
- [ ] The `BED / DINING TABLE ?` hedge rendering live, amber, with the real
      `LBL nn%` confidence readout in the data card
- [ ] Hold `T`, ask "what do you see" — the transcript appears dim/italic
      above YAP's spoken answer in the subtitle track, sound off
- [ ] Say "stop" mid-narration-line and show it actually cuts off
- [ ] The Voice input panel block: mic status, ASR state/latency, the
      on-device-only note
- [ ] The Latency breakdown panel, all seven-minus-one stages populated
      live, next to the unchanged FPS/inference/draw numbers from Day 5
- [ ] State plainly on camera: no real spoken command has been transcribed
      and checked for accuracy yet — the fake-camera device has no real
      microphone input, same shape of caveat as "no audio confirmed
      audible" from Day 4

## Day 7 (superseded scope) — robustness + mobile + performance
**Superseded by the V2 pivot — see below.** This was Day 7's plan before
`v2-architecture-research.md` and `v2-roadmap.md` existed. None of it
shipped as written; most of it is subsumed by the V2 plan rather than
simply dropped:
- Rear camera + portrait + touch controls, WebGPU backend + WebGL fallback,
  adaptive frame skipping, decoupling detection/display resolution — all of
  this was aimed at making the *browser build* faster and more mobile-ready.
  V2's tier scheduler (T0–T3, `v2-architecture-research.md` §2a) replaces
  "skip frames on a static scene" with a structural always-on-but-cheap /
  on-demand-but-expensive design, and mobile is now Day 14 territory with a
  different engine underneath. Not done as originally scoped; superseded by
  a better version of the same goal.
- Permission-denied / no-camera / model-load-failure handling and low-light
  behavior — genuinely still open, still real V1 (browser build) gaps,
  worth doing if the browser mode gets more filming use, but not part of
  the V2 critical path Days 7–15.
- Open-vocabulary CLIP relabeling and wake word — explicitly still on the
  table, now as Day 8 (open-vocab, via YOLOE) and Day 10 (wake word,
  §10.2 open decision) in `v2-roadmap.md`, with a real fix instead of a
  browser-side CLIP crop classifier.

## Day 7 — "I built the wrong thing" — the autopsy + the foundation — COMPLETE ✅
**Supersedes the scope above.** See `v2-roadmap.md` and
`v2-architecture-research.md` for why. Full results: `day7-baseline.md`.
- [x] `?bench=1` instrumentation (`src/bench/frameRecorder.ts`) — rAF-delta
      ring buffer + `PerformanceObserver('longtask')`, gated entirely behind
      the query flag, zero effect on the normal path
- [x] `scripts/bench.mjs` + `scripts/generate-bench-assets.sh` — headless
      Chrome/Puppeteer harness driving scenarios A–E against real fake-camera
      video, not manual clicking
- [x] **Methodology bug found and fixed before trusting a number**: a 15fps
      fake-video source was silently throttling every rAF loop in the page
      (detect, draw, the bench recorder itself) to 15Hz — not a real cost.
      Fixed by regenerating source video at 30fps; documented in
      day7-baseline.md and `generate-bench-assets.sh` so it isn't
      rediscovered on Day 8.
- [x] Scenarios A–E measured, `day7-baseline.md` written — all five held a
      clean 60fps/zero-longtask result; the local-llm/local-tts/ASR stack
      never finished loading this session (network conditions, not a code
      bug — D13's fallback path handled it correctly throughout), so the
      genuine compute stall the day was built to capture is a carried
      item for Day 8, not something papered over as measured
- [x] `public-notes.md` — "no backend", "runs entirely in your browser",
      "video never leaves your device" struck through and dated; "no API
      keys" confirmed as the surviving claim; NOT-real list extended with
      depth, face recognition, open-vocabulary detection, "runs on my phone"
- [x] `engine/` — Python skeleton: `capture.py` (camera in its own
      `multiprocessing.Process`, `cv2.CAP_AVFOUNDATION`), `motion.py` (pure
      frame-differencing gate), `main.py` (JSON lines on stdout). `--synthetic`
      mode exercises the full process-boundary/queue path without a camera.
- [x] Real camera capture verified working end-to-end this session
      (1920×1080@30 reported), after an initial permission failure from a
      colder process context — both outcomes recorded honestly, see
      day7-baseline.md
- [x] Motion gate cost measured: synthetic ~0.25ms p50; real camera (native
      res downscaled for the gate) ~1.31ms p50 — over the ~1ms target,
      by a knowable, explained amount
- [x] Latest-wins depth-1 queue (decisions.md D29) verified — no buffering
      observed in either run
- [x] Gated fraction on a still scene: 100% over 65s, both synthetic and
      real camera — flagged as needing a real-motion comparison before being
      treated as the tier scheduler's settled headline number
- [ ] *(Optional, cut)* detection in a Web Worker, comparing scenario C —
      no detection loop exists yet in this build to move; not applicable
      until Day 8's Python vision core exists. Not the same experiment as
      originally scoped (moving the *browser's* TF.js loop off-thread) —
      that specific bonus experiment is now moot since V2 doesn't keep the
      browser as the detection host. Not missed; superseded.

## Day 8 — ship
- [ ] Deploy static build to a public URL
- [ ] README with GIF + honest capability/limitation list
- [ ] Final 60–90s demo recording
- [ ] Series wrap-up write-up

**Note:** the above is the *original* Day 8 (browser-build-era) plan.
`v2-roadmap.md` now owns Days 8–15 with a different shape — see that file.
This entry stays as a record of what was originally planned, same as the
superseded Day 7 block above.

## Day 8 (V2) — carried forward
No camera access this session (sandboxed, no display/hardware) — everything
below needs a real machine with a camera before it can close. See
`day8-results.md` and `decisions.md` D30-D32 for what *did* ship without one.
- [ ] Run the intermittent-motion test against a **real** clip (enter, hold
      still 20s, move again) — this session only had a staged synthetic
      stand-in (`--synthetic-intermittent`). Confirms/changes `MOTION_THRESHOLD`
      (currently 4.0, unchanged, explicitly not tuned — D32).
- [ ] Shoot the bed/microphone comparison and the live `prompts.txt`-edit
      demo through `engine/debug_window.py` — written, untested against real
      hardware.
- [ ] Re-measure motion-gate cost on real camera frames (Day 7's 1.31ms p50)
      once/if the camera capture resolution changes (build-order item 8, cut
      for time this session).
- [ ] `prompts.txt` hot-reload is implemented (mtime check in `main.py`'s
      loop) but only exercised against synthetic frames — confirm it behaves
      the same mid-session on a real camera run.
- [ ] Day 3's track-id-persistence clip (walk out of frame and back, confirm
      id persists) — still not shot; still needs a real webcam. Not
      attempted this session either (no camera access), so this stays open,
      not closed.

## Known issues
- Narration timing values (`STABLE_MS`, `min_seconds_between_lines`) still need
  tuning against real footage → Day 4
- Bundle is ~1.3MB (TF.js) — code-split or lazy-load the model → Day 6/8
- `object-fit: cover` will crop if a camera reports a non-16:9 aspect → Day 7
