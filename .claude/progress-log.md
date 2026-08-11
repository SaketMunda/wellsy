# Progress Log

---

## Day 1 — 2026-08-06

**Goal:** Ship the smallest credible loop. Camera in, HUD and voice out.

### Researched
- Browser detection options — TF.js/COCO-SSD vs MediaPipe vs cloud API.
  Chose TF.js: two npm packages, ~12ms inference, no assets to wrangle.
- Why single-shot detection is what makes real-time in-browser possible.
- Narration timing — established early that *when to speak* is the hard problem,
  not *what to say*.

### Decided
Nine decisions recorded in [decisions.md](decisions.md). The load-bearing ones:
- **Browser-only, no backend** — latency + privacy + shipping speed in one choice
- **Detections in a ref, not React state** — the key performance decision
- **Detect loop and draw loop are separate** — smooth HUD regardless of inference rate
- **Narration gates on stability, then describes change** — not the full scene

### Built
```
src/vision/    types.ts, useCamera.ts, useDetector.ts
src/hud/       drawHud.ts, HudCanvas.tsx, StatusPanel.tsx
src/narration/ describeScene.ts, useNarrator.ts
src/App.tsx    composition
```
Full loop: camera → COCO-SSD on WebGL → canvas HUD → spoken narration, plus a
live telemetry panel.

### Verified
Real headless Chrome with a synthetic camera device:
`camera live · model ready · 59.8 FPS · 12ms inference · 0 console errors`.
Production build compiles clean.

### Found and fixed
**Label text rendered backwards.** The overlay canvas was CSS-mirrored to match
the mirrored selfie video — which mirrors text too. Caught by *looking at a
screenshot*, not by the build. Fixed by mirroring box coordinates rather than
the canvas.

Worth noting: a green typecheck and a clean build both passed while this bug was
live. Visual verification caught what static checks structurally could not.

### Still missing
- Detection quality on a **real scene** is unverified — the synthetic camera is
  an abstract colour pattern. Needs a real webcam.
- Narration timing numbers are **first guesses**, untuned against real footage.
- Speech audio unverified (headless Chrome has no voices).
- No temporal tracking → boxes jitter.
- Desktop only.

### Can be shown publicly
Everything. The loop is real and self-evidencing: live boxes, on-screen
telemetry, spoken narration. The mirroring bug is a genuinely good story, and
the jittery boxes are a natural cliffhanger for Day 2.

**Hook:** *"I gave my laptop eyes in one day. It just told me what's on my desk."*

### Next
Day 2 — narration latency: events, not frames; decouple + rate-limit.

---

## Day 2 — 2026-08-07

**Goal:** The roadmap owner decided Day 2's story is a bug-and-fix: narration
was chained to the 60fps detect loop, sixty opinions a second, all fighting
each other. Two fixes — talk about events, not frames; decouple narration onto
its own clock with a rate limit. Also: reschedule the week (old Day 2–7 become
3–8), and retire the `src/demo/` "broken mode" layer that Day 2 no longer needs.

### Researched
- Read `src/narration/events.ts`, `src/narration/useNarrator.ts`,
  `src/narration/config.ts` end to end, rather than trusting the reshuffle
  prompt's summary of them.
- Traced every code path in `useNarrator` that reaches `speak`/`generateLine`
  to confirm none of them bypass the sampler → stability gate → event tracker
  → rate limit chain.

### Decided
- **Treat this as "apply the fix if it's there," not "build it."** The
  narrator-personality work already shipped this architecture before this
  session started. No gap was found — nothing still fires narration on raw
  per-frame detections — so no narration code needed to change for the fix
  itself.
- **Retire the demo/failure-injection layer entirely** rather than keep it
  around unused, since Day 2's story no longer needs a staged "broken mode"
  episode.
- **Renumber the roadmap** — old Day 2 (tracking) through Day 7 (ship) shift to
  Day 3 through Day 8, across `week-roadmap.md`, `tasks.md`, `plan.md`, and
  `public-notes.md`.

### Built
- Verified (no code change needed): the events-not-frames + decoupled +
  rate-limited narration architecture, against both the source and the
  existing 23-test suite in `src/narration/narrator.test.ts`.
