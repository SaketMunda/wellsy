# Day 5 — "Same brain, better face" (HUD + UX polish)

You're working in the YAP repo (`yap-hud`) — a build-in-public live vision
overlay: camera → COCO-SSD detection → IoU tracking → HUD overlay → narration
(templates or a local LLM) → speech, all in-browser, no backend, no API keys.
The `.claude/` directory is the project's build-in-public workspace. **Read the
relevant files before editing anything** — they are the current source of
truth, not any summary of this project you may have been given.

Read at minimum before starting: `.claude/decisions.md` (all of D1–D13),
`.claude/week-roadmap.md` (Day 5 + Day 6 sections), `.claude/tasks.md`,
`.claude/architecture.md`, `.claude/public-notes.md` (especially the
"What is REAL / What is NOT real yet" lists at the bottom), and the whole of
`src/hud/` — `drawHud.ts`, `HudCanvas.tsx`, `StatusPanel.tsx` — plus
`src/App.tsx`, `src/App.css`, `src/vision/types.ts`, and
`src/narration/useNarrator.ts`.

---

## The goal, stated precisely

**Make it look like the future.** The reference points are the fictional
interfaces people already have in their heads: Iron Man's JARVIS and FRIDAY,
Spider-Man's E.D.I.T.H. and Karen. Concentric reticles that converge on a
target, callouts with leader lines, monospace caps telemetry, a cyan/amber glow
with real depth, motion that reads as *acquiring* and *tracking* rather than
*drawing rectangles*, a power-on sequence that boots rather than appears.

That aesthetic is the day's deliverable, and it is not decoration — it *is* the
thesis: **perceived intelligence is mostly interface design.** The model does
not change today. Nothing in `src/vision/` or `src/narration/` gets smarter.
The entire delta is presentation, and the video's whole point is that the
same detections feel ten times smarter because of how they're drawn.

Two boundaries on that goal:

1. **Build the visual language, not the branding.** Reticles, rings, scan
   sweeps, leader lines, boot sequences and monospace telemetry are generic
   sci-fi HUD grammar — use them freely. Do not copy Marvel assets, do not
   use their marks or fonts, and do not name anything in the product or the
   docs JARVIS / FRIDAY / EDITH / Karen. YAP is YAP.
2. **No new network dependencies.** No webfont from a CDN, no icon set, no
   image assets fetched at runtime. The project's headline claim is that it
   works offline after first load (D10, D13) and a Google Fonts link would
   quietly break it. System monospace and drawn-in-canvas geometry only. If
   a font is genuinely needed, it ships as a self-hosted file in `public/`
   and you state the added bytes.

---

## Where things stand

Shipped, and NOT this session's job to redo or "improve while you're in there":

- **Day 1** — camera, COCO-SSD (~12ms/frame, WebGL), canvas HUD, Web Speech.
- **Day 2** — narration is event-driven: a 250ms sampler, a 900ms stability
  gate, one line per 4s. Do not retune these today.
- **Day 3** — `src/vision/tracker.ts` gives objects persistent ids and
  smoothed boxes. **Do not touch the tracker.** It is on the roadmap's
  "never cut" list and its smoothing constants were tuned against a real
  webcam (D11).
- **Day 4** — local LLM (`llmLineGenerator.ts`, generate-ahead) and local TTS
  (Kokoro in `speech.ts`). Local TTS **works in `npm run dev` and is broken in
  a production build** (D13) — that's a known open bug, not yours to fix today.

Carried into Day 5 from Day 4's cut list (`tasks.md`): narration timing tuning,
spatial language, salience ranking. **Salience ranking is now partly a Day 5
concern** — see "primary target" below — but only the *visual* half of it.

---

## The hard problem — read this before you write any drawing code

`drawHud` is a **pure, stateless function**: it takes a `Frame` and paints it.
`HudCanvas` calls it every rAF tick with whatever is currently in `frameRef`.
That design was correct for Days 1–4 and it is exactly what blocks Day 5.

Everything cinematic you're about to build needs **state that outlives a single
frame**:

- A lock-on animation needs to know *when this track id first appeared* so the
  brackets can converge over ~300ms instead of snapping.
- A target-lost fade needs to animate a track that **is no longer in
  `frame.tracks` at all** — the tracker drops it and it's simply gone. Right
  now there is nothing to fade.
