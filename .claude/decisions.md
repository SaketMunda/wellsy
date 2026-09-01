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
**Cost:** Up to ~1s of latency before WELLSY comments on something new. Correct
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
unlike the LLM loader's hard WebGPU gate (D13, `wellsyUnavailable` on no
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
against "wellsy"/"hey wellsy") is explicitly the stretch item per the day's own
brief and was not attempted — push-to-talk is a complete feature on its
own, not a broken one. Because only push-to-talk shipped, the
self-hearing gate ("don't let WELLSY's own voice trigger the mic") was not
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
cached at `~/.cache/wellsy/weights` — outside the repo, on purpose (see
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

---

### D34 — `MOTION_THRESHOLD` tuned against real footage, 4.0 → 5.0 (retires D32)
**Decided:** Day 9, corrected mid-session
**A mistake, recorded honestly:** the first pass of this entry claimed "no
camera access this session," copied from Day 7/8's genuinely-true finding
without re-testing it in this session. That was wrong — `cv2.VideoCapture(0,
cv2.CAP_AVFOUNDATION)` opened the real camera and read real frames the
moment it was actually tried. Caught after the user pushed back on it. The
rest of this entry is the real, corrected work done afterward.
**What was measured:** two real clips (`engine/clips/`, real camera, this
machine's room). A 25s passive/ambient sample (nothing deliberately moved):
raw mean-diff (0–255 scale) min=0.973, p50=1.268, p95=2.951, **max=4.220**,
mean=1.472 — at the old threshold (4.0), pure sensor/lighting noise alone
crossed the gate on 0.7% of frames. A 20s sample with real movement in
frame: min=0.940, p50=1.045, p95=2.484, **max=6.195**, mean=1.345 — mostly
ambient, with one real motion spike clearing 6. (The first clip file was
overwritten by a path bug in the one-off recording script before it could
be committed; the printed distribution from both runs is preserved here and
in `day9-results.md`, which is the real evidence this decision rests on.)
**Decision: `MOTION_THRESHOLD` 4.0 → 5.0** (`engine/motion.py`). 5.0 sits
above the measured real noise ceiling (4.22) with margin, comfortably below
the one measured real motion sample (6.195). This is a real number from
real footage — not synthetic, not carried forward untouched a third time.
**Honest caveat, stated the same way D11/D15/D21's first-guess constants
were:** one real motion sample is a point, not a distribution — the
noise-floor evidence here is stronger than the motion-side evidence.
**Revisit if:** real use shows false-opens from ambient noise/lighting
flicker even at 5.0, or shows real motion failing to open the gate — either
direction is real signal this number should move on, not evidence the
tuning method was wrong.

---

### D35 — Day 9 bridge: `websockets` sync server, thread-per-server not asyncio, throttled to 8Hz independent of capture rate, camera architecture (A) confirmed
**Decided:** Day 9
**Transport:** `engine/bridge.py` runs `websockets.sync.server.serve` in a
background thread, bound to `127.0.0.1` only (checked with `lsof`, not
assumed — a client `connect()` to `0.0.0.0` "succeeding" is a macOS loopback
quirk on the *client* side, not evidence the server bound wide). Chosen over
rewriting `main.py`'s frame loop onto asyncio because the loop is already a
working synchronous design (D29) and there was no reason to touch it just to
add a socket — the sync API lets the WebSocket server exist as a bolt-on
thread instead of a rewrite.
**Camera ownership: architecture (A), verified, not assumed.**
day9-prompt.md asked for a first-ten-minutes check of whether this machine
allows the browser and Python to hold the camera simultaneously — an
earlier pass of this entry wrongly reported that check as blocked (see
D34's correction note; same mistake, same fix). Actually run: two
independent `cv2.VideoCapture` readers opened the same camera index at
once and both read real frames, and separately, headless Chrome holding a
live `getUserMedia` stream (`readyState: 'live'`) while a Python process
read 196 real frames over an overlapping window
(`scripts/camera-dual-test.mjs`). Both halves of the real question —
Python-vs-Python and browser-vs-Python — checked directly. (A) is real and
confirmed on this machine, not a default taken on faith. If a future
session on different hardware finds macOS refuses simultaneous access, the
fallback is (B): Python ships JPEG/H.264 frames over the same socket and
owns the only camera read, at the cost of an encode on the hot path and the
CPU number the episode depends on.
**Coordinate contract:** the bridge payload carries `sourceWidth`/
`sourceHeight` (the engine's own capture resolution) alongside every
frame's tracks/detections; `useEngineSocket.ts` rescales every bbox into the
*displayed* video element's resolution (`video.videoWidth`/`videoHeight`) on
receipt. A resolution mismatch between the two independent camera readers —
expected under (A), by construction — is absorbed here rather than becoming
a coordinate bug. Mirroring needed no new logic: the engine's OpenCV capture
is unmirrored, matching the same "raw video-pixel-space" convention the
browser's own TF.js detections have always used (D5) — `drawHud.ts`'s
existing `mirrored: true` flip (built for the browser's own CSS-mirrored
`<video>`) applies to engine-sourced boxes unchanged, no new mirroring code
anywhere.
**Push rate: throttled to `DETECT_HZ` (8Hz), independent of capture rate —
found broken, then fixed.** The first version broadcast once per captured
frame, which is fine when detection is on (already gated near 8Hz by
`main.py`'s existing `DETECT_INTERVAL_S` check) but was measured at
~26–30Hz with `--no-detect` on, since that flag bypasses the detection
cadence gate entirely and stdout's own `emit()` has always fired every
captured frame (Day 7/8 behavior, unchanged). day9-prompt.md is explicit
the bridge should push at "detection rate, not frame rate" — added a
second, bridge-only throttle (`last_broadcast_time`) so the WS cadence is
correct regardless of whether T1 detection is on, off, or bypassed by a
flag. stdout's `emit()` itself is untouched, still per-capture-frame, so it
stays byte-compatible with Day 8 (day9-prompt.md's own verification rule).
**Latest-wins crossing the socket (D29's rule, third layer now — queue,
then process boundary, now a WebSocket):** `useEngineSocket.ts`'s
`onmessage` unconditionally overwrites `frameRef.current`. No queue, no
array — the browser's own event loop delivers one message at a time and
each one fully replaces the last. This required no additional buffering
logic to get right; it falls out of a ref-write handler by construction, the
same way `frameRef` has worked since Day 1 (D3).
**Staleness: a disconnect after being live degrades to `stale`, not
`error`.** The first version's `ws.onclose` jumped straight to `error` on
any close, which meant killing the engine never surfaced the staleness
banner day9-prompt.md asked for — caught live by
`scripts/day9-bridge-test.mjs` (`staleVisible: false` on the first run),
not assumed correct from the code. Fixed with an `everReady` flag: a close
before the socket was ever `ready` is a real connection failure (`error`,
the existing curtain-error UI); a close *after* being ready means the
engine died mid-session, which the app treats as `stale` — the last real
frame stays on screen, honestly marked old, per the same discipline as
`UNIDENTIFIED` (D22). Measured: banner appeared 1005ms after a `SIGKILL`
to the engine process group — inside the ~1s target.
**A second D29-shaped process-management gotcha, found by the test
harness, not designed around in advance:** `uv run python main.py`'s
wrapper process does not exec-replace itself with the Python interpreter on
this setup — SIGKILLing the wrapper's own PID left `main.py` running,
still holding the WebSocket port. `scripts/day9-bridge-test.mjs` now spawns
the engine detached and kills the whole process group
(`process.kill(-pid, 'SIGKILL')`). Worth carrying into any future script
that drives `main.py` through `uv run` rather than the bare interpreter.
**`src/hud/` untouched — zero lines.** `hudState.ts`, `drawHud.ts`, and
`HudCanvas.tsx` needed no changes; every Day 9 change lives in
`src/App.tsx` (frame-source switching, staleness banner), `src/App.css`
(banner styling, reusing the project's existing amber token per D19), and
the new `src/vision/useEngineSocket.ts`. This is the measured version of
the seam-held thesis day9-prompt.md names — `git diff --stat -- src/hud/`
is empty, not asserted.
**Cost:** one new Python dependency, `websockets` (`engine/pyproject.toml`)
— chosen for its sync server API specifically to avoid an asyncio rewrite
of `main.py`'s loop. No new browser dependency; `WebSocket` is a native API.
**Revisit if:** a future session on different hardware finds (A) doesn't
hold (simultaneous access denied) — switch to (B) per the note above,
immediately rather than fighting it, per this project's own house rule
(D30's MLX-gap precedent). Also revisit the τ value (D15): three real burst-screenshot attempts
against the live `?engine=1` HUD (real camera, real person) found the
motion gate — even retuned to 5.0 — doesn't clear for localized desk-
distance gestures (hand to face, hand through hair), so T1 never re-ran
during any of the three windows and there was nothing fresh to interpolate
toward. Full account, including the first attempt's engine-timing miss, in
day9-results.md. τ is still unchanged at 70ms and still genuinely untested
— but the reason is now specific (need full-body motion, not a desk
gesture) rather than "no camera."

---

### D34 (amended, Day 10) — τ finally tested against real full-body motion: changed verdict, not yet a changed constant
**Decided:** Day 10, Part 0.3
**What Day 9 asked for:** stand up, step back, walk across frame while
`?engine=1`/`main.py` runs — the one condition that reliably clears the
motion gate and produces the repeated fresh T1 runs τ actually needs to be
judged against. Two earlier attempts this session recorded near-zero motion
(camera pointed away from the person — a real setup mistake, not a finding,
see day10-results.md). The third attempt, with the person actually in
frame and genuinely walking, is the real result: **27.7% of frames cleared
the gate** (vs. Day 9's three desk-gesture attempts, all effectively 0%),
producing **89 real T1 detection ticks** over 20s.
**The finding:** consecutive-tick box movement (the same real detections
τ's exponential lerp has to smooth between) had **mean 55.7px, p95 252.5px,
max 707.2px**, against a **mean inter-tick gap of 225ms** (not the nominal
125ms — the gate still closes between motion bursts, one outlier gap
reached 6.8s while the walker paused). At τ=70ms, the mean-case jump is
>95% resolved before the next tick arrives (225ms is ~3.2 time constants) —
interpolation genuinely helps the common case. But the p95/max jumps
(252–707px) occur *within* a single tick interval on a fast walk, and
70ms of exponential decay cannot close a 700px gap before the next real
update lands — the box will visibly lag behind a fast-moving subject for a
real, non-trivial fraction of that gap.
**Verdict: changed, with evidence — the assumption underlying τ=70ms (tuned
against the fake-camera device's churn, D15) does not fully hold under real
fast full-body motion.** Not retuned this session: the numbers above justify
lowering τ for fast motion specifically, or adding velocity-aware
interpolation, but doing that without also re-verifying the *slow*-motion
case (where 70ms was already known to look right) risks trading one
visible artifact for another on a session that didn't have time to check
both. Flagged for Day 11+ with the real per-tick delta distribution now in
hand instead of a guess.
**Cost of the walk-test process itself, stated honestly:** two of three
attempts this session wasted a full 20s recording each because the camera
wasn't actually pointed at the person walking — not a code or hardware
problem, purely a coordination miss between the remote session and the
person physically walking. Worth naming since it's the same shape of
mistake as Day 9's first τ attempt (engine budget expired before the
burst), just a different cause.

---

### D36 — A query forces a fresh T1 look, synchronously, before `describeScene` reads anything
**Decided:** Day 10, Part 0.1 (the blocker)
**Why:** Day 9's τ investigation found the real bug that makes Day 10's
demo impossible as originally scripted: the motion gate does not open for
a seated person's localized gestures, so a person sitting still and asking
a question hits a T1 that hasn't re-run in seconds — `describeScene` would
confidently narrate a stale room. **The fix is not to retune
`MOTION_THRESHOLD`** — lowering it to catch small gestures reopens the
noise floor D34 measured and throws away the 6–13%-idle-CPU number the
project is built on. **The fix is that asking a question is itself a
reason to look**: `PreemptionSeam.request_fresh_look()` (`tiers.py`) blocks
T3's calling thread until `main.py`'s capture loop runs one synchronous,
on-demand T1 detection on the *current* frame — regardless of the gate —
and hands the result back.
**This is the tier model working exactly as designed, not a workaround:**
ambient sensing (ongoing T1 on its own 8Hz schedule, gated by T0) stays
cheap and lazy *because* the query path (T3) can pay for its own freshness
on the rare occasions it actually needs it. T0 keeps computing every frame
regardless — "do not gate the gate" — only T1's *own-schedule* detection
pauses while a query is in flight (see D37 below).
**Measured, real camera, real detector (`verify_preemption.py`,
`engine/clips/preemption-verify.jsonl`):** one forced look cost **33.4ms**
of real inference time (well inside D8/D9's ~30–45ms in-loop estimate),
delivered to the requesting thread in **71.2ms wall-clock** round trip
(includes the ~40ms polling granularity of `main.py`'s frame loop, not
just the inference itself). During the ~2s the seam stayed active
afterward (simulating TTS speaking the answer), **zero** further
`inferenceMs` values were produced — ambient sensing genuinely paused, not
just throttled. Full evidence in day10-results.md row 3/4.
**Cost:** every describe_scene/query_object answer now pays ~33–70ms it
didn't pay before, on top of STT/intent/TTS latency — reported plainly in
the table, not hidden inside a "feels instant" claim. `wake`/`sleep`/`stop`/
`help`/`unknown` intents skip this entirely (see `query_loop.py`'s
`handle_command`) since they need no scene data.
**Revisit if:** a future tier (T2 depth/segmentation, Day 13) needs the
same forced-look pattern — `PreemptionSeam` already generalizes past the
one caller Day 10 gives it.

---

### D37 — T3 lives in the engine; `parseIntent`/`describeScene` ported to Python behind one shared fixture
**Decided:** Day 10, Part 1
**Why the engine, not the browser:** audio has to be native (mic in,
speakers out), and the preemption seam and the tracks T3 needs to read are
already Python (D28's V2 pivot). Routing STT/intent/TTS through a
WebSocket round trip to the browser and back would add latency to
precisely the one path where latency is the entire point of the day.
**`engine/intent.py`** is a direct, line-for-line-equivalent port of
`src/voice/parseIntent.ts` — same regex patterns, same priority order
(`stop` checked first, `unknown` never guesses). **`engine/scene.py`**
likewise ports `describeScene`/`queryObject`, same honesty rule (an
uncertain track reports as "unidentified," never resolved to a winner).
**The drift-prevention mechanism asked for:** `spec/intent-cases.json` is
the single source of truth for every `parseIntent` test case; both
`src/voice/parseIntent.test.ts` (now just a `for` loop over the JSON) and
`engine/test_intent.py` (pytest, `@pytest.mark.parametrize` over the same
JSON) read it. All 20 cases pass in both languages — verified by actually
running both suites this session (`npm run test`, `uv run pytest`), not
assumed from the port being "obviously equivalent." `describeScene`'s
cases were ported natively into `engine/test_scene.py` instead of a shared
fixture — the brief only asked for intent cases to be shared, and
`describeScene`'s test helper (`track(...)`) is TS-shaped enough that
forcing it through JSON would cost more than it prevents.
**The TS originals are frozen as legacy**, per the day's own instruction —
they keep working for browser-only mode (`src/voice/`, `src/narration/`
untouched otherwise) but are no longer where new intent/scene logic gets
written.
**Cost:** two implementations of the same logic to keep in sync by hand
for anything that isn't a case in the shared spec (e.g. a new regex
pattern needs editing in both `parseIntent.ts` and `intent.py`) — accepted,
since the alternative (one canonical implementation called over a socket)
was ruled out for the latency reason above.
**Revisit if:** the two implementations are ever caught disagreeing on a
transcript *not* in `spec/intent-cases.json` — add it as a new case
immediately rather than patching one side.

---

### D38 — Silence is the default: ambient narration is now an explicit opt-in, not the product's baseline
**Decided:** Day 10, Part 2
**Why, stated as a product decision and not a config change:** Days 1–6
built a system that narrates constantly, on the theory that a HUD should
always be talking about what it sees. Six days of that work is what
*taught* the project the opposite lesson — `day7-baseline.md`'s CPU-floor
finding (D28) and the τ/motion-gate investigation both point at the same
root cause: doing maximum work, including maximum *talking*, whether or
not anyone needs the answer. Day 10 flips the default: **WELLSY speaks in
exactly three cases — asked (T3), a rule fires (not built), or ambient mode
is explicitly on** (`query_loop.py`'s `ambient_enabled`, `False` by
default, set `True` only by the `wake` intent — mirroring the browser
build's original D6/D26 wake/sleep semantics, now scoped to a mode instead
of the entire narrator).
**`engine/ambient.py`** is the new engine-side ambient narrator, and it is
deliberately the smallest thing that could satisfy "ambient mode, when on,
still narrates something real": track-id-diffing appear/disappear lines,
rate-limited to one per 4s, gated on `ambient_enabled` and on the
preemption seam being idle (ambient stays quiet while T3 has the floor).
It is **not** a port of `events.ts`/`generateLine.ts`/`templates.ts`'s
authored joke-line bank or salience ranking — out of scope for a day whose
point is that this mode is off, not that it's eloquent. The bridge's
broadcast payload now carries `ambientEnabled` so the HUD can show whether
WELLSY could currently speak unprompted; **the actual browser-side visual
indicator was cut for time this session** — see "what was cut" in
day10-results.md.
**Cost:** the honest one — six days of narration-engine work (D6, D12, D13,
D21, D22's templates/events/LLM-line machinery) becomes a mode nobody turns
on by default. That's not a regression; it's what "on-demand" actually
costs, stated plainly rather than buried in a config default.

---

### D39 — Wake phrases: transcribe-then-match, not a trained keyword spotter; real numbers, real collision found live
**Decided:** Day 10, Part 3
**How it's built:** `query_loop.py`'s `_wake_thread` keeps a rolling
~1.5s audio window (VAD-gated — never runs STT on silence, the audio-side
mirror of `motion.py`'s vision-side T0), transcribes it with the same
`Stt` instance T3 uses for commands, and fuzzy-matches (`difflib`,
word-window sliding, threshold 0.72) against `engine/wake_phrases.txt` —
hot-reloaded on mtime change, same pattern as `prompts.txt`. **This is not
a trained keyword spotter and the report says so on camera**; a real one
(openWakeWord) would need synthetic-speech data generation plus a training
run for a custom phrase like "Wellsy" — hours, not this session's budget —
and stays the documented upgrade path.
**VAD is an energy gate, not Silero.** `webrtcvad` (the other "small, CPU"
option named in the brief) is unmaintained and its wheel imports
`pkg_resources`, which current `setuptools` no longer ships on Python
3.13 — confirmed broken in this environment before being ruled out, not
assumed. `engine/vad.py`'s adaptive-noise-floor RMS gate is the same
*shape* of solution as `motion.py` (a cheap statistic against a floor, no
model, no extra weights) and needed no network fetch.
**TTS deviates from the brief's Kokoro/Piper suggestion — macOS `say`,
documented in `engine/tts.py`'s own module docstring.** Day 10's hardest,
most-overdue requirement was "audio confirmed audible on real speakers by
a human" (open since Day 1/D13). `say` cannot fail to produce audio the
way a freshly-wired ONNX/PyTorch TTS stack still might — and **that risk
is not hypothetical**: D13's own Kokoro-in-the-browser saga is exactly this
kind of stack failing to ship working audio for an entire session. `say`
also made "stop interrupts mid-word" trivial (SIGTERM on the subprocess).
Piper (`pip install piper-tts`, real local neural voices) is the named
upgrade path once voice quality matters more than the audibility gap it
closed today.
**Confirmed audible, by a human, for real** (day10-prompt.md's nine-day-old
open item): `say -v Samantha` played through the room's default output
(an HT-S20R soundbar, found powered off on the first attempt — a real,
if mundane, part of the verification) and was confirmed heard on retry.
This is the first time in the project's history this has been checked by
a person listening rather than an exit code.
**A real, live collision found and not tuned around:** during a live test
session, the original wake word was repeatedly transcribed as "app"/"App." —
Moonshine heard it as the much more common word "app." One full success
was also captured live: wake match on "hey yo" (0.77 ratio) correctly
triggered a real query — `"What do you see?" -> describe_scene -> "two
things: a person and a glasses."` in **119.1ms** end to end. The
original-wake-word / "app" collision is a genuine finding, not a tuning failure — a
short, low-information-content syllable colliding with a common English
word is exactly the failure mode this file's own header warns bare "yo"
would have, discovered for the original wake word instead. **Decision: keep "hey wellsy" /
"wellsy" / "hey yo" as the current default phrase list** (they still work —
"hey yo" succeeded live) **but flag the collision plainly and carry a
wake-word rename as open, owner's call, for Day 11.** `wake_phrases.txt`
being hot-reloadable, one-line-per-phrase means whatever replacement is
chosen costs one line to ship, not a code change.
**Bare "yo" ships behind `--enable-yo`, off by default** — see
`wake_phrases.txt`'s header for the phonetic-collision reasoning
(`day10-prompt.md`'s own argument, unchanged): a ~150ms single syllable
inside "you"/"your"/"yeah"/"YouTube" can't be made both sensitive and
precise. Not measured against the full 10-minute/20-utterance acceptance
bar this session — see day10-results.md for what was and wasn't run to
that bar, and why.
**The feedback trap (day10-prompt.md Part 3):** wake matching is
suppressed while `QueryLoop._speaking()` is true (WELLSY can't wake itself up
hearing its own voice), but this only gates the wake-listener thread —
push-to-talk (`_ptt_thread`) is a separate thread reading stdin and is
never gated by TTS playback, so "stop" always works mid-word by design,
not by accident.

---

### D39 (amended) — Three real bugs found from live usage, immediately post-ship
**Decided:** Day 10, same session, after the project owner tried it live
and reported it back as genuinely not good enough — correctly.
**Bug 1, the big one: `_wake_thread` was transcribing on every ~30ms
VAD-positive frame, not once per phrase.** While someone spoke even a
short sentence, that's dozens of overlapping `moonshine.transcribe()`
calls fighting the detector for CPU on every frame — not a tuning issue,
a straightforward logic bug (there was no debounce at all). This is the
actual root cause of "it responded so late the frame had changed": the
STT thread was busy re-transcribing itself throughout the entire time
someone was talking, not waiting on them once. **Fixed:** transcription
now only fires on a phrase boundary (continuous speech, then
`WAKE_PHRASE_PAUSE_SECONDS` of quiet) plus a hard
`WAKE_TRANSCRIBE_COOLDOWN_SECONDS` backstop — one transcribe call per
utterance, not per frame.
**Bug 2, a likely contributor to bug 3: two simultaneous `sd.InputStream`s
on the same input device.** The post-wake command recording
(`_record_utterance`) opened its *own* `InputStream` while the wake
thread's own `InputStream` (the one that had just detected the wake
phrase) was still open around it — nested, nested, on the same default
device. `_record_utterance` now accepts an already-open `stream` and reads
from it directly for both the post-wake and in-conversation paths, so
exactly one stream is open at a time for those call sites. (Push-to-talk's
`_record_utterance()` still opens its own — it always runs concurrently
with the wake thread's stream regardless, and narrowing that down wasn't
this session's priority.)
**Bug 3 (really a symptom of bugs 1/2, not separately fixed): "do you see
a cellphone" got answered as if `describe_scene` had been asked.** Given
bug 1's overlapping transcribe calls and bug 2's stream contention, a real
question getting mangled into something that pattern-matches as
`describe_scene` instead of `query_object` is exactly what garbled,
partial STT output produces — `parseIntent` did its job correctly on
whatever text it was actually given; the text itself was the problem.
Also switched the STT model default from `moonshine/tiny` to
`moonshine/base` (`engine/stt.py`) for real accuracy headroom — `tiny`
consistently misheard the original wake word as "app" and is simply too small a model for
full sentences, not just short wake phrases.
**Missing feature, not a bug, also raised live: no "stay awake" window.**
Every question required repeating "hey wellsy." Added
`QueryLoop.in_conversation` (a rolling `CONVERSATION_WINDOW_SECONDS = 10s`
deadline, extended after every handled command except `stop`/`sleep`) —
while active, the wake thread skips the wake-phrase match entirely and
records a follow-up the moment speech starts, using
`_record_utterance`'s own proper silence-tail logic rather than the fixed
1.5s wake-detection window (a real question can run longer than that).
**None of these three fixes were verified against real human speech by
this agent** — the same mic-permission-per-process constraint from
Part 0.2 still applies (this session's own process can't get clean mic
audio; every real test has to run from Terminal.app). Verification is a
live retest, not a claim made from code review alone.
**Revisit if:** the fixes don't hold up under a real retest — if
transcription is still slow/garbled, the next suspect is
`WAKE_TRANSCRIBE_COOLDOWN_SECONDS`/`WAKE_PHRASE_PAUSE_SECONDS` (both
first-guess constants, same caveat as every other timing constant in this
project) or the `base` model still not being accurate enough, in which
case `moonshine/small` (if Moonshine ships one) or a non-Moonshine STT
becomes the next thing to try.

**Bug 4, found from a crash report, not a description: `--t3` could
SIGSEGV at shutdown.** A `--synthetic --t3` diagnostic run this session
crashed with `EXC_BAD_ACCESS` inside `cffi`'s `ffi_call_SYSV`, on a thread
whose stack showed a PortAudio-style real-time audio callback. Cause: the
wake-listener thread held an open `sd.InputStream` and was a daemon
thread — at process shutdown, Python kills daemon threads abruptly rather
than letting them exit cleanly, so if `Py_Finalize` starts freeing Python
objects while CoreAudio's callback thread is still mid-callback into one
of them, that's a use-after-free, not a catchable Python exception.
**Fixed:** the wake thread is no longer daemon; `QueryLoop.stop()` now
joins it (3s timeout) so the process waits for its
`with sd.InputStream(...)` block to actually exit and close the stream
before the interpreter is allowed to proceed toward finalization.
Push-to-talk's thread stays daemon (it blocks on `sys.stdin.readline()`,
which can't be interrupted from another thread the way a frame-at-a-time
read loop can) — this narrows the crash window to push-to-talk's brief
active-recording periods rather than eliminating it, an honest remaining
gap rather than a claimed-complete fix. Verified: a `--synthetic --t3`
run through its full `--seconds` lifecycle now exits cleanly (exit code
0, no crash) — not yet re-verified against a real, longer, real-camera
`--t3` session.

**Retest result (real mic, real speech, Terminal.app):** all four fixes
held up. `wakeToAnswerMs`/`followUpMs` dropped from the pre-fix 2500ms+ to
68-145ms once past the initial recording wait; "hey yo, what do you see"
correctly found the cell phone once it entered frame
(`'five things: a person, a cell phone, a chair, a glasses, and a bed.'`,
92.4ms); the conversation window worked (multiple follow-ups answered with
no repeated wake phrase); no crash on Ctrl+C. New gap found in the same
retest: "are you there?" and "thanks" — real conversational phrases, not
in `parse_intent`'s grammar — both fell to `unknown` ("i didn't understand
that"), which reads as broken rather than as a deliberately narrow
grammar. See D40.

### D40 — Real local LLM in the engine, native (MLX), as the fallback for whatever `parse_intent` calls `unknown`

**The question that forced this:** after the D39-amendment retest, the
user asked directly why the engine was still hand-writing regex for every
new conversational phrase ("are you there", "thanks") one at a time,
pointing out this project already has a local LLM (D13: Qwen2.5-0.5B via
WebLLM) and asking why it wasn't handling this. Fair question — the
honest answer is that D13's LLM only ever existed in the **browser**
(WebGPU), and D37 moved T3 into the **Python engine**, a separate process
with no WebGPU. The engine had zero LLM. Every `unknown` was a hardcoded
dead end, not a scoped decision to stay dumb forever.

**What did NOT change:** `parse_intent`'s deterministic grammar
(`stop`/`wake`/`sleep`/`describe_scene`/`query_object`/`help`, plus this
session's new `presence`/`thanks` patterns) still owns every
safety/reliability-critical command with zero model in the loop — D6/D25's
original reasoning stands unchanged: "stop" not actually stopping is a
correctness bug an LLM must never be allowed to introduce.

**What's new:** `engine/llm.py` wraps `mlx-lm` (Apple's native MLX
framework — Metal-accelerated, no browser, no Docker, the correct fit for
running natively on this M4 Pro) loading
`mlx-community/Qwen2.5-0.5B-Instruct-4bit` — same model family and size
D13 already vetted for tone/safety, different runtime. Wired into
`QueryLoop.handle_command`'s `unknown` branch only: whatever
`parse_intent` doesn't recognize now gets a real generated reply instead
of a canned "i didn't understand that" (which still exists as the
fallback if `llm=None`, e.g. running without `--t3`'s full setup).

**Real measured numbers, this session, this machine (no cloud, nothing
estimated):**
- Cold load (`mlx_lm.load`, model already cached locally): **3074.2ms**
- Per-query, warm, via `Llm.respond()` directly: 196.8ms, 153.2ms, 153.5ms
  across three different questions — one outlier at 1436.2ms on the very
  first call after load (plausibly first-call Metal kernel compilation;
  not re-measured in isolation this session)
- Same three calls routed through `QueryLoop.handle_command`'s `unknown`
  branch (includes `parse_intent` + `_speak` dispatch overhead, not just
  raw generation): 262.0ms and 263.8ms — consistent with the warm
  standalone numbers, confirming the wiring adds negligible overhead
- Sample real answers: `"what should I have for lunch?"` →
  *"I'm sorry, I don't have a meal plan or specific dietary requirements.
  My camera feed can tell you what I'm wearing today."*; `"random
  open-ended chatter"` → *"I'm here to listen, but I don't have the
  ability to provide commentary on live streams."* — on-persona, not
  hallucinating a command, exactly the intended behavior

**Not yet done, an honest gap:** this was verified with a fake STT
(canned transcripts fed directly to `handle_command`), not a real spoken
question through the full wake-thread → STT → LLM → TTS path — that
retest is still owed, same as every other audio-path claim in this
project, because this agent's own process cannot get real mic audio
(Part 0.2's permission-scoping finding, unchanged). The 0.5B model is
also the *smallest* Qwen2.5 instruct size, same house rule as D13/stt.py's
model picks — if answers come back too generic or occasionally off-tone
in real use, `Qwen2.5-1.5B-Instruct-4bit` is the documented next step up,
not a redesign.

**Cost:** a new dependency (`mlx-lm`, pulled into `engine/pyproject.toml`)
and a new model download (~300-400MB, cached under the same
`~/.cache/wellsy/weights` exception as STT/detector weights via
`HF_HOME`) — the first real new weights added since D30's cache boundary
was drawn, justified the same way D30 always allowed: a new capability,
not scope creep.

**Amendment — real retest found the LLM was ungrounded, fixed same
session:** first real-speech retest (Terminal.app, real mic) confirmed no
crash and the wake/conversation/routing fixes from the D39 amendment all
held. But "can you describe the room?" got answered with fluent, entirely
invented decor — *"a cozy and comfortable place with a modern and stylish
decor... walls adorned with artwork"* — none of it real; the actual scene
moments earlier was a person, cell phone, chair, glasses, bed.
Root cause: `Llm.respond()` never received `tracks` — nothing grounded
it in what the detector actually sees, so any scene-shaped question got a
plausible hallucination instead. A related, not-yet-fixed gap the same
retest surfaced: zero conversation memory (each call is a stateless
single turn), so a follow-up reacting to a previous answer got a confused
non-sequitur back.

**Fixed the grounding gap:** `handle_command`'s `unknown` branch now runs
the same forced-fresh-look (`preemption.request()` /
`request_fresh_look()`) describe_scene/query_object already use, builds a
`describe_scene(tracks)` string, and passes it into `Llm.respond(transcript,
scene=...)` as system context — "unknown" gets the same freshness
guarantee as an explicit command, not a stale or absent one.
`SYSTEM_PROMPT` also now tells the model plainly it has no memory of
earlier turns, so it says so instead of guessing at follow-ups
(the memory gap itself is NOT fixed — a real fix needs turn history
passed into every call, not attempted this session).

**Verified (synthetic tracks, not yet real camera + real speech):** same
transcript "can you describe the room?" against fake `[person, chair,
bed]` tracks now answers *"The room appears to be a small, cozy space
with a person sitting on a chair and a bed."* — grounded, matches the fed
tracks, `freshLookMs` ~10ms (negligible added cost). Not yet re-verified
against a real camera + real spoken question — same owed retest as
everything else audio-path in this project.

**Second amendment — grounding fixed wrong objects, not invented details,
found on the very next real retest:** "Hey Wellsy, describe the room" (real
mic, real camera) correctly named the real objects but added
*"a person standing by it"* — the user was sitting. Root cause: `tracks`
carries labels/counts only, never posture/action/color/decor — there is
no pose signal anywhere in this pipeline (YOLOE gives boxes + labels,
nothing else). The LLM wasn't wrong about grounding, it was doing what
small instruct models do when asked to "describe": filling in plausible
flavor text beyond the facts it was actually given.

First fix attempt — a plain prose instruction added to `SYSTEM_PROMPT`
("never invent details beyond that list") — **did not work**, tested
against synthetic `[person, chair]` tracks: it kept inventing "a cozy
living room," "a book in hand," "a laptop," "a couch," "a tall armchair."
Qwen2.5-0.5B is too small to reliably obey a negative prohibition stated
as prose — a known weakness of tiny instruct models, not a prompt-wording
mistake to iterate on.

**What worked:** a single worked few-shot example in the message list
(`llm.py`'s `FEW_SHOT` — one user/assistant turn demonstrating exactly
"see these objects, say only these objects") instead of a rule. Small
models follow a demonstrated pattern far more reliably than a stated
constraint. Retested against the same synthetic `[person, chair]` tracks
across three phrasings — "describe the room" / "can you describe the
room?" / "what do you think of this room?" — all three now stay grounded
("I see a person and a chair -- that's all I can make out.", "I think
this room has a person and a chair.") with no invented furniture or
posture. A fourth, unrelated check ("tell me a joke") still comes back
weak/degenerate ("Why not tell me a joke?") — an honest remaining
limitation of a 0.5B model on genuinely open-ended non-scene chat, not
something this fix targets or claims to fix.

**Not yet done:** re-verified only against synthetic tracks, not yet a
real camera + real spoken "describe the room" asking the user to check
whether "standing" (or any other invented posture) is gone for real.

**Third amendment — the 0.5B model itself was the ceiling; swapped MLX +
Qwen2.5-0.5B for Ollama + qwen2.5:7b:** the very next real retest hit a
different, worse failure: "what am I holding?" against a scene with only
[person, chair] answered "I'm holding a person" — confidently wrong, and
not fixable by more prompt engineering, because the facts given were
already correct; the model just connected them incoherently. That's a
genuine reasoning-capacity ceiling of a 0.5B model, not a grounding gap.

User pushed back hard on relying on MLX for this, citing real prior
experience: Ollama + a 7B-class Qwen model running "almost realtime" in
another project on this same machine. Checked rather than assumed:
`ollama list` showed `qwen2.5:7b` (4.7GB) already pulled, no download
needed. User also proposed Docker — rejected and explained why, not just
overridden: Docker Desktop on macOS runs Linux containers in a VM with no
Metal/GPU passthrough (a 7B model would run on CPU-emulated Linux, not
fast) and no clean camera/mic passthrough into a container (macOS
AVFoundation/CoreAudio don't cross that boundary) — this project already
committed to no-Docker, native-only for exactly these reasons (D13).
Ollama itself is not Docker: it's a native macOS binary already using
Metal via llama.cpp, so switching to it costs nothing this project needs.

**Measured before switching (not assumed):** `qwen2.5:7b` via Ollama's
local HTTP API, default temperature, answered the same "what am I
holding?" question correctly once ("The camera doesn't show you holding
anything") but wrongly on a third repeat ("You are holding a person") --
same failure mode, just less frequent (2/3 vs 0/3 for the 0.5B/MLX path).
Lowering `temperature` to 0.2 made answers consistent but consistently
*wrong* ("You are holding a camera," invented, 5/5) -- confirming
temperature alone doesn't fix grounding on this model either. Adding the
same few-shot worked-example technique that fixed the 0.5B model's decor
hallucination, combined with temperature 0.2, gave 5/5 correct, honest
answers ("I cannot see what you are holding") with no hallucination.

**Swapped:** `engine/llm.py` now talks to a local Ollama server (`ollama
serve`, the user's existing setup, not started or managed by this
project) over stdlib `urllib` -- no new dependency for the HTTP call.
`mlx-lm` was removed from `engine/pyproject.toml` entirely (replaced, not
kept alongside). `Llm.__init__` now pings Ollama's `/api/version` and
raises immediately with a clear message if the server isn't running,
rather than failing confusingly on the first real query.
`main.py`'s setup log changed from "loading LLM..." to "checking
Ollama..." since there's no model load in this process anymore --
Ollama's own process owns that.

**Real measured latency, this session, this machine, warm (no cloud):**
388-694ms per query through the full `QueryLoop.handle_command` path
(includes `parse_intent` + fresh-look + LLM call + `_speak` dispatch) --
noticeably higher than the 0.5B/MLX path's 250-330ms, still well under a
second, judged an acceptable trade for materially more reliable
reasoning. Synthetic smoke test (fake tracks, no real camera/mic) showed
zero hallucination across "what am I holding?" / "describe the room" /
"tell me a joke" -- the joke was also qualitatively better than the
0.5B model's. **Not yet verified against real camera + real spoken
question** -- same owed retest as everything else audio-path in this
project.

**Real camera + real speech retest, done same session:** no crash,
conversation window intact, and grounded answers held for clear cases
("I see a person and a cell phone" matched real detected tracks). Four
real gaps surfaced, left open rather than chased further -- the user
explicitly asked to fine-tune "progressively," not all in one session:

1. **Latency variance:** one `llmMs` spiked to 3040ms (vs. the usual
   250-400ms), stretching that exchange's `wakeToAnswerMs` to 7211ms.
   Likely Ollama evicting the model from memory between calls and
   reloading it warm again -- a keep-alive setting is the probable fix,
   not yet investigated.
2. **Posture invention still happens outside the few-shot's exact
   shape:** "what am I doing right now?" answered "You're standing next
   to the chair" -- invented, same class of error the few-shot fixed for
   "describe the room"-shaped questions specifically. The fix does not
   generalize to every phrasing that could imply posture/action.
3. **"You're holding glasses"** -- plausibly the detector's still-unresolved
   "glasses" false-positive (see the still-outstanding `detect-log.jsonl`
   diagnostic, requested but never captured) flowing through a now-correctly-
   grounded LLM. If so, the LLM isn't at fault here -- `tracks` was.
4. **STT word-order garbling** ("What I am holding" instead of "what am I
   holding") sometimes trips the model into a harmless "I didn't catch
   that, could you repeat?" rather than answering wrong -- a softer
   failure than before, still friction, root cause is STT accuracy, not
   this session's LLM work.

**Fourth amendment — a real, serious bug: an unhandled LLM/Ollama error
could silently kill wake-word listening for the rest of the session.**
Reported live as "Hey App doesn't wake up anything, but the engine is
continuously running" -- exactly the signature of `_wake_thread` dying
silently while `capture_worker` (a separate process) kept going. Root
cause, found by inspection: `handle_command`'s `unknown`/LLM branch called
`self.preemption.request()` then `self.llm.respond(...)` with no
try/except -- any exception from that network call to Ollama (down,
timeout, malformed response) propagated straight out of `handle_command`,
uncaught, into `_wake_thread`'s loop, which also had no handler around the
call. Python threads that raise just die, silently, with no crash visible
to the rest of the process. Two failures at once: (1) the wake thread
(and push-to-talk) is gone for the rest of the run, and (2)
`self.preemption.release()` -- right after the now-skipped LLM call --
never runs, so the preemption seam stays stuck `active` forever, freezing
ambient T1 too, not just voice.

**Fixed:** the LLM call is now wrapped in `try/except/finally` --
`finally: self.preemption.release()` guarantees the seam is never stuck,
and the `except` falls back to a spoken "i had trouble reaching my
language model just now" instead of propagating. Added a second layer of
defense at all three call sites of `handle_command()` inside the
always-on threads (`_ptt_thread`, and both wake-thread call sites) --
any *other* unexpected exception now gets logged and the loop continues,
rather than the thread dying. **Verified** with a fake LLM that always
raises: `preemption.active` correctly returns to `False` (not stuck), a
spoken fallback answer is produced, and a second call right after proves
the loop is still alive and handling commands normally.

---

### D41 — Qwen3-VL replaces the label→template→LLM chain (the brain swap)

**Decided:** Day 11, per the Endgame rewrite's own naming of this as the
day's one non-negotiable ship. See `.claude/day11-results.md` for the full
numbers this rests on; this entry is the reasoning and the retire/keep
list.

**Why, structurally, not just "a bigger model":** D40's three amendments
each fixed a symptom (few-shot to stop invented decor, forced-fresh-look to
stop stale answers, temperature to reduce variance) of one root cause: the
LLM never saw a pixel. It reasoned about a word list (`describe_scene()`'s
string), so any question needing posture, held objects, printed text, or
anything outside the tracker's 80-ish-prompt vocabulary got a plausible
invention instead of an "I don't know." A model that receives the actual
frame does not have this failure mode by construction — it can only invent
*within* what it sees, not conjure detail a word list never carried.

**What D40 got right, and what Day 11 retires:** D40's forced-fresh-look
mechanism (`PreemptionSeam.request_fresh_look()`), the `try/except/finally`
exception discipline, and the whole `unknown`→LLM routing shape are all
kept, unchanged in structure — only the payload changed (an image added,
not tracks removed). What's retired: the few-shot worked example in
`llm.py` (existed only to compensate for blindness) and, functionally, the
temperature-tuning-as-primary-defense framing — `TEMPERATURE = 0.2` is
still set, but grounding no longer depends on it the way D40's third
amendment's investigation implied it might.

**Model choice, on measured latency, not the brief's first guess:**
`qwen3-vl:8b` (pulled first, per instruction) measured first-token p50
2753.3ms / p95 3048.4ms on this M4 Pro (24GB) — well outside "answerable
directly." `qwen3-vl:4b`, measured the same way (12 real streamed queries,
`day11_bench.py`, a new non-shipped harness), came in at p50 1692.5ms / p95
2282.4ms — roughly half the cost, identical correctness on every reading
test and both verbatim grounding retests run against it. **Shipped:
`qwen3-vl:4b`.** Neither model hit the brief's own "~1.5s comfortable" bar
— stated plainly rather than rounded up to a win. The mitigation is
structural (T2/T3 behind `PreemptionSeam`, the fast deterministic path
still answers `describe_scene`/`query_object` in ~17ms unchanged), not a
latency trick that made either model actually fast.

**The two Day 10 failures, retested verbatim, both resolved on real data:**
"what am I doing right now?" (was: invented "standing" for a seated user)
now answers "sitting" on both 8B and 4B. "what am I holding?" (was:
invented "holding glasses") now correctly says nothing is held, on both
models, despite `glasses` being a real, confident (1.0) tracked label in
the same frame — the exact case D40 could never resolve, because the old
chain had no way to distinguish "an object is detected somewhere in frame"
from "the user is holding it." See day11-results.md Part 5 for the full
verbatim answers and the honest caveat that this doesn't prove the failure
mode can never recur under different conditions, only that these two
specific documented failures did not reproduce.

**A new, measured limitation, not hidden:** the VLM-vs-tracks disagreement
heuristic (`provenance.py`, D43) was found this session to over-flag —
58% (11/19) on a real 20-query run — because it fires on any answer that
doesn't restate the tracked object labels, regardless of whether the
question was about object identity at all. Recorded as a real finding in
both `provenance.py`'s docstring and the results doc, not smoothed over to
make row 7 of the measurement table look cleaner.

**Cost:** `engine/llm.py`'s diff is a near-total rewrite (182 lines
changed) — the module's job changed shape, not just its prompt.
`engine/tiers.py`'s `PreemptionSeam` result tuple grew a third element
(`frame_bgr`), additive for both existing callers. `engine/query_loop.py`
gained ~140 lines: frame/screen routing, provenance logging, the same
exception shape as D40's fourth amendment, now covered by a new regression
test (`test_query_loop.py`) proving the seam is never left stuck `active`
for either of Day 11's two new failure points (VLM raising, screen capture
raising). No new pip dependency — `cv2` (already present) handles JPEG
encoding; the Ollama HTTP call is still stdlib `urllib`.

**Revisit if:** a future machine's GPU makes 8B's extra headroom worth the
2x latency cost — `MODEL_NAME` is a one-line change. Also revisit the
disagreement heuristic once a version scoped to identity-shaped questions
is built (not attempted this session, per the brief's own no-refinement
rule for carried debt).

---

### D42 — Screen capture as a second perception source, on-demand only

**Decided:** Day 11, day11-prompt.md Part 2 — the first genuinely new
input type since Day 1 (spec §23, previously at zero).

**Shipped:** `engine/screen_capture.py`, `screencapture -x` to a scratch
file inside `engine/clips/` (never `/tmp`, per the project's own boundary
rule), loaded via `cv2.imread`, scratch file deleted before the function
returns. Directly tested working in isolation: 203.9ms for a real
1920x1080 capture. Routing: `query_loop.py`'s `_wants_screen()`, a small
fixed keyword list ("my screen", "the screen", "my monitor", etc.) checked
against the transcript before deciding which frame to fetch — deliberately
**not** folded into `parse_intent.py`, which day11-prompt.md's boundary
keeps untouched for the safety-critical intents (`stop`/`wake`/`sleep`)
only. The default for an ambiguous "what's this?" is the camera — this
project's whole premise is holding something up to be seen — overridable
only by naming the screen explicitly, per the brief's own instruction to
pick a default and state it rather than build a disambiguation dialogue.

**A real environment limitation, found and reported rather than papered
over:** this session's shell runs in a sandboxed/remote context where
`screencapture -x` genuinely captures live pixels (confirmed: the captured
image's menu bar tracked real frontmost-app changes as Terminal/Preview/
TextEdit were switched via `open`/AppleScript) but no window this agent
spawns ever rendered inside the captured frame, across either of the
machine's two virtual displays — only the desktop wallpaper came back.
`osascript`'s keystroke automation is separately blocked outright. This
reads as a session/display-routing quirk of the sandbox this agent runs
in, not a bug in `screen_capture.py` — its own direct, isolated test
passed cleanly. Per the project owner's live call (asked, not guessed),
Part 3's reading tests bypass this code path and feed generated images
directly as `frame_bgr` instead — real coverage of the VLM's reading
ability, not of screen capture's pixels reaching it end-to-end. The
routing logic itself (`_wants_screen()`, fallback-to-camera on capture
failure) is covered by `test_query_loop.py` via a monkeypatched
`capture_screen`.

**Privacy, said out loud per the brief's instruction, not left as a
disclaimer:** the screen is captured only on an explicit request that
already matched a keyword before any capture call happens, the resulting
frame lives in memory for exactly the one VLM call that answers the
question, and the on-disk scratch file is deleted before the function
returns. Nothing about screen content persists beyond the provenance
line's `frameSource: "screen"` tag (D43) — no pixels, no OCR'd text, no
filename.

**Cost:** one new file, no new dependency (`cv2`, `subprocess` already
present). **Revisit if:** the sandbox's window-rendering gap is ever
resolved (or this ships from the project owner's own Terminal.app, which
Day 9/10's mic-permission precedent suggests may behave differently) — a
real end-to-end screen-capture-to-VLM test with actual on-screen content is
still owed.

---

### D43 — Provenance logging for VLM answers, extending D22's discipline

**Decided:** Day 11, day11-prompt.md Part 1.3, spec §19.

**Shipped:** `engine/provenance.py`, one JSONL line per VLM answer into
`clips/provenance.jsonl` (not a new cache location — D30's boundary is
about model weights, not per-run logs; `clips/` already holds every other
per-run artifact this project writes). Each line carries: the claim
(`answer`), the transcript, `source` (`vlm` or `vlm+tracks`), `frameSource`
(`camera`/`screen`), the tracker's labels at the time, `frameAgeMs`,
`llmMs`, and a `possibleDisagreement` heuristic flag — the same
claim→source→timestamp→confidence→freshness shape D22's `labelConfidence`/
`runnerUpLabel` discipline established for tracks, extended to the new
layer.

**The disagreement heuristic, measured rather than assumed, and found
weaker than hoped — recorded honestly:** `flag_disagreement()` checks
whether any confidently-tracked label appears as a substring of the VLM's
answer. A real 20-question run against one real frame (tracks:
`[person, glasses, blanket]`, all confidence 1.0) flagged **11/19 (58%)**,
with one Ollama timeout excluded. Reading the 11 flagged cases shows this
is a precision problem, not a recall win being undersold: "is there a
window?" → "Yes, there's a window..." gets flagged purely because the
answer doesn't restate "person"/"glasses"/"blanket", not because it
contradicts the tracker at all. The heuristic's docstring originally
(incorrectly) claimed it "under-counts more than it over-counts" — written
before this measurement existed; corrected in the same session once real
data contradicted it, per the project's own rule that a recalled or
authored claim gets checked against current evidence, not left standing
once proven wrong.

**What the heuristic is actually good for, stated precisely:** zero false
negatives against the narrow case it can detect at all (a claim that
directly contradicts a confidently-tracked label never slips through
unflagged), at the cost of a high false-positive rate on correct-but-
off-topic answers. Useful as a "worth a human glance" tripwire in the raw
JSONL, not yet precise enough to report as a real disagreement-rate metric
on its own.

**Cost:** one new file, no new dependency. Reuses `scene.py`'s
`UNCERTAIN_CONFIDENCE` constant to exclude already-hedged track labels from
the check, rather than duplicating the threshold a third time.

**Revisit if:** a version scoped to identity-shaped questions (only check
disagreement when the question is plausibly asking "what is this object"
rather than about color, position, count, lighting, etc.) is built — not
attempted this session, per the brief's own no-refinement-of-prior-day rule
applied to same-day scope creep too.

---

### D44 — Chatterbox Turbo replaces `say -v Samantha`, pulled forward from Day 14 into Day 11

**Decided:** Day 11, mid-session, on the project owner's explicit, live
direction — not planned, not a quiet scope add. D39 shipped `say -v
Samantha` deliberately as a stopgap to close the nine-day-old audibility
gap, naming the real ask (human-sounding, emotional TTS) and scoping it to
Day 14 (`v2-roadmap.md`, Chatterbox Turbo already named there). The owner
pushed back hard, live, mid-Day-11: *"I can't wait for Day 14... just get
rid of it."* This entry is that swap, done immediately, with every real
cost found and stated rather than smoothed over because the ask was urgent
and emotional.

**Model, verified current the same session, not assumed from the earlier
roadmap research:** a live web check confirmed Chatterbox Turbo
(`ResembleAI/chatterbox-turbo`, Resemble AI, MIT license, 350M params) is
real, current, and installable via `pip install chatterbox-tts` (which
ships both `chatterbox.tts` and the faster `chatterbox.tts_turbo`).

**Three real installation problems, found and fixed, not glossed over:**
1. `chatterbox-tts` hard-pins `torch==2.6.0` — a downgrade from this
   project's `torch==2.13.0`. Checked before accepting: `ultralytics` only
   requires `torch>=1.8.0`, no real conflict. **Regression-tested** after
   downgrading: YOLOE inference cost 3849.9ms on the first call (cold
   Metal kernel compile — the same phenomenon D40 already documented for
   the LLM path), then a steady 21.8-22.2ms on every call after — matches
   pre-downgrade performance.
2. Loading the model raised `TypeError: 'NoneType' object is not
   callable` on `perth.PerthImplicitWatermarker()`. Traced (not guessed):
   `perth`'s watermark submodule imports `pkg_resources`, which modern
   `setuptools` (84.x) dropped in late 2025. Fixed with `setuptools<81`,
   the last line still shipping it — chosen over disabling the
   watermarker, since keeping Resemble's own audio-provenance watermark
   active on every generated clip is the more responsible default for a
   project whose entire ethos is honesty about what's real.
3. `exaggeration`/`cfg_weight` are accepted by `.generate()` but **silently
   ignored by the Turbo checkpoint** — its own runtime warning says so.
   The emotion-control knob `v2-roadmap.md`'s Day 14 description named
   only works on the slower base `chatterbox.tts.ChatterboxTTS`, not
   Turbo. Turbo still delivers a real neural voice, not `say`'s formant
   synthesis — it fixes baseline robotic-ness, not dynamic emotional
   range. Stated plainly rather than let the "emotion control" framing
   from the roadmap stand uncorrected.

**Real measured cost, this machine, this session — the headline finding,
not hidden:**
- **Latency:** Resemble's own claim is "75ms latency, 6x real-time"
  (almost certainly CUDA-measured). On this M4 Pro's MPS backend, real
  generation for short assistant-shaped replies: `"okay."` 3167ms, `"i am
  listening."` 1652ms, `"yes, one person in view."` 2269ms, `"nothing in
  view right now."` 1852ms — real-time factor **~1.1x-3.3x**, i.e.
  generation takes about as long as, or longer than, the resulting clip,
  not 6x faster. Cold model load: 7693ms, now pre-warmed at startup
  (`main.py`) so it isn't paid on the first live utterance.
- **This directly costs Day 10's centerpiece number.** The 119.1ms
  intent-to-TTS-start measurement (D36, day10-results.md) depended on
  `say` producing audio within milliseconds of being invoked. Every
  Chatterbox utterance now has a real **1.6-3.2 second pause** before any
  sound starts, even for the deterministic fast-path answers that used to
  be instant. The fast path itself (`parse_intent` → tracks →
  `describe_scene`) is unchanged and still computes its answer in ~17ms —
  what changed is that *speaking* any answer now has a real, human-
  noticeable wait in front of it that didn't exist before.
- **Idle CPU got measurably noisier with the model resident.** `--synthetic
  --t3` (Chatterbox pre-warmed, not being called): main process averaged
  **~18% of one core** across 5 samples (15.9/44.5/11.7/9.0/10.7%,
  including a real spike to 44.5%), vs. Day 11's earlier `--t3` baseline
  (Ollama only, no resident PyTorch TTS model) of 5.8-8.6%. Plausibly
  PyTorch/MPS background threads a resident model keeps alive in-process
  — unlike Ollama, which runs as a separate server process with no
  memory/thread cost inside the engine's own PID. **Day 8's ~6-8% idle
  target does not hold once Chatterbox is loaded** — a real, disclosed
  regression, not swept into the "no regression" framing D41's idle-CPU
  row used for the VLM path.
- **Memory:** ~10.4-10.5% of 24GB (~2.5GB) resident for the engine's main
  process with Chatterbox loaded, on top of YOLOE/Moonshine/tracker —
  Ollama's LLM/VLM weights don't count against this since they live in
  Ollama's own separate process.

**Interruption, kept working, implemented differently.** `say`'s subprocess
made "stop mid-word" a SIGTERM away. Chatterbox generates a whole clip
in-process then plays it via `sounddevice` — `SpeechHandle.stop()` sets a
cancellation flag (checked before playback starts, so a stop during the
1.6-3.2s generation window prevents the clip from ever playing) and calls
`sd.stop()` (cuts actual playback). **Measured, both directions:**
cancelling during generation produced zero audio and left the loop able to
speak a second utterance normally right after; cancelling 800ms into real
playback returned control in **114ms** — not SIGTERM-instant, but a real,
fast, working interrupt. **Not true mid-generation cancellation** — if
`stop()` fires while `model.generate()` is running, that call still runs to
completion on its background thread (the user hears nothing either way;
the CPU cost of the discarded generation isn't reclaimed). Acceptable for
a first cut; the `chatterbox` library doesn't expose a way to abort
generation mid-flight.

**Cost:** two new dependencies (`chatterbox-tts`, `setuptools<81` pinned
down from 84.x), `torch` downgraded 2.13.0→2.6.0 project-wide (regression-
tested against YOLOE, holds), `engine/tts.py` rewritten in full (subprocess
→ in-process PyTorch model + `sounddevice` playback), `main.py` gained a
TTS pre-warm step at startup.

**Revisit if:** the 1.6-3.2s pause proves worse in real use than the
robotic voice it replaced — Kokoro-82M (already vetted, D13/D39) is the
named fallback, a one-file swap back to something faster but less
expressive. Also revisit if real emotional/exaggeration control is wanted
badly enough to justify testing the slower base `ChatterboxTTS` instead of
Turbo. The idle-CPU regression is worth a real profiling pass (is it MPS
allocator threads, autograd, something reducible) rather than accepted as
a permanent cost, once there's a day with room for it.

---

### D45 — Proactive JARVIS-boot greeting: a person appearing opens the conversation window without a wake phrase

**Decided:** Day 11, immediately after D44, same live session, on the
project owner's direct ask: *"Can we not use the wake up, but just
initiate by their own if I first appear in the frame. And say 'Hey Sir!
What's for today?' or something funny greetings inspired by JARVIS."*

**What this is not:** not the spec's §16 Proactive Intelligence Engine
(Expected Benefit × Urgency × Confidence ÷ Interruption Cost scoring),
which stays scoped to Day 14 as planned — that's a general-purpose
proactive-alerting system. This is one narrow, hand-scoped trigger:
`person` track transitions absent→present, speak one real JARVIS-style
line, open the same conversation-follow-up window `handle_command` already
opens after any answered command. `parse_intent`'s `wake`/`sleep`/`stop`
grammar is completely untouched — the wake *phrase* still exists and still
works exactly as before; this adds a second, automatic way into the
conversation window, it doesn't replace or weaken the first.

**Shipped:** `engine/greeting.py`, `PersonGreeter`, wired into `main.py`
alongside `AmbientNarrator`, updated every frame off the same `last_tracks`
the ambient narrator already reads. **Deliberately not gated behind
`QueryLoop.ambient_enabled`** (unlike `ambient.py`'s D38 "silence is
default" narration) — this is the one kind of unprompted speech the owner
explicitly asked to always be on today. Scoped tight to avoid reopening
the narration-fatigue problem D38 was built to close: fires once per
genuine appearance (a 120-second cooldown, first-guess constant, not
tuned against real walk-away/return footage this session), not on every
frame a person is visible, not on other objects appearing.

**Greeting content: real time-of-day, not fabricated.** `datetime.now().hour`
picks one of four small line banks (morning/afternoon/evening/night),
`random.choice`d so it doesn't say the identical line every time — the
same honesty rule D17 applied to "never print a number with no real source
behind it" applied here to "never claim a time of day that isn't real."
JARVIS-toned ("Good morning, sir. What's on the agenda today?"), not the
literal line the owner suggested verbatim, since a small bank reads better
over repeated real use than one fixed catchphrase would.

**Tested two ways:** `test_greeting.py` (7 cases, synthetic tracks, a
mocked `QueryLoop` — the appear/no-repeat/cooldown/gap/busy-state logic,
all without needing camera or TTS) and a real live run this session: real
camera, real YOLOE detection, a real person (this session's operator)
appearing in frame, a real greeting selected, real Chatterbox Turbo
generation, real audio out the real speakers. `in_conversation` flipped
`False`→`True` in the same tick the greeting fired, confirmed by direct
inspection of `QueryLoop`'s own state, not assumed from the code reading
right.

**A real gap found and fixed en route:** `ChatterboxTurboTTS.from_pretrained`
was making a live Hugging Face Hub metadata round-trip even with weights
already cached under `HF_HOME` — one real run stalled 30+ seconds on it
(unauthenticated rate limiting, same warning class STT/LLM setup already
logs). Fixed with `HF_HUB_OFFLINE=1`, set lazily inside `tts.py`'s model
loader (not globally in `main.py`, since `Stt`'s very first-ever run on a
fresh machine still needs one real fetch) — weights don't change between
runs once downloaded, so forcing cache-only load is correct, not a
workaround.

**Cost:** one new file (`greeting.py`), a 6-line wiring change in
`main.py` (import + instantiate + one `.update()` call alongside the
existing `ambient.update()`), one new test file. No new dependency. Reuses
`QueryLoop.speak_ambient()` (which already checks `preemption.active`) and
`QueryLoop._extend_conversation()` (which `handle_command` already calls
after every answered command) rather than inventing new plumbing.

**Revisit if:** real use shows the 120s cooldown is wrong in either
direction — too naggy if you step out of frame briefly and back (lower
grace, not shorter cooldown, is probably the actual fix), or too rare if
you want a "welcome back" moment sooner after a real absence. Also revisit
whether the greeting should route the same provenance logging (D43) VLM
answers get — not done this session, since a greeting isn't a claim about
anything observed, just a social opener.

### D46 — `--quiet` flag, and pausing T1 while TTS is speaking (a real contention bug, not a config tweak)

**Decided:** Day 11, same session, after the owner ran the engine live and
reported three concrete problems from a pasted terminal log: unprompted
speech with no browser open, confusion about whether the engine needs the
browser at all, a wall of meaningless per-frame JSON, and — in a follow-up
message with a second real log — **distorted TTS audio** and the engine
answering a real question with "i had trouble reaching my language model
just now" (`query_loop.py`'s hard-coded fallback for an `Llm.respond()`
exception).

**`--quiet` (main.py):** suppresses the per-frame JSONL `emit()` prints to
stdout; keeps `[setup]`/`[t3]`/`[warn]`/`[error]`/`[gated-fraction]` lines.
Purely cosmetic — doesn't touch the WebSocket bridge (the browser HUD's
copy of the same data is unaffected either way) or engine behavior.

**The distortion and the LLM error were not two unrelated bugs — traced to
one real cause, not assumed.** `query_loop.py`'s `handle_command` releases
`preemption` (`finally: self.preemption.release()`) the instant
`_speak_and_log` *starts* Chatterbox generation — `speak()` is
fire-and-forget, returning a handle immediately, well before generation or
playback finishes (`tts.py`'s own docstring already states real generation
takes 1.6–3.2s on this machine). `main.py`'s T1 loop only checked
`preemption.active` before resuming YOLOE (MPS) inference at up to 8Hz —
so as soon as `release()` fired, T1 resumed while Chatterbox was still
mid-generation on the same MPS device *and* `sounddevice` was mid-playback
on the real-time audio callback thread. Verified in isolation
(`chatterbox.generate()` alone, no contention: clean float32 in [-1, 1],
no NaN/inf, correct mono shape — ruling out a data bug in `tts.py` itself)
before concluding the cause was concurrent GPU/CPU load, not corrupt audio
data. Three real MPS-bound workloads (YOLOE, Ollama's llama.cpp Metal
backend, Chatterbox's torch/MPS backend) sharing one GPU, plus CPU
contention starving PortAudio's real-time callback, is a well-known class
of failure (audio crackle/underrun under host starvation) and directly
explains both symptoms the owner saw: garbled sound (the audio side of the
contention) and a request to Ollama slow or failing enough to hit
`Llm`'s exception path (the GPU side).

**Fix:** `main.py`'s T1-resume condition now also checks
`not query_loop._speaking()`, gating detection the same way `preemption.active`
already does, for the same reason — extending an existing pattern rather
than inventing new plumbing. Held at the T1-resume check specifically, not
by delaying `preemption.release()` itself, so a forced fresh-look request
(`poll_force_request()`, unconditional, above this check) still isn't
blocked by an unrelated ambient/greeting utterance in flight.

**Not verified live this session** — this agent has no mic/speaker access
in this sandbox (the same standing limitation noted since Day 9/10 for
capturing real wake-latency numbers). The fix is a direct, evidenced
response to the owner's real report and passes the existing 47-test suite,
but the owner is the one who can confirm on real hardware whether the
distortion is actually gone.
