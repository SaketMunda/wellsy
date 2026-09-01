# V2 Roadmap — Days 7–15

Supersedes Days 7–8 of `week-roadmap.md`. Days 1–6 shipped and stand.
Architecture and reasoning: `v2-architecture-research.md` — this file is the
schedule, that file is the *why*. Phase numbers below refer to its §9.

**The frame:** Days 1–6 built a system that talks at you. V2 builds one that
answers you. Everything below serves the reframe in §2 — *JARVIS answers, he
does not narrate* — which is simultaneously the product fix and the
performance fix.

**Hard constraints on this schedule:**
- **Day 15 is a filming and shipping day, not a building day.** The thing
  that gets demoed on Day 15 must be working at the end of Day 14. Nothing
  new lands on 15.
- Nine days is tight for a runtime migration. **§"If it slips" at the bottom
  is not decoration** — read it before Day 12, not after.
- Every day still ends with something filmable. A day whose only output is a
  refactor is a day the series can't use.

---

## The series arc (so the episodes have a shape)

| Days | Beat |
|---|---|
| 7 | **The confession.** I promised an Iron Man HUD and built a chatty box. Here's the profiler proving why. |
| 8–9 | **The rebuild.** New engine, same face. It stops being wrong about what it sees. |
| 10–11 | **It answers.** The JARVIS moment, then the voice stops being annoying. |
| 12 | **It knows who I am.** |
| 13 | **It sees in depth.** The visual payoff episode. |
| 14 | **It fits in a pocket.** |
| 15 | **Ship.** |

The pivot itself is the best content in the series. *"I built the wrong thing
for six days, here's the exact moment I realised"* outperforms another polish
day, and it's true.

---

## Day 7 — "I built the wrong thing" (the autopsy + the foundation) — SHIPPED ✅
**Phase 0 + the start of Phase 1.** Full numbers: `day7-baseline.md`.
decisions.md D28 (the pivot itself) and D29 (the depth-1 queue rule, decided
before `engine/`'s first line, not after a bug).

**What Day 8 should know before starting:**
- The motion gate's real-camera cost (~1.3ms p50 at native-resolution
  downscale) is measurably above the ~1ms target this file and
  `v2-architecture-research.md` assumed — a known, explained gap (the
  downscale itself), not a surprise to rediscover. Budget T1 accordingly.
- The still-scene gated-fraction (100% over 65s, both synthetic and real
  camera) is a strong number but a single-condition one — it hasn't been
  checked against a scene with real intermittent motion yet, which is
  actually the case the tier scheduler is being built for. Worth an early
  Day 8 check once T1 exists to gate.
- A real methodology trap was found and fixed today, worth remembering for
  any future headless-Chrome measurement in this project: a fake video
  source's declared frame rate throttles the whole page's `requestAnimationFrame`
  cadence in headless Chrome, not just video decode. Always use a source fps
  at or above the real target rate (30fps here), or every rAF-driven number
  quietly caps at the source rate.
- **The compute stall itself was not captured this session** — the
  local-llm/local-tts/ASR stack got stuck mid-download (network conditions,
  not a bug) and never reached the compute stage, so scenario D shows zero
  long tasks by construction, not by disproof. Re-run once model loads are
  reliable, before treating "the browser build never visibly stutters" as
  settled either way.
