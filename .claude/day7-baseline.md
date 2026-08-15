# Day 7 baseline — the before-picture

**Frozen reference commit:** `b60e903` (Day 6 post-ship fixes), one commit
ahead of `origin/master` at the start of this session. Every future
comparison in this series names what it's comparing against — this is that
name.

**Machine:** Apple M4 Pro (per `v2-architecture-research.md` §4), macOS,
Chrome (Puppeteer-managed, headless). **This machine was not idle during
measurement** — several other processes (other Claude Code sessions) were
running concurrently on it, discovered mid-session when a bench run that had
succeeded once started timing out for no code reason. Where that mattered,
it's called out below. This is a real machine doing real multitasking, not a
clean bench rig — stated plainly per the day's own honesty rules.

---

## Methodology

- **Harness:** `scripts/bench.mjs`, headless Chrome via Puppeteer, driving
  the app through `--use-fake-device-for-media-stream` +
  `--use-file-for-fake-video-capture=<file>.y4m`. Run against `npm run dev`
  (not the production preview) because local-tts (Kokoro) only works there —
  see decisions.md D13. `?bench=1` gates a small recorder
  (`src/bench/frameRecorder.ts`) that is otherwise entirely inert.
- **A methodology bug found and fixed before trusting any number:** the
  first pass used a 15fps source video. Headless Chrome throttles the
  *page's entire rAF cadence* to match the fake video source's declared
  frame rate — not just `<video>` element updates, every `requestAnimationFrame`
  callback on the page, including the detect loop, the HUD draw loop, and
  this bench recorder itself. A 15fps source was silently capping every
  number in this document at 15Hz — a measurement artifact, not a real
  cost. Confirmed by a standalone probe: 15fps source → rAF locked to
  15.0Hz; 30fps source → rAF ran free at ~59.8Hz. All numbers below use a
  **30fps source** (`scripts/generate-bench-assets.sh`), matching a
  plausible real webcam.
- **Frame timing:** `frameDeltas` = ms between consecutive `rAF` callbacks
  on the main thread, recorded continuously. `longTasks` = the browser's own
  `PerformanceObserver('longtask')` entries (≥50ms main-thread blocks).
  Percentiles (p50/p95/max), not means — the mean hides exactly the freeze
  this document exists to find.
- **CPU proxy:** Chrome DevTools Protocol `Performance.getMetrics`'s
  `TaskDuration` (cumulative main-thread busy seconds), delta over the
  measured window ÷ wall-clock window = the fraction of one CPU core the
  renderer's **main thread** kept busy. This is the closest thing this
  headless, non-interactive environment can produce to an Activity-Monitor
  reading for a specific process — but it is a **floor, not the whole
  number**: it excludes the GPU process and the compositor thread, both of
  which are doing real work for TF.js/WebGL and WebGPU inference. Read
  `cpuFraction` as "at least this much," not "exactly this much."
- **Each scenario runs 60s**, timed from the moment the camera+model (and,
  where the scenario needs them, the LLM/TTS) are confirmed ready — model
  load time is excluded from the timed window on purpose; it's a separate,
  already-measured number (D13: ~45–63s cold, ~11s warm).
- Raw JSON per scenario: `scripts/bench-output/scenario-{A..E}.json` (not
  committed — regenerate with `scripts/generate-bench-assets.sh` then
  `node scripts/bench.mjs`).

---

## Scenarios A–E

All five ran the full 60s window at a clean **60.0 rAF fps**, p50/p95 delta
**16.67ms** (exactly one 60Hz frame) in every scenario, and **zero**
`longtask` entries anywhere. That flat result is itself a finding — see
"the stall" below for why it's not the whole story.

