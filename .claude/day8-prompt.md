# Day 8 — "It stops being wrong"

You are picking up YAP on Day 8. Days 1–7 have shipped. Read
`.claude/context.md`, `.claude/decisions.md` (D1–D29 — **D28 and D29 are
today's foundation**), `.claude/v2-architecture-research.md` (§1d, §2a, §4,
§7), `.claude/v2-roadmap.md`, and `.claude/day7-baseline.md` before you touch
code. `engine/` exists and runs. This document is the brief for today only.

---

## The goal, stated precisely

Yesterday measured the problem. Today replaces the part of it that everyone
can see.

1. **A real detector.** `lite_mobilenet_v2` is why a bed is a `dining table`
   and a microphone is a `tie`. YOLOE via MLX, open-vocabulary and
   text-promptable, at 8 Hz.
2. **A real tracker.** ByteTrack/BoT-SORT replaces the hand-rolled IoU
   tracker. Day 3's tracker and Day 6's label voting retire with honours —
   they were the right fixes for a weak detector, and the detector is what's
   changing.
3. **The tier scheduler, built today, not retrofitted.** T0 (motion gate,
   exists) and T1 (detection + tracking) real; T2 and T3 wired as stubs that
   do nothing. Retrofitting an attention budget onto an always-on loop is
   precisely the mistake Day 7 documented.

The thesis for the day: **switching to Python did not fix detection quality.
Changing models fixed detection quality.** Today does both, and only one of
them is the reason it works. Say that on camera — the audience will assume
the language was the fix, and it wasn't.

---

## Boundaries

- **Everything lives in this repo.** Code, weights config, notes, measurement
  output — all inside `/Users/saketmunda/Work/Startup/projects/yap-hud`.
  Not `/tmp`, not a scratchpad. Model weights that must be cached outside the
  repo (HuggingFace cache) are the one exception; record where they land in
  `engine/README.md` so Day 15's packaging knows.
- **No cloud (D10).** No inference API, no hosted model endpoint. Weights
  download once and run locally, forever after.
- **No WebSocket, no HUD, no React today.** That is Day 9 and it is a full
  day. Today's output is JSON lines on stdout. If you find yourself opening
  `src/`, stop.
- **No LLM, no TTS, no voice.** Days 10–11.
- **Do not delete the browser build or the browser tracker.** It is the
  before-picture, the fallback, and the honest comparison. `src/` should be
  untouched at the end of today.
- **Do not tune `MOTION_THRESHOLD` by feel.** It is 4.0 and Day 7 flagged it
  as an untuned first guess. Tune it against a real recorded scene, with the
  number written down — see Part 1.

---

## Where things stand (read this, it saves an hour)

Day 7 shipped `engine/` — `capture.py` (own process), `motion.py` (pure
`to_gate_gray` + `motion_gate`), `main.py` (depth-1 latest-wins queue per
D29), synthetic mode for camera-less runs, JSONL on stdout, gated-fraction on
stderr. It runs. Build on it; do not restart it.

Four findings from yesterday that change what you do today:

1. **The motion gate costs ~1.3ms p50, not the ~1ms the research doc
   assumed** — and the cost is the `cv2.resize` downscale from native
   resolution, not the diff. So budget T1 against 1.3ms, *and* try the
   obvious fix: **request a smaller frame from the camera** rather than
   capturing large and shrinking. If AVFoundation will hand back 640×480
   directly, the gate gets cheaper for free and T1 wants a smaller frame
   anyway.
2. **The 100% gated-fraction on a still scene is a single-condition
   number.** It has never been tested against a scene with *intermittent*
   motion — which is the only case the tier scheduler actually exists for. A
   gate that is 100% correct on a frozen room and wrong on a room where
   someone occasionally moves is worse than no gate. **Test this early today,
   as soon as T1 exists to be gated.**
3. **Scenario E sharpened the diagnosis**: the ~72%-of-one-core always-on cost
   is a *detection-loop* cost, not an LLM/TTS one. The LLM/TTS prefetch never
   even starts when the frame is empty — D13's event gating already handles
   that. **This means today's T1 gating is aimed at exactly the right
   target**, and it also means the headline number to beat is specific:
   72% of a core, idle.
4. **The compute stall was never captured** — the model downloads stalled, so
   scenario D shows zero long tasks by construction, not by disproof. Not
   today's problem, but do not cite "the browser build never stutters" as if
   it were established.

---

## Part 1 — T1: the detector

### The model

**YOLOE** via MLX, open-vocabulary and text-promptable. The prompt list is
the whole point: `microphone` is not one of COCO's 80 classes, so no
threshold, no tracker, and no amount of voting could ever have fixed it.
Today you type the word.

- Keep the prompt list in **`engine/prompts.txt`**, one term per line,
  user-editable, hot-reloaded if that is cheap and left alone if it is not.
  Seed it with the objects that actually appear in the filming room —
  including `microphone`, `bed`, `monitor`, `keyboard`, `chair`, `person` —
  plus a couple of things deliberately *not* present, so the demo can show it
  correctly finding nothing.