- **Scenario E sharpened the diagnosis**: the ~72%-of-one-core always-on
  cost is a **detection-loop** problem, not an LLM/TTS one — with nothing in
  frame, the LLM/TTS prefetch never even starts (D13's own event-gating
  already does that part), while the 60Hz detector runs full inference
  regardless of scene content. T1's motion gate (this file, Day 8) is
  targeting exactly the right thing; T2/T3's on-demand gating matters more
  for other reasons (§2b's speech policy, mobile battery) than for this
  specific idle-cost number.

**Ships:**
- **Honest before-numbers** on the current build: FPS, inference ms,
  main-thread long-task duration, and specifically what frame timing does the
  moment LLM and TTS fire. **Capture the stall on video** — it is the whole
  episode.
- **Measure what idle costs.** This is the §2 baseline: how much compute the
  system burns answering a question nobody asked.
- **Retire the false claims in `public-notes.md`** — "no backend", "video
  never leaves your device", "runs entirely in your browser". Explicitly
  struck through with the date, not quietly deleted. A private server is
  coming and those sentences stop being true.
- **Python skeleton**: `uv` project, camera capture via PyAV/OpenCV
  (AVFoundation), frame-differencing motion gate, JSON frames to stdout.
  Headless, no model yet — prove the plumbing and the process boundaries
  before anything expensive sits on them.
- Commit the outstanding D26/D27 fixes first, so the browser build is a clean
  frozen reference point.

**Concept:** Every number in the research doc is from someone else's machine.
Today produces ours — and the before-half of a comparison that only gets to
exist once.

**Demo:** Split screen: the frame-time graph flatlining the instant narration
fires, next to the idle CPU reading of a system that's computing an answer to
a question nobody asked.

**Hook:** *"Six days in, I profiled my own project and found the bug was the
design. It's been doing maximum work at all times, whether or not anyone was
listening."*

**Risk:** Half a day of measurement can become a full day of yak-shaving on
Python camera permissions on macOS. Timebox the skeleton to 3 hours; the
numbers are the deliverable, the skeleton is the head start.

---

## Day 8 — "It stops being wrong" (Phase 1) — SHIPPED

**Shipped:**
- **YOLOE via Ultralytics on PyTorch/MPS at 8 Hz**, open-vocabulary and
  text-promptable — not MLX (see below). `engine/prompts.txt` drives
  `model.set_classes()`; open vocabulary works exactly as planned, only the
  runtime differs from the original spec.
- **ByteTrack** (`supervision`) replaces the hand-rolled IoU tracker.
  D11/D21/D27 retired — `decisions.md` D31 explains why each was right for
  the old detector and what makes it unnecessary now.
- **The tier scheduler, built on day one.** T0 always-on motion gate with
  ~1s hysteresis (a paused gesture doesn't freeze mid-frame); T1
  detect+track at 8Hz max, rate-limited and gate-controlled; T2/T3 exist as
  real wired stub functions (`engine/tiers.py`) plus a `PreemptionSeam`
  class, doing nothing yet.
- Measured: 76.4 FPS unthrottled, ~6-8% idle CPU with the gate vs ~18-23%
  with it forced off, 5-minute memory stability, kill-capture-doesn't-hang.
  See `.claude/day8-results.md` for the full table.

**What changed from the plan — MLX:** checked directly (not assumed after a
failed attempt) that no PyPI package implements an open-vocabulary detector
on MLX — `mlx`/`mlx-metal`/`mlx-vlm`/`mlx-image` all exist and install, but
none of them are YOLOE. Building YOLOE's text-prompt head from scratch in
raw MLX ops is a multi-day project, not an afternoon's conversion fight —
so there was nothing to timebox; the gap was structural, found in under an
hour. Took the PyTorch/MPS path instead, which is strictly closer to the
original intent than the plan's own named fallback (YOLO26, non-open-vocab)
since it keeps text-prompting. Full reasoning: `decisions.md` D30.

**What didn't get real evidence:** no camera access this session (sandboxed,
no display/hardware) — the intermittent-motion test ran against a staged
synthetic clip, not a real room. `MOTION_THRESHOLD` stays at 4.0,
unchanged, explicitly *not* tuned (D32) — the gate's open/close logic was
confirmed correct, but a synthetic high-contrast bar doesn't stand in for
real lighting/noise, so tuning against it would be tuning by feel with
extra steps. The bed/microphone shot wasn't taken for the same reason —
`engine/debug_window.py` is written but untested against real hardware.

**What Day 9 should know before starting:**
- **JSONL shape is settled** (`engine/README.md`): `detections`, `tracks`
  (id/label/score/bbox/ageMs/missedFrames/labelConfidence/runnerUpLabel/
  labelVotes — matches `src/vision/types.ts`'s `Track` closely enough that
  the bridge should be plumbing), `inferenceMs` (null = T1 didn't run this
  frame, tracks/detections are a carried-forward repeat, not empty).
- **End-to-end capture→track latency is ~75-85ms** (p50/p95, synthetic) —
  this is Day 9's floor before any network/render latency stacks on top.
  D15's τ=70ms interpolation (browser build) was designed for exactly this
  kind of gap between real updates.
- **A still scene never goes empty** — T1's last output is held and
  re-emitted on gated/rate-limited frames on purpose. If Day 9's bridge (or
  the HUD) ever shows an empty room while the JSONL still has non-empty
  `tracks`, that's a bridge bug, not an engine one.
- **Camera hardware is needed** for the first real validation of
  `MOTION_THRESHOLD`, the bed/microphone shot, and `debug_window.py` — none
  of those got real evidence this session; flag this early if Day 9 also
  runs sandboxed.
- **No WebSocket/HUD work happened today** — `src/` has zero diff, exactly
  as required.

---

