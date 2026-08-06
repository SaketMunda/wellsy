# YAP — Yet Another Perception

A live vision overlay. Point your webcam at the world; YAP draws a heads-up
display over the video showing what it recognises, and narrates the scene out
loud as things change.

**Runs entirely in your browser.** No backend, no API keys, no uploads — video
never leaves your device.

```bash
npm install
npm run dev
# open http://localhost:5173, click "Start camera"
```

First load downloads the model weights (a few MB); cached afterwards.

## What it does

- **Detects** objects in real time — COCO-SSD on the TensorFlow.js WebGL backend
- **Draws** a HUD overlay: tracking brackets, labels, confidence, live telemetry
- **Narrates** what changes, in the voice of a documentary narrator who is
  deeply unimpressed — optionally spoken via the Web Speech API
- **~12ms** inference per frame

## What it doesn't do (yet)

- Knows **80 object classes** only (the COCO set) — no text, faces, or brands
- Object *detection*, not scene *understanding* — it knows "chair", not "kitchen"
- No temporal tracking yet, so boxes jitter between frames
- Desktop browsers only

## How it works

Three loops, decoupled by a ref:

```
camera → [detect loop: COCO-SSD @ ~20-60fps] ─┐
                                              ├→ frameRef ─→ [draw loop: canvas @ 60fps]
                                              └→ [narration sampler @ 4fps → speech]
```

Narration is two layers, deliberately kept apart:

```
settled scene → [event layer: appear/disappear/count_change/still_present] → truth
                                    ↓
                [personality layer: template bank + no-repeat memory] → voice
```

The event layer states facts; the personality layer may only restyle them,
never invent them. Flip **boring mode** in the panel to show the raw events for
the same rows — the sarcasm is a rendering, the detection underneath is real.
The whole personality is a plain template bank: no LLM, no API, no network, so
it works offline and costs nothing per line.

Detections never enter React state — that would re-render the tree 30×/second.
See [.claude/architecture.md](.claude/architecture.md) for the full picture and
[.claude/decisions.md](.claude/decisions.md) for why each choice was made.

## Project structure

```
src/vision/     camera + model + detect loop
src/hud/        canvas drawing + telemetry panel
src/narration/  scene → English + speech timing
.claude/        build-in-public workspace: research, decisions, roadmap
```

## Building in public

This is a 7-day build. Progress, research notes, and the daily narrative live in
[.claude/](.claude/) — see [week-roadmap.md](.claude/week-roadmap.md).
