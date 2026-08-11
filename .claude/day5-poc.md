# Day 5 POC — HUD/UX polish, verified

## The claim being verified

Day 5's thesis: the model doesn't change, only presentation does, and the
same detections should read as visibly more intelligent because of it. That
requires a new HUD render-state layer (`src/hud/hudState.ts`) since the
existing `drawHud` was a pure, stateless function with nowhere to hold
acquire/exit/interpolation state — and it requires proving the polish didn't
cost the frame budget Day 6 is measured against.

## What works, verified

1. **`src/hud/hudState.ts`** — `updateHudState(prev, frame, dtMs, frameW,
   frameH) -> next`, pure, same shape as `tracker.ts`'s `updateTracks`.
   7 unit tests (`hudState.test.ts`): acquire progress advances with real
   `dtMs` and caps at `ACQUIRE_MS`; a track absent from the current frame
   enters `exiting` and is released after `EXIT_MS`; a track that reappears
   with the same tracker id is *not* left in an exiting state; box
   interpolation measurably closes the gap toward the latest tracked box
   over successive ticks; primary selection picks the larger, more central
   of two candidates; `primaryProgress` eases toward 1/0 correctly; phase is
   stable for a given id across ticks.
2. **`drawHud.ts`** — rewritten to a single `DrawHudOptions` object,
   consumes `HudState` instead of a raw `Frame`. Lock-on acquire (brackets
   converge inward), release+fade on loss, primary-target treatment
   (dimming, glow reserved for primary only, confidence ring, honest
   `SIZE n% OF FRAME` readout, leader-line callout), per-target breathing
   motion phased by track id, `prefers-reduced-motion` freezes ambient
   sweeps/pulses/rotation but keeps state-driven fades (those encode a real
   transition, not decoration).
3. **`HudCanvas.tsx`** — owns `hudStateRef`, computes real elapsed `dtMs`
   per rAF tick (`t - lastT`, clamped to 100ms against a backgrounded-tab
   reflow), measures HUD draw time and reports it to the panel at ~4Hz.
4. **`src/hud/SubtitleTrack.tsx`, `BootSequence.tsx`, `ShortcutOverlay.tsx`**
   — DOM components per the canvas/DOM split; boot lines are each bound to
   a real prop, no fake progress.
5. **Bundle discipline.** Main chunk unchanged at **1,313.88 kB** (Day 4's
   baseline was ~1.31MB) — none of Day 5's work touched the eager bundle.

## Verification method

- **Read** `decisions.md` (D1–D13), `week-roadmap.md`/`tasks.md` Day 5
  sections, `architecture.md`, `public-notes.md`, and the whole of
  `src/hud/`, `src/App.tsx`, `src/App.css`, `src/vision/types.ts`,
  `src/narration/useNarrator.ts` before writing anything, per the session
  brief.
- **Static checks:** `npx tsc -b`, `npm run build`, `npx oxlint src/`,
  `npm run test` (**55 tests**, up from 48 — the 7 new `hudState.test.ts`
  tests) — all clean.
- **Live run, headless Chrome (Puppeteer) + fake camera device,**
  `--use-fake-device-for-media-stream --use-fake-ui-for-media-stream
  --enable-unsafe-webgpu`, 1400×900:
  - **Boot sequence, captured mid-boot:** `CAMERA ONLINE`, `VISION MODEL
    BOOTING`, tracker/narrator lines still dimmed-in — each word is the real
    `cameraStatus`/`modelStatus` at that instant, not a scripted sequence.
  - **Live HUD, screenshotted ~2s after model ready:** converging bracket
    reticle around a tracked "kite" detection, confidence ring drawn as a
    real arc, `SIZE 15% OF FRAME` readout, primary-target leader-line
    callout — all rendered from real per-frame data, no placeholder text.
  - **Telemetry read directly off the DOM:** `FPS 60.5`, `Inference 11ms`,
    **`HUD draw 0.1ms`**, `Targets` tracking the fake camera's churn. FPS and
    inference are unchanged from the Day 3/4 baseline (~60 FPS, ~11-12ms) —
    Day 5's HUD did not regress the frame budget with a single target on
    screen.
  - **Narration → subtitle wiring, captured live:** the narration log's
    styled line (`"kite on scene. expectations remain low."`) appeared
    verbatim in the on-frame subtitle track at the bottom of the viewport,
    confirming the DOM subtitle reads the same `LogEntry` the panel does,
    not a separate/stale copy.
  - **Exit-fade animation, caught live, not staged:** stopping and
    restarting the camera dropped the tracker's active track while the
    HUD's own render state kept the last-known bracket and label on screen,
    visibly dimmed and still partially drawn (`KITE #13 · 0.0s`, faded) —
    this is `hudState.ts`'s exit window doing exactly its job: fading a
    target the tracker itself had already fully forgotten about.
  - **Shortcut overlay:** `?` opened it over the live HUD with all five
    bindings listed and legible; `Escape` closed it; the overlay did not
    block the canvas draw loop underneath (HUD kept animating visibly
    behind the blurred backdrop).
  - **Narrow viewport (375×800, full-page screenshot):** the `.stage` grid
    correctly collapsed to a single column (the existing 900px breakpoint,
    unmodified), the subtitle track stayed centered and legible at the
    smaller width, the telemetry panel stacked below the viewport instead
    of overlapping it. Not a full mobile pass (that's Day 7's job) — just
    confirmation Day 5 didn't break the existing collapse.
  - **`prefers-reduced-motion: reduce` emulated live:** no console errors,
    HUD kept rendering (state-driven fades still play — they carry real
    information), ambient chrome sweep and per-target breathing froze to a
    static state as intended.
  - **Zero console errors** across the entire run (boot → live → subtitle →
    shortcuts → narrow viewport → reduced motion → stop/restart), captured
    via Puppeteer's console/pageerror listeners, not eyeballed.

