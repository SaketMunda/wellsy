# Demo Script

## The one-liner
> YAP turns any webcam into a heads-up display that sees what's in front of it
> and tells you what it sees — in real time, entirely on your own device.

---

## Day 1 demo flow (60–90 seconds)

### 0:00 — Cold open, no explanation
Screen already showing the dark HUD, "PERCEPTION OFFLINE".
Click **Start camera**.

> "Watch this."

Let the model load. The wait is honest — say so:
> "It's downloading the vision model. That happens once."

### 0:10 — The moment
Boxes snap onto you and whatever's on your desk. Say nothing for two seconds.
**Let the visual land.** Then:

> "That's my webcam. Nothing is being uploaded anywhere. That's my laptop's
> GPU, running a neural network, thirty times a second."

### 0:25 — Prove it's live
Pick up a cup. Hold up your phone. Move a chair into frame.
New brackets appear.

> "It's not a filter. Every box you see is a real prediction on a real frame."

### 0:40 — Narration
Turn narration on. Let it speak.

> "And it tells me what changed. Not what's there — what *changed*. That
> difference turns out to be the entire hard part."

### 0:55 — The telemetry
Point at the panel.

> "Twelve milliseconds to look at a frame and decide what's in it. Sixty frames
> a second. No server, no API key, no internet after the first load."

### 1:10 — Honest close
> "It knows eighty kinds of object. The boxes still shake, because right now
> every frame is a fresh guess with no memory. That's tomorrow."

---

## Terms to simplify

| Don't say | Say instead |
|---|---|
| COCO-SSD | "a model trained to spot 80 everyday objects" |
| Single-shot detector | "it figures out what and where in one look" |
| Inference latency | "how long it takes to look at one frame" |
| WebGL backend | "it runs on the graphics card" |
| Bounding box | "the bracket around the thing" |
| requestAnimationFrame loop | "it runs every frame" |
| Temporal tracking | "does it remember it saw that a second ago" |

---

## What makes this exciting even though it's unfinished

1. **It's visibly real.** The boxes move because the world moves. You cannot
   fake that on camera, and viewers know it.
2. **It runs on the machine you're looking at.** No cloud, no key. That's a
   surprisingly strong hook right now.
3. **The numbers are on screen.** 12ms, 60 FPS. It's self-evidencing.
4. **The flaws are interesting.** Jittery boxes aren't an embarrassment —
   they're a cliffhanger for Day 2.

---

## Recording notes

- **Good light.** Detection quality lives and dies here.
- **Have props ready** in reach: cup, phone, book, chair, laptop, bottle. All
  COCO classes; all reliably detected.
- **Record system audio** so the narration is captured.
- Keep the **telemetry panel in frame** — it's most of the credibility.
- Don't cut the model-loading wait. Showing the unglamorous part builds trust.
- Best single shot for a thumbnail: brackets locked on your face + the FPS
  counter visible.

---

## If it fails live
Say what you see. "It thinks my headphones are a cell phone." That's more
compelling than a clean run — it shows the seams, and the seams are the content.
Never re-record to hide a wrong label; narrate it instead.
