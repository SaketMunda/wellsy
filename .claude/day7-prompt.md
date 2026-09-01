# Day 7 — "I built the wrong thing"

You are picking up WELLSY on Day 7. Days 1–6 have shipped. Read
`.claude/context.md`, `.claude/decisions.md` (D1–D27), `.claude/tasks.md`,
`.claude/architecture.md`, and — this one matters more than usual —
`.claude/v2-architecture-research.md` and `.claude/v2-roadmap.md`, which
together explain why today exists. This document is the brief for today only.

---

## The goal, stated precisely

Today is the pivot day. It has three deliverables and **the first one is the
episode**:

1. **Measure the current build honestly, and capture the stall.** Every
   performance number in the research doc came from someone else's machine.
   Today produces ours — including the number nobody has ever looked at:
   what the system costs when *nothing is happening and nobody has asked it
   anything*.
2. **Retire the claims that stop being true.** Days 1–6 were sold on "no
   backend, runs entirely in your browser, video never leaves your device."
   V2 has a Python engine and an optional private server. Those sentences get
   struck through with a date, not quietly deleted.
3. **Stand up the Python skeleton** — camera, motion gate, JSON out. No model.
   Prove the plumbing and the process boundaries before anything expensive
   sits on them.

The thesis for the day: **the bug was the design.** Six days of work built a
system that does maximum work at all times regardless of whether anyone needs
the answer. Fixing the threading would have made that waste *faster*. It
would not have made it stop.

---

## Boundaries

- **Everything lives in this repo.** Every file you create — code, notes,
  measurement output, scratch scripts — goes inside
  `/Users/saketmunda/Work/Startup/projects/wellsy`. Not `/tmp`, not a
  scratchpad, not a home directory. No exceptions.
- **No cloud, still (D10).** Nothing today calls out to a network service.
  The private server discussed in the research doc is Day 14 and is hardware
  the user owns; it changes nothing about today.
- **Do not start deleting the browser build.** It is the before-picture, it
  is the fallback if MLX fights back on Day 8, and it ships as a mode. Today
  adds a sibling directory; it does not remove a working system.
- **Do not install a detection model today.** The temptation to "just try
  YOLO quickly" will be strong and it will eat the measurement work. That is
  Day 8, it has a fallback plan, and it needs the whole day.
- **Do not tune anything you measure.** Today's numbers are the baseline. A
  baseline you optimised while measuring is worthless as a comparison.

---

## Where things stand

Day 6 shipped per-track label voting, `UNIDENTIFIED` hedging, push-to-talk
local Whisper, deterministic `parseIntent`, grounded `describeScene`, and the
latency breakdown panel. Two post-ship fixes (D26, D27) are committed. The
working tree is clean and `e5b1c55`/`b60e903` are the frozen reference point.

What is known and does not need rediscovering:
- **Zero Web Workers in `src/`.** Detection rAF, HUD draw rAF, the 250ms
  narration sampler, WebLLM inference, Kokoro TTS and every React render share
  one thread.
- **Three inference runtimes, one GPU**: TF.js/WebGL, WebLLM/WebGPU, ONNX
  Runtime/WASM. No coordination, separate memory arenas, ~1GB of weights in
  one tab.
- Day 5's `hudState.ts` interpolates toward the latest detection at τ=70ms
  (D15). Nothing has ever exploited this.

---

## Part 1 — The autopsy (this is the deliverable, do it first)

### What to measure

Write the results to **`.claude/day7-baseline.md`**. Every number needs the
conditions it was taken under, or it isn't a number.

| # | Scenario | What to record |
|---|---|---|
| A | Camera on, detection on, **narration off, voice off** | FPS, inference ms, HUD draw ms, longest long-task, CPU% |
| B | A, plus **template narration on** | same, plus time-to-line |
| C | B, but **`local-llm` + `local-tts`** — the full Day 4 stack | same, plus LLM ms, TTS ms |
| D | C, plus **push-to-talk held and a question asked** | same, plus ASR ms, and *what frame timing does during ASR* |
| E | **Idle scene** — camera on, nothing moving, full stack loaded | CPU%, GPU%, frames processed per minute, lines generated |