## Measured (before/after)

| | Day 4 baseline | Day 5 |
|---|---|---|
| FPS | ~60 | 60.0–60.5 |
| Inference | ~11-12ms | 11-12ms |
| HUD draw | not measured (no telemetry field existed) | **0.1ms** (1 target, headless fake-camera device) |
| Main bundle chunk | ~1.31MB | 1,313.88 kB (unchanged) |
| Test count | 48 | 55 |

HUD draw time is comfortably inside the single-digit-millisecond budget the
day5 brief set.

### Second pass — visual density rewrite

The first pass drew four corner brackets, one confidence circle and two
lines of text. On real footage that reads as an *annotation*, not an
instrument — the honest verdict was that it did not look like the thing the
day was named after. `drawHud.ts` was rewritten around a denser vocabulary,
with the model and `hudState.ts` untouched (all 55 tests still pass
unmodified — the state layer's contract didn't move):

- chamfered (45°-cut) corner brackets with an inner hairline echo
- a 60-tick graduated ring with major/minor ticks and four segment gaps,
  counter-rotating against a segmented four-arc outer ring
- the confidence arc kept, now with a cap dot and a track behind it
- radial notches at the diagonals
- an elbow leader line into a real **data card** — coloured header bar,
  four rows (`CONF` with a bar gauge, `AREA`, `POS`, `AGE`), corner
  registration ticks, auto-flipping to whichever side has room
- graduated **frame-edge rulers** labelled 25/50/75, with dashed axis
  drop-lines and arrow markers riding them at the primary's real centre
- chamfered frame corners, a faint grid, a centre reticle with a diamond,
  and a `TRK nn` slug bound to the real live-track count
- secondary targets reduced to bracket + centre pip, keeping hierarchy
  readable and keeping their per-target cost near zero

Every new readout is still a real measurement: `AREA` is box area over frame
area, `POS` is the box centre as a percentage of frame width/height, `AGE`
is the tracker's own track age, `TRK` is the live target count. The ruler
graduations are a scale of the frame itself — real by construction. Still
no distance in metres.

The per-label accent hue band was also narrowed (160–240° → 168–194°); the
wider band was hashing some labels into muddy blues with almost no contrast
against camera footage.

### Draw cost by target count — measured

Benchmarked directly against the real module (`import('/src/hud/drawHud.ts')`
through the Vite dev server, inside headless Chrome), 1280×720 canvas, 60
warmup frames then 300 timed frames per target count, synthetic `HudState`:

| Targets | 1 | 3 | 5 | 8 | 12 |
|---|---|---|---|---|---|
| ms / `drawHud` call | 0.050 | 0.047 | 0.049 | 0.058 | 0.070 |

Essentially flat — the D18 bet (glow reserved for the primary target only,
secondaries reduced to bracket + pip) holds: cost is dominated by the
single primary instrument and the frame chrome, both constant, so adding
targets is nearly free. 12 targets cost 0.07ms against a 16.7ms frame
budget. This is the 5+ target check the brief asked for and the first pass
did not have.

## Still missing / not verified

- ~~HUD draw cost at 5+ simultaneous targets.~~ **Now measured** — see the
  target-count table below.
- **A real single-object acquire → hold → lose arc.** The fake camera's
  synthetic pattern churns tracks on its own noise, so what was observed
  live was an exit-fade triggered by *stopping the camera*, not a target
  smoothly walking out of frame under its own motion. The exit-fade
  mechanism is confirmed working; the *feel* of a clean real-world
  acquire/hold/lose sequence is not yet filmed.
- **Strobing on a flickering track.** Not stress-tested against a track
  that rapidly gains/loses tracker-side matches (missed-frame churn right at
  the tracker's grace-window edge) — the brief flags this as the most
  likely ugly failure mode and it wasn't specifically provoked this session.
- **Real audio + subtitle timing together.** The subtitle track was
  confirmed to show the correct line; it was not checked against actual
  spoken audio timing, since no audio has been confirmed audible from any
  machine this project has run on across all five days now (D13).
- **A true mobile-width interaction pass** (touch, not just a narrow
  screenshot) — Day 7's job per the roadmap, only a static-width check was
  done here.
- **Interpolation constant (τ = 70ms) and primary-selection tie-breaking**
  are first-guess defaults, not tuned against real, fast hand motion —
  flagged for revisit in decisions.md D15/D16 if real footage shows lag or
  primary flicker.

## Can be shown publicly

Everything captured in this session is real and independently checkable:
the boot sequence's four lines are literally the app's own status props,
the confidence ring is a real arc drawn from `Detection.score`, the size
readout is real division (box area / frame area, no fabricated metres), the
HUD draw-time number came off the live telemetry panel rather than being
claimed, and the exit-fade was caught happening on camera, not staged. The
honest gaps above (multi-target perf, real-motion feel) are exactly the kind
of cliffhanger this project has used every day so far — say them plainly.
