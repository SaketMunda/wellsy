# Architecture

**Status: current as of Day 3.**

## The whole system in one picture

```
┌── Camera ─────────┐
│  getUserMedia     │
│  <video> element  │  ← the only source of pixels
└─────────┬─────────┘
          │
          ├──────────────────────────────┐
          │                              │
┌─────────▼──────────┐        ┌──────────▼───────────┐
│  DETECT LOOP       │        │  DRAW LOOP           │
│  (useDetector)     │        │  (HudCanvas)         │
│                    │        │                      │
│  rAF → COCO-SSD    │        │  rAF → drawHud()     │
│  on WebGL          │        │  on <canvas>         │
│  ~15-60 FPS        │        │  60 FPS              │
└─────────┬──────────┘        └──────────▲───────────┘
          │                              │
          │      ┌─────────────────┐     │
          └─────►│  frameRef       │─────┘
                 │  (a React ref)  │
                 │  detections,    │
                 │  fps, latency   │
                 └────────┬────────┘
                          │
                 ┌────────▼─────────┐
                 │  NARRATION       │
                 │  (useNarrator)   │
                 │  samples 4x/sec  │
                 │  stability gate  │
                 │  → speechSynth   │
                 └──────────────────┘
```

## The one architectural idea that matters

**Three loops, decoupled by a ref.**

The detect loop, the draw loop, and the narration sampler all run at their own
natural speed and communicate through a single mutable `frameRef`. Nothing waits
on anything else.

Why this matters:
- Detection at 18 FPS still renders a smooth 60 FPS HUD.
- React never re-renders on the hot path. Detections **never** enter React state.
- The narrator samples reality on its own clock rather than being driven by
  frame events, so its timing logic stays simple.

If detections went into `useState`, the entire component tree would re-render
30×/second and the framerate would collapse. This is the single most important
performance decision in the project.

## File layout

```
src/
├── vision/
│   ├── types.ts          Detection, Track, Frame — the shared vocabulary
│   ├── tracker.ts        Pure function: IoU-matches + smooths detections into tracks.
│   ├── useCamera.ts      Owns the MediaStream. Knows nothing about AI.
│   └── useDetector.ts    Owns the model + detect loop + tracker. Knows nothing about drawing.
├── hud/
│   ├── drawHud.ts        Pure canvas drawing. No React, no state, fully testable.
│   ├── HudCanvas.tsx     Owns the draw loop + canvas sizing.
│   └── StatusPanel.tsx   Telemetry + narration log.
├── narration/
│   ├── events.ts         Track enter/exit → structured NarrationEvents. No side effects.
│   └── useNarrator.ts    Timing logic + speech output.
├── App.tsx               Composition + top-level on/off state.
└── App.css               All styling. One file is correct at this size.
```

**The layering rule:** `vision/` never imports from `hud/` or `narration/`.
Data flows one way. This is what makes the camera swappable (webcam → phone →
video file) without touching the HUD.

**The purity rule:** `drawHud.ts`, `tracker.ts`, and `events.ts` are pure.
Given the same input they produce the same output, with no React and no
browser APIs beyond the canvas context. These are the files most likely to
grow, and keeping them pure keeps them testable.

## Key implementation details

### Coordinate spaces (a real source of bugs)
Three different spaces are in play:
1. **Video pixel space** — what the model returns (e.g. 1280×720).
2. **CSS space** — the displayed size of the video element.
3. **Device pixel space** — canvas backing store, scaled by `devicePixelRatio`.

`drawHud` takes explicit `scaleX`/`scaleY` to map 1→2, and `HudCanvas` handles
2→3 via `ctx.setTransform(dpr, ...)`. Keeping this conversion in one place is
deliberate.

### Mirroring
The video is CSS-mirrored for a natural selfie view. The **canvas is not.**
Instead `drawHud` flips box coordinates (`canvasW - x - w`).
Mirroring the canvas would render all label text backwards — this was an actual
Day 1 bug, caught in a screenshot. See [research.md](research.md) §5.

### Model choice
`lite_mobilenet_v2` COCO-SSD, WebGL backend. Loaded once, cached in a ref.
Confidence floor 0.5, max 12 detections/frame — both are latency guards as much
as quality guards.

## What this architecture does NOT do yet
- **No motion prediction or re-identification.** The Day 3 tracker matches by
  IoU overlap and survives a short grace window (5 missed frames); it does
  not predict velocity (no Kalman filter) and does not re-identify an object
  that fully leaves and later returns — that gets a new id.
- **No scene-level reasoning.** Only object labels, no "this is a kitchen". → Day 4.
- **No mobile camera path.** Desktop webcam only. → Day 7.
- **No frame throttling.** Detection runs as fast as it can, which is wasteful
  on a static scene. → Day 6.

## Extension points already in place
- `useCamera` can be swapped for a file/stream source without touching anything
  downstream — the rest of the system only knows about a `<video>` element.
- `Track` (in `types.ts`) is a `Detection` plus `id`/`ageMs`/`missedFrames` —
  narration and HUD both consume it without knowing how it was computed.
- `events.ts` is a pure function of tracks — swapping rule-based narration for
  an LLM downstream is a one-file change in `generateLine.ts`.