Scenario **D is the stall** and scenario **E is the argument**. Everything
else is context for those two.

### How to measure it

- **Frame deltas**: a `PerformanceObserver` on `longtask`, plus a rAF loop
  recording `delta = now - last` into a ring buffer. Anything over 50ms is a
  dropped frame; anything over 200ms is a visible freeze. Report the
  distribution — p50, p95, max — not the mean. The mean hides exactly the
  thing we're looking for.
- **Add a `?bench=1` mode** to the app that starts the recorder and, on `B`
  or a button, dumps the ring buffer as JSON. Keep it small and keep it
  behind the flag; this is instrumentation, not a feature.
- **CPU/GPU**: macOS Activity Monitor, or `powermetrics` if you can get it
  without sudo friction. Record the reading for the browser process
  specifically, not the whole system.
- **Run each scenario for 60 seconds minimum.** Short samples miss the
  garbage collector and miss the LLM.
- Take a **Chrome DevTools performance trace** during scenario D and save the
  screenshot into `.claude/` — the flame chart with one long orange block is
  the single most useful image the series will produce this week.

### The number that matters most

Scenario E answers: *what does this system cost to run when it has nothing to
say and nobody has asked it anything?* Express it as a percentage of a
laptop's CPU, and as a fraction of E's work that produced anything a human
consumed. That ratio is the entire justification for the tier scheduler on
Day 8.

### Optional, only if there is time left

Move detection into a Web Worker and re-run scenario C. This tests the §1a
diagnosis directly. It is genuinely interesting and it is genuinely optional —
**do not let it eat Part 2 or Part 3.** If it happens, it is a bonus finding,
and it does not get merged; it gets measured and reverted.

---

## Part 2 — Retire the claims

In **`.claude/public-notes.md`**, the claims that survived six days and do not
survive V2:

- "No backend"
- "Runs entirely in your browser"
- "Video never leaves your device"
- "No API keys" — this one *survives*, and it is now the strongest remaining
  claim. Do not strike it.

Strike the dead ones with a dated line each, in the existing honesty section,
in this shape:

> ~~"Video never leaves your device"~~ — **retired Day 7.** V2 runs a local
> Python engine and optionally a private server the user owns. The honest
> replacement: *"your data goes to hardware you own, and nowhere else."*
> Still a strong claim. A different one.

Then add the replacement claims as live entries. The point of this exercise
is that anyone reading `public-notes.md` in six months can see exactly what
was promised, when it stopped being true, and what replaced it. Quietly
deleting a claim you made on camera is the thing this project does not do.

**Also add to the "NOT real yet" list**, since V2 will make all of these
tempting to say early: real depth measurement, face recognition, open-
vocabulary detection, and "it runs on my phone."

---

## Part 3 — The Python skeleton (timebox: 3 hours, hard stop)

Create **`engine/`** in the repo root. `uv` and Python 3.13 are installed.

### What it must do

```
camera (AVFoundation) → frame differencing motion gate → JSON lines on stdout
```

That is all. No model, no tracker, no HUD, no WebSocket.

### What it must prove

1. **Camera access works from Python on this machine**, including whatever
   macOS permission dialog appears — this is exactly the kind of thing that
   silently eats a morning on Day 8 if it is discovered on Day 8.
2. **The motion gate is genuinely cheap.** Target: under ~1ms per frame,
   measured. It is the T0 tier and everything in §2 rests on the claim that
   always-on sensing can be nearly free. Verify the claim now, while it is
   cheap to be wrong about.
3. **Process boundaries hold.** Capture runs in its own process and hands
   frames across a **latest-wins queue of depth 1 — drop frames, never
   buffer.** Build it this way from the first commit. §7 of the research doc
   exists because the fastest route to reproducing the browser bug in Python
   is a thread-per-workload design with unbounded queues, and by the time it
   hurts it is expensive to undo.

### Shape of the output

Emit one JSON object per processed frame on stdout, near enough to the
existing `Frame` type in `src/vision/types.ts` that Day 9's bridge is
plumbing rather than translation:

```json
{"t": 1723600000.123, "motion": 0.041, "gated": false, "captureMs": 2.1, "gateMs": 0.7}
```