- Record which YOLOE variant and weights, with the download size and source,
  in `decisions.md`.

### The fallback, and when to take it

**MLX + YOLOE is the single biggest unknown in the V2 plan.** It sits on
Day 8 deliberately, where there is room to recover.

- **Decide by mid-afternoon.** If MLX is fighting — conversion failures,
  missing ops, wrong output shapes — take **YOLO26 via PyTorch MPS or
  CoreML** and move on. It is slower and it is *not* open-vocabulary, which
  costs the day its best demo beat, but it is still enormously better than
  `lite_mobilenet_v2` and the day still ships.
- If you take the fallback, say so plainly in the report and in
  `decisions.md`, including what specifically broke. "MLX didn't work" is not
  a finding; "MLX's export path for YOLOE's text-encoder head fails at X" is.
- **Do not spend the evening on it.** An evening lost here is Day 9's
  bridge, and the bridge is what makes any of this visible.

### Rate

**8 Hz, not 60.** This is not a compromise and should not be described as
one. Day 5's `hudState.ts` interpolates toward the latest detection at τ=70ms
(D15), so 8 Hz detection renders as 60 Hz motion — but that only gets proven
on Day 9. Today, just build 8 Hz and record what the model could have done
unthrottled, because "it runs at N FPS and we deliberately use 8" is a much
better line than "it runs at 8".

---

## Part 2 — T1: the tracker

**ByteTrack or BoT-SORT.** Both handle the thing Day 3 and Day 6 hand-rolled:
identity across occlusion, and — critically — identity across a *label flip*,
which is what D21's cross-label gate and D27's two-pass fix existed to paper
over. A better detector plus a real tracker should make that entire class of
bug disappear.

- Prefer whichever is already packaged with the detector's ecosystem. This is
  not the day to hand-roll a Kalman filter.
- **Track ids must be stable enough to film.** Day 3's still-open verification
  task — the track-id-persistence clip, never shot — becomes trivially
  shootable today. Shoot it.
- Emit tracks in a shape near enough to `src/vision/types.ts`'s `Track` that
  Day 9's bridge is plumbing, not translation. You own both ends of that
  contract; keep it boring.

**The honesty carry-over:** Day 6's `UNIDENTIFIED` discipline (D22) survives
the model change. An open-vocabulary model can be confidently wrong just like
a closed one — it will happily match `microphone` to something microphone-ish.
Keep a confidence floor and keep the system's right to say it doesn't know.
The prompt list makes it *possible* to be right; it does not make it certain.

---

## Part 3 — The tier scheduler

This is the part that is easy to skip and expensive to add later.

```
T0  motion gate        always on, every frame, ~1.3ms      (exists)
T1  detect + track     on motion, 8 Hz max                 (today)
T2  deep look          on demand — STUB, wired, does nothing (Day 13)
T3  respond            on request — STUB, wired, does nothing (Day 10)
```

**T2 and T3 must exist as real seams today**, even though they are empty. A
function that takes a request and returns immediately, in the right place in
the loop, with the preemption path drawn. The point is that Day 10 and Day 13
plug in rather than restructure.

### The trap: gating detection is not the same as having no tracks

If T0 gates a frame, T1 does not re-run inference — **but the tracks from the
last detection remain valid and must keep being emitted.** A still room does
not become an empty room. Get this wrong and the HUD blanks whenever the
scene holds still, which is the exact opposite of the intended behaviour and
will look like a catastrophic regression on Day 9.

### Hysteresis

Motion stopping should not instantly stop detection. Keep T1 running for a
short cooldown (start with ~1s) after the last motion frame, so the scene
settles before inference stops. Otherwise a person who pauses mid-gesture
freezes the perception mid-gesture.

### The intermittent-motion test (do this the moment T1 works)

Record or stage a scene with real intermittent motion — someone entering,
sitting still for 20s, moving again. Measure:

- gated fraction over the whole clip
- **how many frames of real motion the gate missed** (the only failure that
  matters)
- CPU with the gate, and CPU with the gate forced off

That third number against yesterday's **72% of one core** is the day's
headline. Tune `MOTION_THRESHOLD` against this clip, once, and write the
chosen value and its justification into `decisions.md`.

---

## Part 4 — The measurements

Into **`.claude/day8-results.md`**, in the same style as `day7-baseline.md`:

| # | Question | Number |
|---|---|---|
| 1 | Unthrottled detection FPS on this machine | vs the research doc's borrowed 124.9 |
| 2 | Detection ms per frame at 8 Hz | p50 / p95 |
| 3 | Idle CPU, still room, gate on | **vs Day 7's 72% of one core** |
| 4 | Idle CPU, gate forced off | isolates what the gate buys |
| 5 | Gated fraction, intermittent-motion clip | and missed-motion frames |
| 6 | Motion gate cost after any capture-resolution change | vs 1.3ms |
| 7 | End-to-end capture→track latency | the number Day 9 inherits |

