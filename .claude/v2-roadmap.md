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
  real, live collision — "yap" keeps transcribing as "app." A replacement
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
- "yap" needs a new name before more wake-word polish is worth doing.
- Mic permission on this machine is scoped **per actual process**, not
  per-user — Terminal.app, VS Code's integrated terminal, and this agent's
  own process tree each need their own grant. Worth remembering before
  losing time to it again.

**Ships:**
- **Wake word / push-to-talk → Moonshine (~107ms) → `parseIntent` →
  `describeScene` → TTS.** Deterministic answers only. Proving the
  interaction model at minimum latency, before there is any LLM to blame for
  slowness or for lying.
- **T3 preempts T1** — a question in flight pauses ambient sensing. This is
  why the STT latency problem disappears rather than being optimised away.
- **The speech policy lands: silence is the default.** YAP speaks when asked,
  when a rule fires, or when ambient mode is explicitly on. Days 1–6's
  narration becomes an off-by-default mode.
- **Kokoro or Piper natively** — the D13 espeak/Rollup production-build bug
  does not exist outside a bundler.
- **Close the oldest open gap in the project: confirm audio is audible on
  real speakers.** Never verified once across six days.

**Concept:** The moment it stops performing and starts responding. Everything
before this was a system that talked. This is a system you can interrupt.

**Demo:** Silent room. Silent HUD. *"YAP, what do you see?"* — one beat —
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

## Day 11 — "It learns when to shut up" (Phase 4)

**Ships:**
- **MLX-LM with Qwen3 8B–14B.** Roughly 20× the browser's 0.5B, on 24GB of
  unified memory, at published ~130 tok/s.
- **The voice spec as code, not as a wish** (§6): `FACTUAL` default and `WRY`
  behind a **humour gate** — a ≥10-minute cooldown *and* a trigger condition.
  Hard length caps: acknowledgement ≤4 words, factual answer ≤1 sentence.
- **Grounding survives.** The LLM restyles `describeScene`'s output; it never
  invents a fact. Same split as `events.ts` on Day 2.
- **`llmLineGenerator.ts`'s "Roast the habitat" prompt dies**, along with its
  four sarcastic examples and zero plain answers. That prompt is the literal,
  traceable cause of the tone complaint.
- Ambient narration returns as an explicitly off-by-default mode.

**Concept:** A 0.5B model can hold exactly one register, so ours was
relentlessly deadpan about a chair. An 8B model can hold "concise and
factual, with rare dry wit." But most of the fix isn't the model or the
prompt — it's that it now speaks a tenth as often, and rarity is what makes
wit land.

**Demo:** The same question, three answers side by side: Day 4's 0.5B roast,
Day 11 `FACTUAL`, and the one-in-twenty `WRY` line. The third one is funny
*because* the first two weren't trying to be.

**Hook:** *"My AI was sarcastic about everything, constantly. Turns out
that's not a personality — that's a stuck register."*

**Risk:** 8B first-token latency on top of STT could break the sub-second
feel Day 10 established. **Mitigation is structural: `parseIntent` and
`describeScene` still answer without the LLM**, so the fast path stays fast
and the LLM is a restyle pass that can be skipped under a timeout.

---

## Day 12 — "It knows who I am" (Phase 5)

**Ships:**
- **SCRFD + ArcFace** (InsightFace) — 512-d embeddings, once per new person
  track, cached by track id. Not per frame.
- **Explicit enrolment only.** You show your face, you give a name. Never
  covert, never learned in the background.
- **Three bands, not two:** match / **unsure → say nothing** / no-match.
  Calling someone by the wrong name is a worse failure than not recognising
  them, and 1:N is much harder than 1:1.
- **The greeting rule** — known person enters frame, YAP greets by name and
  offers. **The unregistered rule** — see the wording decision below.
- **Memory layers:** person registry (SQLite + numpy), episodic log
  (timestamped, enables *"what happened while I was out"*), session context
  (so *"what about behind me?"* resolves).

**Concept:** The one judgement that must happen without being asked — and
therefore the one deliberate exception to the entire on-demand architecture.

**Demo:** Walk into frame: *"Welcome back, Saket."* A friend walks in:
`UNREGISTERED · NOT IN REGISTRY`. Enrol them live on camera, they walk out
and back in, and it greets them by name.

**Hook:** *"It remembers me now. And when it doesn't know you, it says so —
it doesn't guess your name."*

**Open decision — needed before this day (§10.1):** an unregistered face is
your mother, a courier, a friend, essentially every time. `"Threat detected"`
would be the first factually false thing this system has ever said, in a
project whose entire credibility is that it never claims more than it knows.
**Recommendation: `UNREGISTERED · NOT IN REGISTRY` by default** — on a red
plate it lands harder anyway, because it sounds like a system that means it —
**plus an opt-in theatrical mode** that swaps the wording for filming. Your
call; both are one config flag.

**Risk:** Biometric data has real legal weight (GDPR Art. 9, BIPA). Embeddings
stay local, enrolment is explicit, and there is a visible delete. Say this
out loud in the episode — it's a credibility beat, not a disclaimer.