`gated: true` means the motion gate suppressed downstream work — which is
what Day 8's T1 will hang off. Log the fraction of frames gated over a minute
of a still room. **That fraction is the tier scheduler's headline number**,
and having it a day early makes Day 8's episode much easier to film.

### What not to build

No detection, no tracking, no async framework selection, no WebSocket, no
config system, no CLI arg parsing beyond what one afternoon needs. This is a
spike that has to survive into Day 8, not a framework.

---

## Build in this order. Cut from the bottom.

1. Instrumentation (`?bench=1`, the ring buffer, the long-task observer)
2. Scenarios A–E measured and written to `.claude/day7-baseline.md`
3. The DevTools trace screenshot of scenario D
4. `public-notes.md` claim retirement
5. `engine/` camera capture running and permissioned
6. Motion gate + gated-fraction number
7. Process boundary with the depth-1 queue
8. *(Optional)* the Web Worker experiment

**Items 1–4 are the day.** If 5–7 do not land, Day 8 starts with a camera
spike instead of a model — annoying, survivable. If 1–4 do not land, there is
no before-picture, and the comparison that carries the next eight episodes
does not exist. It cannot be recreated later: once Day 8 lands, the old
numbers are gone.

---

## The honesty rules for today

- **Report the numbers that are boring.** If scenario E turns out to be
  cheaper than the research doc assumed, say so, in the doc, in the episode.
  The tier scheduler is still right for latency and for mobile, and a
  diagnosis that survives contact with a measurement is worth more than one
  that was never tested.
- **Do not present a Chrome trace as a general claim about browsers.** It is
  one machine, one build, one tab.
- **Label every borrowed number.** The research doc's benchmarks stay marked
  as someone else's until they are re-measured here.
- **The pivot is not a failure and should not be narrated as one.** Six days
  produced a working perception pipeline, an event layer, a tracker, a HUD
  design language and an honesty discipline — all of which survive. What
  changes is *when* it runs, and where.

---

## Verification

- `npm run lint`, `npm run test`, and **`npm run build`** all pass. D13 is a
  standing warning that this project's production build can break in ways dev
  does not — check it even on a day that barely touches `src/`.
- `?bench=1` is off by default and adds nothing measurable to the normal
  path. Verify by running scenario A with and without the flag.
- `engine/` runs from a clean checkout with `uv run`, and its README says how
  in two lines.
- The frozen reference commit is recorded in `.claude/day7-baseline.md`, so
  every future comparison names what it is comparing against.

---

## `.claude/` updates (part of the work, not paperwork)

- **`day7-baseline.md`** — new. Scenarios, conditions, numbers, the trace
  screenshot, the frozen commit hash.
- **`decisions.md`** — D28: the V2 pivot itself, with the measured
  justification, the claims retired, and what survives from Days 1–6. This is
  the most consequential decision entry in the project so far; give it the
  space it deserves.
- **`decisions.md`** — D29: latest-wins depth-1 queues, drop frames never
  buffer, decided before the first Python process was written and why.
- **`public-notes.md`** — the retirement block from Part 2.
- **`v2-roadmap.md`** — mark Day 7 shipped, and if a measurement contradicts
  a Day 8–15 assumption, say so *there*, in the day it affects.
- **`tasks.md`** — carry forward anything cut.

---

## House rules

- Small commits, each one a working state.
- Comments explain *why*, never *what*. Match the density of the existing
  code — `tracker.ts` is the reference.
- No dependency added without a line in `decisions.md` saying why.
- If something takes longer than its timebox, stop and write down where it
  got stuck. That note is worth more than a half-finished spike.

---

## Report back with

1. **The numbers** — scenarios A–E, in a table, with conditions.
2. **The stall, described precisely** — what blocks, for how long, during
   what.
3. **Scenario E's verdict** — what the always-on design costs when nobody is
   asking, and whether it justifies the tier scheduler as strongly as the
   research doc assumed. Answer honestly either way.
4. **Whether the Python skeleton stands**, the measured motion-gate cost, and
   the gated fraction on a still room.
5. **What was cut**, and what Day 8 inherits because of it.
6. **Anything measured today that contradicts the V2 plan.** This is the last
   cheap moment to find out.
