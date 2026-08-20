# Day 9 — "Same face, new engine"

You are picking up YAP on Day 9. Days 1–8 have shipped. Read
`.claude/context.md`, `.claude/decisions.md` (D1–D33), `.claude/tasks.md`,
`.claude/v2-roadmap.md` (Day 8's SHIPPED block and Day 9's plan), and
`.claude/day8-results.md`. This document is the brief for today only.

---

## The goal, stated precisely

The Python engine works and nobody has ever seen it. Today it drives the HUD.

1. **The bridge.** `engine/` pushes frames over a local WebSocket; the React
   HUD renders them. `hudState.ts` and `drawHud.ts` should need almost no
   change — they consume a `Frame`, and we own that shape.
2. **Cash in the 8 Hz / 60 Hz illusion.** D15's τ=70ms interpolation was
   built on Day 5 for frame-rate independence and has never been tested
   against a genuinely slow source. Today it either pays for itself or it
   gets retuned — on evidence, on camera.
3. **Clear the camera debt Day 8 could not.** Day 8 ran sandboxed with no
   camera. Three things were left explicitly unfinished (D32, the
   bed/microphone shot, `debug_window.py`). Today needs a real camera
   anyway, so these are nearly free today and expensive on any later day.

The thesis for the day: **the seam held.** Five days of HUD work survived a
total engine transplant — a different language, a different model, a
different process — because the boundary between *what is true* and *how it
is drawn* was drawn in the right place on Day 2.

---

## Boundaries

- **Everything lives in this repo.** Every file — code, notes, captured
  clips, measurement output — goes inside
  `/Users/saketmunda/Work/Startup/projects/yap-hud`. Not `/tmp`, not a
  scratchpad, not a home directory. The model-weights cache
  (`~/.cache/yap-engine/weights`, D30) remains the single recorded
  exception and does not get extended today.
- **No cloud (D10).** The WebSocket binds to **localhost only**. Not
  `0.0.0.0`, not a LAN address, not a tunnel. The private server is Day 14
  and is hardware the user owns; it changes nothing about today.
- **Do not delete the browser-only build.** It stays alive behind a flag as
  the honest before-picture and as the fallback. Today's work is additive:
  the HUD gains a second frame source, it does not lose its first.
- **No LLM, no TTS, no voice.** T3 is Day 10. `tiers.py`'s stubs stay stubs.
  If you find yourself opening `src/narration/` or `src/voice/`, stop.
- **No T2 work.** D33 chose Grounding DINO for the on-demand pass and
  deliberately did not implement it. That stands. Do not front-run Day 13.
- **Do not tune τ (or anything else) before you have measured it.** Same
  rule as Days 7 and 8: a number tuned during the measurement is not a
  number.

---

## Where things stand (read this, it saves an hour)

From Day 8, carried forward verbatim because rediscovering any of it is
wasted time:

- **The JSONL shape is settled.** `engine/main.py`'s `emit()` writes
  `t`, `motion`, `gated`, `captureMs`, `gateMs`, `detections`, `tracks`,
  `inferenceMs`. `tracks` already carries
  `id/label/score/bbox/ageMs/missedFrames/labelConfidence/runnerUpLabel/labelVotes`
  — close enough to `src/vision/types.ts`'s `Track` that the bridge should
  be plumbing, not translation. Where it isn't, fix the *engine* side to
  match the type, not the type to match the engine.
- **`inferenceMs: null` is meaningful.** It means T1 did not run this
  frame, and `tracks`/`detections` are a deliberate carried-forward repeat.
  It does not mean "no data."
- **A still scene never goes empty.** T1's last output is held and
  re-emitted on gated and rate-limited frames on purpose. **If the HUD ever
  shows an empty room while the JSONL still has non-empty `tracks`, that is
  a bridge bug, not an engine one.** This is the single most likely way to
  break Day 8's work today without touching it.
- **The end-to-end floor is ~75–85ms** (p50/p95, capture→track, synthetic).
  That is what the bridge inherits *before* any serialisation, network, or
  render latency stacks on top. Today's job includes finding out what the
  total actually is.
