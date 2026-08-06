# YAP — Yet Another Perception

## What it is
A live vision overlay. Point a camera at the world; YAP draws a heads-up display
over the video showing what it recognises, and narrates the scene out loud as
things change.

## What problem it actually solves
The honest framing: this is not solving a burning enterprise pain. It is a
**perception interface** — a demonstration that a browser, with no server and no
API key, can see and describe the world in real time.

The real use cases it points at:
- **Accessibility** — a running audio description of what's in front of a camera.
- **Ambient awareness** — a screen that tells you what changed rather than what's there.
- **Robotics/AR groundwork** — the same detect → track → describe loop that any
  embodied system needs, made visible and debuggable.

The demo value is that perception becomes *legible*. You can watch the machine
think.

## The one-sentence version
> YAP turns any webcam into a heads-up display that sees what's in front of it
> and tells you, in real time, entirely on your own device.

## Core constraints (chosen deliberately)
1. **Runs entirely in the browser.** No backend, no upload, no API keys. Video
   never leaves the device. This is a privacy story *and* a latency story *and*
   a "you can clone it and it just works" story.
2. **Real-time or it doesn't count.** Target ≥15 FPS end-to-end. A 2 FPS demo
   is a slideshow, not a HUD.
3. **Nothing faked.** Every box on screen comes from a real model running on
   real pixels. No pre-recorded overlays, no scripted narration.

## Who this is for
Two audiences at once:
- **Viewers** of the build-in-public series, who need to understand *what*
  computer vision is doing and *why* it's hard.
- **Engineers** who might clone the repo and want a clean, readable real-time
  CV pipeline that isn't a 40-file abstraction maze.

## What "done" looks like after 7 days
A polished, mobile-capable live vision HUD with stable tracking, well-timed
narration, and a latency story worth explaining — plus a complete public
narrative of how it was built.

## Related docs
- [architecture.md](architecture.md) — how the loop is wired
- [decisions.md](decisions.md) — why each choice was made
- [week-roadmap.md](week-roadmap.md) — the 7-day path
- [day1-poc.md](day1-poc.md) — what shipped on Day 1