## Day 9 — "Same face, new engine" (Phase 2) — SHIPPED

**Shipped:**
- **Local WebSocket bridge**, `127.0.0.1` only (`engine/bridge.py`,
  `websockets.sync.server` on a background thread). `engine/main.py`'s
  stdout `emit()` is byte-identical to Day 8; the bridge is a separate
  payload built alongside it, carrying two extra fields
  (`sourceWidth`/`sourceHeight`) for the coordinate contract.
- **`src/vision/useEngineSocket.ts`** — same `Frame` shape as
  `useDetector.ts`. `hudState.ts`/`drawHud.ts`/`HudCanvas.tsx` needed **zero**
  changes — `git diff --stat -- src/hud/` is empty. Every Day 9 change lives
  in `App.tsx`, `App.css`, and this one new file.
- **`?engine=1` flag**, default off — the browser-only build (Days 1–6) is
  unaffected when the flag is absent; `useDetector` runs exactly as before.
- **Latest-wins crossing the socket** (D29's rule, now a third layer: queue,
  process boundary, WebSocket) — `onmessage` unconditionally overwrites
  `frameRef.current`, no queue, no buffering.
- **Staleness handling** — a 1s timeout, plus a disconnect-after-live
  degrading to `stale` (not a hard `error`) so the last real frame stays on
  screen, honestly marked old, per the same discipline as `UNIDENTIFIED`
  (D22). Measured: banner visible 1005ms after the engine was killed.
- Full writeup: `decisions.md` D35, `.claude/day9-results.md`.

