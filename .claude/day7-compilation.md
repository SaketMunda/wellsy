# Day 7 — everything in one place

*"I built the wrong thing" — the autopsy + the foundation.*
Compiled for video prep. Images referenced below live in
`.claude/day7-images/`. This file is self-contained — no need to open
anything else.

---

## 1. The premise (context for viewers)

Days 1–6 shipped a browser-only, no-backend, no-API-key live vision HUD
that narrates what it sees, continuously. Day 7 is the pivot day: measure
the current build honestly, retire the claims that stop being true, and
lay the first brick of a new architecture (a local Python engine) —
*before* touching anything expensive.

**The thesis:** the bug was the design. Six days of work built a system
that does maximum work at all times, regardless of whether anyone needs
the answer. Fixing bugs in that design would only make the waste faster.
It wouldn't make it stop.

**Frozen reference commit:** `b60e903` (Day 6 post-ship fixes) — every
future comparison in this series names this as what it's comparing
against.

**Machine:** Apple M4 Pro, macOS, Chrome (Puppeteer-managed, headless).
Not a clean bench rig — several other processes were running concurrently
on the same machine throughout measurement. Where that mattered, it's
called out below.

---

## 2. Methodology (the part that's good content on its own)

- **Harness:** a Puppeteer script drives the app through a fake camera
  device, samples frame timing continuously via `requestAnimationFrame`,
  and reads Chrome's own `PerformanceObserver('longtask')` and
  `Performance.getMetrics` CPU counters — real browser signals, not
  guesses.
- **A real bug was found and fixed before trusting a single number:** the
  first pass fed the fake camera a 15fps test video. Headless Chrome
  throttles the **entire page's** `requestAnimationFrame` cadence to match
  a fake video source's declared frame rate — not just video decode, every
  rAF callback on the page, including detection, HUD drawing, and the
  measurement tool itself. The 15fps source was silently capping every
  number in the experiment at 15Hz. Confirmed with a standalone probe:
  15fps source → rAF locked to exactly 15.0Hz; 30fps source → rAF ran free
  at ~59.8Hz. Every number below uses a 30fps source, matching a real
  webcam.
- **Percentiles, not means.** p50/p95/max — a mean hides exactly the
  freeze this whole exercise exists to find.