- **~6–8% idle CPU with the gate on**, ~18–23% with it forced off, 76.4 FPS
  unthrottled inference, ~1.18GB RSS flat over 5 minutes. Day 7's browser
  build sat at ~72% of one core doing nothing. That comparison is the
  episode's spine and it must survive today: **if the bridge costs 30% CPU,
  the headline is gone.** Measure it.
- **Killing the capture child is safe; killing the parent orphans it.**
  Known, procedural, not a code bug — but you will be starting and stopping
  the engine all day today. Kill the child.
- **`MOTION_THRESHOLD` is 4.0 and is not tuned** (D32). The gate's
  open/close logic is confirmed correct against a synthetic bar. It has
  never seen a real room's lighting, sensor noise, or shadow motion.

---

## Part 0 — Clear the camera debt (first 45 minutes, timeboxed)

Do this **before** the bridge, because everything after it is more fun and
this will not survive contact with a working WebSocket.

1. **Record one real clip** into `engine/clips/` (add it to `.gitignore` if
   it is large; commit a short one if you can): walk into frame → **hold
   still for 20 seconds** → move again. This is the exact clip D32 asked
   for.
2. **Replay `motion.py`'s two functions against it** and report the raw
   mean-diff distribution across all three phases. The question is only:
   *is there daylight between the still phase's noise floor and the moving
   phase's signal, and where does 4.0 sit in that gap?*
3. **Set `MOTION_THRESHOLD` once, on that evidence, and write down the clip
   and the number together** (D34, retiring D32). If 4.0 turns out to be
   right, say that — "measured, unchanged" is a finding and it is a better
   one than a number that moved for no reason.
4. **Run `debug_window.py` against the real camera** — it has never been
   executed against live hardware or a display. Expect it to be broken in
   some small way. Fix it; it is your debugging tool for the rest of the day.
5. **Shoot the bed/microphone comparison.** Point the camera at a bed and a
   microphone. The old browser build calls them `dining table` and `tie`
   (D2). YOLOE with `prompts.txt` calls them `bed` and `microphone`. This
   is Day 8's headline shot, it has been owed since Day 8, and it takes two
   minutes with `debug_window.py` running.
6. **Film Day 3's track-id-persistence clip** while you have the camera up —
   an object leaves frame and returns, the id holds. Owed since Day 3,
   trivial now that ByteTrack is in.

If any of 1–6 overruns, **stop and carry it forward with a note.** Do not
let the debt eat the bridge; the bridge is the day.

---

## Part 1 — The bridge

### The decision that has to be made first

**Who owns the camera, and where do the pixels the HUD draws on come from?**

There are two answers and they have different failure modes:

- **(A) Two independent readers.** The browser opens the camera for display
  only (no detection); Python opens it separately for detection. Cheap, the
  60 Hz video path stays native, no encode on the hot path. Risks: macOS
  may or may not permit simultaneous access — **verify this in the first
  ten minutes, not at hour four** — and the two streams can differ in
  resolution, field of view, mirroring, and exposure. Boxes drawn over a
  *different instance* of the same scene is a subtle, demo-ruining bug.
- **(B) Python owns the camera and ships pixels too.** JPEG/H.264 frames
  over the same WebSocket. Alignment is guaranteed by construction and
  there is exactly one camera owner. Costs: an encode on the hot path, and
  bandwidth that competes with the CPU number the episode depends on.

**Recommendation: (A)**, because it keeps the video at 60 Hz for free and
the whole day's thesis is that the seam is clean. But verify simultaneous
access first, and if the browser and Python cannot both hold the camera on
this machine, switch to (B) immediately rather than fighting it — that is
today's equivalent of Day 8's MLX call, and the same rule applies: *"it
didn't work" is not a finding.* Write down what specifically failed.

If you take (A), the coordinate contract is not optional. Boxes are in
video-pixel space (`types.ts`), and the two streams' pixel spaces may not
match. Put **`sourceWidth`/`sourceHeight` in the frame envelope** and have
the bridge scale, so a resolution change on either side is a non-event.
Check mirroring explicitly — the browser self-view is conventionally
flipped and Python's is not.