**Label anything still borrowed as borrowed.** Every MLX benchmark in §4 of
the research doc is someone else's machine until item 1 replaces it.

---

## The demo, and building for it

The episode is a side-by-side of the same corner of the same room. Browser
build: `TIE 88%`. Engine: `MICROPHONE`. Then a live edit of `prompts.txt`
adding a word it has never been trained to name, and it finds the thing.

**So make that filmable today**, even without the HUD: a debug window
(`cv2.imshow` is fine, this is scaffolding not product) drawing boxes and
labels from the engine's own output. Ugly is fine — Day 9 brings back the
real HUD. What matters is that the bed/microphone comparison gets shot while
the contrast is fresh, and that the old numbers still exist to shoot against.

---

## Build in this order. Cut from the bottom.

1. YOLOE (or the fallback) loading and detecting on a single still image
2. Wired into `engine/`'s loop at 8 Hz, behind the existing motion gate
3. Tracks from a real tracker, ids stable, in the JSONL output
4. T2/T3 stubs and the preemption seam
5. The intermittent-motion test + `MOTION_THRESHOLD` tuned once, on evidence
6. The measurement table
7. The `cv2.imshow` debug window and the bed/microphone comparison shot
8. Capture-resolution change to bring the gate cost down
9. Hot-reload of `prompts.txt`

**Items 1–3 are the day.** Without them Day 9 has nothing to bridge. Item 4
is the one that gets skipped under pressure and costs the most later — it is
twenty minutes of empty functions; do not trade it for item 9.

---

## The honesty rules for today

- **Report the FPS you actually got**, not the one in the blog post. If MLX
  gives 40 FPS rather than 124.9, that is still five times what is needed at
  8 Hz, and a real number beats a flattering one.
- **If the fallback path was taken, the episode says so.** "The exciting
  approach didn't work, here's the boring one that did" is a good episode and
  a true one.
- **An open-vocabulary model that finds `microphone` is not a model that
  understands microphones.** Do not let the demo imply comprehension. Add the
  distinction to `public-notes.md`'s NOT-real-yet list if it isn't there.
- **Do not claim the tier scheduler's savings until item 3 vs item 4 in the
  measurement table exists.** The argument is good; it still needs its number.

---

## Verification

- `uv run main.py --synthetic` still works end to end **with no camera**.
  This is the project's headless-verification path and it must survive today,
  or every future session loses the ability to check its own work.
- `uv run main.py --seconds 60` on the real camera produces valid JSONL with
  detections and stable track ids.
- Killing the capture process does not hang the main loop; the depth-1
  latest-wins queue (D29) still holds under a slow consumer — **verify this
  specifically now that T1 makes the consumer genuinely slow.** This is the
  first day the queue discipline is actually load-bearing.
- Memory does not grow over a 5-minute run.
- `src/` is untouched: `git status` shows changes only under `engine/` and
  `.claude/`.

---

## `.claude/` updates (part of the work, not paperwork)

- **`day8-results.md`** — new. The measurement table, conditions, and the
  intermittent-motion findings.
- **`decisions.md`** — D30: the detector choice, with the variant, the
  weights, the size, whether MLX or the fallback, and what specifically
  decided it. D31: the tracker choice, and an explicit note that D11, D21 and
  D27 are superseded — with *why* they were right for the model they were
  written against. D32: `MOTION_THRESHOLD`, tuned, with the clip it was tuned
  on.
- **`v2-roadmap.md`** — mark Day 8 shipped; add a "what Day 9 should know"
  block in the same shape Day 7 left for you. That block was genuinely useful
  this morning; pay it forward.
- **`public-notes.md`** — open-vocabulary detection moves off the NOT-real
  list if it shipped, with the "finding is not understanding" caveat added.
- **`tasks.md`** — carry forward anything cut, and close Day 3's
  track-id-persistence clip if it got shot.

---

## House rules

- Small commits, each a working state.
- Comments explain *why*, never *what*. `engine/motion.py` and
  `src/vision/tracker.ts` are the reference for density and tone.
- No dependency without a line in `decisions.md` saying why.
- Timebox the MLX path to mid-afternoon. Write down where it got stuck if it
  does — that note is worth more than a half-working export.

---

## Report back with

1. **Which detector shipped** — MLX/YOLOE or the fallback — and what decided
   it.
2. **The measurement table**, with borrowed numbers now replaced by ours and
   anything still borrowed marked as such.
3. **Is the bed a bed and the microphone a microphone?** With the shot, or
   with an honest account of why not.
4. **What the gate actually saves** — idle CPU with and against Day 7's 72%,
   and how many real-motion frames it missed on the intermittent clip.
5. **Whether T2/T3 stubs exist**, and where the preemption seam sits.
6. **What Day 9 inherits** — the JSONL shape, the end-to-end latency, and
   anything about the track output the bridge will have to accommodate.
7. **Anything measured today that contradicts the V2 plan.**