- A primary-target treatment needs to know the previous primary so focus can
  *transfer* rather than teleport.
- Any pulse, sweep, or ring needs a per-track phase, not a global clock, or
  every object on screen pulses in unison and it reads as a screensaver.

So the first thing to build is not a visual. It's a **HUD render-state layer**
— something like `src/hud/hudState.ts` — that sits between the detection frame
and the painter:

- Keyed by track id, holding per-target animation state (age since first seen
  on screen, acquire progress 0→1, exit/fade progress, current interpolated
  box, whether it is the primary).
- Updated once per rAF tick from `frameRef.current` **plus** a real delta-time,
  so animation speed is frame-rate independent (a 120Hz display must not
  animate twice as fast as a 60Hz one — use elapsed ms, never per-frame
  increments).
- Retains targets the tracker has dropped for a short exit window so they can
  animate out, then releases them. **This is its own memory — do not extend
  `tracker.ts` to do it.** Detection-side track lifetime is a vision concern
  with tuned constants; how long a bracket lingers on screen is a rendering
  concern. Keep the seam.
- Pure and testable: `updateHudState(prev, frame, dtMs) → next`, same shape as
  `updateTracks` in `tracker.ts`, which is the house pattern. Unit test it.

**The second half of the same problem: render-time interpolation.** Detection
produces a new box every ~12–80ms; the display refreshes every ~16ms. Today the
box holds its last position and then jumps. For the smooth "it's tracking me"
feel, the HUD state layer should interpolate the drawn box toward the latest
detected box each render tick (an exponential ease on dt, in the same spirit as
the tracker's α=0.4 but at display rate). Be honest about the tradeoff in
`decisions.md`: **interpolation adds a few frames of visual lag in exchange for
smoothness.** Pick a value that still feels locked-on, and say what you picked
and why.

`drawHud` stays a pure painter — it now takes HUD state instead of a raw
`Frame`. Its positional parameter list is already at eight and this will push
it further: **switch it to a single options object** while you're changing the
signature anyway.

---

## Canvas or DOM — the rule

Both are fine, and the split matters:

- **Anchored to a moving box** (brackets, rings, labels, leader lines) →
  **canvas**. DOM elements chasing a 60fps-moving target cause layout thrash.
- **Anchored to the frame** (subtitle track, boot sequence, corner chrome,
  shortcut overlay, the status panel) → **DOM + CSS**. You get real text
  rendering, real accessibility, real transitions, and text a screen reader
  and a video viewer can both actually read.

Follow that split unless you have a specific reason not to, and record the
reason if you deviate.

---

## What to build, in priority order

Ship top-down. **Cut from the bottom** if the timebox runs out — the series is
already on an 8-day plan against a 7-day target, so an honest partial day beats
a spillover.

### 1. The HUD render-state layer + interpolation
Described above. Nothing else on this list is achievable without it. Also fold
in a small cleanup while you're here: `drawHud.ts` has a dead `CYAN` constant
kept alive by a `void CYAN;` at line 155 — the palette should live in one place
shared by canvas and CSS (a `theme.ts` exporting the tokens that `App.css`'s
`:root` vars mirror), not as stray hex literals across two files.

### 2. Target lifecycle animation — acquire, track, lose
The single biggest perceived-intelligence win, and the most filmable.
- **Acquire:** brackets converge inward from outside the box, ~250–350ms, with
  a brief flare/ring on lock. The label types or fades in rather than popping.
- **Tracking:** subtle continuous motion — a slow ring rotation, a bracket
  breathing, a scan tick — that is *per-target phased*, not globally synced.
- **Lose:** brackets release outward and fade over ~300ms. This is what the
  exit window in the state layer exists for.

### 3. Primary target treatment
One target is the subject; the rest are context. Pick it by a simple, stated
rule (box area × centrality is the obvious one — the existing code already
picks the largest for its tracking line). The primary gets the full treatment:
brighter, full reticle, a callout with a leader line, telemetry. Everything
else dims to a quieter secondary state. **Focus transfer must animate**, not
cut — that transition is the shot that sells the whole day.

### 4. On-frame subtitle track
The narration line, rendered large and legible at the bottom of the video
frame, timed in and out with a fade.

Prioritise this properly: **no audio has been confirmed audible from any
machine across all four days so far** (D13, `day4-poc.md`), and social video is
watched muted by default anyway. The subtitle track is what makes the narration
visible in a reel at all — it is the difference between the series' central
feature being legible on camera and being invisible. It is not a nice-to-have.

Wiring note: the HUD currently receives no narration. `useNarrator`'s `log`
lives in `App.tsx` and is passed only to `StatusPanel`. The newest `LogEntry`
(it has `text`, `boring`, and `at`) needs to reach the viewport. Keep "boring
mode" working in the subtitle too — showing the literal event line on-frame is
the project's proof that the narration is driven by real detections.

### 5. Boot sequence
Replace the plain "Perception offline" / "Loading vision model…" curtains with a
staged power-on: chrome drawing itself in, systems reporting ready one line at
a time (camera → model → tracker → narrator), a scan sweep, then live. Two
reasons this earns its place: it gives every video and reel a cold open, and it
turns the genuinely slow parts (camera permission, model load, and on Day 4's
path a multi-second LLM load) into something that reads as intentional
sequencing instead of a frozen page.

Each boot line must correspond to a **real** state transition already available
(`cameraStatus`, `modelStatus`, `llmStatus`, `ttsStatus`) — see the honesty
rule below. A fake progress bar is out.

### 6. Confidence ring and size readout — honestly labelled
A ring around the primary target showing detection confidence is a genuine
data-bound visual: `Detection.score` is real and currently displayed nowhere
since Day 3 replaced `label score%` with `LABEL #id · age`.

**The distance estimate needs care.** A bigger box is nearer only for a known
object at a known focal length; you have neither. Do not print metres. Either
label it as what it actually is (relative size / apparent scale, in
frame-relative units) or leave it out. A fabricated "2.4 m" would be the first
untrue thing this project has ever put on screen, and the series' entire
credibility is the honesty of the numbers.

### 7. Keyboard shortcuts + a shortcut overlay
`Space` start/stop, `N` narration, `B` boring mode, `V` voice, `?` for an
overlay listing them. Don't capture keys while a control has focus, and make
sure every shortcut maps to a control that still exists and is still reachable
by mouse and keyboard.

---

## The honesty rule — this is the one that can sink the day

Every visual element must be **bound to real data**. A ring must encode a real
number. A boot line must reflect a real state. A scan sweep is fine as ambient
chrome; a "SCANNING 47%" readout that counts up on a timer is a lie. The
project's `public-notes.md` maintains explicit REAL / NOT-real lists and the
whole series' credibility rests on them.

Day 5 is the day with the highest risk of overclaiming, because *the interface
starts implying capability the model doesn't have*. A HUD that looks like
E.D.I.T.H. invites viewers to assume scene understanding, identity recognition,
memory, threat assessment, depth sensing — YAP has **none** of that. It draws
boxes around 80 COCO classes and says something dry about them.

So: build the aesthetic fully, then say the honest thing out loud in
`public-notes.md` and on camera. *"This looks like it understands the room. It
does not. It's the same 80-class detector as day one, drawn better — and the
fact that it feels smarter is the actual finding."* That framing is stronger
content than the overclaim would be, and it's the only version that survives
someone reading the code.

---

## Performance budget — Day 6 is watching

Day 6 is the measured-performance day, benchmarked against today's numbers.
Ship a beautiful HUD that costs 15ms a frame and you'll spend Day 6 undoing
Day 5 instead of optimising the detector.

- **Measure FPS and per-frame HUD draw cost before you start and after you
  finish**, and record both in `day5-poc.md`. Add a HUD draw-time number to the
  telemetry panel if it isn't there — Day 6 needs it anyway.
- `ctx.shadowBlur` is the usual culprit and the existing code already uses it
  per-bracket per-frame. If glow is getting expensive, the standard fixes are
  a pre-rendered offscreen glow sprite, a CSS `filter`/`blur` on a separate
  compositing layer, or fewer blurred passes — not "it's probably fine."
- Target: the HUD draw stays in **single-digit milliseconds** on the dev
  machine with 5+ targets on screen, and FPS does not regress measurably from
  the Day 4 baseline. If you can't hit that, say so with numbers and name what
  you'd cut.
- Respect `prefers-reduced-motion`: reduce the sweeps, pulses and rotation to
  static states. Everything must remain fully readable with motion off.
- Don't regress mobile. `App.css` collapses the panel at 900px; Day 7 is the
  mobile day, but the HUD must not become unusable on a phone-sized viewport
  today. Check one narrow layout.

---

## Verification — do it for real, don't assume

Every prior day was verified against a running instance, not just type-checked:

- Run `npm run dev`, start the camera, and **watch it** — with a real webcam if
  one is reachable. This is a *visual* day; a passing type-check verifies
  nothing about it. Capture before/after screenshots or a short clip: the Day 1
  HUD versus the Day 5 HUD on the same scene is the day's headline asset.
- Verify the animations against real target behaviour: walk out of frame and
  confirm the lose-animation actually plays (this needs a track to be dropped —
  the fake camera device's synthetic pattern churns tracks quickly, which is
  useful here even though it defeated Day 3's persistence demo).
- Verify a track that flickers in and out doesn't produce strobing acquire
  animations — that's the most likely ugly failure mode.
- Confirm the subtitle track shows real narration lines and that boring mode
  swaps them.
- `npx tsc -b`, `npm run build`, `npx oxlint src/`, `npm run test` — all clean.
  Existing tests (`narrator.test.ts`, `tracker.test.ts`, the Day 4 adapter
  suites) must not be weakened. Add unit tests for the HUD state layer:
  acquire progress advances with dt, an absent track enters exit and is
  eventually released, interpolation converges.
- Report the main-chunk bundle size against Day 4's ~1.31MB.

---

## Update the `.claude/` workspace

- `.claude/tasks.md` — check off Day 5 items; add a "What to film for Day 5"
  checklist in the same shape as Days 2–4.
- `.claude/week-roadmap.md` — mark Day 5 ✅ SHIPPED in the established pattern,
  replacing planning language with what actually shipped and real numbers.
- `.claude/progress-log.md` — append a Day 5 entry in the same five-part
  structure as Days 1–4.
- `.claude/decisions.md` — continue the D1–D13 format (decided / why / cost /
  revisit-if). Expect at least: the HUD state layer as a separate concern from
  the tracker; the interpolation constant and its smoothness-vs-lag tradeoff;
  the canvas/DOM split; the primary-target selection rule; and whatever you
  decided about the distance readout.
- Create `.claude/day5-poc.md` — verification notes, before/after performance
  numbers, and an explicit list of what could **not** be verified.

---

## Also produce: the content assets

The project owner presents this publicly and needs documents to read from and
show on screen — content assets, not engineering notes.

**`.claude/public-notes.md`** already has a Day 5 stub ("Same brain, better
face" / *"Perceived intelligence is mostly interface."*). Fill it out to the
full structure Days 1–4 use: **Concept** (one line), **Simple explanation**
(2–4 lines, plain language), **What viewers should notice** (self-evidencing
on-screen things, not claims), **What was hard** (most likely the stateless-
painter problem, or the frame-rate-independent animation, or the perf budget),
**Posts** (X, LinkedIn, reel caption — specific, numbers-forward, no
"AI-powered"). Then update the REAL / NOT-real lists: this is the day that most
needs "the interface implies more capability than the model has" written down
explicitly on the NOT-real side.

**`.claude/demo-script.md`** — add a Day 5 section matching the existing
per-day structure. The intended flow: cold open on the boot sequence; the same
scene under the Day 1 HUD and the Day 5 HUD side by side, stating plainly that
the model is byte-identical; a slow walk-through of one target acquiring,
holding, and being lost; the primary-target focus transferring between two
objects; the subtitle track carrying the narration with the sound off; closing
on the FPS counter to prove the polish didn't cost the frame budget.

This is the most visual day of the series and probably the best reel — script
it like that.

---

## House rules (don't violate these)

- Scope discipline: `src/vision/` and `src/narration/` logic is **off limits**
  today except for the wiring needed to get narration lines to the viewport.
  If you spot a bug there, write it in `tasks.md` and leave it.
- No speculative abstractions, no unrelated refactors, no error handling for
  scenarios that can't happen. No animation framework — this is canvas, rAF,
  and CSS transitions.
- Default to no code comments; add one only where the *why* is genuinely
  non-obvious. Match the terse style in `drawHud.ts`, `useDetector.ts`,
  `useNarrator.ts`.
- Every public-facing claim must be something you actually watched happen.
  Screenshots or it didn't ship — this is a visual day.
- Prefer the cheaper draw call. Twice.
- Report back in five parts: what was researched, what was decided, what was
  built, what is still missing, what can be shown publicly.