**Camera access: real, confirmed working this session — a correction.** An
earlier pass of this document wrongly claimed "no camera access, sandboxed,
same as Day 7/8," copied without re-testing. Actually tried, after the
user pushed back on it: the real camera opens and reads real frames, both
from Python (`cv2.VideoCapture`) and the browser (headless Chrome's
`getUserMedia`), separately and **simultaneously** — confirmed directly,
not assumed. What followed with real hardware: `MOTION_THRESHOLD` retuned
from real footage (D34), a real bed correctly labeled `bed` through the
live HUD (screenshot in day9-results.md), real end-to-end latency measured
(p50 77ms, matching Day 8's synthetic estimate), and architecture (A)
confirmed rather than assumed. The one item that stayed unresolved with a
specific, real reason (not a blanket access excuse): τ — see
`decisions.md` D35 and `day9-results.md` for the full account, including
three real attempts.

**What changed from the plan:** the bridge's broadcast rate needed its own
throttle separate from `main.py`'s existing `DETECT_INTERVAL_S` gate — the
first version broadcast at capture rate (~26-30Hz) whenever `--no-detect`
bypassed the detection cadence check, which the plan's "8Hz not 60Hz" rule
didn't anticipate as a distinct code path. Fixed with a bridge-only
`last_broadcast_time` throttle; stdout stayed untouched either way.

**Concept, confirmed rather than just claimed:** the seam between "what is
true" and "how it's drawn," drawn on Day 2, survived a total engine
transplant with a measured zero-line diff in `src/hud/`.

**Demo, shot for real:** a real bed, correctly labeled `bed` (not `dining
table`) through the live HUD with a real person tracked, real narration
reacting to real tracks — screenshotted this session (`day9-results.md`).
The full "detection runs at 8Hz and nobody could tell" reveal (with a
frame-graph recording) is still unfilmed, but the underlying claim is now
demoed on real hardware, not just plumbing-verified on synthetic data.

**What Day 10 should know before starting:**
- **`?engine=1` works end-to-end on real hardware**, confirmed this
  session: real camera, real bed detection, real end-to-end latency
  (p50 77ms), real dual-camera-access (architecture (A) confirmed, not
  assumed), real staleness/engine-death behavior.
- **`MOTION_THRESHOLD` is now 5.0**, tuned against two real clips (D34) —
  not carried forward untouched a third time.
- **τ=70ms is unchanged, and the reason is now specific:** three real
  burst-screenshot attempts found the motion gate (even at 5.0) doesn't
  clear for a seated person's localized gestures — it averages motion over
  the whole downscaled frame, so a hand near a face is too small a
  fraction to register. T1 never re-ran during any of the three windows,
  so there was nothing fresh to interpolate toward. **Needs full-body
  motion** (standing, walking across frame) to actually test — not another
  camera-access excuse, a specific next step. See day9-results.md.
- **A process-management gotcha, worth knowing before Day 10 scripts
  anything against `main.py`:** `uv run python main.py`'s wrapper process
  does not exec-replace itself — killing the wrapper's PID orphans the real
  Python process, which keeps holding the WebSocket port. Kill the process
  group, not the PID `uv run` hands back.

---

## Day 10 — "JARVIS, what am I looking at?" (Phase 3) ⭐ — SHIPPED

**The centrepiece day. Zero LLM in the path.**

**What shipped, real hardware, real evidence:** the query loop end to end
(`engine/query_loop.py`: mic → VAD → Moonshine → `parseIntent` → forced-
fresh-T1 → `describeScene` → `say` → speakers), `PreemptionSeam` finally
wired to a real caller (D36), a real live success captured (`"what do you
see?" -> "two things: a person and a glasses."` in 119.1ms post-transcription),
ambient narration off by default (D38), wake phrases via transcribe-then-
match (D39), and audio confirmed audible by a human for the first time in
the project's history. Full numbers, including the honest gaps: see
day10-results.md.

**What did NOT ship as planned, stated plainly:**
- **TTS is macOS `say`, not Kokoro/Piper** — a deliberate, documented
  deviation (D39) to guarantee the nine-day-overdue audibility check
  actually closed this session rather than risking another D13-style
  bundler saga. Piper stays the real upgrade path once voice quality
  matters more than the gap it closed.
- **The wake-word acceptance bar (10 min / 20 utterances) was not run** —
  only a handful of live utterances were tried. What it *did* surface: a
  real, live collision — the wake word keeps transcribing as "app." A replacement
  phrase was discussed but deliberately deferred to the project owner's
  judgment rather than picked under session time pressure.
- **The full wake/press → first-spoken-word latency (roadmap's own row 1)
  was not cleanly captured** — the breakdown logging existed but the first
  live run was interrupted before it printed; the fix shipped for the next
  run, but that run didn't happen this session (mic permission ended up
  scoped to Terminal.app only, not the VS Code integrated terminal or the
  agent's own process — three different permission contexts on the same
  machine, a real and mildly absurd macOS TCC finding worth keeping for the
  write-up).

**What Day 11 should know before starting:**
- The deterministic loop works and has a *partial* real latency number
  (119.1ms for intent→TTS-start alone) to compare an LLM-in-the-loop
  version against — get the full wake-to-answer number in the first few
  minutes of Day 11, the instrumentation is already there.
- The forced-fresh-T1 cost is small and real (33.4ms) — budget any new
  LLM-path latency against that, not against zero.
- The wake word needs a new name before more wake-word polish is worth doing.
- Mic permission on this machine is scoped **per actual process**, not
  per-user — Terminal.app, VS Code's integrated terminal, and this agent's
  own process tree each need their own grant. Worth remembering before
  losing time to it again.
- **Explicit product ask, stated after the Day 10 retest, for a coming
  day, not now:** the user wants TTS to sound genuinely human, including
  emotional expressiveness — not the flat, reliable-but-robotic `say
  -v Samantha` voice this session deliberately shipped with. This is the
  Piper upgrade already named as the path in D39, now with an explicit
  emotion/expressiveness requirement on top of just "not robotic" — worth
  scoping as its own demo beat (e.g. Day 14's polish pass) rather than
  bolting on quietly, since expressive/emotional TTS is a bigger lift than
  a plain neural-voice swap (prosody control, likely a different model
  than base Piper, real latency cost to re-measure).

**Ships:**
- **Wake word / push-to-talk → Moonshine (~107ms) → `parseIntent` →
  `describeScene` → TTS.** Deterministic answers only. Proving the
  interaction model at minimum latency, before there is any LLM to blame for
  slowness or for lying.
- **T3 preempts T1** — a question in flight pauses ambient sensing. This is
  why the STT latency problem disappears rather than being optimised away.
- **The speech policy lands: silence is the default.** WELLSY speaks when asked,
  when a rule fires, or when ambient mode is explicitly on. Days 1–6's
  narration becomes an off-by-default mode.
- **Kokoro or Piper natively** — the D13 espeak/Rollup production-build bug
  does not exist outside a bundler.
- **Close the oldest open gap in the project: confirm audio is audible on
  real speakers.** Never verified once across six days.

**Concept:** The moment it stops performing and starts responding. Everything
before this was a system that talked. This is a system you can interrupt.

**Demo:** Silent room. Silent HUD. *"WELLSY, what do you see?"* — one beat —
a grounded, accurate, one-sentence answer. Then *"stop"*, and it stops
mid-word. The silence before the answer is the demo.

**Hook:** *"For six days it wouldn't shut up. Today I made it quiet — and
that's what finally made it feel intelligent."*

**Risk:** Wake-word implementation is **open decision §10.2** and needs
deciding before this day starts: a real keyword spotter (openWakeWord) keeps
T0 genuinely cheap; transcribe-then-match is a day faster to build and
honest if described as such. **Default to push-to-talk working first**,
wake word as the same-day stretch. A wake word that misfires on camera is
worse than a button that doesn't.

---

# ==========================================================================
# ENDGAME REWRITE — 2026-08-22, start of Day 11
# ==========================================================================
#
# Everything below replaces the original Days 11-15. The original plan is in
# git history (commit a2c6428 and earlier) if it's ever needed.
#
# **Why this was rewritten.** Audited the build against
# `jarvis_friday_edith_combined_ai_system_spec.md`. Result: roughly 15% of
# the spec, concentrated almost entirely in §7 Layer A (Perception). Zero
# memory (§C), zero context engine (§8), zero tools (§12), zero permissions
# (§13), zero proactive engine (§16), zero orchestrator (§21), below
# Autonomy Level 0 (§26). The spec's own MVP Phase 1 — "JARVIS Core:
# identity, memory, preferences, contextual conversation, basic tool
# calling" — sits at ~19%.
#
# The structural failure, stated plainly: **Days 1-10 built one capability
# ten times.** Day 1 saw things and said what it saw; Day 3 tracked it
# better, Day 5 drew it prettier, Day 8 labelled it correctly, Day 9 plumbed
# it faster, Day 10 made it wait to be asked. Every episode refined the same
# sentence. That is why there is no differentiator and why the series has
# had nothing new to show.
#
# The word "HUD" does not appear once in the spec's 1,292 lines. Camera
# vision is one input among fifteen in Layer A. The old roadmap spent its
# remaining days deepening that same corner (faces, depth, mobile).
#
# **The new rule for every remaining day — the spec's own §37 test:** does
# this make the AI better at *understanding the user*, *understanding the
# environment*, *deciding what matters*, or *acting on their behalf safely*?
# Days 1-10 hit exactly one of those four. Days 11-15 must hit the other
# three.
#
# **Day 15 is no longer filming-only. Day 15 is Endgame: everything wired,
# end to end, working.** Not optimized, not beautiful — working. "First
# build it, then make it beautiful."
#
# ==========================================================================

## The differentiator, named

Every assistant on the market does calendar-and-email tool calling. Almost
none of them can **see**. The thing WELLSY will have that they don't is
**vision-grounded agency**:

> *"Log this."* — while holding a receipt.
> *"File a bug about that."* — pointing at an error on screen.
> *"Who just walked in? Don't read that out loud."*

Days 1-10 are not wasted. They are the **input** to a product that does not
exist yet. The mistake was believing the eyes *were* the product.

## Stack replacements — verified current as of 2026-08-22, not picked from memory

The v1 browser build shipped COCO-SSD/MobileNet (a **2017** model). The
current engine still runs `qwen2.5:7b` (2024) and macOS `say -v Samantha`
(a 2009 voice). Every component below was checked against what is actually
state of the art this month. **This check is now mandatory before any model
choice** — see `memory/wellsy_no_stale_tech.md`.

| Slot | Current in repo | Replacing with | Why |
|---|---|---|---|
| Understanding / reasoning | YOLOE labels → `describe_scene` template → `qwen2.5:7b` | **Qwen3-VL-8B** (Apache 2.0, 69.6 MMMU, 96.1 DocVQA, ~6GB @ Q4) | One model that *sees and reasons*. Kills the label→template→LLM telephone game that caused every grounding bug (D40's amendments). Reads **screens and documents** — §23, which the build has zero of |
| Voice out | macOS `say -v Samantha` | **Chatterbox Turbo** (350M, sub-200ms, emotion-exaggeration control) — Kokoro-82M as the fallback if latency bites | Closes the standing expressive-TTS ask. First open-source model with real emotion control |
| Voice in | Moonshine (buffered) | **Moonshine v2** (Ergodic Streaming Encoder) — Parakeet TDT if v2 disappoints | Streaming, not buffered. Barge-in and turn-taking (§24) need it |
| Identity | — | **InsightFace 1.0** (May 2026 — SCRFD + ArcFace, no C++ toolchain needed now) | Verified still current, not a stale default. Answers §6-P2's *"who is asking?"* |
| Ambient T1 | YOLOE @ 8Hz | **stays** | It is the cheap always-on tier and it works. Qwen3-VL is T2/T3, on demand |

---

## Day 11 — "It stops identifying and starts understanding" (the brain swap)

**Spec:** §7 Layer A+B, §23 Screen and Vision Intelligence, §18 Knowledge.

**Ships:**
- **Qwen3-VL-8B replaces the entire label→template→LLM chain.** `describe_scene`'s
  string templating stops being the source of answers. The model looks at the
  actual frame.
- **`parse_intent` survives untouched** for `stop`/`wake`/`sleep` — an LLM must
  never decide whether "stop" stops (D6/D25, unchanged).
- **Screen capture as a second perception source.** `screencapture` /
  ScreenCaptureKit on demand. This is a *new input type*, the first since Day 1.
- **It reads.** Error logs, terminal output, documents, receipts, handwriting,
  labels, book spines. The current build cannot read a single word.
- **Grounding is enforced structurally, not by prompt** — the model gets the
  frame *and* the track list; every claim carries provenance (§19).
- YOLOE stays as T1; Qwen3-VL runs as T2/T3 only, behind the `PreemptionSeam`.

**Concept:** For ten days it has been matching pixels to an 80-word vocabulary
and reading answers off a template. Today it just *looks* — and the entire
grounding-bug class from Day 10 (the invented posture, "you're holding
glasses") disappears because there is no longer a telephone game to garble.

**Demo:** Point it at a terminal showing a real stack trace. *"What's wrong?"*
It reads the error out loud and says what broke. Then hold up a receipt:
*"How much?"* Nothing in ten days of build could do either.

**Hook:** *"I deleted my object detector's job description. It doesn't identify
things any more — it just looks."*

**Risk:** 8B VLM inference on M4 Pro may be too slow for the sub-second feel
Day 10 established. **Mitigation is structural: it's T2/T3 only** — the fast
deterministic path (`parse_intent` → tracks) still answers instantly, and the
VLM is the deep-look tier. If 8B is too slow, drop to Qwen3-VL-4B and say the
number on camera.

**What Day 12 should know before starting:**
- **The risk called it exactly right.** 8B measured first-token p50
  2753ms/p95 3048ms — dropped to `qwen3-vl:4b` (p50 1692ms/p95 2282ms,
  ~half the cost, identical correctness on every test run against it).
  Neither model hit the brief's own "~1.5s comfortable" bar; the fast
  path staying separate is what actually saves the interaction, not model
  size. See `decisions.md` D41, `day11-results.md`.
- **The thesis held on real data**: both Day 10 grounding failures
  ("standing next to the chair", "holding glasses") retested verbatim,
  did not reproduce, on two model sizes. Memory (Day 12's actual job) is
  the next thing that can quietly reintroduce invention — a model with
  turn history has a new way to hallucinate ("didn't we already establish
  X?") that a stateless one-shot VLM call structurally cannot.
- **Provenance logging exists now** (`clips/provenance.jsonl`, D43) but
  its disagreement heuristic is weak (58% over-flag rate, measured, not
  assumed) — Day 12's memory/confidence work should not treat
  `possibleDisagreement` as a trustworthy signal without tightening it
  first.
- **A real sandbox limitation, not a code bug:** this agent's shell can
  capture the real screen but cannot make any window it spawns actually
  render on the capturable display (D42). If Day 12's face-identity work
  (§6-P2, InsightFace) needs to *display* anything (an enrollment UI, a
  confirmation prompt), budget time to find out early whether the same
  gap applies, rather than discovering it mid-day.
- **The standing mic-permission gap is now two days old** (row 3, both
  Day 10 and Day 11's results docs) — the wake/press→first-word latency
  number still needs the project owner's own Terminal.app to capture.
  Worth just doing this first, before Day 12 adds a second thing that
  needs it (voice-based memory enrollment, if that's how "who is this"
  ends up being confirmed).
- **`ollama ps` confirms models unload/reload cheaply** — 8B and 4B were
  swapped mid-session with no engine restart needed, just a different
  `MODEL_NAME`. If Day 12 adds a second local model (embeddings for
  semantic memory, say), Ollama's existing keep-alive/eviction behavior
  is already proven to coexist fine with the vision model, at least
  sequentially — concurrent resident cost with a second model wasn't
  tested.

---

## Day 12 — "It remembers me" (memory, identity, context engine)

**Spec:** §5 Core Identity, §7 Layer C (all six memory types), §8 Context
Engine, §9 Situation Model, §19 Provenance, §25 Memory Behavior Rules.

**Ships:**
- **SQLite memory, six layers** — working, episodic, semantic, procedural,
  relationship, project. **Nothing in the engine currently persists.** Kill
  the process today and WELLSY forgets you exist; after Day 12 it doesn't.
- **The Context Engine** — the spec's own *"central component that makes the AI
  feel intelligent"* (§8). Assembles User + Conversation + Memory + Environment
  + Time + Active Tasks + Permissions into one live current-context object,
  continuously maintained rather than rebuilt per request (§9).
- **Face identity via InsightFace 1.0**, folded into memory rather than shipped
  as a party trick — it answers §6-P2's *"who is asking?"*, which Day 13's
  permission layer needs. **Three bands: match / unsure → say nothing /
  no-match.** Explicit enrolment only, never covert. Visible delete.
- **Memory rules enforced (§25):** confidence + provenance on every memory,
  decay for transient junk, and *never* silently converting a guess into a
  fact. User can inspect, edit, delete.
- **Cross-session continuity** — restart the process, it picks up the thread.

**Concept:** Ten days of a system with total amnesia. The spec's Phase 1
success criterion is one sentence — *"the AI should feel like it knows the
user"* — and until today the honest answer was that it doesn't know you
between two consecutive sentences.

**Demo:** Have a conversation. Kill the engine. Restart it. *"What was I doing
before?"* It knows. Then a second person walks into frame — it greets them by
name and the context visibly changes.

**Hook:** *"For ten days I rebuilt its brain every morning, because it forgot
me every night."*

**Risk:** Memory is easy to build and hard to make *useful* — a log nobody
queries is not memory. **The retrieval path is the deliverable, not the
schema.** Biometrics carry real legal weight (GDPR Art. 9, BIPA): local only,
explicit enrolment, visible delete, said out loud in the episode.

---

## Day 13 — "It does things" ⭐ (tools, agent loop, permissions)

**The differentiator day. The one that makes it an assistant instead of a
describer.**

**Spec:** §11 Planning and Agent Loop, §12 Tool Orchestration, §13 Permission
Architecture, §26 Autonomy, §27 Failure Handling, §29 Auditability.

**Ships:**
- **A tool registry** where every tool declares capability, input/output schema,
  auth, permission level, risk level, latency, **reversibility**, and audit
  requirement (§12). Not hardcoded function calls — a registry the orchestrator
  reasons about.
- **The real agent loop (§11):** Observe → Understand → Check Memory →
  Determine Goal → Plan → **Check Permissions** → Execute → Observe Result →
  Verify → Adapt/Retry/Escalate → Report. The build currently does three of
  those eleven steps.
- **Risk levels 0-3 with real enforcement (§13).** Level 0-1 auto; Level 2+
  requires spoken confirmation; Level 3 requires explicit policy. *"It can call
  the tool"* is never *"it may call the tool."*
- **Six real tools to start:** files, calendar, reminders/notes, web search,
  sandboxed shell, and macOS app control. Enough to be useful, few enough to
  finish.
- **Action audit log (§29)** — a real one, actions not frames. *"What did you
  do?"* returns a clear answer.
- **Failure handling (§27):** never claim success on failure, preserve partial
  progress, escalate honestly.

**Concept:** Vision-grounded agency. Everyone's assistant can read your
calendar. Nobody's can look at the thing in your hand and act on it.

**Demo:** Hold up a receipt — *"log this."* It reads the vendor and amount and
files it. Then, pointing at a real failing terminal: *"file a bug about that."*
It reads the trace, drafts the issue, and **stops to ask before sending** —
because that's Level 2.

**Hook:** *"Today it stopped telling me what it can see and started doing
something about it."*

**Risk:** The largest single day in the series. **Hard priority order: registry
→ permissions → agent loop → tools, and tools come last** so the count can
shrink to three without losing the episode. A tool that fires without
confirmation on camera is the worst possible outcome — the confirmation gate
ships before the tools do.

---

## Day 14 — "It speaks first, and it sounds human" (proactive engine + voice)

**Spec:** §16 Proactive Intelligence, §15 Communication Modes, §24 Voice
Interaction, §14 Personality, §3 FRIDAY layer.

**Ships:**
- **The proactive engine (§16)** — the real scoring rule:
  `Expected Benefit × Urgency × Confidence ÷ Interruption Cost`, with a
  configured threshold. This is the FRIDAY layer and the closest thing in the
  spec to what people actually mean by "JARVIS."
- **Communication modes (§15):** Normal, **Tactical** (*"Battery 12%. Meeting in
  14 minutes."*), Analytical, **Alert**, Silent. Verbosity adapts to urgency.
- **Chatterbox Turbo** — expressive, emotional, sub-200ms. The nine-day-old
  robot-voice complaint closes here.
- **Moonshine v2 streaming + real barge-in** — interrupt it mid-sentence and it
  yields, mid-word. Speaker identification wired to Day 12's face identity, so
  it knows who is talking.
- **The personality engine (§14) as config, not as a prompt string** — calm,
  concise, warm, discreet, dry wit behind a cooldown gate. Hard caps:
  acknowledgement ≤4 words, factual answer ≤1 sentence.
- **`llmLineGenerator.ts`'s "Roast the habitat" prompt dies** — the literal,
  traceable cause of the tone complaint.

**Concept:** Day 10 made it quiet. Today it earns the right to break its own
silence — once, correctly, about something that actually mattered. Judgement
about *when to speak* is the hardest thing in the spec and the one people
recognise instantly.

**Demo:** Working in silence. It speaks, unprompted, exactly once — and it's
right. Then interrupt it mid-sentence; it stops mid-word and listens.

**Hook:** *"I spent a week teaching it to shut up. Today I taught it the one
thing that's harder — knowing when to speak anyway."*

**Risk:** A proactive system that misfires on camera is worse than a silent
one. **Threshold high, tuned live, and one deliberate demo trigger prepared.**
If Chatterbox's latency breaks the feel, fall back to Kokoro-82M and say why.

---

## Day 15 — "Endgame" (orchestrator, everything wired, end to end)

**This is a build day AND the ship day. Not filming-only. The whole system,
end to end, working — not optimized, not beautiful. Working.**

**Spec:** §20 Multi-Agent, §21 Unified Orchestrator, §30 One Intelligence,
§32 Example End-to-End Interaction, §34 High-Level Architecture.

**Ships:**
- **The Unified Orchestrator (§21)** — decides which capability, which tools,
  which context, what sequence, what needs approval, how failure is handled,
  when the objective is complete. One entry point in front of everything Days
  11-14 built.
- **One identity, one voice, one memory across every surface (§30).** Internally
  it is a VLM, a detector, a memory store, a tool registry, a policy engine.
  Externally it is one thing.
- **The §32 interaction, for real:** an outcome-level request — *"prepare me for
  my next meeting"* — resolved into steps the user never specified.
- **Packaged and runnable** — one command, weights fetched on first run.
- **Public repo, README, honest capability/limitation list** including
  everything this still doesn't do.
- **The full demo film.**

**Concept:** Fifteen days, one wrong turn at Day 1, one honest correction at
Day 11, and a local AI that sees, remembers, decides and acts.

**Demo:** Silence. *"Prepare me for my next meeting."* It checks memory, reads
the screen, pulls the calendar, spots the unfinished item, asks permission for
the one consequential action, does the rest, and reports in one sentence.

**Hook:** *"Fifteen days. Day 11 I threw out the plan and rebuilt what it
actually was. Here's everything — including the ten days I got wrong."*

**Rule:** No new capability after 18:00 on Day 15. Integration and bugs only.

---

## If it slips (cut in this order — and say so on camera)

1. **Tool count on Day 13** — three real tools with a working registry and
   permission gate beats six tools bolted on. Never cut the registry or the gate.
2. **Speaker identification** (Day 14) — face identity from Day 12 already
   answers "who is asking" when they're in frame.
3. **Procedural + relationship memory** (Day 12) — working, episodic and
   semantic carry the episode.
4. **Analytical mode** (Day 14) — Normal, Tactical, Alert and Silent are enough.
5. **Screen capture** (Day 11) — the camera path alone proves the VLM swap,
   though this is the most painful cut on the list because §23 is a real gap.
6. **Packaging** (Day 15) — demo from source and ship the repo.

**Never cut:** Qwen3-VL replacing the label chain (Day 11), persistence
(Day 12), the permission gate (Day 13), and the orchestrator (Day 15). Those
four are the entire Endgame thesis — it understands, it remembers, it acts
safely, and it is one thing rather than five.

## What must be true for five days to work

- **No day is spent refining a previous day.** Debt gets carried and stated on
  camera, not repaid at the cost of a new capability. This rule is the direct
  fix for what went wrong in Days 1-10.
- **Every model choice is verified current before it is written** — not pulled
  from habit. See `memory/wellsy_no_stale_tech.md`.
- **Every day ends with something a viewer has not seen before.** Not faster,
  not cleaner — *new*.
- **Days are not silently merged.** If Day 13 needs two days, it takes them from
  Day 14, and Day 14's cut is announced.
