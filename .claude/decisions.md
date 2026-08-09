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
**Kokoro TTS status — a genuine bug found, not glossed over:** on first
attempt, `kokoro-js`'s phonemizer (`espeak-ng`, compiled to WASM, running in
a Worker) failed at synthesis time with `Invalid language identifier:
"en-us". Should be one of: .` — its internal language table came back empty.
Root-caused to missing cross-origin isolation: `kokoro-js`/`onnxruntime-web`
and `web-llm` both ship multi-threaded WASM builds that need
`SharedArrayBuffer`, which browsers only grant a page that opts into
`Cross-Origin-Opener-Policy: same-origin` + `Cross-Origin-Embedder-Policy:
require-corp`. Added both headers to `vite.config.ts` (dev *and* preview
servers). That fixed the silent-degrade-to-broken failure mode (a Worker now
visibly spins up), but **the same "Invalid language identifier" error
persists even with COI enabled** — the model loads, `state` correctly
reaches `ready`, and the app **correctly falls back to `system`
speechSynthesis with a console warning** rather than going silent (per the
non-negotiable "never go silent" rule), but Kokoro itself has not yet been
heard to actually speak in this environment. Filed as a real open bug, not
worked around by quietly defaulting away from it: `voice_engine` still
defaults to `'system'` (D10-safe, zero download, known-good), and switching
to `'local-tts'` is an explicit opt-in for the demo, with the honest caveat
stated on camera if it's still broken at recording time.
**Revisit if:** the Kokoro/phonemizer language-table bug gets root-caused
(next suspects: `phonemizer`/`kokoro-js` version pin, or the Worker's own
COI status not inheriting the page's) — or if it doesn't, drop to a
non-Worker phonemizer path or a different local TTS model entirely, per D10's
"smaller local model, never a cloud call" fallback rule. Also revisit the
0.5B tone quality if a smaller-but-better-tuned instruct model lands in
WebLLM's catalog.
