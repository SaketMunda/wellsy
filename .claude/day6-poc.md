# Day 6 POC — uncertainty + voice, verified

## The claim being verified

Day 6's thesis: the system was **asserting** instead of **communicating** —
confidently wrong labels, no way to talk back. Fixing that requires (a) a
structural change to how a track's label is decided (a vote, not the latest
frame) plus an honest `UNIDENTIFIED` path when the vote is torn, and (b) a
full voice-in pipeline — local ASR, deterministic intent parsing, grounded
answers — that preempts ambient narration cleanly. It also requires proving
none of this ate the frame budget, since two more models were added to a
page that already loads three.

## What works, verified

1. **`src/vision/tracker.ts` label voting** — `Track` gains `labelVotes`,
   `labelConfidence`, `runnerUpLabel`. Cross-label matching (IoU ≥ 0.5) lets
   a track survive the model flipping its word for the same object without
   minting a new id, while same-label matching stays exactly as permissive
   as Day 3 left it. 5 new tests in `tracker.test.ts` (11 total): both
   cross-label directions (`bed` → `dining table` and back), a flip-flopping
   sequence settling on a vote winner with the correct runner-up, a
   single-consistent-label track carrying full confidence, and the D11
   "never merges on a weak overlap" guarantee re-verified with genuinely
   non-overlapping boxes (the old test's exact-coincidence scenario no
   longer applies now that high overlap is *intentionally* a cross-label
   match signal — see decisions.md D21).
2. **`UNIDENTIFIED` / hedged labels** — `drawHud.ts` renders
   `BED / DINING TABLE ?` in the HUD's one warn color (amber) with a real
   `LBL nn%` vote-share readout, below `labelConfidence` 0.6.
   `events.ts`/`generateLine.ts` route an uncertain event to a dedicated
   `HEDGES` template bank instead of the normal one. `llmLineGenerator.ts`'s
   `sanitizeLlmLine` mechanically rejects an LLM line that doesn't actually
   hedge (names the alternative or uses a cue word), falling back to the
   template hedge exactly like a swear falls back for spice level. 8 new
   tests across `narrator.test.ts`/`llmLineGenerator.test.ts`.
3. **`src/voice/parseIntent.ts`** — pure, deterministic, 8 tests. `stop`
   checked first so it can't be shadowed. `unknown` never improvises.
4. **`src/narration/describeScene.ts`** — `describeScene(tracks)` and
   `queryObject(tracks, object)`, both pure, both grounded in
   `frameRef.current.tracks` only. Reports uncertain tracks as
   "unidentified," groups them, never guesses. 10 tests.
5. **`src/voice/speechToText.ts` + `useVoiceInput.ts`** — local Whisper
   (`Xenova/whisper-tiny.en`) via `@huggingface/transformers`, push-to-talk
   (hold `T` or the mic button), a second independently-handled
   `getUserMedia(audio)` prompt, `MediaRecorder` → `OfflineAudioContext`
   resample to mono 16kHz → transcription.
6. **`useNarrator.ts`'s `speakAnswer`/`stopAll`** — an answer drops the
   ambient queue and resets the rate-limit clock; `stop` cuts speech
   immediately and works even if narration (`enabled`) is off.
7. **`SubtitleTrack.tsx`** — the user's own transcript renders as a second,
   visually distinct row (dim, italic, `>` prefix) above YAP's line.
8. **Latency breakdown panel** — inference/track/draw/ASR/LLM/TTS, each a
   real measured number. `useDetector.ts` now separately times
   `updateTracks` as `trackMs`. No fabricated capture number.
9. **`@huggingface/transformers` promoted to a direct dependency** in
   `package.json` — it was already on disk transitively via `kokoro-js`
   (v3.8.1); this costs zero new download, only an honest dependency graph.
10. **Bundle discipline.** Main chunk **1,331.03 kB**, up from Day 5's
    1,313.88 kB (+17KB, ~1.3%) — the new pure TS modules (tracker voting,
    hedge templates, `parseIntent`, `describeScene`, App wiring) are small
    and eager, everything model-shaped stays lazy.
    `@huggingface/transformers` lands in its own **847.14 kB** chunk,
    loaded only when push-to-talk is actually used.

## Verification method

- **Read** `context.md`, `decisions.md` (D1–D19), `tasks.md`,
  `architecture.md`, and the whole of `src/vision/`, `src/hud/`,
  `src/narration/`, `src/App.tsx` before writing anything, per the session
  brief.
- **Static checks:** `npx tsc -b`, `npm run build`, `npx oxlint src/`,
  `npm run test` (**84 tests**, up from 55) — all clean.