- Removed `src/demo/` (all 8 files) and its wiring from `App.tsx`,
  `HudCanvas.tsx`, `useNarrator.ts`, `StatusPanel.tsx`, `drawHud.ts`,
  `App.css`; deleted `.claude/ep03-cue-sheet.md`; cleaned two stale comments
  in `src/narration/ids.ts` and `templates.ts` that referenced the removed
  layer.
- `.claude/week-roadmap.md`, `.claude/tasks.md`, `.claude/plan.md`,
  `.claude/public-notes.md` renumbered; new Day 2 sections written in the
  existing voice.
- `.claude/demo-script.md` — Day 2 demo flow, built around live telemetry
  instead of a staged before/after (reconstructing the old frame-chained
  narrator would mean deliberately regressing working code, which this
  project's own rules treat as staging a fake failure).
- `.claude/day2-poc.md` — verification notes and observed numbers.

### Verified
`npx tsc -b`, `npm run build`, `npx oxlint src/`, and `npm run test` (23
tests) all clean after the demo-layer removal. Headless Chrome (Puppeteer,
synthetic fake-camera device) confirmed detection still runs independently at
`60.0–60.4 FPS`, `11ms` inference, `0` console errors, over a 2-minute
observation window.

### Still missing
- **An actual narration line observed end-to-end.** The synthetic fake-camera
  pattern flickers too fast (0/1 targets, roughly every 5s) to ever hold the
  900ms `STABLE_MS` window, so the log stayed empty for the full 2-minute
  headless run — same limitation Day 1 already flagged for this stability
  gate. That the log stayed silent under constant flicker is itself
  consistent with the gate working, but a real settled event was not watched
  firing live in this session.
- **Speech audio** — unverified, headless Chrome has no voices (same caveat as
  Day 1).
- **Narration timing tuned against real footage** — still Day 4's job, per the
  rescheduled roadmap.

### Can be shown publicly
The architecture story is real and verifiable in the code and tests: events,
not frames; a decoupled 250ms sampler; a 4-second rate limit; "boring mode"
proving each styled line traces to a real detection event. The removal of the
demo layer is also honest content — it shows the project keeping only what the
current story needs.

**Hook:** *"YAP had two jobs running at two speeds. The eyes kept up. The
mouth was drowning."*

### Next
Day 3 — IoU tracking, box smoothing, persistent object IDs (the original
Day 2 plan, now one day later).

---

## Day 3 — 2026-08-08

**Goal:** Give detections identity across frames. Detection answers "what's
here now"; tracking answers "is this the same thing as before" — boxes stop
jittering and get a persistent id + age.

### Researched
- Read `architecture.md`, `decisions.md`, `week-roadmap.md`/`tasks.md` Day 3
  sections, `public-notes.md`, and the full vision/hud/narration source
  (`types.ts`, `useDetector.ts`, `drawHud.ts`, `HudCanvas.tsx`, `events.ts`,
  `useNarrator.ts`, `describeScene.ts`, `generateLine.ts`, `templates.ts`)
  before writing anything, per the session brief.
- Confirmed `describeScene.ts`/`SceneState` were only ever consumed by
  `useNarrator.ts` (`toSceneState`/`sameScene`) — safe to retire once the
  narrator moved to track-based input.
- Confirmed the existing `narrator.test.ts` template-bank tests construct
  `NarrationEvent` objects directly and don't touch `createEventTracker`, so
  keeping `count_change` in the type/template system wouldn't need those
  tests rewritten — only the dedicated "event tracker" describe block would.

### Decided
Two new entries in [decisions.md](decisions.md) (D11, D12):
- **Same-label IoU matching, α = 0.4 smoothing, 5-missed-frame grace** — the
  simplest tracker that kills jitter and survives brief occlusion without a
  Kalman filter or re-identification, per the explicit Day 3 timebox.
- **`count_change` goes dormant rather than deleted.** Track-based events mean
  every count delta already rides an `appear`/`disappear` for the specific
  track that caused it, so `count_change` has no remaining trigger from
  `createEventTracker`. Deleting the type, its ~25 authored template lines,
  and updating their dedicated tests was judged bigger than Day 3's actual
  ask; it stays defined and revisit-flagged instead of quietly vanishing.

### Built
```
src/vision/tracker.ts     updateTracks() — pure IoU matcher + smoothing (new)
src/vision/types.ts       Track type, Frame.tracks (new)
src/vision/useDetector.ts wires the tracker into the detect loop
src/hud/drawHud.ts        renders tracks: "LABEL #id · age" replaces "label score%"
src/narration/events.ts   createEventTracker.update(tracks, now, idle) — track-based
src/narration/useNarrator.ts  stability gate compares track-id sets, not label counts
src/narration/describeScene.ts  deleted (dead once useNarrator stopped calling it)
```
`src/narration/narrator.test.ts`'s "event tracker" suite rewritten for the
new `Track[]`-based signature; the template-bank/generateLine suites were
untouched since they don't depend on event derivation.

### Verified
- `npx tsc -b`, `npm run build`, `npx oxlint src/`, `npm run test` (23 tests)
  all clean.
- **Live, headless Chrome + fake camera device (Puppeteer):**
  `camera live · model ready · 60.0–60.1 FPS · 12ms inference · 0 console
  errors`.
- Temporarily instrumented the detect loop to log each frame's tracks
  (id/label/ageMs/missedFrames/bbox), observed over ~30 samples, then removed
  the instrumentation before finishing. Confirmed: ids assigned monotonically
  and hold steady across consecutive frames; `missedFrames` climbs during a
  gap (seen up to 3) before a track is dropped and a fresh id takes its
  place; `ageMs` accumulates correctly frame to frame; bbox values move
  gradually toward the new detection rather than jumping — smoothing is
  visibly active, not a no-op.
- **Screenshot confirms the HUD label change**: captured `KITE #13 · 0.3s`
  rendered on a live bracket, replacing the old `label score%` format —
  see `day3-poc.md`.

### Still missing
- **Real-webcam verification of occlusion recovery and new-object-gets-new-id**
  — the fake-camera device's synthetic pattern doesn't hold a stable
  detection long enough to walk something out of frame and back, the same
  limitation Day 1/2 already noted for narration stability. First thing to
  check when recording.
- **A jitter before/after clip** — the headline demo asset for the day —
  needs a real webcam and real movement, not the synthetic pattern.
- **Smoothing/grace-window tuning against real footage** — α = 0.4 and the
  5-missed-frame threshold are reasonable defaults, not measured against a
  real camera's actual frame-drop behavior yet.
- Speech audio — still unverified in headless Chrome (no voices), same
  caveat as every prior day.

### Can be shown publicly
The tracker is real and independently verifiable: the HUD literally displays
`LABEL #id · age`, which only a working tracker can produce, and the
architecture change (events derived from track identity, not count-diffing)
is a genuinely more accurate design, not just a relabeling. The still-missing
real-webcam clip is an honest cliffhanger — Day 1 and Day 2 both had one too.

**Hook:** *"Yesterday it saw. Today it remembers."*

### Next
Day 4 — narration tuned against real footage, spatial language, salience
ranking, event narration built on Day 3 tracks, and the local-LLM/local-TTS
voice upgrade (per D10 — no cloud, ever).

---

## Day 4 — 2026-08-09

### Researched
- Read `decisions.md` (D1, D10 binding), `week-roadmap.md`/`tasks.md` Day 4
  sections, `architecture.md`, `public-notes.md`, and all of `src/narration/`
  before writing anything, per the session brief.
- Inspected `@mlc-ai/web-llm`'s actual prebuilt model catalog
  (`node_modules/@mlc-ai/web-llm/lib/index.js`) for real `vram_required_MB`
  figures rather than picking a model from a README table — Qwen2.5-0.5B-
  Instruct-q4f16_1-MLC (944.62 MB, `low_resource_required: true`) is the
  smallest instruct-tuned model WebLLM currently ships.
- Read `kokoro-js`'s type definitions and README for its `dtype`/`device`
  options before choosing `q8` (~85MB) over `fp32` (~326MB, the README's
  WebGPU recommendation) — the download-size floor mattered more here than
  the WebGPU-path quality delta, given D10's mobile-latency framing.
- Confirmed via `grep` that neither `pickVoice` nor `speak`/`primeSpeech`/
  `stopSpeaking` from `speech.ts` were consumed anywhere outside
  `useNarrator.ts`, so widening `speech.ts`'s internals was safe without a
  wider blast radius.

### Decided
One new entry in [decisions.md](decisions.md) (D13):
- **Qwen2.5-0.5B-Instruct via WebLLM** for the line generator, **Kokoro-82M
  via `kokoro-js`** for TTS — both chosen against measured catalog numbers,
  not vibes.
- **Generate-ahead, not widen-to-async.** `LineGenerator` stays synchronous;
  a new optional `prefetch(event)` hook starts inference the moment an event
  is queued (well before its narration slot), and `generateLine`/`foldLine`
  read a cache, falling back to templates if it isn't ready. Chosen because
  widening to `Promise<string>` would force the 250ms sampler to either
  block or grow its own polling logic — generate-ahead gets that for free
  from timing the project already has (900ms stability + 4s rate limit).
- **Character enforcement is a filter (`sanitizeLlmLine`), not a prompt and
  a hope** — word-ceiling truncation, banned-word/swear rejection, all
  independent of whatever the system prompt actually got the model to do.

### Built
```
src/narration/llmLineGenerator.ts   local-LLM LineGenerator, prefetch + WeakMap cache (new)
src/narration/llmLineGenerator.test.ts  13 tests against a fake engine (new)
src/narration/localTts.test.ts      5 tests against a fake TTS model (new)
src/narration/generateLine.ts       LineGenerator gains optional prefetch()
src/narration/speech.ts             local-tts engine behind the existing surface
src/narration/config.ts             line_generator_engine, voice_engine
src/narration/useNarrator.ts        wires prefetch-on-queue, engine swap, status plumbing
src/hud/StatusPanel.tsx             engine toggles + load state + latency numbers
src/App.tsx                         passes llmStatus/ttsStatus through
vite.config.ts                      COOP/COEP headers (dev + preview) — see D13
```

### Verified
- `npx tsc -b`, `npm run build`, `npx oxlint src/`, `npm run test` (48 tests,
  up from 23) all clean. Main bundle chunk unchanged at ~1.31MB; WebLLM and
  Kokoro each land in their own lazily-loaded chunk (~6.0MB, ~2.2MB) —
  confirmed by reading the actual `vite build` chunk list, not assumed.
- **Live, headless Chrome + fake camera device (Puppeteer,
  `--enable-unsafe-webgpu`):** full run documented in `day4-poc.md`. Highlights:
  cold LLM load ~45–63s (real ~945MB download), warm reload **11.1s with 0
  bytes re-fetched**, first inference 350–567ms, narration correctly kept
  producing template lines while the model was still loading, network cut
  entirely mid-session (tab kept open) and the app kept generating new lines
  with **zero** requests fired.
- **Found and fixed, live:** Kokoro TTS synthesis threw `Invalid language
  identifier` — root-caused to missing `SharedArrayBuffer`/cross-origin
  isolation (both `kokoro-js` and `web-llm` ship threaded WASM). Added
  `Cross-Origin-Opener-Policy`/`Cross-Origin-Embedder-Policy` headers to
  `vite.config.ts`. This fixed the *silent degrade* (a Worker now visibly
  spins up) but the underlying phonemizer error persists — filed as an open
  bug in D13, not worked around by quietly changing the default engine.
  Every failed local-tts call correctly logs a warning and falls back to
  `speechSynthesis` rather than dropping the line.

### Still missing
- **Kokoro has never actually spoken**, in this session or any prior one —
  the fallback path has been exercised, not the real voice.
- **No audio confirmed audible from any machine, across all four days.**
  This session is headless with no speaker; even `speechSynthesis` (191
  voices reported available) cannot be confirmed to actually produce sound
  from here. Stated loudly per the session brief, not glossed over.
- **Mobile.** No phone was reachable. The model-choice rationale (D13) rests
  on WebLLM's published VRAM figures and desktop latency only.
- **Peak memory** — not measured, no reliable sampling method available in
  this environment.
- **Timing tuning, spatial language, salience ranking** — cut per the
  agreed Day 4 scope decision; none reached. Carried to Day 5+.

### Can be shown publicly
Both model swaps are independently verifiable on camera, not just claimed:
the network tab shows a genuine multi-hundred-MB download the first time an
engine switches on, the panel shows live load/latency numbers, and a second
load from the same profile visibly skips the download. The generate-ahead
fallback is demonstrable live — flip to `local-llm` and the log keeps
producing template lines with zero stutter while the real download runs in
the background. The Kokoro bug is itself good content: a real, named,
not-yet-fixed failure with a working, provable fallback, exactly the kind of
seam `demo-script.md` already asks to show rather than hide.

**Hook:** *"A better voice usually means a cloud bill. Ours doesn't."*

### Next
Day 5 — HUD/UX polish (lock-on animation, confidence rings, primary-target
treatment, subtitle track, keyboard shortcuts). Carried in from Day 4's cut
list: narration timing tuning, spatial language, salience ranking. Open from
Day 4: the Kokoro phonemizer bug, and the still-outstanding "has anyone
actually heard this thing" check on real hardware.

---

## Day 5 — 2026-08-11

**Goal:** Make it *look* like the future without changing the model at all.
The thesis: perceived intelligence is mostly interface design. Reference
points were generic sci-fi HUD grammar (reticles, converging brackets, leader
lines, boot sequences), explicitly not Marvel branding.

### Researched
- Read `decisions.md` (D1–D13), `week-roadmap.md`/`tasks.md` Day 5 sections,
  `architecture.md`, `public-notes.md`, and the whole of `src/hud/`,
  `src/App.tsx`, `src/App.css`, `src/vision/types.ts`,
  `src/narration/useNarrator.ts` before writing anything, per the session
  brief.
- Confirmed the actual blocker before writing any visual code: `drawHud` was
  a pure, stateless function of a `Frame`, which structurally cannot animate
  acquire/lose/breathing — none of that state has anywhere to live. This
  reframed "build the HUD polish" into "build a state layer first, then the
  polish."
- Checked `LlmStatus`/`TtsStatus`/`CameraStatus`/`ModelStatus` shapes in
  `llmLineGenerator.ts`, `speech.ts`, `useCamera.ts`, `useDetector.ts` before
  designing the boot sequence, so every boot line binds to a real enum value
  instead of an invented one.

### Decided
Five new entries in [decisions.md](decisions.md) (D14–D18): a separate HUD
render-state layer rather than extending the tracker or widening `drawHud`
(state layer's memory is a rendering concern, tracker's is a vision concern
— keep the seam); render-time box interpolation at τ=70ms (smoothness for a
few frames of lag, stated as a tradeoff, not tuned against real fast
motion); primary-target selection as box-area × frame-centrality (extends
the existing "pick the largest" tracking-line logic); the distance readout
as a labelled relative-size percentage, not fabricated metres (the day's
sharpest honesty-rule risk); and reserving `ctx.shadowBlur` glow for the
primary target only, as the standard fix for a flagged perf cost center.

### Built
```
src/hud/hudState.ts        HUD render-state layer (new) — updateHudState()
src/hud/hudState.test.ts   7 unit tests (new)
src/hud/theme.ts           shared color tokens (new) — kills the dead CYAN
src/hud/drawHud.ts         rewritten: single options object, HudState input,
                            acquire/track/lose, primary treatment, confidence
                            ring, honest size readout, reduced-motion aware
src/hud/HudCanvas.tsx      drives hudState + real dtMs + draw-time telemetry
src/hud/StatusPanel.tsx    new "HUD draw" telemetry stat
src/hud/SubtitleTrack.tsx  on-frame narration subtitle (new, DOM)
src/hud/BootSequence.tsx   staged power-on, every line real state (new)
src/hud/ShortcutOverlay.tsx  Space/N/B/V/? overlay (new)
src/App.tsx                keyboard shortcuts, reduced-motion hook, wiring
src/App.css                subtitle/boot/shortcut styles + reduced-motion query
```

### Verified
- `npx tsc -b`, `npm run build`, `npx oxlint src/`, `npm run test` (55
  tests, up from 48) all clean. Main bundle chunk unchanged at 1,313.88 kB.
- **Live, headless Chrome + fake camera device (Puppeteer,
  `--enable-unsafe-webgpu`):** full run in `day5-poc.md`. Boot sequence
  screenshotted mid-boot showing real per-system state; live HUD showing a
  converging reticle, real confidence-ring arc, and `SIZE 15% OF FRAME`;
  telemetry read directly off the DOM (`FPS 60.5`, `Inference 11ms`, **`HUD
  draw 0.1ms`**); the subtitle track showed the exact styled narration line
  from the log; stopping/restarting the camera caught the exit-fade
  animation live — a bracket the tracker had already fully dropped, still
  visibly fading on screen, which is `hudState.ts`'s exit window doing its
  job; the shortcut overlay opened/closed correctly over a still-animating
  HUD; a 375×800 screenshot confirmed the existing 900px collapse still
  holds with the new elements; `prefers-reduced-motion` emulated live froze
  ambient sweep/breathing while keeping state-driven fades. Zero console
  errors across the entire run.

### Still missing
- **HUD draw cost at 5+ simultaneous targets** — only ever measured against
  1 tracked object this session (the fake-camera device's ceiling), not the
  multi-target budget check the brief asked for.
- **A real single-object acquire→hold→lose arc under real motion** — what
  was verified live was the exit-fade triggered by stopping the camera, not
  a target walking out of frame on its own. Needs a real webcam.
- **Strobing on a flickering/marginal track** — the brief's flagged most-
  likely ugly failure mode, not specifically stress-tested this session.
- **Real audio timed against the subtitle track** — still no audio confirmed
  audible from any machine across all five days now (D13).
- τ=70ms interpolation and the area×centrality primary rule are first-guess
  defaults, not tuned against real fast motion or a real two-object scene.

### Can be shown publicly
Everything in this session is independently checkable, not just claimed: the
boot lines are literally the app's own status props, the confidence ring is
a real arc from `Detection.score`, the size readout is real division with no
fabricated distance, the HUD draw-time number came straight off the live
panel, and the exit-fade was caught happening on camera rather than staged.
The still-open gaps (multi-target perf, real-motion feel) are this project's
recurring, honest kind of cliffhanger.

**Hook:** *"Same AI as yesterday. Feels ten times smarter. That gap is
design."*

### Next
Day 6 — performance: WebGPU backend + fallback (measured), adaptive frame
skipping, decoupled detect/display resolution, a latency breakdown panel.
Day 5's HUD draw-time telemetry (~0.1ms at 1 target) is the number Day 6
inherits and needs to hold at 5+ targets — that verification gap carries
forward as Day 6's first thing to check, not a fresh unknown.

---

## Day 6 — 2026-08-11

**Goal:** Two complaints from real use that are the same complaint — YAP
says confidently wrong things about what it sees, and it can only talk *at*
you. Ship "I don't know" and "ask me something," not a performance pass.
The day's own prompt reshuffled the *original* Day 6 (WebGPU, frame
skipping, resolution decoupling) out to Day 7, keeping only the latency
breakdown panel as load-bearing since two more models were about to load
onto the page.

### Researched
- Read `context.md`, `decisions.md` (D1–D19), `tasks.md`, `architecture.md`
  before touching code, per the session brief.
- Read all of `src/vision/tracker.ts` + `tracker.test.ts`, `src/hud/
  drawHud.ts` + `hudState.ts`, `src/narration/events.ts`,
  `generateLine.ts`, `templates.ts`, `useNarrator.ts`, `llmLineGenerator.ts`,
  `speech.ts`, `src/App.tsx`, `StatusPanel.tsx` before writing anything —
  the day touches almost every layer of the system at once, and getting the
  existing seams wrong would have been expensive.
- Confirmed via `npm ls puppeteer` and the local Puppeteer Chrome cache that
  the same live-verification technique every prior day used (headless
  Chrome + fake-camera device) was available this session too, plus
  confirmed a bundled Chromium existed locally so verification didn't
  depend on network access to download one mid-session.

### Decided
Six new entries in [decisions.md](decisions.md) (D20–D25): the
`mobilenet_v2` A/B, measured and reverted as a negative result (cost
confirmed, accuracy benefit unconfirmed — no real bed/table scene to test
against); per-track label voting with an asymmetric cross-label match gate
(0.15 same-label, 0.5 cross-label — the width of that gap is what protects
against a chair inheriting a person's id); `UNIDENTIFIED`/hedging as a
continuous `labelConfidence` threshold rather than a scripted state, with
the LLM mechanically forced to hedge rather than resolve; deterministic
`parseIntent`, never the LLM, for control actions; local Whisper over the
free (but cloud-streaming) browser `SpeechRecognition` API, push-to-talk
only; and voice answers preempting the narration queue via a plain `await`
rather than forcing the generate-ahead model onto a request-response
interaction it wasn't built for.

### Built
```
src/vision/tracker.ts          label voting, cross-label match gate (rewritten)
src/vision/tracker.test.ts     +5 tests (11 total)
src/vision/types.ts            Track gains labelVotes/labelConfidence/runnerUpLabel
src/vision/useDetector.ts      separately-timed trackMs stat
src/hud/drawHud.ts             UNIDENTIFIED hedge rendering, real LBL readout
src/hud/hudState.ts            TargetState carries labelConfidence/runnerUpLabel
src/narration/events.ts        uncertain/alternativeObject on NarrationEvent
src/narration/templates.ts     HEDGES bank (new)
src/narration/generateLine.ts  routes uncertain events to HEDGES
src/narration/llmLineGenerator.ts  uncertainty prompt case + sanitizer hedge check
src/narration/describeScene.ts     describeScene + queryObject (new, revived from Day 3)
src/narration/describeScene.test.ts  10 tests (new)
src/narration/useNarrator.ts   speakAnswer/stopAll (preempt + rate-limit reset)
src/voice/parseIntent.ts       deterministic intent parser (new)
src/voice/parseIntent.test.ts  8 tests (new)
src/voice/speechToText.ts      local Whisper adapter (new)
src/voice/useVoiceInput.ts     push-to-talk hook: mic, MediaRecorder, resample (new)
src/hud/SubtitleTrack.tsx      user transcript row, visually distinct (rewritten)
src/hud/StatusPanel.tsx        Voice input + Latency breakdown panel blocks
src/hud/ShortcutOverlay.tsx    "Hold T" entry
src/App.tsx                    voice command wiring, mic button, T shortcut
src/App.css                    subtitle-track restructure, panel-note style
package.json                   @huggingface/transformers promoted to a direct dep
```

### Verified
- `npx tsc -b`, `npm run build`, `npx oxlint src/`, `npm run test` (**84
  tests**, up from 55) — all clean.
- **Model A/B, live, headless Chrome + fake-camera device:** `lite_
  mobilenet_v2` (kept) at 11ms inference / ~60 FPS vs `mobilenet_v2`
  (reverted) at 16–17ms / ~57–60 FPS, 5 samples each. Real numbers, not
  estimated — see day6-poc.md.
- **Live, headless Chrome + fake-camera device, against the production
  build** (`npm run build && npm run preview`, not just dev — deliberately,
  since D13 flagged this exact dependency family's Rollup risk): FPS 60.1,
  inference 11ms, track 0.02ms, HUD draw 0.1ms — unchanged from Day 5.
  Voice input panel present, mic granted, Whisper reached `ASR: ready` with
  zero console errors (only benign onnxruntime info/warning lines). Unlike
  Kokoro (D13), this dependency did **not** hit the Rollup bundler bug.
- **A direct synthetic-`HudState` render** (same technique `day5-poc.md`
  used for its draw-cost benchmark) proved the `BED / DINING TABLE ?` hedge
  renders correctly — amber label, real `LBL 52%` readout, a confident
  secondary target rendering normally alongside it — with zero exceptions.
  Full method and the screenshot description are in day6-poc.md.

### Still missing
- **A real spoken command, transcribed and checked for accuracy** — the
  fake-camera device has no real microphone input. Same shape of gap as "no
  audio confirmed audible" (open since Day 4).
- **The uncertainty hedge on a real ambiguous-object camera scene** — no
  bed/dining-table-confusable scene was available in headless verification;
  proven correct via the tracker's unit tests and a direct synthetic render
  of the drawing code instead.
- **Open-vocabulary relabeling (CLIP)** and **wake word** — both explicitly
  cut this session per the day's own prioritization (items 6 and 8 of 8).
  The microphone-as-`tie` failure mode is still open. Carried to Day 7+.
- Mic permission *denial* was not exercised against a real browser prompt
  (the fake-media-stream flag always grants).

### Can be shown publicly
The model A/B numbers came off the live panel under both real
configurations. The `BED / DINING TABLE ?` render is the actual `drawHud.ts`
module executing, not a mockup. The production-build ASR verification is a
genuine Rollup output, catching exactly the kind of bundler risk D13
already burned a session on for a sibling dependency. FPS/inference/draw
are unchanged from Day 5's measured baseline. The honest gaps — no real
spoken command checked, no real ambiguous-object scene, CLIP and wake word
both cut cleanly rather than half-built — are stated plainly in
day6-poc.md, not buried.

**Hook:** *"An AI that admits uncertainty reads as more intelligent, not
less."*

### Next
Day 7 — robustness + mobile + the performance work reshuffled out of Day 6
(WebGPU backend, adaptive frame skipping, resolution decoupling — a mobile
battery budget is where that actually matters most). Open-vocabulary CLIP
relabeling and wake word are both candidates to pick back up here if there's
room, but robustness/mobile takes priority per the day's own scope note.