| # | Scenario | FPS (rAF) | p50 delta | p95 delta | max delta | Long tasks | CPU (main-thread floor) | Narration lines |
|---|---|---|---|---|---|---|---|---|
| A | Detection on, narration off, voice off | 60.0 | 16.67ms | 16.67ms | 16.67ms | 0 | **72.7%** | 0 |
| B | A + template narration on | 60.0 | 16.67ms | 16.67ms | 33.33ms | 0 | **74.1%** | 8 |
| C | B + local-llm + local-tts (config) | 60.0 | 16.67ms | 16.67ms | 16.67ms | 0 | **76.2%** | 8 (template, see below) |
| D | C + push-to-talk question mid-run | 60.0 | 16.67ms | 16.67ms | 33.33ms | 0 | **74.7%** | 8 (template, see below) |
| E | Idle scene, full stack loaded, nothing moving | 60.0 | 16.67ms | 16.67ms | 16.67ms | 0 | **72.4%** | **0** |

### Scenario D — the stall, described precisely (and what didn't get captured)

**The honest headline: the compute stall the episode is supposed to show did
not happen this session, and the reason why is itself the most useful single
finding of the day.** Configured for scenario C/D, `line_generator_engine:
'local-llm'` and `voice_engine: 'local-tts'` never left the `loading` state
in either scenario — confirmed via the app's own `llmStatus`/`ttsStatus`
(exposed to the harness as `window.__yapStatus`), and separately via the
push-to-talk voice panel, which showed `ASR loading 4%` the entire time
scenario D's push-to-talk was held. **Qwen2.5-0.5B, measured at 45–63s cold
in D13's own earlier session, sat in `loading` for 7+ minutes with zero
forward progress** on one isolated retry today before the harness gave up
waiting — not slow, stuck. Kokoro TTS failed outright on every attempt
(`ERR_HTTP2_PROTOCOL_ERROR` / `ERR_QUIC_PROTOCOL_ERROR` fetching its weights,
falling back to `speechSynthesis` exactly as D13's fallback design intends).
Plain `curl` and a bare Puppeteer page both fetched `huggingface.co`
successfully throughout the same window, so this isn't a blanket
connectivity failure — it's specific to large chunked model-shard fetches,
in headless Chrome, on a machine running several other concurrent processes
this session (see the machine note at the top of this document).

Two consequences, both worth stating plainly:
1. **`generate-ahead`/fallback (D13) worked exactly as designed under real
   failure**, not just in a synthetic test: narration kept producing fresh
   template lines throughout scenario D (`"a dining table appears. no one
   asked, but here we are..."`), the UI showed honest live state
   (`LLM: loading 0%`, `TTS: loading 16%`, `ASR: loading 4%`) rather than
   hanging or lying, and frame timing never degraded. This is the D13
   fallback path getting a real, unplanned stress test — and passing it.
2. **Because the LLM/TTS/ASR fetches never resolved, the actual inference
   stall this episode is built around — the moment those models are loaded
   and computing — was not exercised this session.** The zero-long-task,
   flat-CPU result for scenarios A–D describes "detection + draw + template
   narration + three stalled model downloads in flight," not "detection +
   draw + narration while an LLM/TTS/ASR are actively computing." The
   in-flight downloads themselves cost nothing measurable on the main
   thread (fetches are off-thread) — which is a real, honest data point,
   just not the one the day was built to capture. **For what the loaded-
   engine compute cost actually looks like, D13's own numbers are the best
   available evidence and are borrowed explicitly here, not re-claimed as
   today's**: LLM inference 350–567ms per line, Kokoro TTS first-call
   latency ~3–4s (dev-server only, per D13's standing production-build
   caveat).
3. A concrete, narrower finding *did* survive: at the moment push-to-talk
   was held (`askedAtMs` 28.5s into the window), frame timing shows **two
   isolated ticks at 33.33ms (one dropped 60Hz frame each), nothing worse** —
   see `.claude/day7-scenario-d-timeline.png`. Not a freeze, because ASR
   itself never got past 4% loaded.

**This needs re-running once network conditions allow a real model load to
complete** — flagged explicitly for Day 8, not silently treated as "no
stall exists." See `v2-roadmap.md`'s Day 7 update.

### Scenario E — the always-on cost, and the number that matters most

**The idle scene burned essentially the same CPU as every busy scene —
72.4%, against A's 72.7%, B's 74.1%, C's 76.2% — for zero output.**
`window.__yapStatus.detectFps` stayed at ~60Hz throughout scenario E's full
minute pointed at a flat, unmoving gray frame — the current (V1) detector
has no motion gate at all, so TF.js runs a full COCO-SSD inference pass on
every single rAF tick regardless of whether the frame changed since the
last one. `lineCount` stayed at **0** the entire 60s — with nothing in
frame to detect, zero narration events ever queued, so (as a direct
consequence) the LLM/TTS prefetch path never even attempted to start —
`llmState`/`ttsState` sat at `idle`, not `loading`, the only scenario where
that was true. That's a genuinely different failure shape than "the LLM
runs uselessly in the background" — in this architecture the *detector*
is the always-on cost; the LLM/TTS are at least already event-gated by
design (D13's generate-ahead only fires `prefetch(event)` when an event is
queued).

**The ratio the research doc asks for:** ~72% of one CPU core, continuously,
producing **0 of 0** narration lines a human would have heard in that
minute. Expressed the other way: **100% of scenario E's measured compute
went toward work that produced nothing anyone would notice.** This is
measured, not modeled, and it is a clean, strong number *for* the tier
scheduler's T0/T1 split (v2-architecture-research.md §2a) — motion gating
the detector is precisely the fix for exactly this measured waste, and it's
a detection-loop problem specifically, not (this session) an LLM/TTS
problem, which is a more precise diagnosis than the research doc's original
framing assumed. See "answers to the prompt's own questions" below.

### Trace

Chrome DevTools has no interactive GUI session in this headless,
non-interactive environment — there is no panel to screenshot. What exists
instead, made from this session's own `?bench=1` recording (the same
underlying signal a DevTools flame chart reads: main-thread frame time over
time, with the push-to-talk moment marked): **`.claude/day7-scenario-d-timeline.png`**
(`scripts/render-scenario-d-chart.mjs`). It shows a flat 60fps green line
for the entire window with two isolated single-frame blips around the
push-to-talk mark — consistent with "the stall" above: nothing froze,
because nothing was actually computing yet.