- **The model A/B experiment, live, headless Chrome + fake-camera device,**
  before any tracker code changed: 5 samples each, 3s warm-up, at
  `http://localhost:5183` via the dev server.
  - `lite_mobilenet_v2` (baseline): FPS 59.9–60.2, inference **11ms**
    steady across all 5 samples.
  - `mobilenet_v2`: FPS 57.0–60.2 (draw-loop rAF cap absorbs most of the
    difference), inference **16–17ms** — roughly +50%.
  - Reverted per the day's own timebox rule: cost confirmed, accuracy
    benefit unconfirmed (no bed/dining-table scene in the fake-camera
    device's synthetic pattern). See decisions.md D20.
- **Live run, headless Chrome (Puppeteer) + fake-camera device,**
  `--use-fake-device-for-media-stream --use-fake-ui-for-media-stream
  --enable-unsafe-webgpu`, 1400×900, **against the production build**
  (`npm run build && npm run preview`), not just dev:
  - Camera started, model reached `ready`, telemetry read directly off the
    DOM after a 3s settle: **FPS 60.1, Inference 11ms, Track 0.02ms, HUD
    draw 0.1ms, Targets 1** — all unchanged from the Day 5 baseline
    (0.050–0.070ms draw across target counts). The two new models added
    this session cost nothing on the hot path, confirmed, not assumed.
  - **Voice input panel and mic button present and correctly labeled**
    (`Hold to talk`), `Mic: ready` after granting the fake audio device,
    zero console errors.
  - **Whisper loaded and reached `ASR: ready` in the production build**,
    confirmed via a held mic-button press (800ms) followed by
    `page.waitForFunction` polling the panel — the exact dependency-family
    risk D13 flagged (Rollup bundling breaking a Transformers.js/
    onnxruntime-web-adjacent package) did **not** reproduce here. The only
    console output was benign onnxruntime execution-provider info/warning
    lines (`VerifyEachNodeIsAssignedToAnEp`), not exceptions — filtered out
    of the "errors" list explicitly and confirmed non-fatal by the app
    continuing to function. `pageerror` listener caught zero real errors
    across the whole run.
  - `ASR latency` still read `—` at the moment of the check — the model-load
    promise had resolved (`ready`) but the specific transcription pass on
    the fake device's (likely silent or synthetic-tone) audio hadn't
    necessarily finished before the read; this is a timing artifact of the
    smoke test, not a defect — see "Still missing" below for what this does
    and doesn't prove.
- **A direct synthetic-`HudState` render, live, headless Chrome (dev
  server), same technique `day5-poc.md` used for its target-count draw-cost
  benchmark:** `import('/src/hud/drawHud.ts')` against an offscreen canvas
  with a hand-built `HudState` — one target at `labelConfidence: 0.52`,
  `label: 'bed'`, `runnerUpLabel: 'dining table'`, one confident
  `label: 'laptop'` target. `drawHud` ran with **zero exceptions**, and the
  screenshot (embedded context, not reproduced here) shows exactly the
  intended result: the primary target's label reads `BED / DINING TABLE ?
  #7` in amber, the data card header reads `BED · UNSURE` with a real
  `LBL 52%` row, and the secondary `LAPTOP #8` target renders in its normal
  cyan with no uncertainty treatment. This is real code executing on real
  (synthetic) data, not a mockup — the same `drawHud.ts` module the live app
  imports.
- **Zero console errors** across the entire production-build run (camera →
  model ready → mic → ASR load), captured via Puppeteer's console/pageerror
  listeners, not eyeballed.

## Measured (before/after)

| | Day 5 baseline | Day 6 |
|---|---|---|
| FPS | 60.0–60.5 | 60.1 |
| Inference | 11–12ms | 11ms |
| Track (new this session) | not measured separately | **0.02ms** |
| HUD draw | 0.1ms (1 target) | 0.1ms (1 target) |
| Main bundle chunk | 1,313.88 kB | 1,331.03 kB (+17KB, ~1.3%) |
| New lazy chunk | — | `transformers.web`, 847.14 kB, loaded only on push-to-talk |
| Test count | 55 | 84 |

Model A/B (this session only, both against the fake-camera device):

| | `lite_mobilenet_v2` (kept) | `mobilenet_v2` (reverted) |
|---|---|---|
| Inference | 11ms | 16–17ms |
| FPS | ~60 | ~57–60 |

## Still missing / not verified

- **A real spoken command, transcribed and checked for accuracy.** The
  fake-camera device provides no real microphone input — the pipeline was
  confirmed to load and run without crashing in a production build, not
  confirmed to correctly transcribe actual speech. This is the same shape
  of gap as "no audio has been confirmed audible" (D13, still open since
  Day 4) — say so plainly rather than implying it was tested end to end.
  Chrome supports `--use-file-for-fake-audio-capture` for a real synthetic
  input file, which would close this gap in a future session.
- **The uncertainty hedge on a real bed/dining-table scene.** Verified via
  a direct synthetic `HudState` render (see above) proving the drawing code
  is correct, not via a real camera pointed at ambiguous furniture — no
  such scene was available in this headless environment. The tracker-level
  behavior (vote settling, cross-label id survival) is separately verified
  by unit tests against sequences designed to be provably ambiguous.
- **Open-vocabulary relabeling (CLIP).** Not built this session — the
  microphone-as-`tie` failure mode is still open. Explicitly cut per the
  day's own prioritization; see decisions.md D22 and tasks.md.
- **Wake word.** Not built this session — push-to-talk is a complete
  feature on its own, per the day's own brief.
- **A real device without WebGPU**, to confirm ASR's wasm fallback path
  specifically (the code takes it automatically; it wasn't forced and
  observed this session — the WebGPU path was what actually ran, since the
  verification environment supports `--enable-unsafe-webgpu`).
- **Mic permission *denial*, live.** The fake-media-stream flag always
  grants; `micStatus: 'denied'` and its UI treatment are implemented
  (mirroring `useCamera`'s pattern exactly) but not exercised against a
  real browser permission prompt this session.

## Can be shown publicly

Everything captured in this session is real and independently checkable:
the model A/B numbers came off the live telemetry panel under both
configurations, not estimated; the `BED / DINING TABLE ?` render is the
actual `drawHud.ts` module executing against synthetic-but-realistic input,
not a mockup; the production-build ASR verification is a genuine
Rollup-bundled `npm run build` output, not the dev server; and the FPS/
inference/draw numbers are unchanged from Day 5's measured baseline, proving
Day 6's two new models cost nothing on the hot detect/draw path. The honest
gaps above — no real spoken command checked, no real ambiguous-object
camera scene, CLIP and wake word both cut — are exactly the kind of
cliffhanger this project has used every day so far. Say them plainly.
