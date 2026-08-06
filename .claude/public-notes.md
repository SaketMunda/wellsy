# Public Notes — build-in-public content

## The series premise (one line)
> 7 days. Building an AI that sees the world through a camera and describes it
> in real time. No backend, no API keys — it runs in your browser.

---

## Day 1 — "I gave my laptop eyes"

**Concept:** Real-time object detection in the browser.

**Simple explanation (2–4 lines):**
> A neural network looks at each video frame and, in one pass, guesses both what
> objects are in it and where they are. That "one pass" is why it's fast enough
> for live video — older approaches had to scan an image hundreds of times.
> It runs on your graphics card, in a browser tab. Nothing is uploaded.

**What viewers should notice:**
- Boxes track objects as they move — it's live, not a filter
- 12ms inference, 60 FPS, on screen
- It speaks only when something *changes*

**What was hard:**
The narration. Making an AI describe a scene takes ten minutes. Making it
describe a scene *without being unbearable* is the actual work — every frame
it'd say something, and low-confidence boxes flicker so it stutters. Solved with
a stability gate: an object must hold steady for ~a second before YAP mentions it.

**The bug worth telling:**
All my labels rendered backwards. I'd mirrored the video for a natural selfie
view, then mirrored the overlay to match — which mirrored the text too. Fix:
mirror the *coordinates*, not the canvas.

**Posts:**
- **X:** "Day 1 of building YAP. My browser now sees. 12ms per frame, 60fps, no
  server, no API key. Every box is a real prediction on a real frame. 🧵"
- **LinkedIn:** Lead with the privacy/latency angle — on-device inference is the
  interesting engineering claim, not "I used an AI model".
- **Reel caption:** "I gave my laptop eyes in one day 👁️ It just told me what's
  on my desk. Runs entirely in the browser — nothing uploaded."

---

## Day 2 — "It learned to remember"
> Detection asks "what's here now?". Tracking asks "is that the *same* thing I
> saw a second ago?". Everything that feels intelligent comes from the second
> question.

**Line:** "Yesterday it saw. Today it remembers."

## Day 3 — "Teaching it when to shut up"
> Getting an AI to talk is easy. Getting it to talk only when it's worth it is
> the product.

**Line:** "The hard part of a talking AI isn't the talking."

## Day 4 — "Same brain, better face"
> I didn't touch the model today. It feels twice as smart. That gap is design.

**Line:** "Perceived intelligence is mostly interface."

## Day 5 — "33 milliseconds"
> At 30fps you get 33ms to capture, think, and draw. Optimisation is just
> deciding where those milliseconds go.

**Line:** "Real-time isn't a feature, it's a budget."

## Day 6 — "Trying to break it"
> Demos work in one room with good light. Products work in the dark, on a
> phone, with the camera denied.

**Line:** "Every demo works on the demo machine."

## Day 7 — "Here's the link"
> 7 days, no backend, no API keys, no cost. Open the link and your laptop starts
> seeing.

---

## What is REAL (claim freely)
- Live object detection on real camera frames, on-device
- ~12ms inference, real-time framerate
- Video genuinely never leaves the device
- Narration is generated from actual detections
- Everything on screen comes from a real model

## What is NOT real yet (never overclaim)
- ❌ "It understands scenes" — it detects **objects**. It doesn't know "kitchen"
  or "someone is cooking".
- ❌ "It recognises anything" — **80 fixed classes**. No text, no faces, no brands.
- ❌ "It tracks objects" — not yet. Day 2. Each frame is currently independent.
- ❌ "Production ready" — it's a 7-day build.
- ❌ Don't imply a custom-trained model. It's an off-the-shelf model, well
  integrated. **The engineering is the pipeline, not the network** — say that,
  it's a more honest and more interesting claim anyway.

## Tone rules
- Show the failures. Wrong labels are content, not shame.
- Always show the telemetry — numbers beat adjectives.
- Never say "AI-powered". Say what it actually does.
- End every day on what's broken. That's the reason to come back tomorrow.