- **CPU is a floor, not the whole number.** The main-thread busy fraction
  (Chrome's `TaskDuration` metric) excludes the GPU process and compositor
  thread, both doing real work for the TF.js/WebGL and WebGPU inference.
  Read every CPU% below as "at least this much."
- Each scenario ran a full 60 seconds, timed from the moment the app was
  actually ready (model load time excluded on purpose).

---

## 3. Scenarios A–E — the numbers

All five scenarios held a clean **60.0 fps**, p50/p95 delta of exactly
**16.67ms** (one 60Hz frame), and **zero** long tasks — the browser's main
thread never once blocked for ≥50ms in this session, in any scenario.

| # | Scenario | FPS | p50 | p95 | max | Long tasks | CPU floor | Narration lines |
|---|---|---|---|---|---|---|---|---|
| A | Detection only, narration off, voice off | 60.0 | 16.67ms | 16.67ms | 16.67ms | 0 | **72.7%** | 0 |
| B | A + template narration on | 60.0 | 16.67ms | 16.67ms | 33.33ms | 0 | **74.1%** | 8 |
| C | B + local-llm + local-tts (configured) | 60.0 | 16.67ms | 16.67ms | 16.67ms | 0 | **76.2%** | 8 (template fallback) |
| D | C + push-to-talk question mid-run | 60.0 | 16.67ms | 16.67ms | 33.33ms | 0 | **74.7%** | 8 (template fallback) |
| E | Idle scene, full stack loaded, nothing moving | 60.0 | 16.67ms | 16.67ms | 16.67ms | 0 | **72.4%** | **0** |

**Image:** `day7-images/04-scenario-cpu-flat.png` — bar chart of the CPU
column above, with narration-line counts alongside. The flatness across
all five bars is the visual point.

### Scenario D — "the stall" that didn't happen, and why that's the finding

The compute stall this whole exercise was built to capture **did not
happen this session** — and the reason is itself the most useful single
finding of the day.

- The local LLM (Qwen2.5-0.5B) never finished loading. D13, an earlier
  session, measured its cold load at **45–63 seconds**. This session, on
  one isolated retry, it sat in a `loading` state for **7+ minutes with
  zero forward progress** before the measurement harness gave up waiting.
  Not slow — stuck.
- The local TTS (Kokoro) failed outright on every attempt
  (`ERR_HTTP2_PROTOCOL_ERROR` / `ERR_QUIC_PROTOCOL_ERROR` fetching its
  weights) and correctly fell back to the browser's built-in voice.
- The ASR (Whisper, for push-to-talk) also never got past ~4% loaded.
- **Outbound network worked fine the whole time** — plain `curl` and a
  bare browser page both fetched the model host successfully throughout.
  The failure was specific to large, chunked model-weight downloads
  inside headless Chrome, under load, in this session — not a blanket
  connectivity problem.

**Image:** `day7-images/03-stuck-download.png` — bar chart comparing D13's
45–63s cold load and ~11s warm reload against this session's 7+ minute
stuck load.

**Two things worth saying on camera, both true at once:**
1. The fallback design (built on an earlier day) worked exactly as
   intended under a real, unplanned failure — narration kept producing
   fresh lines the whole time, the UI showed honest live state
   (`LLM: loading 0%`), nothing hung, nothing lied.
2. Because the downloads never finished, the actual computational stall —
   the moment a loaded LLM/TTS/ASR would be *computing*, not just
   fetching — was never exercised. That has to be re-measured, and this
   document says so plainly rather than quietly treating "no stall
   observed" as "no stall exists."
3. One narrow real result survived: at the exact moment push-to-talk was
   held, frame timing shows two isolated single-frame blips (33ms instead
   of 16.7ms) and nothing worse.

**Image:** `day7-images/05-scenario-d-timeline.png` — the closest thing to
a "DevTools flame chart" this headless, non-interactive environment can
produce: a chart of real recorded frame-time data across the full 60s
window, with the push-to-talk moment marked. Flat green line, two small
blips, no freeze — because nothing was actually computing yet. (Chrome
DevTools has no GUI to screenshot in this environment; this is the same
underlying signal, self-rendered and labeled as such.)

### Scenario E — the number that matters most

**The idle scene — camera pointed at a flat, unmoving frame — burned
essentially the same CPU as every busy scene: 72.4%, against 72.7% for
plain detection and 76.2% for the full stack configured.** For a full
minute, it produced **zero** narration lines.

Why: the current detector has no motion gate at all. It runs a full
object-detection pass on every single frame at 60Hz, whether or not
anything in the scene has changed. Interestingly, the LLM/TTS engines
*didn't* run uselessly here — with nothing to detect, no narration event
ever queued, so the "generate ahead" prefetch never even started. The
waste in this architecture is specifically in the **detection loop**, not
evenly spread across every engine.

**The ratio:** ~72% of one CPU core, continuously, for output a human
would consume zero of. Expressed the other way — **100% of scenario E's
measured compute went toward nothing anyone would notice.**

**Image:** `day7-images/04-scenario-cpu-flat.png` (same chart as above —
bottom red bar is E).

---

## 4. What survives the pivot, stated plainly

Not a failure narrative. Six days produced a real perception pipeline, an
event layer, a tracker, a HUD design language, and an honesty discipline —
all of which carry forward. What changes is *where* inference runs and
*when* it's allowed to.

**Image:** `day7-images/01-architecture-before-after.png` — side-by-side:
the old single-tab, zero-worker, three-uncoordinated-runtime browser
architecture, next to the new split (browser = HUD only, Python = a
separate process talking to it over a local connection).

**The new architecture's core rule (decided before writing the first line
of Python, not after a bug):** process-per-workload, never thread-per-
workload — Python has a GIL, the same shape of problem as the browser's
single main thread, and porting everything into one Python process would
just reproduce the exact same stall in a new language. Frames cross
process boundaries through a **latest-wins queue of depth 1** — drop
frames, never buffer. A queue that grows is latency that grows; a stale
frame is worthless.

**The tier scheduler, the actual fix (planned, not all built yet):**

**Image:** `day7-images/02-tier-scheduler.png` — T0 (always on, ~1–3%
CPU, no neural nets — this is the layer Day 7 actually built) through T3
(expensive, rare, only when the user is waiting for an answer).

- **T0 — always on:** motion detection, voice-activity detection. Cheap
  by design.
- **T1 — ambient sense:** object detection + tracking, but only when
  motion clears the T0 gate. Not built yet — Day 8.
- **T2 — deep look:** depth, segmentation, pose, face, OCR. On demand
  only. Day 12–13.
- **T3 — respond:** speech-to-text → intent → LLM → text-to-speech, only
  after a wake word or push-to-talk. Day 10–11.

The reframe in one line: *"JARVIS answers. He does not narrate."* Right
now this project is an always-on commentator that happens to have a
camera. The goal is a system that's quietly aware, expensively smart only
on request, and almost always silent.

