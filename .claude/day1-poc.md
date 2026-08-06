# Day 1 POC — shipped

## What works, verified

The full loop, end to end:

1. **Camera** — `getUserMedia` at 1280×720, bound to a `<video>`, mirrored.
2. **Detection** — COCO-SSD (`lite_mobilenet_v2`) on the TF.js WebGL backend,
   running in a `requestAnimationFrame` loop.
3. **HUD** — canvas overlay: corner brackets, glowing labels with confidence,
   crosshair, frame corners, sweeping scanline, a tracking line to the largest
   target.
4. **Narration** — Web Speech API speaks scene changes, gated by a stability
   window and a cooldown.
5. **Telemetry** — live FPS, inference ms, target count, camera/model status,
   and a rolling narration log.

## Verification

Run in **headless Chrome with a synthetic camera device** via Puppeteer:

```
Camera:     live
Model:      ready
FPS:        59.8
Inference:  12 ms
Video:      1280x720
Console errors: none
```

The model detected and bracketed a shape in the synthetic test pattern
(labelled `kite 68%` — wrong label, but the fake device is an abstract colour
pattern, so a wrong label there means nothing).

**A real bug was caught this way:** label text rendered **mirrored**. The
overlay canvas was CSS-flipped to match the mirrored video, which flipped the
text too. Fixed by mirroring coordinates instead of pixels.

## What is NOT verified

Stated plainly, because it matters:

- **Detection quality on a real scene.** The synthetic camera device is an
  abstract pattern, not a room. Real-world accuracy needs a real webcam.
- **Narration timing on real scenes.** The stability/cooldown numbers
  (900ms / 3.5s) are first guesses. On the synthetic input the scene flickered
  too much to trigger an utterance. Tuning these against real footage is
  explicitly Day 3's job.
- **Speech output.** `speechSynthesis` has no voices in headless Chrome. The
  narration *logic* runs and logs; audio needs a real browser.

**First real-webcam check to run:** start the camera, raise one hand, and
confirm the box tracks the hand on the *same* side of the screen it appears on.
That confirms the mirror fix against a genuinely asymmetric scene.

## Running it

```bash
npm install
npm run dev
# open http://localhost:5173 and click "Start camera"
```

First load downloads model weights (a few MB), then they're cached.

## Deliberately not done on Day 1

- Temporal tracking → Day 2 (this is why boxes jitter)
- Spatial/salience-aware narration → Day 3
- Animations and lock-on polish → Day 4
- WebGPU, frame skipping → Day 5
- Mobile, edge cases, tests → Day 6

## Honest limitations to state publicly

- Knows **80 object classes** only (the COCO set). No text reading, no faces,
  no specific brands.
- It's **object detection, not scene understanding** — it knows "chair" and
  "person", not "someone is cooking in a kitchen".
- Each frame is detected **independently**, so boxes jitter and objects have no
  identity across frames.
- Desktop browser only, for now.