---

## Day 13 — "It sees in three dimensions" (Phase 6) ⭐

**The visual payoff episode.**

**Ships:**
- **Depth Anything V2** — real relative depth. This **retires D17**, the
  standing rule that the HUD may not claim distances because it couldn't
  measure them. It can now.
- **Segmentation masks** (YOLOE-seg / SAM2) — silhouettes instead of
  rectangles. The single biggest available upgrade to how it *looks*.
- **Pose** (YOLO26-pose) — orientation, gesture, "facing away".
- **OCR on demand** — read a screen, a label, a book spine.
- All of it **T2: on demand only, never on the hot path.** Asked-for, not
  always-on. This is the day the attention budget earns back its complexity.

**Concept:** Everything up to now was rectangles and words. This is the day
it starts looking like the thing in the film — and it's affordable *only*
because it runs when asked, not sixty times a second.

**Demo:** *"YAP, scan the room."* The HUD blooms: silhouettes trace real
outlines, depth shades near-to-far, a real distance number appears next to a
label — and it's true this time. Then it collapses back to quiet.

**Hook:** *"Day 5 I refused to put distances on screen because it couldn't
actually measure them. Today it can, so today they're real."*

**Risk:** This is a 2+ day phase compressed into one. **Priority order is
depth → segmentation → pose → OCR, and it is a hard order.** Depth alone
carries the episode and retires a documented limitation. Pose and OCR are
explicitly expendable — see the slip list.

---

## Day 14 — "It fits in a pocket" (Phase 7 + freeze)

**Ships:**
- **On-device mobile T1** via CoreML/ExecuTorch export. Published: YOLO26n at
  11.3 ms/frame on an iPhone 15 Pro Max — at 8 Hz ambient sensing that's
  under 10% of the phone's budget. The phone was never the problem; the
  always-on design was.
- **The private server split**: phone runs camera, motion gate, detection,
  tracking and all HUD rendering locally; the server runs T2/T3 on demand.
  A 50–150ms round trip is invisible when the user has just asked a question
  and is already waiting.
- **Auth and TLS before a single byte leaves the LAN.** Private is not
  automatically secure.
- **FEATURE FREEZE at end of day.** Whatever exists at 23:59 on Day 14 is
  what gets filmed on Day 15.

**Concept:** The architecture that made it fast on the desktop is the same
architecture that makes it possible on a phone. That's not a coincidence —
it's the whole argument.

**Demo:** Walking through a real space holding a phone, HUD live, asking it
questions out loud and getting answers back.

**Hook:** *"The Iron Man HUD only works if it's the thing in your hand, not
the thing on your desk."*

**Risk:** **This is the most likely day to be cut**, and cutting it costs the
least — Day 15 can film on the Mac. If Day 13 overran, take mobile down to
"detection running on the phone, questions answered on the desktop" and say
so plainly on camera.

---

## Day 15 — "Ship it" (Phase 8) — FILMING ONLY

**Ships:**
- **Packaged app** — Tauri or py2app, weights fetched on first run.
- **Public repo, README with GIF**, and an honest capability/limitation list
  that includes everything §11 says this still doesn't fix.
- **The polished 60–90s demo film.**
- **Series wrap-up write-up** — what real-time perception actually costs,
  what's genuinely hard, and the honest account of the Day 7 pivot.

**Concept:** Fifteen days, one wrong turn, one honest correction, and a local
perception system that answers when asked.

**Demo:** The full thing, clean, end to end: silence, a question, an answer,
a scan, a greeting by name.

**Hook:** *"15 days. It sees, it remembers, it answers, and it stays quiet
until you ask. Here's everything — including the six days I got wrong."*

**Rule:** No new features today. None. Bugs that break the demo, and nothing
else.

---

## If it slips (cut in this order)

1. **OCR and pose** (Day 13) — depth and segmentation carry the episode alone.
2. **Mobile on-device export** (Day 14) — demo on the Mac, show the phone as
   a plan with the benchmark numbers behind it.
3. **The private server** (Day 14) — all-local is topology A in §8 and it was
   always a legitimate shipping configuration.
4. **Wake word** (Day 10) — push-to-talk is honest, reliable, and films fine.
5. **Segmentation masks** (Day 13) — depth alone still retires D17.
6. **Episodic log** (Day 12) — the registry and greeting are the demo; "what
   happened while I was out" is the stretch.

**Never cut:** the Day 8 detection upgrade, the Day 10 query loop, and the
Day 15 freeze. Those three are the entire V2 thesis — it sees correctly, it
answers when asked, and it actually ships.

## What must be true for nine days to work

- **Two decisions made before they block a day**: wake-word approach (before
  Day 10) and the unregistered-person wording (before Day 12).
- **Day 8's MLX fallback is decided by mid-afternoon**, not at midnight.
- **Days are not silently merged.** If Day 13 needs two days, take it from
  Day 14 and say so — do not take it from Day 15.