---

## 5. The Python engine (what actually got built this session)

A skeleton: **camera → motion gate → JSON lines on stdout.** No model, no
tracker, no HUD, no networking yet — proving the plumbing before anything
expensive sits on it.

- **Camera access from Python, verified for real.** First attempt failed
  with a macOS permission error (`not authorized to capture video`) — the
  exact kind of speed bump that eats a morning if discovered later instead
  of now. A later attempt in the same session succeeded, camera reporting
  1920×1080 at 30fps.
- **The motion gate is genuinely cheap** — pure frame-differencing, no
  model. Measured cost:
  - Against a synthetic (generated) frame: **0.25ms median**, 1.25ms max.
  - Against the real camera at native resolution, downscaled for the
    gate: **1.31ms median**, 2.60ms max — modestly over the ~1ms target,
    for a known, explained reason (the downscale step itself, which the
    synthetic frame never has to pay for).
- **The process boundary holds.** Camera capture runs in its own OS
  process; frames cross to the consumer through the latest-wins,
  depth-1 queue described above. Verified working both with a synthetic
  frame generator and the real camera — no buffering observed in either
  case.
- **Gated fraction on a still scene: 100%** over a full 65-second run,
  both synthetic and real camera. In other words: point the camera at a
  quiet room and, with this gate in place, **not a single frame** would
  have reached a downstream detector. This is the strongest available
  number for why the tier scheduler matters — though it still needs a
  cross-check against a scene with real, intermittent human motion (the
  actual target use case) before being treated as fully settled.

---

## 6. Claims retired (and what replaces them)

Days 1–6 were sold on three sentences. As of Day 7, they're struck
through, dated, and replaced — never quietly deleted:

> ~~"No backend"~~ — **retired Day 7.** The engine is now a local Python
> process on your own machine, and an optional private server (hardware
> you own) is planned for later. Replacement: *"the backend is a process
> on your machine, not someone else's server."*

> ~~"Runs entirely in your browser"~~ — **retired Day 7.** The browser is
> now the interface; a local Python process does the seeing. Replacement:
> *"the interface is a browser tab; the eyes are a local process."*

> ~~"Video never leaves your device"~~ — **true through the next several
> planned days**, changes once an optional private server ships later.
> Replacement when that lands: *"your data goes to hardware you own, and
> nowhere else."*

**What survives unchanged, and is now the strongest remaining claim:**
**"No API keys."** No third-party cloud service — no cloud vision, no
cloud LLM, no cloud TTS/STT — has been called once across this entire
project, Day 1 through today. That does not change.

---

## 7. The honest answers, in one place

1. **Did the frame timing ever actually freeze?** No — not once, in any
   scenario, this session. Zero long tasks recorded anywhere.
2. **Does that mean there's no stall to fix?** No — it means the models
   never finished loading, so the actual compute-stall moment was never
   reached. What *was* captured: three independent model-loading
   pipelines (LLM, TTS, ASR) with no shared coordination or retry policy,
   one of them stuck for 7+ minutes on a machine with working general
   network access. That's the same "uncoordinated, always-maximal-effort"
   diagnosis the pivot is built on — caught in the act, a different way
   than planned.
3. **What's the single strongest number from today?** Scenario E: ~72% of
   one CPU core, continuously, producing zero narration lines in a full
   minute — and it's specifically the always-on detection loop causing it,
   not the LLM/TTS (which are already at least event-gated by an earlier
   day's design).
4. **Does the Python skeleton actually work?** Yes — camera capture, the
   motion gate, and the depth-1 process-boundary queue are all verified,
   against both a synthetic frame source and the real camera.
5. **What's explicitly unfinished, carried to Day 8+?** A real scenario-D
   compute stall (needs a successful model load to measure); cross-
   checking the still-scene gated-fraction against real intermittent
   motion; and everything past T0 in the tier scheduler (T1 detection,
   T2 deep-look, T3 respond) — none of that is built yet, all of it is
   planned.

---

## Image index

| File | What it shows |
|---|---|
| `day7-images/01-architecture-before-after.png` | Browser-only (Days 1–6) vs. browser + Python engine (Day 7+) |
| `day7-images/02-tier-scheduler.png` | The T0–T3 attention budget, what's built vs. planned |
| `day7-images/03-stuck-download.png` | Model load time: 45–63s measured before vs. 7+ min stuck today |
| `day7-images/04-scenario-cpu-flat.png` | CPU floor across scenarios A–E — flat regardless of activity |
| `day7-images/05-scenario-d-timeline.png` | Frame-time timeline during the push-to-talk moment — no freeze |
