# Progress Log

---

## Day 1 — 2026-08-06

**Goal:** Ship the smallest credible loop. Camera in, HUD and voice out.

### Researched
- Browser detection options — TF.js/COCO-SSD vs MediaPipe vs cloud API.
  Chose TF.js: two npm packages, ~12ms inference, no assets to wrangle.
- Why single-shot detection is what makes real-time in-browser possible.
- Narration timing — established early that *when to speak* is the hard problem,
  not *what to say*.

### Decided
Nine decisions recorded in [decisions.md](decisions.md). The load-bearing ones:
- **Browser-only, no backend** — latency + privacy + shipping speed in one choice
- **Detections in a ref, not React state** — the key performance decision
- **Detect loop and draw loop are separate** — smooth HUD regardless of inference rate
- **Narration gates on stability, then describes change** — not the full scene

### Built
```
src/vision/    types.ts, useCamera.ts, useDetector.ts
src/hud/       drawHud.ts, HudCanvas.tsx, StatusPanel.tsx
src/narration/ describeScene.ts, useNarrator.ts
src/App.tsx    composition
```
Full loop: camera → COCO-SSD on WebGL → canvas HUD → spoken narration, plus a
live telemetry panel.

### Verified
Real headless Chrome with a synthetic camera device:
`camera live · model ready · 59.8 FPS · 12ms inference · 0 console errors`.
Production build compiles clean.

### Found and fixed
**Label text rendered backwards.** The overlay canvas was CSS-mirrored to match
the mirrored selfie video — which mirrors text too. Caught by *looking at a
screenshot*, not by the build. Fixed by mirroring box coordinates rather than
the canvas.

Worth noting: a green typecheck and a clean build both passed while this bug was
live. Visual verification caught what static checks structurally could not.

### Still missing
- Detection quality on a **real scene** is unverified — the synthetic camera is
  an abstract colour pattern. Needs a real webcam.
- Narration timing numbers are **first guesses**, untuned against real footage.
- Speech audio unverified (headless Chrome has no voices).
- No temporal tracking → boxes jitter.
- Desktop only.

### Can be shown publicly
Everything. The loop is real and self-evidencing: live boxes, on-screen
telemetry, spoken narration. The mirroring bug is a genuinely good story, and
the jittery boxes are a natural cliffhanger for Day 2.

**Hook:** *"I gave my laptop eyes in one day. It just told me what's on my desk."*

### Next
Day 2 — IoU tracking, box smoothing, persistent object IDs.
