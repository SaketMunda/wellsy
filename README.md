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


Python engine (real detector, tracking, and the Day 10 query loop)

cd /Users/saketmunda/Work/Startup/projects/yap-hud/engine
uv run python main.py                    # real camera, runs until Ctrl+C
Useful flags:

--seconds N — stop after N seconds instead of running forever
--t3 — turn on the Day 10 query loop (mic, wake phrases "hey yap"/"yappy"/"hey yo", push-to-talk via Enter, TTS through speakers)
--enable-yo — also accept bare "yo" as a wake word (off by default, see decisions.md D39)
--synthetic — no real camera needed, exercises the pipeline against a generated frame
--no-ws — disable the WebSocket bridge, stdout JSONL only
To see it in the browser HUD with the real engine driving detection:


# terminal 1
cd engine && uv run python main.py --t3

# terminal 2
cd /Users/saketmunda/Work/Startup/projects/yap-hud && npm run dev