---

## The Python skeleton (`engine/`)

- **Camera access from Python, verified live** (not assumed): the first
  attempt from a colder process context failed with `OpenCV: not authorized
  to capture video` — the exact macOS-permission speed bump
  day7-prompt.md predicted landing on Day 8 if undiscovered today. A later
  attempt in the same session succeeded (`cv2.CAP_AVFOUNDATION`, 1920×1080@30
  reported by the device) — camera access for this host process had already
  been granted at the OS level. **Practical takeaway for Day 8:** the first
  real-camera run on a fresh machine/profile will trigger a one-time macOS
  permission dialog for whatever process hosts the shell; grant it once,
  it's not repeated. `engine/README.md` says this in two lines.
- **Motion gate cost, measured** (`engine/motion.py`, 160×120 grayscale
  frame differencing):
  - Synthetic frame source (multiprocess path, `--synthetic`), 65s / 1665
    frames: gate p50 **0.25ms**, p95 **0.49ms**, max **1.25ms**.
  - Real camera (1920×1080 native, downscaled to 160×120 for the gate),
    65s / 1919 frames: gate p50 **1.31ms**, p95 **1.65ms**, max **2.60ms**.
  - **Honest read:** the ~1ms target (day7-prompt.md) holds for the
    synthetic path and is exceeded, modestly, on the real camera at its
    native 1920×1080 capture resolution — the downscale itself
    (`cv2.resize`, `INTER_AREA`, full-res → 160×120) is the added cost the
    synthetic frame never pays, since `make_synthetic_frame` is generated
    small. Revisit if T1 ends up wanting the gate cost that's already this
    close to a shared frame budget with a real detector loop.
  - `captureMs` (blocking `cap.read()`, includes waiting for the next
    camera frame — an honest number, not just decode time) sat around
    **32–34ms**, consistent with the camera's own reported 30fps.
- **Process boundary + latest-wins queue (D29), verified working**: both
  the synthetic and real-camera runs go through the same
  `multiprocessing.Process` capture worker and depth-1 `Queue`
  (`capture.py`'s `put_latest` — drain, then insert, never block, never
  grow). No buffering behavior observed in either run.
