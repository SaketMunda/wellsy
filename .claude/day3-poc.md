# Day 3 POC — IoU tracking, verified

## Update — real-world id-churn bug, found and fixed same day

After this doc's original headless verification, real-webcam use surfaced
exactly the risk this doc's "not verified" section had flagged: track ids
climbed rapidly (a stationary phone past `#240`; a person's id incrementing
while standing still) instead of staying stable. Root cause: plain IoU ≥ 0.3
against the previous frame failed on real footage far more often than
expected — `lite_mobilenet_v2`'s box for a *static* object is noisy enough to
regularly drop IoU below 0.3 frame to frame, worse for small objects — and a
single failed match immediately minted a new track/id rather than waiting out
the grace window. Fixed in `src/vision/tracker.ts`: added a center-distance
fallback match (same label, centers within half the average box diagonal),
loosened the IoU threshold to 0.15, and widened the missed-frame grace window
from 5 to 20. Locked in with a new `src/vision/tracker.test.ts` using
jitter deliberately large enough to have broken the old threshold. Full
writeup in decisions.md D11. This is still not verified against an actual
real webcam in this session (see "not verified" below) — the fix is verified
by unit test and reasoning about the reported symptom, not by re-observing a
real camera.

## The claim being verified

Detection answers "what's here *now*" — every frame independent, boxes
jitter, no identity. Day 3's job was to build a tracker that answers "is this
the *same* thing as before": persistent numeric IDs, smoothed boxes, and
survival through a brief missed detection.

## What works, verified

1. **`src/vision/tracker.ts` — `updateTracks`.** Pure function:
   `(previousTracks, detections, dtMs, nextId) => Track[]`. Matches by IoU
   (≥ 0.3) restricted to the same COCO label, applies exponential smoothing
   (α = 0.4) to matched boxes, ages every surviving track by `dtMs`, and
   keeps unmatched tracks alive for up to 5 missed frames before dropping
   them.
2. **Wired into the detect loop** (`src/vision/useDetector.ts`) — tracks are
   computed once per detection tick and carried on `Frame.tracks`, alongside
   the existing raw `Frame.detections`.
3. **HUD renders track identity.** `src/hud/drawHud.ts`'s `drawLabel` now
   reads `LABEL #id · age`s — confirmed live via screenshot (below), showing
   `KITE #13 · 0.3s` on a real bracket.
4. **Narration reads tracks directly.** `src/narration/events.ts`'s
   `createEventTracker.update` now takes `Track[]` and derives
   appear/disappear from track-id set differences, not label-count diffing.
   `src/narration/useNarrator.ts`'s stability gate compares the sorted
   track-id set between samples instead of label counts.

## Verification method

- **Read** the full Day 1–2 architecture and source before writing anything
  (`architecture.md`, `decisions.md`, `week-roadmap.md`/`tasks.md` Day 3
  sections, `public-notes.md`, `types.ts`, `useDetector.ts`, `drawHud.ts`,
  `HudCanvas.tsx`, `events.ts`, `useNarrator.ts`).
- **Unit tests**: `npm run test` — 23 tests pass, including a rewritten
  `describe('event tracker', ...)` block in `narrator.test.ts` exercising
  `createEventTracker` against fabricated `Track[]` input: appear-per-track
  (a second same-label track is its own `appear`, not a `count_change`),
  disappear, still_present idle escalation and idle-clock reset, and
  confidence reporting.
- **Static checks**: `npx tsc -b`, `npm run build`, `npx oxlint src/` all
  clean.
- **Live run**: headless Chrome (Puppeteer) against `npm run dev`, camera
  started with the synthetic fake-device video feed. Observed:
  ```
  Camera:     live
  Model:      ready
  FPS:        60.0–60.1
  Inference:  12 ms
  Console errors: none
  ```
- **Direct tracker-state inspection.** Temporarily added a console.log inside
  the detect loop (gated behind a `window.__yapDebugTracks` flag, removed
  before finishing this session) dumping each frame's tracks
  (`id`, `label`, `ageMs`, `missedFrames`, `bbox`). Sampled ~30 ticks over a
  live run. Observed, verbatim:
  ```
  TRACKS []
  TRACKS [{"id":1,"label":"kite","age":35,"missed":0,"bbox":[442,223,401,332]}]
  TRACKS [{"id":1,"label":"kite","age":283,"missed":3,"bbox":[446,178,396,373]}]
  TRACKS []
  TRACKS [{"id":2,"label":"kite","age":183,"missed":0,"bbox":[446,181,378,370]}]
  ```
  This confirms, directly rather than inferentially: ids are assigned
  monotonically and held stable across consecutive frames (id `1` persists
  from `age:35` to `age:283` while `missed` climbs to 3 during a gap before
  the track is dropped); a fresh id (`2`) is assigned to the next detection
  once the old one is gone; `ageMs` accumulates correctly frame-to-frame; and
  bbox values move gradually rather than snapping, i.e. smoothing is
  measurably active, not a no-op.
- **Screenshot.** Captured the HUD mid-detection: a bracket labelled
  `KITE #13 · 0.3s`, replacing the old `label score%` format. Visual proof
  the id+age display actually renders, not just that the type compiles.

## What is NOT verified from this session — stated plainly

- **Occlusion recovery on a real object** (walk out of frame, walk back
  within the 5-missed-frame grace window, same id). The synthetic fake-camera
  device is an abstract shifting pattern whose detection confidence dips
  below the 0.5 floor unpredictably — tracks get dropped and replaced with
  new ids well inside a few hundred ms, which is both expected (same
  limitation Day 1/2 already documented: the fake device doesn't hold a
  stable scene) and not the same thing as watching a real person walk behind
  a doorframe and reappear. **First real-webcam check to run:** walk out of
  frame and back within ~1 second, confirm the on-screen id number is
  unchanged.
- **A genuinely new object getting a new id** vs. an old object's id being
  reused — same real-webcam caveat as above.
- **Smoothing constant (α = 0.4) and the 5-missed-frame threshold tuned
  against real movement.** Both are reasonable first choices (see
  decisions.md D11), not measured against a real camera's frame-drop
  pattern.
- **The jitter before/after clip** — the day's headline demo asset — needs a
  real webcam with real hand/body movement to show meaningfully; a synthetic
  pattern's "jitter" isn't representative.
- **Speech audio** — unverified, headless Chrome has no voices (same caveat
  every prior day has stated).

## Running it

```bash
npm install
npm run dev
# open http://localhost:5173 and click "Start camera"
```

## Next

Day 4 — tune narration timing against real footage, spatial language,
salience ranking, event narration built on these tracks, and the
local-LLM/local-TTS voice upgrade (no cloud, ever — see decisions.md D10).
