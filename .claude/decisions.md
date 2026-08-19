# Decisions

Each entry: what was decided, why, and what it costs.

---

### D1 — Browser-only. No backend, no API keys.
**Decided:** Day 1
**Why:** Three wins in one choice. (a) **Latency** — no network round trip;
inference is ~12ms locally vs 200–800ms to a cloud vision API. (b) **Privacy** —
video never leaves the device, which is a genuinely strong claim and great
public narrative. (c) **Shipping speed** — no auth, no deploy, no cost, no rate
limits. `npm install && npm run dev` and it works.
**Cost:** Capped at what runs on-device. Can't use a large multimodal model for
rich scene description without breaking the constraint.
**Revisit if:** never — reaffirmed at Day 4 (see D10). No cloud call, ever,
even an optional one. Richer narration comes from a *local* LLM, not a hybrid.

---

### D2 — TensorFlow.js + COCO-SSD (`lite_mobilenet_v2`)
**Decided:** Day 1
**Why:** The fastest credible path to real boxes on real pixels — two npm
packages, no asset wrangling. `lite_mobilenet_v2` over the default MobileNet v2
because latency *is* the product for a HUD.
**Cost:** 80 fixed classes. Slightly lower accuracy than the heavier variant.
**Measured:** ~12ms inference, 60 FPS loop (headless Chrome, software GL).

---

### D3 — Detections live in a `ref`, not React state
**Decided:** Day 1
**Why:** State updates at 30Hz re-render the tree 30×/second and tank the
framerate. The ref decouples the detect loop from the draw loop entirely.
Telemetry is mirrored into state at ~4Hz for the panel, where staleness is
invisible.
**Cost:** Slightly unusual React. Deliberate, and commented in the code.
**This is the single most important performance decision in the project.**

---

### D4 — Separate detect loop and draw loop
**Decided:** Day 1
**Why:** They have genuinely different natural frequencies. The HUD should
animate at 60 FPS (scanline, chrome) even when inference delivers 18 FPS. Boxes
hold their last position between inferences — which is what real HUDs do anyway.
**Cost:** Two `requestAnimationFrame` loops to reason about.

---

### D5 — Mirror coordinates, not the canvas
**Decided:** Day 1, after seeing a bug
**Why:** CSS-mirroring the overlay canvas to match the mirrored video also
mirrors the label **text**, rendering it backwards. Caught in a headless
screenshot. Flipping box coordinates in `drawHud` fixes it cleanly.
**Cost:** None. Strictly better.

---

### D6 — Narration gates on *stability*, then *change*
**Decided:** Day 1
**Why:** The hard problem in narration is timing, not wording. Three gates:
sample at 4Hz, require a scene to hold ~900ms (kills flicker from
low-confidence boxes), enforce a ~3.5s cooldown. And describe what *changed*,
not the full scene — re-reading everything is what makes narration feel robotic.
**Cost:** Up to ~1s of latency before YAP comments on something new. Correct
trade: a narrator that stutters is worse than one that's briefly late.
**Numbers are first-guess, not tuned on real scenes — that's Day 3's job.**

---

### D7 — Pure functions for drawing and describing
**Decided:** Day 1
**Why:** `drawHud.ts` and `describeScene.ts` are the two files most likely to
grow through the week. Keeping them free of React and side effects makes them
testable and safe to iterate on.
**Cost:** A few more arguments passed explicitly.

---

### D8 — Vite + React + TypeScript
**Decided:** Day 1
**Why:** Instant HMR matters when tuning a visual real-time system — you see
changes without losing the camera stream. TypeScript earns its keep on
coordinate-space bugs specifically.
**Cost:** None meaningful at this scale.

---

### D9 — No test suite on Day 1
**Decided:** Day 1
**Why:** The Day 1 risk is "does the loop work at all", which is verified by
looking at it, not by unit tests. Verification was done with a real headless
browser using a fake camera device — that caught an actual bug (D5) that unit
tests would not have.
**Cost:** Regressions possible. `describeScene.ts` is pure and is the obvious
first thing to test — planned for Day 6.
**This is a deliberate speed trade, not an oversight.**

---

### D10 — Local LLM + local TTS. No cloud APIs, ever.
**Decided:** Day 4 planning
**Why:** D1's on-device story (no backend, no API keys, video never leaves the
device) was always the product's core claim. The current narrator voice
(Web Speech `speechSynthesis`) is free and offline but flat — robotic
cadence, no emotional range. The upgrade path is explicitly **not** a cloud
LLM or cloud TTS call: the plan targets mobile as a first-class platform, and
a cloud round-trip is both a latency regression and a broken privacy/cost
promise on a device that's supposed to work with no network at all. Instead:
a **local LLM** (small enough to run on-device — think WebLLM/ONNX/GGUF-class
models in the few-hundred-MB-to-low-single-digit-GB range, not a 7B+ model) to
generate richer narration lines, and a **local neural TTS** engine (not the
default OS voice) for expressive speech — both selected for the *tiniest*
footprint that's still qualitatively better than templates + `speechSynthesis`,
because mobile latency budget is the binding constraint, not desktop.
**Cost:** Model download/cache size on first load. Meaningfully more complex
than the current template-based narrator. Quality ceiling is lower than a
frontier cloud model — an explicit trade for latency, privacy, and zero
running cost.
**Revisit if:** on-device tiny models can't hit an acceptable latency/quality
bar on real mobile hardware — but the fallback is a *smaller* local model or
staying with the current template narrator, not a cloud call.
**This is a hard product constraint, not a preference — do not propose a
cloud API for narration or voice, even as an optional mode.**

---

### D11 — IoU tracker: same-label matching, α = 0.4 smoothing, missed-frame grace
**Decided:** Day 3. **Revised:** Day 3, same day, after real-webcam use.
**Why:** Simplest thing that kills jitter and gives objects identity without a
Kalman filter or re-identification, per the explicit Day 3 timebox.
- **Match requires the same COCO label**, not just box overlap — a chair
  should never inherit a person's id on an ambiguous overlap. Cost: a
  detector mislabeling the same object frame-to-frame (rare, but happens near
  the confidence floor) creates a spurious id churn instead of being caught
  by position alone. Accepted — correctness of identity mattered more than
  never losing an id to a labeling flicker.
- **α = 0.4 for exponential smoothing** — a reasonable middle value, not
  tuned against real footage. Revisit if real movement shows visible lag.
- **Missed-frame grace window** before a track is dropped.

**The bug this revision fixes:** the first cut matched purely on IoU ≥ 0.3
against the *previous* frame. On real webcam footage this failed constantly,
not rarely — `lite_mobilenet_v2` (chosen for speed, D2) is noisy enough that
the box for one completely static object routinely shifts far enough between
two real frames to drop IoU under 0.3, and small objects (a phone) are worse,
since the same few pixels of jitter are a bigger fraction of a small box.
Worse than the threshold itself: the code's *response* to one failed match
was to immediately mint a brand-new track/id for the unmatched detection,
rather than waiting out the grace window — so a single noisy frame, not just
a genuine miss, reset identity. Reported live: a stationary phone climbing
past `#240`, a person's id incrementing continuously while standing still.
**Fix:** two changes to `src/vision/tracker.ts`.
1. **Center-distance fallback** — same label, box centers within half the
   average box diagonal, counts as a match even when IoU alone is low. Center
   distance is much less sensitive to small-object jitter than IoU. IoU
   threshold also loosened, 0.3 → 0.15.
2. **Missed-frame grace widened**, 5 → 20, since 5 frames is well under 100ms
   at the 60fps this ran at in headless testing but a much shorter, less
   forgiving window on real hardware running the model at real webcam
   framerates.
Locked in with `src/vision/tracker.test.ts` (new), covering: id stability
under aggressive small-object jitter chosen so consecutive-frame IoU is
provably below the old 0.3 threshold; id stability under steady walking
motion; a genuinely new object still getting a new id; grace-window
recovery after a brief gap; and eventual drop + fresh id after a gap well
past the grace window.
**Cost:** No Kalman filter means no velocity-based prediction — a track's box
freezes at its last known position during a miss rather than extrapolating
forward. No re-identification — an object that fully leaves frame and a new
object of the same class entering later gets a new id. Both explicitly out
of scope for Day 3. The center-distance fallback trades a little precision
for robustness — two different, similarly-sized, same-label objects that
happen to swap positions between frames could in principle be mismatched;
accepted, since the common case (one object, jittery box) matters far more
for this project than the rare adversarial case.
**Revisit if:** real footage still shows id churn (loosen further, or move to
a proper predicted-position tracker), or α = 0.4 visibly lags fast motion.