- **Gated fraction on a still/near-still scene:** synthetic (near-static
  slow-moving synthetic shape) — **100% gated** over the full 65s/1665-frame
  run. Real camera pointed at a mostly-still desk scene — **100% gated**
  over the full 65s/1919-frame run (`motion` stayed in the 0.0–0.0134
  range, `MOTION_THRESHOLD = 4.0` on a 0–255 scale). **This number needs
  the caveat day7-prompt.md itself asks for:** a genuinely still room over a
  full minute produced zero non-gated frames in both runs — a strong
  headline number for Day 8's tier-scheduler pitch, but not yet
  cross-checked against a scene with real, intermittent human motion (someone
  walking through periodically), which is the actual target use case and
  the next thing to measure once T1 exists to gate.

---

## Answers to the prompt's own questions

1. **The stall, described precisely:** it didn't happen this session, and
   that's a finding, not a gap to paper over. Every scenario, including
   push-to-talk mid-flight, held a clean 60fps with zero long tasks, because
   the LLM (7+ minutes stuck `loading`, never resolved), TTS (failed outright
   on every attempt, correct fallback triggered), and ASR (stuck at 4%
   loaded) never actually reached the compute stage this episode is about —
   only the download stage, which costs nothing on the main thread. The
   *download* stalling for this long, repeatedly, in a session with working
   general network access, is itself a real finding about running three
   independent model-loading pipelines with no shared coordination or
   retry/backoff policy (v2-architecture-research.md §1b/§1c) — it's a
   different kind of "the design does maximum uncoordinated work" evidence
   than a frame freeze would have been, not a weaker one.
2. **Scenario E's verdict:** yes, and more precisely than assumed going in.
   The always-on cost is real and large (~72% of one CPU core, continuously,
   for zero output over a full minute) — but it's a **detection-loop**
   problem in this architecture, not an LLM/TTS one: with nothing in frame,
   the LLM/TTS prefetch path never even starts (event-gated by D13's own
   design), while the 60Hz TF.js detector runs full inference on every tick
   regardless of scene content. This *sharpens* the tier scheduler's case
   rather than weakening it — T0's motion gate (proven cheap today, see
   below) is aimed at exactly the actual waste, not a diffuse one.
3. **Does the Python skeleton stand:** yes — camera capture, the motion
   gate, and the depth-1 process boundary all verified working, both against
   a synthetic frame source and a real camera. Gate cost is under budget on
   synthetic frames and modestly over budget (~1.3ms median) at the real
   camera's native downscale cost — a real number to design T1 against, not
   an assumption.
4. **What was cut:** the optional Web Worker experiment (§ of day7-prompt.md)
   — moot this session since there's no detection loop in `engine/` yet to
   move off-thread, and the browser build's own detect loop showed zero
   long-task evidence to chase. A genuine scenario-D compute stall was not
   captured (see above) and needs a re-run once model downloads complete
   reliably — carried to Day 8 explicitly, not silently dropped.
5. **What Day 8 inherits:** the real-camera gate cost (~1.3ms, not ~1ms) as
   a design input; the still-scene gated-fraction as a strong but
   single-condition number that wants a real-motion comparison before it's
   treated as settled; and the sharpened diagnosis that the detection loop,
   specifically, is where scenario E's waste lives — which argues T1's
   motion-gated detector (already the Day 8 plan) is targeting the right
   thing. Also inherits an open item: re-measure scenario D with a fully
   loaded LLM/TTS/ASR stack once that's reliably achievable.
6. **Anything measured today that contradicts the V2 plan:** nothing
   contradicts the plan, but one assumption needs sharpening: the research
   doc's stall narrative (§1a, "any one of these blocking stalls all the
   others") is framed around LLM/TTS computation colliding with the frame
   loop. Today's data suggests the browser build's detection loop is the
   dominant, unconditional cost (scenario E), while LLM/TTS are already
   *conditionally* triggered (only on a narration event) rather than
   constantly running — so the T1 motion gate (Day 8) is doing more of the
   real work here than the T2/T3 on-demand gating, at least for this
   specific always-on-cost question. Both are still correct and both still
   ship; this just says which one is carrying more of scenario E's number.
