# Research — the fastest credible path

Written in plain language, deliberately: these explanations double as narration
scripts for the series.

---

## 1. Getting a camera into a web page

`navigator.mediaDevices.getUserMedia()` gives a `MediaStream`. Attach it to a
`<video>` element and you have live pixels. Requires HTTPS or `localhost`.

**Gotchas found:**
- iOS Safari needs `playsInline` or the video hijacks fullscreen.
- `video.videoWidth` is `0` until metadata loads — everything downstream must
  wait for `readyState >= 2`.
- Selfie view should be **mirrored** or it feels wrong to the user. This has a
  sting in the tail (see §5).

## 2. Object detection in the browser

Three realistic options were considered:

| Option | Speed | Setup cost | Verdict |
|---|---|---|---|
| **TensorFlow.js + COCO-SSD** | ~10–30ms/frame on WebGL | Two npm packages | **Chosen** |
| MediaPipe Object Detector | Comparable, sometimes faster | WASM assets, more config | Day 6 candidate |
| Cloud vision API | 200–800ms round trip | API key, cost, privacy | Rejected for the live loop |

**COCO-SSD** = a Single-Shot Detector trained on the COCO dataset. It knows
**80 everyday object classes**: person, chair, laptop, cup, phone, dog, car…

The `lite_mobilenet_v2` variant was chosen over the default. It's smaller and
faster at a small accuracy cost — the right trade when latency *is* the product.

**Explain-it-simply version:**
> The model looks at the image once, and in that single pass it guesses both
> *what* things are and *where* they are. That's the "single shot" part — older
> systems had to scan the image hundreds of times.

## 3. Why "single shot" matters for a HUD

Older detectors (R-CNN family) proposed regions, then classified each one —
accurate but far too slow for live video. SSD collapses both jobs into one
forward pass. This is the single architectural fact that makes real-time
in-browser detection possible at all.

## 4. Where the compute happens

TF.js runs on the **WebGL backend**: the neural network is executed as shader
programs on the GPU. This is why a laptop can do this at all — on CPU the same
model is roughly an order of magnitude slower.

- **WebGL** — works everywhere, chosen for Day 1.
- **WebGPU** — newer, faster, less universal. A Day 6 experiment.

## 5. The mirroring trap (a real bug, found and fixed on Day 1)

The natural instinct is to mirror the video with CSS `transform: scaleX(-1)`,
then mirror the overlay canvas the same way so the boxes line up.

**This is wrong.** Mirroring the canvas also mirrors the *text* drawn on it —
labels render backwards. Confirmed visually in a headless-browser screenshot.

The fix: leave the canvas unmirrored and flip the **coordinates** instead:
`x_draw = canvasWidth - x_detected - boxWidth`. Boxes align, text reads
correctly.

This is a great teaching beat — it's visual, it's obvious once seen, and it
shows why you verify with your eyes and not just a green build.

## 6. Narration: the hard part is *when*, not *what*

Turning detections into a sentence is trivial. Deciding when to speak is where
the product lives. Naive approaches and why they fail:

- **Speak every frame** → 30 utterances/second. Unusable.
- **Speak on any change** → low-confidence boxes flicker in and out; the
  narrator stutters "chair… no chair… chair…".
- **Speak on a fixed timer** → re-reads the same scene forever, feels robotic.

**The approach taken** — three gates a scene must pass before it's spoken:
1. **Sample** the scene 4×/second (not every frame).
2. **Stability gate** — the same set of objects must hold for ~900ms. This
   kills flicker.
3. **Cooldown** — a hard floor of ~3.5s between utterances.

Plus: describe the **change**, not the whole scene. "A laptop just came into
view" beats re-listing everything every time.

Speech itself is the built-in **Web Speech API** (`speechSynthesis`) — zero
dependencies, zero cost, offline.

## 7. Rendering the HUD without killing the framerate

Key insight: **detection results do not belong in React state.**

Pushing detections into state re-renders the component tree 30×/second and the
framerate collapses. Instead detections live in a `ref`, and the canvas runs its
own `requestAnimationFrame` loop reading from it. Only slow-moving telemetry
(FPS, counts) is mirrored into state, ~4×/second, for the side panel.

Second insight: the **draw loop and the detect loop run at different speeds**.
The canvas animates at 60 FPS while inference may deliver 20 FPS. Boxes simply
hold their last known position between inferences — which is exactly what real
HUDs do.

## 8. What makes it *look* like a HUD

Not accuracy — style. Cheap, high-impact tricks:
- **Corner brackets** instead of full rectangles → reads as "tracking".
- **Glow** (`shadowBlur`) on the strokes.
- **A sweeping scanline** — pure decoration, enormous perceived-tech value.
- **Monospace, uppercase, letterspaced** labels.
- **Live telemetry** (FPS, inference ms) — makes the system feel instrumented,
  and doubles as genuinely useful debug output.

## 9. Known limits (to state honestly, never hide)

- COCO-SSD knows **80 classes only**. It cannot name your specific coffee mug
  brand or read text.
- It does **object detection**, not scene understanding. It doesn't know
  "kitchen" or "someone is cooking" — that's Day 3–4 work built on top.
- No **tracking identity** yet: object #1 this frame isn't linked to object #1
  last frame. That's why boxes jitter. Day 3 fixes this.
- First load downloads model weights (a few MB); cached afterwards.

## Sources / anchors
- TensorFlow.js `@tensorflow-models/coco-ssd` package docs
- COCO dataset — 80-class label set
- MDN: `getUserMedia`, `SpeechSynthesis`, Canvas 2D API