---

### D12 — Narration switched to track-based events; `count_change` goes dormant
**Decided:** Day 3
**Why:** `src/narration/events.ts` used to diff label *counts* between settled
scenes, so a second person walking in when one was already present read as
`count_change: person 1→2` — accurate about the number, wrong about the
event. With tracks carrying identity, every count delta already rides an
`appear` (a new track id) or a `disappear` (a track id that's gone) for the
specific object that caused it, so `count_change` has no remaining case that
produces it from this path.
**Cost:** `count_change` stays in `NarrationEventType`, `TEMPLATES`, and
`byInterest` — the type, ~25 authored joke lines, and the priority ordering
are all still there, just unreachable from `createEventTracker`. This was a
deliberate choice over deleting them outright: ripping out an entire
authored template bank and its dedicated tests was judged bigger-than-Day-3
scope for a path that becomes correctly unreachable as a *side effect* of the
tracking fix, not a change anyone asked for on its own. It does mean the
codebase now carries one dead branch until a decision is made either to
delete it or find it a new legitimate trigger.
**Revisit if:** Day 4+ work either (a) confirms `count_change` has no future
use and deletes it + its templates cleanly, or (b) finds it a genuine new
meaning (e.g. a track's label being corrected mid-life by a confidence
re-check) — don't leave it dormant indefinitely.

---

### D13 — Local LLM (WebLLM + Qwen2.5-0.5B) and local TTS (Kokoro-82M), generate-ahead to stay synchronous
**Decided:** Day 4
**Why an LLM at all, and why this one:** D10 committed to a local LLM, no
cloud, sized for mobile. WebLLM (`@mlc-ai/web-llm`) was chosen over
Transformers.js-for-text-generation because its prebuilt catalog ships
WebGPU-compiled model libraries with measured `vram_required_MB` per model —
the actual number needed to pick the smallest one, not a guess.
**Qwen2.5-0.5B-Instruct (q4f16_1, 944.62 MB VRAM, `low_resource_required:
true`)** is the smallest *instruct-tuned* model in that catalog — smaller
options exist (down to ~0.5B is already the floor for anything base-instruct
in WebLLM today; nothing like a 135M/360M instruct model is in the prebuilt
list) — so this is "smallest that clears the bar," per the house rule,
measured against WebLLM's actual registry rather than assumed.
**Cost:** Requires WebGPU. No WebGPU (older mobile Safari, some Android
WebViews) means `state: 'unavailable'` and a permanent, correct fallback to
templates — never a hang, never a cloud call. ~945MB VRAM is real weight on a
phone; this is the known ceiling risk called out in D10, not yet resolved.
**Why Kokoro-82M for TTS:** smallest widely-used *neural* (not formant/robotic)
TTS with a browser runtime (`kokoro-js`, Transformers.js/onnxruntime-web
under the hood). Loaded at `dtype: "q8"` (~85–90MB) rather than `fp32`
(~326MB) — README recommends fp32 for the WebGPU path, but `q8` is the
deliberate choice here: the download-size floor mattered more than the
quality delta for a nature-documentary narrator, and `q8`/`wasm` avoids
committing every device to WebGPU just to get a voice out at all (`system`
`speechSynthesis` needs neither WebGPU nor a big download, so it stays the
safe fallback either way).
**The async problem — approach chosen: generate-ahead, not widen-to-async.**
`LineGenerator` stays fully synchronous (`generateLine`/`foldLine`); a new
optional `prefetch(event)` hook starts inference the moment an event is
*queued* in `useNarrator.ts`, not when it's *spoken*. Because the pipeline
already has a 900ms stability gate plus up to `min_seconds_between_lines`
(4s default) of rate-limit buffer before that event's narration slot arrives,
a ~350–600ms chat completion (measured, see below) almost always finishes
inside that window. `generateLine`/`foldLine` read a `WeakMap<NarrationEvent,
…>` cache keyed by the event object itself and fall back to the template
generator — synchronously, no await, ever — if the line isn't cached yet,
failed, or got rejected by the character filter. This was chosen over
widening the interface to `Promise<string>` because a widen-to-async version
would force `useNarrator`'s 250ms sampler tick to either block on `await`
(reintroducing exactly the "mouth chained to a clock it doesn't control"
failure Day 2 fixed) or grow its own separate readiness-polling logic that
generate-ahead gets for free from timing the project already has.
**In-flight inference is serialized**, not parallel — a promise chain in
`llmLineGenerator.ts` ensures only one chat completion runs at a time, since
WebGPU/WASM inference backends are not generally safe for concurrent calls
and only one line is ever needed at once anyway.
**Character enforcement is a filter, not a hope.** The system prompt states
the voice rules and gives a few authored lines as tone anchors, but
`sanitizeLlmLine()` is what's actually load-bearing: strips wrapping quotes,
lowercases, converts `!` to `.`, rejects `BANNED_WORDS` hits, rejects swear
words below `spice_level` 2, rejects anything under 3 words, and **truncates**
(never passes through) anything over `line_max_words` — matching the
day4-voice-prompt's explicit "truncate or re-roll, never let a long line
through." A rejected line falls back to the template generator for that slot,
exactly like an unloaded model would.
**Measured, not claimed (headless Chrome + Puppeteer, fake camera device,
`--enable-unsafe-webgpu`, see `day4-poc.md` for the full run):**
- Qwen2.5-0.5B cold load (first visit, real network): **~45–63s**,
  ~945MB, mostly `params_shard_*.bin` fetches from `huggingface.co` plus
  the WebGPU shader wasm from `raw.githubusercontent.com`.
- Warm reload (same profile, weights already in the browser's Cache
  Storage): **~11s**, confirmed **0 bytes** re-fetched from
  `huggingface.co`/`githubusercontent.com` — the caching claim holds.
- First chat completion after load: **350–567ms**.
- With the network then cut entirely (CDP offline, tab kept open, no
  reload): the app kept producing new narration lines and fired **zero**
  network requests — inference genuinely has no network dependency once
  loaded.
- Output quality, honestly: the sanitizer's hard rules (word count, banned
  words, swears) held on every observed line, but 0.5B does **not**
  reliably nail the "one deadpan sentence" tone — observed output included
  multi-clause, mildly flowery lines ("kite flew high, its kite spirit
  soaring...") that pass every mechanical check but read closer to
  generic-assistant prose than the authored template bank. This is the
  quality ceiling D10 already flagged as an accepted trade for
  latency/privacy/cost — recorded here as measured, not assumed.
**Kokoro TTS status — a genuine bug found, root-caused, half-fixed, not
glossed over:** `kokoro-js`'s phonemizer (`espeak-ng`, compiled to WASM)
failed at synthesis time with `Invalid language identifier: "en-us". Should
be one of: .` — its internal language table came back empty, deterministically
(every call, not a race — confirmed by observing repeated failures seconds
apart with no self-healing). Two contributing causes found:
1. **Missing cross-origin isolation** — `kokoro-js`/`onnxruntime-web` and
   `web-llm` both ship multi-threaded WASM builds that need
   `SharedArrayBuffer`, granted only to a page with
   `Cross-Origin-Opener-Policy: same-origin` +
   `Cross-Origin-Embedder-Policy: require-corp`. Added both to
   `vite.config.ts` (dev *and* preview servers) — necessary, not sufficient.
2. **The actual root cause: JS-bundler reorganization breaks phonemizer's
   Emscripten glue.** Confirmed by testing `optimizeDeps.exclude:
   ['kokoro-js', 'phonemizer']` in `vite.config.ts`, which tells Vite's dev
   server not to run these through esbuild's dependency pre-bundler —
   **this fixed it in `npm run dev`**, verified live: no error, real
   synthesis, ~3–4s first-call latency, no fallback triggered. Also set the
   Kokoro voice persona to `af_heart` (Kokoro's top-graded, "A"-quality
   female voice) in place of the placeholder `am_onyx` (male) used while
   the engine was still broken.
**Still broken in the production build** (`npm run build` + `npm run
preview`) — Rollup, the production bundler, does its own reorganization of
the same glue code and hits the identical error; `optimizeDeps` only
controls dev-time esbuild pre-bundling and has no Rollup equivalent.
Confirmed this is bundling/module-reorganization, not minification
specifically, by building with `--minify false`: still broken. **Decision:
ship as-is.** Asked the project owner whether to keep chasing a production
fix (likely requires vendoring `kokoro-js`/`phonemizer` as unbundled static
assets so Rollup can't touch them — a real packaging change, not a tweak);
answer was to document and move on for now. `voice_engine` still defaults to
`'system'` (D10-safe, zero download, known-good); `'local-tts'` is an
explicit opt-in that **works in `npm run dev` and does not yet work in a
built/deployed app** — say this plainly if demoing from a production build,
and prefer `npm run dev` for any local-TTS demo footage until the prod fix
lands. Every failed call still logs a warning and falls back to
`speechSynthesis` rather than going silent, in both environments.
**Revisit if:** pursuing the production fix — vendor `kokoro-js` +
`phonemizer` (+ their `@huggingface/transformers` dependency) as static,
unbundled files served from `public/`, imported via a runtime
`import()` Vite is told to ignore, so Rollup never reorganizes them. Also
revisit the 0.5B tone quality if a smaller-but-better-tuned instruct model
lands in WebLLM's catalog.

---

### D14 — A separate HUD render-state layer (`src/hud/hudState.ts`), not an extension of the tracker or `drawHud`
**Decided:** Day 5
**Why:** `drawHud` was a pure, stateless function of a `Frame` — correct for
Days 1–4, but it structurally cannot animate: it has no way to know *when*
a track id first appeared (for a lock-on convergence), no way to draw a
track the tracker has already dropped (for a lose-fade), and no per-target
phase (so every pulse/rotation would beat in unison and read as a
screensaver). The fix is a third pure function, `updateHudState(prev,
frame, dtMs, frameW, frameH) -> next`, in the same shape as `tracker.ts`'s
`updateTracks` — keyed by track id, holding acquire progress, an exit
window, a stable per-id phase (golden-angle spaced, no shared clock), and
the primary-target id. `drawHud` now takes this state instead of a raw
`Frame` and stays pure and stateless itself — it just paints a richer input.
**The seam is deliberate, not incidental:** detection-side track lifetime
(`tracker.ts`'s `MAX_MISSED_FRAMES` grace window, D11) is a vision concern
with constants tuned against real webcam jitter. How long a bracket lingers
on screen after the tracker drops it is a rendering concern with a
completely different tuning goal (looks good, not survives-occlusion). Two
separate memories, two separate reasons to change either one.
**Cost:** A second per-tick state object (a `Map`) alongside the tracker's
own array, and `HudCanvas` now owns two pieces of ref state instead of one.
**Frame-rate independence:** every timed transition (acquire, exit, primary
transfer, box interpolation) is driven by real elapsed `dtMs`, computed in
`HudCanvas` from `t - lastT` on the rAF callback and clamped to 100ms to
stop a backgrounded-tab reflow from making a lock-on animation visibly
teleport through its whole arc in one tick. A 120Hz display advances these
by wall-clock time, not by tick count, so it does not animate twice as fast
as a 60Hz one.

---

### D15 — Render-time box interpolation, τ = 70ms
**Decided:** Day 5
**Why:** Detection delivers a new box every ~12–80ms (D2's measured
inference latency); the display redraws every ~16ms. Without interpolation
the drawn box holds its last position and then jumps on the next detection
tick — visible even at 60 FPS. `hudState.ts` eases the drawn box toward the
latest tracked box every render tick using an exponential time constant
(`BOX_LERP_TAU_MS = 70`): the box closes ~63% of the remaining gap every
70ms. This is the same *shape* of smoothing as the tracker's own α = 0.4
detection-rate smoothing (D11), applied a second time at display rate,
because the two operate on different clocks and neither alone removes both
kinds of visible discontinuity.
**Cost, stated plainly:** interpolation trades a few frames of visual lag
for smoothness — a fast real-world move will visibly lag the box by roughly
one interpolation time-constant before it catches up. 70ms was chosen by
feel (screenshotted against the fake-camera device's churn, see
`day5-poc.md`) as the smallest value that still visibly removed the jump; it
has not been tuned against real, fast hand motion.
**Revisit if:** real-webcam footage shows the lag is more noticeable than
the jump it replaced — lower τ, or drop interpolation for very fast-moving
targets specifically.

---

### D16 — Primary-target selection: box area × frame-centrality
**Decided:** Day 5
**Why:** The existing tracking-line code (Days 1–4) already picked "the
largest track" as a proxy for "the subject" — Day 5's primary-target
treatment needed the same idea, refined so a huge object jammed in a corner
doesn't out-rank a moderately sized, centered one. Score = `bbox area ×
centrality`, where centrality falls linearly from 1 at the frame's center to
0 at its corners (half-diagonal normalized). Whichever live (non-exiting)
target scores highest each tick is primary; `primaryProgress` per target
eases toward 1 (primary) or 0 (not) over `PRIMARY_TRANSFER_MS = 250` so
focus *transfers* between two targets rather than cutting.
**Cost:** No temporal hysteresis — if two targets have near-identical
scores, primary can flicker between them tick to tick. Not observed in
headless verification (the fake-camera scene rarely holds two similarly
salient targets at once) but a plausible real-footage failure mode; not
fixed this session.
**Revisit if:** real footage shows primary flicker between near-tied
targets — add a score-margin/dwell-time requirement before transferring.

---

### D17 — Confidence ring is real; distance is a labelled relative-size readout, not metres
**Decided:** Day 5
**Why:** `Detection.score` is a real number that Day 3 stopped displaying
(it replaced `label score%` with `LABEL #id · age`) — Day 5's confidence
ring puts it back on screen, honestly: the ring's arc length is literally
`score`. The "how far away" instinct a HUD like this invites is not
answerable honestly: a bigger box only means "nearer" for a known object at
a known focal length, and this project has neither (D2's `lite_mobilenet_v2`
gives no depth or camera-intrinsics data). Printing a fabricated "2.4 m"
would have been the first untrue number this project ever put on screen.
Shipped instead: a **relative size readout** — `SIZE 12% OF FRAME`, the
box's real area divided by the real frame area — true, derivable from data
that actually exists, and still gives the HUD-reading-a-scale feeling the
prompt asked for.
**Cost:** Less immediately legible than "2.4 m" would have been — "18% of
frame" needs a beat of interpretation a fake distance wouldn't. Accepted;
see the honesty rule in `day5-hud-prompt.md` and `public-notes.md`'s
NOT-real list.

---

### D18 — Glow (`shadowBlur`) reserved for the primary target only
**Decided:** Day 5
**Why:** `ctx.shadowBlur` was already flagged as the likely perf cost center
before writing any Day 5 code (`day5-hud-prompt.md`'s performance-budget
section) — Days 1–4 paid it per-bracket, per-target, every frame. Rather
than pre-render an offscreen glow sprite (more machinery than a 7-day
timebox justifies for the numbers actually measured), Day 5 narrows where
the cost is paid: `SECONDARY_GLOW = 0`, only the primary target's bracket
gets `shadowBlur`. Non-primary targets are also visually dimmed
(`SECONDARY_ALPHA`), which was already needed for the primary-target
treatment (D16) — the perf win rides along with a visual decision already
being made, not a separate optimization pass.
**Measured (see `day5-poc.md`):** HUD draw time in headless verification
stayed at ~0.1ms with a single target on screen. The fake-camera scene
never produced 5+ objects at once, so target scaling was benchmarked
directly against the real module instead (synthetic `HudState`, 300 timed
frames per count, headless Chrome, 1280×720): **0.050 / 0.047 / 0.049 /
0.058 / 0.070 ms at 1 / 3 / 5 / 8 / 12 targets.** Essentially flat — cost
is dominated by the constant-price frame chrome and the single primary
instrument, so extra targets are nearly free. The bet holds; the
offscreen-sprite approach stays unbuilt.
**Revisit if:** the primary instrument ever gets a second glowing element,
or secondary targets are promoted past bracket + centre pip — both would
move cost from constant to per-target, which is the shape of the problem
this decision was avoiding.

---

### D19 — HUD density is the deliverable, not the animation
**Decided:** Day 5 (second pass)
**Why:** The first Day 5 build had the whole state layer working —
acquire/exit animation, interpolation, primary transfer — and still looked
like a rectangle with a circle around it. The lesson is that the perceived
jump comes from **instrument density**, not from motion: graduated tick
rings, chamfered corners, elbow leader lines into data cards, labelled
frame-edge rulers, registration marks. Animation without that vocabulary
just moves a plain box around smoothly.
**What this rules out:** density for its own sake. Every readout added in
this pass is a real measurement (`CONF` = `Detection.score`, `AREA` = box
area / frame area, `POS` = box centre as % of frame, `AGE` = tracker track
age, `TRK` = live target count), and the rulers are a scale of the frame
itself. The temptation to fill empty edges with decorative bar-graphs and
scrolling hex was refused — that is exactly the fabricated-telemetry line
D17 already drew for distance in metres.
**Cost:** free, measured — see D18's target-count table.
**Revisit if:** a readout is ever added that can't be traced to a real
number, at which point the honesty rule outranks the look.

---

### D20 — `mobilenet_v2` A/B'd against the D2 baseline, reverted: measured cost, unmeasured benefit
**Decided:** Day 6
**Why:** `useDetector.ts` has loaded `lite_mobilenet_v2` since D2, chosen for
speed over accuracy. Day 6's bed/dining-table confusion report is exactly
the kind of thing a heavier backbone might improve, so it was tried:
swapping `base: 'lite_mobilenet_v2'` → `base: 'mobilenet_v2'`, same headless
Chrome + fake-camera-device harness used in every prior session, 5 samples
each, 3s warm-up.
**Measured:** inference rose from **~11ms to ~16–17ms** (roughly +50%); FPS
stayed at ~60 in both cases (the draw loop, not the detect loop, is what's
rAF-capped, so this doesn't yet show up as a visible framerate change).
Inference is still comfortably inside budget at this cost — this was *not*
a latency-forced revert.
**Reverted anyway, and here's the honest reason:** the fake camera device's
synthetic test pattern has no bed and no dining table in it, and no other
real-webcam scene was available this session. There was no way to check
whether the accuracy actually improved — only that the cost was real. Per
the day's own timebox rule ("keep only if accuracy improves and inference
stays inside budget; otherwise revert and record the numbers"), paying a
confirmed 50% inference cost for an unconfirmed accuracy gain is the wrong
trade. `useDetector.ts` still loads `lite_mobilenet_v2`, with the measured
numbers left in a comment at the point of the (unchanged) call.
**This is a negative result, not a non-result** — it rules out "just swap
the backbone" as the fix, which is exactly why D21 below exists.
**Revisit if:** a real webcam scene with a bed/dining-table-style
confusable pair becomes available to test against — the inference cost is
known and affordable if the accuracy case turns out to hold up.

---

### D21 — Per-track label voting + cross-label match gate, not a bigger model
**Decided:** Day 6
**Why:** D20 ruled out "swap the backbone." The actual bug was structural,
not a model-quality problem: `tracker.ts`'s `updateTracks` took a track's
label from whichever detection matched *that* frame — 30 frames of history
per track, thrown away, keeping only the last vote. Worse, matching
*required* the same label (`if (track.label !== detection.label) continue`),
so the instant the model flipped `bed` → `dining table`, the old track went
unmatched and a **brand-new track id was minted** — the same id-churn
failure mode as D11, with a different trigger.
**Two changes to `src/vision/tracker.ts`:**
1. **Cross-label matching, gated on IoU ≥ `CROSS_LABEL_IOU_THRESHOLD`
   (0.5).** Same-label matching stays exactly as permissive as D11 left it
   (IoU ≥ 0.15 *or* center-distance fallback). A *different*-label pair is
   only eligible via a much stricter IoU-only check — no center-distance
   fallback for cross-label, since the geometric case this is fixing (the
   same physical object, box barely moved) is exactly the case with high
   IoU. This is deliberately asymmetric: a chair must never inherit a
   person's id off a weak or coincidental overlap, and the wide gap between
   0.15 (same-label) and 0.5 (cross-label) is what buys that.
2. **A per-track vote histogram** (`Track.labelVotes: Record<string,
   number>`), decayed by `VOTE_DECAY = 0.9` each matched frame before the
   new detection's score is added — a rolling, recency-weighted tally, not
   "first label wins forever" or "latest label wins." `Track.label` is now
   the argmax of this histogram. Two new fields ride along: `labelConfidence`
   (the winner's vote share, 0..1 — a genuinely different number from
   `Detection.score`, which is this frame's raw per-detection confidence)
   and `runnerUpLabel` (second place, for the hedge — see D22).
**Cost:** `Track` carries an extra `labelVotes` map per track — bounded,
since `castVote` prunes entries below `VOTE_PRUNE_THRESHOLD` each update, so
it can't grow unboundedly even under a model that cycles through many
labels. The `0.5` cross-label threshold and `0.9` decay rate are both first-
guess constants (same caveat as D11's `α = 0.4` and D15's `τ = 70ms`) —
tuned against synthetic sequences in `tracker.test.ts`
(`'label voting: a track flip-flopping between two labels settles on a
winner rather than showing the latest frame'` and the two cross-label
direction tests), not real footage.
**Revisit if:** real footage shows the 0.5 threshold either merges two
genuinely different objects that happen to overlap, or fails to catch a
real bed/dining-table flip — tune in the direction the failure points.

---

### D22 — `UNIDENTIFIED` is a `labelConfidence` threshold, not a scripted state
**Decided:** Day 6
**Why:** D21 gives every track a real, continuous `labelConfidence`. Below
`UNCERTAIN_CONFIDENCE = 0.6` (duplicated as a literal in `drawHud.ts`,
`events.ts`, and `describeScene.ts` — same reasoning as `generateLine.ts`'s
`PLURALS` duplication: three separate consumers of the same tracker fact,
not worth a shared import just to agree on one number), the system stops
committing to a single label everywhere at once:
- **HUD** (`drawHud.ts`): the target's label reads `BED / DINING TABLE ?`
  instead of one word, in the HUD's one warn color (amber — reused, not
  invented, per the day's own instruction not to add new visual language),
  plus a real `LBL nn%` readout in the primary data card showing the vote
  share itself.
- **Narration** (`events.ts` → `generateLine.ts`): an `appear`/`disappear`/
  `still_present` event carries `uncertain: boolean` and
  `alternativeObject: string | null`, computed from whichever contributing
  track has the *lowest* `labelConfidence` (hedging about the least-sure
  one is more honest than averaging it away). A dedicated `HEDGES` template
  bank (`templates.ts`) replaces the normal bank entirely for that line —
  "something enters. bed, maybe dining table. hard to say." — never a
  normal template with the uncertain object's name slotted in.
- **Voice answers** (`describeScene.ts`): an uncertain track is reported as
  "something unidentified," grouped with any other uncertain tracks, never
  guessed.
**The LLM must restyle the hedge, never resolve it.** `llmLineGenerator.ts`
passes `uncertain`/`alternativeObject` into the prompt with an explicit
instruction, and `sanitizeLlmLine` gained a mechanical check to match: a
line generated for an uncertain event is rejected — same as a banned word
or an under-spice swear — unless it either names the alternative object or
contains a hedge cue word (`or`, `maybe`, `unclear`, `hard to say`, …). A
confidently single-label line for an uncertain event falls back to the
template hedge bank exactly like a swear falls back to the template
generator.
**Cost:** none of this fires unless a track is genuinely torn — a
consistently-labeled track (`labelConfidence` near 1) never touches this
code path, verified by `tracker.test.ts`'s "single consistent label"
cases and `narrator.test.ts`'s "does not mark an event uncertain when the
track is confident."
**Not built this session (see week-roadmap.md):** open-vocabulary
relabeling via CLIP — the actual fix for a genuinely out-of-vocabulary
object like a microphone (COCO has no `microphone` class at all, so no
amount of voting or hedging can produce the right word, only an honest
"unsure between the 80 words I know"). D21/D22 fix the *in-vocabulary*
confusion (bed vs. dining table, both real COCO classes); they cannot and
do not claim to fix the out-of-vocabulary case. Both are demoable on their
own — see day6-poc.md.

---

### D23 — Deterministic `parseIntent`, not the LLM, for control actions
**Decided:** Day 6
**Why:** `src/voice/parseIntent.ts` is a pure `(transcript: string) =>
Intent` function, fixed-pattern regex matching, no model, no async. This
was not a close call: Qwen2.5-0.5B (D13) is already known, measured, to
occasionally produce flowery off-tone output even under a hard sanitizer —
acceptable for a narration joke, where a rejected line just falls back to a
template. It is not acceptable for deciding whether "stop" actually stops
the narrator, since a control action has no meaningful fallback if the
model mishears its own job. `stop` is checked first, ahead of every other
pattern, specifically so it can never be shadowed by a longer sentence that
happens to contain a different trigger phrase.
**Cost:** this is pattern-matching, not language understanding. Off-script
phrasing ("could you tell me what's around") falls to `unknown` rather than
being loosely interpreted — stated plainly as a NOT-real claim in
`public-notes.md`, not hidden behind a generous demo take. `unknown` also
never improvises a guess at what the user might have meant; it states that
it only handles a fixed set of commands.
**Revisit if:** real usage shows the fixed pattern list is too narrow to be
useful — widen the patterns (still deterministic), don't hand intent
resolution to the LLM.

---

### D24 — Local Whisper (`Xenova/whisper-tiny.en`) via `@huggingface/transformers`, push-to-talk only
**Decided:** Day 6
**Why not the browser's free `SpeechRecognition`:** in Chrome it streams
microphone audio to Google's servers to do the recognition — a cloud call,
and D10 already drew this line for narration/voice with no exceptions and
no toggle. The same reasoning applies here without modification: speech-to-
text runs locally or the feature doesn't ship. This is one of the
better beats of the day precisely because the free, zero-effort option was
sitting right there and had to be turned down on principle.
**Why Whisper, why `tiny.en`, why `@huggingface/transformers`:** the
library is already on disk (v3.8.1), pulled in transitively via
`kokoro-js` — promoted to a **direct** dependency in `package.json` this
session (a transitive dependency you `import` from directly is a footgun
waiting for a lockfile change to break it silently), at zero new download
cost, only model weights. `whisper-tiny.en` (English-only, smallest Whisper
class Xenova ships) was chosen over `whisper-base` because push-to-talk
commands are short, English, and few-word — exactly the case a tiny model
handles fine, and the smallest model that clears the bar is the house rule
(same reasoning as D13's Qwen2.5-0.5B pick).
**Device selection:** WebGPU when `'gpu' in navigator`, wasm otherwise —
unlike the LLM loader's hard WebGPU gate (D13, `yapUnavailable` on no
WebGPU), ASR must keep working on wasm-only hardware, so this is a
preference passed to `transformers.js`'s own device selection, not a
hard requirement that throws.
**Push-to-talk, not always-listening:** hold `T` (added to the shortcut
overlay) or the mic button; release to transcribe. Chosen as the shippable
version for the reasons the day's own brief states: reliable, zero cost
when idle, and immune to a TV or speaker accidentally triggering it — none
of which an always-on wake-word listener can promise without real cost.
Recording happens via `MediaRecorder` at the browser's native audio rate,
then re-rendered to mono 16kHz via `OfflineAudioContext`
(`resampleTo16kMono` in `speechToText.ts`) — the sample rate Whisper
expects — rather than naive downsampling, which would alias.
**A second `getUserMedia` prompt, handled like the first:**
`useVoiceInput.ts` requests audio-only microphone access independently of
`useCamera`'s video-only stream, and denial is handled the same way:
a stated `micStatus`, visible in the panel, never a crash, and every other
feature keeps working with the mic refused.
**Verified in a production build, not just dev** — this mattered because
D13 is a standing warning that this exact dependency family (Transformers.js/
onnxruntime-web-adjacent packages) breaks specifically under Rollup's
bundling, not esbuild's. `npm run build && npm run preview`, headless
Chrome with `--use-fake-device-for-media-stream`: mic permission granted,
`MediaRecorder` captured, Whisper loaded and reached `ready` with **zero
console errors** (only benign onnxruntime execution-provider warnings, not
exceptions) — unlike Kokoro, this dependency does **not** hit the D13
bundler bug. See day6-poc.md for the full run.
**Not verified: a real spoken command transcribed correctly.** The headless
fake-camera device provides no real microphone input (silence or a
synthetic tone, depending on the flag), so end-to-end transcription
accuracy — "did it actually hear 'what do you see' and produce that text"
— was not checked this session. Stated plainly, same standing caveat shape
as "no audio has been confirmed audible" (D13).
**Cost / not shipped:** wake word (always-listening, transcribe-then-match
against "yap"/"hey yap") is explicitly the stretch item per the day's own
brief and was not attempted — push-to-talk is a complete feature on its
own, not a broken one. Because only push-to-talk shipped, the
self-hearing gate ("don't let YAP's own voice trigger the mic") was not
needed and was not built — it only matters for an always-listening mode.
**Revisit if:** wake word is picked up later — it needs voice-activity
segmentation, continuous transcription, and the self-hearing gate this
session skipped as unnecessary for push-to-talk; say plainly that
transcribe-then-match is not a trained keyword spotter, per the day's
honesty rules.

---

### D25 — Voice answers preempt the narration queue; latency breakdown is measured stage-by-stage
**Decided:** Day 6
**Why:** `describeScene.ts` (revived from its Day 3 deletion — see D12 —
under a new name and purpose: a direct answer, not ambient narration) and
`queryObject` are pure functions of `frameRef.current.tracks`, same
grounding discipline as `events.ts`. The wiring problem was making sure an
answer doesn't collide with ambient narration: `useNarrator.ts` gained
`speakAnswer(text)` (drops anything queued, resets the rate-limit clock so
the next ambient line waits the full `min_seconds_between_lines` from *now*,
routes through the same log + speak path so it lands in the subtitle track
like any other line) and `stopAll()` (cuts speech immediately, for the
`stop` intent, independent of `enabled` so it works even if narration
happens to be asleep).
**Await, don't generate-ahead, for this one path.** D13's generate-ahead
model exists because narration's 250ms sampler must never block. A push-to-
talk answer is different in kind: the user just spoke and is waiting for a
reply, so a plain `await` with the LLM's existing ~1.5s effective timeout
(via the sanitizer's ready/error states) is the right shape here, not a
prefetch queue with nothing to prefetch against.
**Latency breakdown panel** (kept from the old Day 6 scope per
week-roadmap.md's reshuffle) reports capture→inference→track→draw→ASR→LLM→
TTS as `StatusPanel` stats, each measured at its own call site
(`useDetector.ts` now separately times `updateTracks` as `trackMs`,
alongside the existing `inferenceMs`/`hudDrawMs`/`llmStatus.lastInferenceMs`/
`ttsStatus.lastSynthMs`/`asrStatus.lastTranscribeMs`). No `capture` number
is shown — the browser doesn't expose when a video frame actually decoded,
only when `useDetector`'s loop next reads it, so there was no real number
to put there; the panel says so rather than showing a fabricated one,
consistent with D17's rule for the same situation.
**Measured, headless Chrome + fake-camera device, production build:** FPS
60.1, inference 11ms, track 0.02ms, HUD draw 0.1ms — unchanged from the Day
5 baseline (0.050–0.070ms across target counts). See day6-poc.md.
**Revisit if:** a real frame-capture timestamp becomes available (e.g. via
`requestVideoFrameCallback`'s metadata) — add it for real then, don't
approximate it now.

---

### D26 — Post-ship bug: push-to-talk could get stuck recording; "stop" now silences narration, not just the current line
**Decided:** Day 6, post-verification (real usage caught what headless
verification couldn't)
**The bug:** `useVoiceInput.ts`'s `start()` is async — it awaits
`ensureStream()` (the mic permission prompt/`getUserMedia`). A fast
press-release of `T` could call `stop()` while `recorderRef.current` was
still `null`, since the `MediaRecorder` hadn't been constructed yet.
`stop()` found nothing to stop and did nothing; `start()` then finished
moments later and began recording anyway, with the matching keyup already
spent — nothing left to ever end that recording. Reported live as "I said
stop and it just kept going" and "it started transcribing" out of nowhere.
Headless verification never caught this because Puppeteer's synthetic
mouse/keyboard events don't reproduce human press-release timing jitter.
**Fix, `useVoiceInput.ts`:** a `stopRequestedRef` flag set the instant
`stop()`/`stopRecorder()` is called, checked at both points `start()`
could otherwise win the race — right after `ensureStream()` resolves, and
right after the recorder actually starts — stopping immediately if the
flag is already set instead of proceeding. A `MAX_RECORDING_MS` (12s) hard
safety timer was also added so a lost keyup (alt-tab, focus loss) can never
leave the mic recording indefinitely regardless of this or any future race.
**The second, non-bug complaint, addressed anyway:** "the voice... still
going on" after saying stop was working as originally specified (the
day6-prompt.md table: `stop` → `stopSpeaking()` + clear the queue, nothing
more) but not as a real user expected it: narration would resume speaking
on its own a few seconds later since `stop` never touched the `enabled`
state, only `sleep` did. Changed `stop`'s handler in `App.tsx` to also call
`setNarrating(false)` — a full stop, not just a cut mid-line. Say "wake up"
to resume, same as after `sleep`.
**Also added: `Escape` as an instant, voice-free hard stop** — calls the
same `stopAll()` + `setNarrating(false)` with zero ASR round-trip, for the
moment a working mic isn't reliable enough. This is the actually-reliable
panic button; voice `stop` still has Whisper's transcription latency
(seconds, not instant) baked in by nature of the pipeline, which is a
property of local ASR, not a bug — `Escape` exists specifically so waiting
on that latency is never the only option.
**Cost:** none — `stopRecorder` is now the single source of truth `stop()`
and the safety timer both call, so they can't drift out of sync with each
other.
**Revisit if:** real usage shows 12s is too short for a genuine longer
question, or too long as a safety ceiling — no data yet either way.

---

### D27 — Post-ship bug: a dominant track (bed) could steal a neighbor's detection (chair/mic) and go silent about everything else
**Decided:** Day 6, post-verification (a second real-usage bug report)
**The bug:** `tracker.ts`'s D21 cross-label matching put same-label and
cross-label candidates into **one shared, score-sorted list**. A same-label
match against an *unchanged* detection scores 1.0 (the highest possible),
so a track never loses its own detection to a thief *as long as that
detection is present*. The actual trigger is one step subtler and far more
common on real footage: `lite_mobilenet_v2` doesn't re-detect every object
on every single frame, even a large stationary one — a `bed` detection can
simply be **absent** for one tick, a completely normal confidence-threshold
flicker. On exactly that tick, the bed track has *no* same-label candidate
at all, so its only option is the cross-label one against whatever nearby
object is detected instead. If that neighbor's own same-label score
(against its own last-known, possibly slightly jittered box) happened to
be *lower* than the bed's cross-label overlap with it — proven by direct
computation and a hand-rolled standalone repro of the old algorithm before
touching test code (chair same-label score 0.333 vs. bed cross-label
overlap 0.75, both clearing their respective gates) — the bed **won the
chair's detection outright and relabeled itself `chair` for that tick**,
while the real chair track was marked `missed`. Repeated over many ticks
of a real cluttered scene (bed near a chair, a mic on a nightstand, etc.),
every nearby object's track kept intermittently starving into the bed's,
which is exactly the reported symptom: narration only ever talks about the
bed.
**Fix:** split matching into **two separate passes**, not one shared
ranked list — `updateTracks` now runs same-label matching to completion
first (exactly D11's original algorithm, untouched), and only *then* runs
cross-label matching on whatever tracks and detections that first pass left
unclaimed. A detection can only be taken cross-label if its own track
already failed to claim it under same-label terms alone — this makes the
steal structurally impossible rather than merely unlikely at a given
threshold value. `CROSS_LABEL_IOU_THRESHOLD` (0.5) is unchanged; the bug
was in candidate *ranking*, not the threshold itself.
**Caught by:** a hand-built standalone JS reproduction of the *old*
algorithm (not the test suite) run against the exact reported symptom
first, to find real trigger geometry before writing a test — an earlier
attempted regression test (`bed`/`chair` boxes overlapping every frame with
no gap in bed's own detection) **passed against the buggy code**, because a
track's own perfect same-label match always wins its detection when that
detection exists every frame; only once the "bed's own detection is
missing for a tick" condition was found did the bug reproduce. The
surviving test in `tracker.test.ts` was verified both ways: confirmed
failing against the pre-fix code (`chair.missedFrames` came back `1`
instead of `0`) via `git stash`, then confirmed passing against the fix —
neither the failure nor the fix was assumed.
**Cost:** none — same-label-first is strictly a more conservative ordering
than the original shared list; every existing D11/D21 test still passes
unmodified.
**Revisit if:** real footage shows a *genuine* same-object relabel (the bed
↔ dining table case D21 was built for) failing to recover because the old
label's detection is present-but-wrong on the same tick a correct relabel
would otherwise happen — not expected, since the model only ever emits one
label per real detection, but worth checking against real footage rather
than assuming.

---

### D28 — The V2 pivot: leave the browser as the perception host, measured before decided
**Decided:** Day 7, after `day7-baseline.md`'s scenarios A–E
**Why, in one line:** six days built a system that does maximum work at all
times whether or not anyone needs the answer, and `v2-architecture-research.md`
§1e/§2 named that as the real root cause before today's measurement existed.
Today's job was to check whether the browser build's *actual* behavior on
this machine supports that diagnosis, or contradicts it — see
`day7-baseline.md` for the full numbers this decision rests on.
**What the numbers said:**
- Scenarios A–C (detection alone, +template narration, +local-llm/tts
  configured) all held a clean 60fps main-thread rAF cadence with **zero**
  `PerformanceObserver('longtask')` entries — the detect/draw/narration
  loops genuinely do not fight each other on this machine at these
  settings, which is worth saying plainly since it's a case *for* the old
  architecture, not against it (per the day's own honesty rules).
- The CPU-floor proxy (`Performance.getMetrics` `TaskDuration`) sat in the
  **~72–76%-of-one-core** range across A–E, essentially flat regardless of
  which engines were configured on — a system computing roughly the same
  amount of work per second whether or not narration, the LLM, or TTS were
  actually doing anything, which is the "maximum work at all times"
  diagnosis, measured rather than assumed.
- **The genuinely load-bearing finding didn't come from the frame-timing
  numbers at all — it came from trying to load the local LLM/TTS stack
  for scenarios C/D/E.** Kokoro TTS failed to fetch its weights
  (`ERR_HTTP2_PROTOCOL_ERROR`/`ERR_QUIC_PROTOCOL_ERROR`, falling back to
  `speechSynthesis` exactly as D13 designed) on every attempt this
  session. Qwen2.5-0.5B, measured at a **45–63s cold load** in D13's own
  session, sat in `loading` for **7+ minutes with zero forward progress**
  on one attempt today before the harness gave up waiting — not slow,
  stuck. Outbound network from this same machine (`curl`, and a bare
  Puppeteer page loaded against `huggingface.co`) worked fine throughout,
  so this isn't a blanket connectivity failure; it's specific to these
  large chunked WASM/model-shard fetches, in this session, inside a
  headless Chrome instance running alongside several other concurrent
  processes on the same machine.
- **This is itself the pivot's evidence, not a methodology footnote to
  bury.** A five-day-old browser app with three independent inference
  runtimes and no coordination between them (§1b/§1c) failed to reliably
  load its own dependencies on a real, working machine, on a real,
  working network, because of resource contention from unrelated
  processes it has no way to see or yield to. That is exactly the fragility
  §1a–§1e describe, caught in the act rather than argued for.
- **Scenario E sharpens where the always-on waste actually lives.** With
  nothing in frame, D13's own generate-ahead design means the LLM/TTS
  prefetch path never even attempts to start (`llmState`/`ttsState` stayed
  `idle`, the only scenario where that was true) — so the constantly-elevated
  CPU floor (~72% of one core, flat across every scenario including the
  empty one, for **zero** narration lines produced in a full minute) is a
  **detection-loop** cost, not an LLM/TTS one: the current detector has no
  motion gate and runs full COCO-SSD inference on every 60Hz tick regardless
  of scene content. This makes Day 8's T1 motion gate the more load-bearing
  half of the tier scheduler for this specific finding, not the T2/T3
  on-demand gating — both still ship, this just says which one is carrying
  more of scenario E's number.
**Decision:** proceed with the V2 pivot as scoped in `v2-roadmap.md` —
Python engine (`engine/`, this session's skeleton), tiered scheduler
(Day 8+), on-demand LLM/TTS instead of always-loaded. Public claims retired
in `public-notes.md` per Part 2 of `day7-prompt.md`.
**What survives, stated plainly (per the day's honesty rule against
narrating the pivot as failure):** the perception pipeline, the event
layer, the tracker, the HUD design language, and the honesty discipline
built across Days 1–6 all carry forward unchanged in spirit — `hudState.ts`
and `drawHud.ts` are designed to consume a `Frame` and don't care what
produced it (architecture.md's layering rule, holding up exactly as
intended). What changes is where inference runs and when it's allowed to.
**What this measurement does NOT show:** that the browser architecture is
*incapable* of running smoothly — scenarios A–C's clean 60fps/zero-longtask
result argues the opposite under these specific settings. The case for V2
is the *structural* one (§1a–§1e, memory pressure, no coordination across
three runtimes, always-on cost) and the operational one (today's stuck
load), not "it visibly stutters on this machine" — that claim would be
false and this document says so.
**Revisit if:** Day 8's Python engine hits the equivalent resource-
contention fragility for a different reason — the fix there needs to be
architectural (process isolation, the tier scheduler, D29's queue
discipline), not "hope the network behaves."
**New dependency: `puppeteer` (devDependency only).** Prior sessions
(Days 4–6) drove headless Chrome for verification via ad hoc `npx puppeteer`
without ever adding it to `package.json` — reproducible only by accident.
Promoted to a real `devDependency` this session since `scripts/bench.mjs`
is now a permanent, rerunnable part of the repo, not a one-off. Dev-only;
adds nothing to the shipped app or its bundle size.

---

### D29 — `engine/`: process-per-workload, latest-wins queues at depth 1. Drop frames, never buffer.
**Decided:** Day 7, before the first line of `engine/capture.py` was written
**Why:** `v2-architecture-research.md` §7 names the trap precisely: Python
has a GIL, which is the same shape of problem as the browser's single main
thread (§1a) — porting all of Days 1–6's workloads into one Python process
reproduces the exact stall in a new language. The fix decided in advance,
not discovered after a bug report the way D26/D27 were: **capture runs in
its own OS process** (`multiprocessing.Process`, not a thread — a real
process boundary, not a GIL-shared one), and hands frames to the consumer
across a `multiprocessing.Queue` capped at depth 1, where every write first
drains whatever was queued before inserting the new frame
(`capture.py`'s `put_latest`). A slow consumer sees a stale-but-recent
frame; it never sees a growing backlog. "A queue that grows is latency that
grows; a stale frame is worthless" (research doc §7) — this is that rule,
as code, on day one.
**Why decided before, not after:** retrofitting an attention/queue budget
onto an already-built always-on loop is exactly the mistake §2/§9 Phase 1
calls out for the tier scheduler, and the same logic applies one level
down — a queue policy is an architectural property, not a tuning knob, and
is far cheaper to get right before the first consumer is written than after.
**Verified, not just designed:** `engine/main.py --synthetic` runs the real
multi-process path (a generator frame in place of a camera, so the queue and
process-boundary mechanics are exercised even without a working camera) —
confirmed frames cross the process boundary and the motion gate consumes
them correctly. `engine/main.py` (real camera) does the same over a genuine
`cv2.VideoCapture(..., cv2.CAP_AVFOUNDATION)` process. See day7-baseline.md
for the measured per-frame cost this bought: gate cost stayed in the
sub-2ms range even with IPC (queue put/get across processes) in the loop,
nowhere near the frame budget.
**Cost:** one full frame copy per `put`/`get` across the process boundary
(no shared memory yet) — acceptable at T0's frame rate and resolution
(160×120 grayscale is what the gate actually touches; the queue currently
carries the full-resolution BGR frame, which is the one place this decision
is deliberately not yet optimal — see Revisit). `put_latest`'s drain-then-
insert has a small, accepted race across processes (the "failure mode of
losing that race is the queue holds one frame instead of zero for an
instant" — comment in `capture.py`), never unbounded growth, which is the
property that actually matters.
**Revisit if:** T1 (detection) is added and profiling shows the full-frame
IPC copy costs more than expected at a higher resolution/rate — move to
shared memory (`multiprocessing.shared_memory`) then, with the cost
measured, not assumed up front.

---

### D30 — T1 detector: YOLOE via Ultralytics on PyTorch/MPS, not MLX
**Decided:** Day 8
**What the plan asked for:** `v2-architecture-research.md` §4 named "YOLOE
via MLX" — open-vocabulary, text-promptable detection on Apple's MLX
runtime, replacing `lite_mobilenet_v2`'s fixed 80 COCO classes (D2), which
is the literal reason a bed reads as `dining table` and a microphone reads
as `tie` in the browser build — no confidence threshold, voting scheme, or
tracker fix (D11/D20/D21/D27) could ever produce a label that isn't in the
model's vocabulary.
**What's actually shipping:** the same model family and the same
capability — YOLOE (`yoloe-11s-seg.pt`, the smallest variant), loaded via
`ultralytics==8.4.120`, running on `device="mps"` (PyTorch's Apple GPU
backend) instead of MLX. Open-vocabulary text-prompting is fully intact —
`engine/prompts.txt` still drives `model.set_classes()` — only the runtime
named in the plan changed.
**What specifically decided it (not "MLX didn't work" — the actual finding):**
Checked directly, not assumed: `mlx`/`mlx-metal` (Apple's base array
framework) installs cleanly, and so do `mlx-vlm` (vision-language models)
and `mlx-image` (classification) — but no PyPI package implements an
open-vocabulary *object detector* on MLX. `uv pip install --dry-run` on
`ultralytics-mlx`, `yoloe-mlx`, and `mlx-yolo` all came back "not found in
the package registry." YOLOE's actual architecture-critical piece — a
CLIP-style text-prompt encoder head fused with a YOLO detection head — has
no existing MLX port to convert *from*; building one from raw MLX ops
would mean re-implementing that fusion from a paper, not converting a
checkpoint, which is a multi-day project on its own. That's a different
and harder problem than "the conversion is fighting me," which is the
scenario the plan's mid-afternoon-timebox was written for. There was
nothing to spend the afternoon fighting — the gap was structural, found in
under an hour of dependency probing, before any conversion was attempted.
**A real cost paid for this choice, found while integrating:** the
TorchScript-serialized MobileCLIP text encoder YOLOE downloads
(`mobileclip_blt.ts`, ~570MB) fails to load under `map_location="mps"` —
`torch.jit.load` raises `TypeError: Cannot convert a MPS Tensor to float64
dtype` — because MPS doesn't support float64 and the checkpoint carries
some in float64. `engine/detector.py`'s `set_prompts()` works around this
by running text-prompt embedding on CPU (a one-off cost per prompt-list
change, not per-frame) and moving only the image model back to MPS for the
per-frame forward pass. This is a second, smaller instance of the same
category of finding as the MLX gap: Apple's ML runtimes have real, checkable
holes, not universal support — worth stating plainly rather than glossing
over now that it's fixed.
**Measured, not borrowed:** unthrottled inference on this machine (M-series,
640×480 input, warm model) is ~76 FPS (mean 13.1ms/frame, p50 12.8ms, p95
16.3ms) — see day8-results.md. This is lower than
`v2-architecture-research.md`'s borrowed 124.9 FPS figure, which was never
measured against this model variant, input size, or machine; the borrowed
number is now superseded by a real one, not confirmed by it.
**New dependencies (house rule: justify each):** `ultralytics` (YOLOE
model + inference, native MPS device support, no MLX equivalent exists —
see above), `supervision` (ByteTrack implementation — see D31),
`git+https://github.com/ultralytics/CLIP.git` (Ultralytics' own CLIP fork,
a hard runtime requirement of YOLOE's text-prompt path — `ultralytics`
attempts to auto-install it via `pip`, which isn't on this project's PATH
since `uv` manages the venv, so it had to be added explicitly).
**Cost:** ~1.5GB across the model weights and the MobileCLIP text encoder,
cached at `~/.cache/yap-engine/weights` — outside the repo, on purpose (see
the boundary in day8-prompt.md and `engine/README.md`'s Weights section).
First run on a fresh machine pays a one-time ~600MB download.
**Revisit if:** an MLX-native open-vocabulary detector ships on PyPI later
(worth a periodic check — this gap may close), or if PyTorch/MPS proves
insufficiently fast at higher resolutions/frame rates than 8Hz demands.

---

### D31 — Tracker: ByteTrack via `supervision`, superseding D11/D21/D27
**Decided:** Day 8
**What's shipping:** `supervision.tracker.byte_tracker.core.ByteTrack`
(imported directly rather than via `supervision`'s top-level `ByteTrack`
alias, which is soft-deprecated as of `supervision==0.30.0` in favor of a
replacement class not yet published — the underlying implementation is the
same code either name points at; revisit when the replacement ships).
`supervision` was chosen over pulling ByteTrack out of `ultralytics`
directly because it's detector-agnostic — it takes plain boxes/scores, not
a specific model's output format, which keeps `engine/tracker.py` decoupled
from `detector.py`'s internals the way `capture.py`/`motion.py` are
decoupled from each other.
**Why D11, D21, and D27 are superseded, and why each was still right for
what it fixed:**
- **D11** (IoU tracker: same-label matching, α=0.4 smoothing, missed-frame
  grace) was the only option available with no re-ID model and a 30-line
  budget — it kept boxes from jittering frame to frame on a fixed-class
  detector. ByteTrack does the same job with a real motion model (Kalman
  filter) and confidence-tiered association, which is strictly more robust,
  but D11 was the correct call for what existed on Day 3.
- **D21** (per-track label voting + cross-label match gate, fixing the
  bed/dining-table flicker) existed because `lite_mobilenet_v2` itself
  flickered between two plausible labels for the same physical object —
  that's a *detector* problem, not a tracker problem, and D30 fixes it at
  the root: an open-vocabulary model doesn't have two fixed, competing
  COCO classes to flicker between in the first place. `tracker.py` keeps a
  lightweight version of the same idea (`labelConfidence`, `runnerUpLabel`,
  a short vote window) because `src/vision/types.ts`'s `Track` shape
  expects it and an open-vocab model can still occasionally waver between
  two prompt words — but the window is short (15 frames, vs D21's tuning
  for a noisier signal) since it's now smoothing a rare wobble, not
  compensating for a structurally confused model.
- **D27** (two-pass same-label-first matching, fixing a dominant track
  stealing a neighbor's detection) was a hand-rolled fix for the hand-rolled
  tracker's greedy matching order. ByteTrack's association algorithm
  (IoU + confidence tiers, not greedy nearest-first) doesn't have this
  failure mode by construction — there's no matching-order bug to patch
  around, so there's nothing to port.
**UNIDENTIFIED discipline survives (D22):** `detector.py`'s
`UNCERTAIN_CONFIDENCE = 0.6` floor is applied per-detection before the
tracker ever sees a label — an open-vocab model can still be confidently
wrong about an unfamiliar object, so the floor stays regardless of which
tracker sits downstream.
**Cost:** one dependency (`supervision`, ~15 transitive packages, mostly
already pulled in by `ultralytics`/`torch`). No GPU cost — ByteTrack runs
on CPU, box coordinates only.
**Revisit if:** `supervision` ships its ByteTrack replacement class before
v0.31.0 removes the deprecated alias — swap the import, no behavior change
expected. Also revisit if re-ID (appearance embedding, not just motion)
becomes necessary — BoT-SORT was the plan's other named option and adds
that; ByteTrack was preferred here because it shipped in the
detector-agnostic package already in use and D31's failure modes (D11/D27)
don't require appearance matching to fix.

---

### D32 — `MOTION_THRESHOLD` stays at 4.0 — real-scene tuning deferred, not skipped
**Decided:** Day 8
**What the plan asked for:** tune `MOTION_THRESHOLD` (`engine/motion.py`,
untuned first guess since Day 7) against a real or staged intermittent-
motion clip (enter → hold still 20s → move again), and write down the
chosen value and what it was tuned on.
**What happened:** this session has no camera access (sandboxed, no
display/hardware), so the intermittent-motion test ran against a *staged
synthetic* clip (`engine/capture.py`'s `make_intermittent_synthetic_frame`,
`--synthetic-intermittent`) — a large high-contrast bar that enters for 3s,
freezes pixel-identical for 20s, then moves again — not the real room
footage the plan asked for. Against that clip, at the existing threshold of
4.0: gate closed correctly and immediately during the frozen phase (raw
mean-diff reads exactly 0.0, ~24x below threshold), and reopened within one
frame of motion resuming. There was no evidence in this run that 4.0 is
wrong — but there's also no real-scene evidence that it's *right*, since a
synthetic high-contrast bar and a real room's lighting/noise/shadow-motion
profile are not the same distribution. Tuning a number against a clip that
doesn't represent the real failure mode (sensor noise, small far-away
motion, lighting flicker) would be tuning by feel with extra steps.
**Decision:** leave `MOTION_THRESHOLD` at 4.0. This is explicitly not the
same as "tuned" — it's the same untuned first guess from Day 7, now with
one piece of new evidence (the gate's open/close *logic* is correct) but
still no real-scene calibration. Recorded here as unfinished, not silently
carried forward.
**Revisit:** first session with camera access — record a real enter/hold-
still-20s/move-again clip, replay `engine/motion.py`'s two functions
against it exactly as `day8-prompt.md` originally specified, and only then
change the constant, with the clip and the number written down together.

---

### D33 — T2's on-demand detector will be Grounding DINO, not a bigger T1 model
**Decided:** Day 8, post-ship, after real-camera testing exposed small/worn-
object misses (spectacles, a held phone) that YOLOE's small variant
(D30, `yoloe-11s-seg.pt`, chosen for 8Hz) structurally can't fix without
giving up the framerate T1 exists for.
**The reframe:** the question raised wasn't "is YOLOE good enough," it was
answered wrong the first time by treating T1 and T2 as one detector choice.
They're not — `v2-roadmap.md`'s tier scheduler already split them by
latency budget: T1 (`engine/detector.py`, this file's D30) runs constantly
at 8Hz and has to stay cheap; T2 (`engine/tiers.py`'s `deep_look` stub,
Day 13) and T3 (`respond` stub, Day 10) run once, on demand, when a human
is already waiting for an answer — the "JARVIS, what am I looking at?"
query path can afford 300ms+ that ambient sensing cannot.
**Decision:** T2/T3's query-time detection pass uses **Grounding DINO**,
not YOLOE at a larger size. Zero-shot open-vocab AP on COCO: ~52.5%
(Grounding DINO) vs the YOLO-World-family's ~35%, with the larger gap
specifically on small/worn objects (mean IoU 0.629 vs 0.408 in third-party
benchmarks) — exactly the spectacles/phone failure mode. T1 keeps YOLOE
unchanged; nothing about D30 is reopened.
**Why not just size up YOLOE/YOLO-World instead:** same architecture
family (CNN, single-stage, speed-over-accuracy by design) — a larger
variant buys some accuracy but doesn't close the small-object gap the way
a transformer-based detector (Grounding DINO, DINO-DETR) does; the
benchmark gap is architectural, not a parameter-count problem.
**Why not RF-DETR:** current SOTA on COCO (60+ mAP) but a fine-tuned
specialist architecture — needs training data per class, not a zero-shot
text-prompt path. Wrong fit for "ask about anything in the room" with no
training set. Revisit once there's a corpus of the project's own footage
worth fine-tuning against — real future upgrade for T2 accuracy, not a
Day 8/10/13 blocker.
**Where this connects to Day 14's private-server split:** Grounding DINO's
per-query cost (~300ms+ on a capable GPU, worse on this Mac's MPS) is the
concrete reason Day 14's "server runs T2/T3 on demand" design exists —
this decision is what that server will actually run. A dedicated GPU
(Jetson AGX Orin over an eGPU — Mac has no real CUDA/eGPU path, Jetson has
full CUDA+TensorRT and is the standard 2026 edge-AI target) executes that
phase early; it is not a scope change to the roadmap.
**Not implemented yet, and deliberately not today:** `tiers.py`'s
`deep_look`/`respond` stay empty stubs. Wiring Grounding DINO in now would
front-run Day 10 (T3, the query loop itself doesn't exist yet) and Day 13
(T2, depth/seg/pose come first in priority order) — `v2-roadmap.md`'s own
rule against silently merging days applies here. This entry exists so the
choice is made and written down before it blocks either day, same pattern
as D28/D29.
**Cost:** a second model (~a few hundred MB–1GB+ depending on Grounding
DINO variant) loaded only when T2/T3 actually fire, not at startup or on
the hot path — no cost to T1's 8Hz budget.
**Revisit if:** Day 10/13 implementation finds Grounding DINO's real
on-device latency (once measured, not benchmarked-elsewhere) unworkable
even for on-demand use, or the Jetson purchase lands and changes what's
affordable to run per query.
