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
**Revisit if:** Day 3 narration needs real scene understanding. The likely
answer is a *hybrid*: local detection stays real-time, an optional cloud call
adds occasional richer description.

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