### What to build

- A WebSocket server on the engine side, **localhost only**, pushing one
  message per emitted frame. Keep `emit()`'s stdout JSONL working
  unchanged — it is how the engine is debugged without a browser, and Day
  8's whole measurement method depends on it.
- **Push at detection rate, not frame rate.** ~8 Hz of messages, not 60. The
  client interpolates. This is the design, so the serialisation risk the
  roadmap names is mostly pre-paid — but confirm the message rate is what
  you think it is.
- **Latest-wins on the client too** (D29's rule, now crossing a socket). If
  a message arrives while one is unprocessed, the older one is dropped. A
  buffered WebSocket is exactly the browser bug in a new pipe.
- A frame source switch in the app — `?engine=1` or similar — where the
  default stays the browser-only build. **The old path must still work when
  the engine is not running.**
- **Staleness must be visible, not silent.** If no message arrives for
  ~1 second, the HUD must show that it is looking at old information —
  degrade the display honestly rather than holding beautiful stale boxes
  forever. This is the same discipline as `UNIDENTIFIED` (D22): the HUD
  never claims to know something it does not currently know. It is also
  what makes the engine dying on camera survivable instead of confusing.

### What not to build

No config UI, no auto-reconnect backoff framework, no protocol versioning,
no message schema library, no multi-client support. One producer, one
consumer, one socket, one afternoon.

---

## Part 2 — Does the illusion actually hold?

This is the part that could go the other way, and it is the more interesting
episode if it does.

D15 chose **τ = 70ms** on Day 5, against a browser detector running at
roughly 30 Hz — updates every ~33ms. The engine delivers updates every
**125ms**. τ=70ms against a 125ms gap means the box may still be visibly
chasing its target when the next update lands, and a fast-moving object will
lag in a way that never showed up at 30 Hz.

So: **measure before touching it.**

- Run the `?bench=1` recorder (Day 7's ring buffer) with the engine driving
  and record the rAF delta distribution — p50, p95, max. The claim is a flat
  frame graph while three processes run. Verify it.
- Film a fast pan and a hand moving quickly across frame. Look at whether
  the boxes lag, snap, or slide.
- If τ needs to change, change it **once**, record the old and new values
  and what the change was judged against, and note that it is now tuned for
  an 8 Hz source (D35). If velocity extrapolation turns out to be the real
  answer rather than a different τ, say so and write it down as a Day 11+
  item — do not build it today.

**The measurement table** goes in `.claude/day9-results.md`:

| # | Metric | Target / comparison |
|---|--------|---------------------|
| 1 | End-to-end camera→pixel-on-screen latency | vs Day 8's ~75–85ms capture→track floor |
| 2 | WebSocket message rate and payload size | should be ~8/s, small |
| 3 | HUD rAF delta p50/p95/max, engine driving | vs Day 7's browser-only distribution |
| 4 | Total CPU: engine processes + browser tab | vs Day 8's ~6–8% engine idle **and** Day 7's ~72% of one core |
| 5 | Behaviour on a still scene | boxes persist, HUD does not blank |
| 6 | Behaviour when the engine is killed mid-run | staleness shown within ~1s, no freeze, no crash |
| 7 | τ verdict | unchanged, or changed with the evidence named |

Row 4 is the headline. Row 5 is the trap. Row 6 is the thing that will
happen live on camera whether you test it or not.

---

## The demo

The HUD looks **identical** to Day 6 — same panels, same typography, same
subtitle track — and underneath it every single number is different: a
different language, a different model, a different process, an open
vocabulary, 8 Hz. The reveal is that nobody watching could tell, followed by
the frame graph sitting flat while three processes run.

The bed and the microphone are labelled correctly, in the same HUD that
called them a dining table and a tie six days ago.

---

## Build in this order. Cut from the bottom.

1. Camera-simultaneity check (ten minutes, decides Part 1's architecture)
2. Part 0's real clip + `MOTION_THRESHOLD` decision
3. WebSocket push, engine → HUD, boxes on screen
4. Coordinate/mirroring contract correct against the real camera
5. Staleness handling + engine-death behaviour
6. `?engine=1` flag with the browser-only path still working
7. Measurements 1–7 into `.claude/day9-results.md`
8. τ verdict
9. Part 0's remaining shots (bed/mic, track-id persistence, `debug_window.py`)

**Items 1–4 are the day.** If 5–6 slip, the demo still exists but it breaks
on camera the first time something goes wrong. If 3–4 slip, there is no
episode — the entire nine-day arc from here forward assumes the HUD is
showing engine output.

Item 9 is placed last but is **not** cuttable to nothing: if the camera is
up at all today, take the bed/microphone shot. It is two minutes and it is
owed.

---

## The honesty rules for today

- **Row 4 is not a controlled A/B and must not be presented as one.** Day 7
  measured a browser tab; today measures Python processes plus a browser
  tab, on a different runtime, with a different measurement method. The gap
  is large enough to be the headline honestly — say what it is, and say
  what it isn't.
- **If the interpolation does not hold at 8 Hz, that is the episode.** "The
  thing I built on Day 5 for exactly this moment needed retuning when the
  moment came" is a better and more useful story than a claim that quietly
  survived because nobody looked.
- **Do not claim the seam held if you had to change `drawHud.ts`.** Count
  the lines you touched in `src/hud/` and report the number, whatever it
  is. That number *is* the thesis, and a small honest number beats a
  rhetorical zero.
- **Every borrowed benchmark stays marked as borrowed** until re-measured
  here. Day 8 already retired one (the 124.9 FPS figure); the rule stands.

---

## Verification

- `npm run lint`, `npm run test`, **`npm run build`** all pass. D13 stands:
  this project's production build has broken in ways dev did not.
- **The browser-only path still runs with the engine stopped**, unchanged.
  Verify by loading the app with no Python process alive.
- `uv run main.py --synthetic` still works, unchanged — the headless path is
  how the engine is tested when hardware is not available, and Day 8 proved
  that matters.
- The stdout JSONL is byte-compatible with Day 8's, so `day8-results.md`'s
  measurement scripts still run.
- The socket is bound to localhost. Check it, do not assume it.

---

## `.claude/` updates (part of the work, not paperwork)

- **`day9-results.md`** — new. The table, the conditions, the clip names.
- **`decisions.md` D34** — `MOTION_THRESHOLD`, tuned or confirmed, against a
  named real clip. Retires D32 either way.
- **`decisions.md` D35** — the bridge: transport, who owns the camera and
  why, the coordinate contract, the latest-wins rule crossing the socket,
  and the τ verdict.
- **`public-notes.md`** — the HUD now renders engine output; the
  browser-only mode is a flag, not the default. Also: "runs in your
  browser" was already retired on Day 7 — check nothing has quietly crept
  back in.
- **`v2-roadmap.md`** — mark Day 9 shipped, with a "What Day 10 should know
  before starting" block in the same shape Day 8 left behind. It worked.
- **`tasks.md`** — carry forward anything cut, especially from Part 0.

---

## House rules

- Small commits, each one a working state.
- Comments explain *why*, never *what*. Match the density of the existing
  code — `tracker.ts` and `engine/main.py` are the references.
- No dependency added without a line in `decisions.md` saying why.
- If something takes longer than its timebox, stop and write down where it
  got stuck. That note is worth more than a half-finished spike.

---

## Report back with

1. **Which camera architecture you took (A or B) and the specific thing
   that decided it.**
2. **The table** — measurements 1–7, with conditions.
3. **How many lines of `src/hud/` you had to change**, and which files.
4. **The τ verdict**, and what it was judged against.
5. **What Part 0 produced** — the threshold number and its clip, and which
   of the four owed shots exist now.
6. **What was cut**, and what Day 10 inherits because of it.
7. **Anything measured today that contradicts the Day 10–15 plan.** Day 10
   is the centrepiece; this is the last cheap moment to find out.
