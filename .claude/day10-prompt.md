# Day 10 — "JARVIS, what am I looking at?"

You are picking up YAP on Day 10. Days 1–9 have shipped. Read
`.claude/context.md`, `.claude/decisions.md` (D1–D35), `.claude/tasks.md`,
`.claude/v2-roadmap.md` (Day 9's SHIPPED block and Day 10's plan), and
`.claude/day9-results.md` — especially its τ section, which contains the
finding that decides Part 0 below. This document is the brief for today only.

This is the ⭐ day. It is the centrepiece of the whole V2 arc, and it is the
first day since Day 1 where the thing being built is not a capability but a
*behaviour*.

---

## The goal, stated precisely

**Zero LLM in the path. That is not a limitation today, it is the design.**

1. **The query loop, end to end, deterministic.** Mic → VAD → Moonshine →
   `parseIntent` → `describeScene` → TTS. Every answer comes from code that
   *cannot* lie. When Day 11 adds the LLM and something is slow or wrong,
   you will know which half caused it, because today's half will have a
   number attached to it.
2. **T3 preempts T1.** A question in flight pauses ambient sensing. This is
   why the STT latency problem *disappears* rather than getting optimised
   away. `engine/tiers.py`'s `PreemptionSeam` has been sitting inert since
   Day 8 waiting for its first caller. Today it gets one.
3. **The speech policy: silence is the default.** YAP speaks when asked,
   when a rule fires, or when ambient mode is explicitly enabled. Days 1–6's
   constant narration becomes an off-by-default mode. Six days of work
   becomes a toggle, on purpose, on camera.
4. **Wake phrases: "Hey Yap" / "Yappy".** Push-to-talk works first and stays
   as the filming fallback. See Part 3 — the wake word has a specific,
   measurable acceptance bar and it is allowed to fail that bar.
5. **Close the oldest open gap in the project: confirm audio is audible on
   real speakers.** Never verified once in nine days.

The thesis for the day: **the moment it stops performing and starts
responding.** Everything before this was a system that talked. This is a
system you can interrupt.

---

## Boundaries

- **Everything lives in this repo.** Code, notes, clips, screenshots,
  measurement output — all inside
  `/Users/saketmunda/Work/Startup/projects/yap-hud`. Not `/tmp`, not a
  scratchpad, not a home directory. **Day 9 broke this** — it wrote
  `/tmp/real_hud_engine.png` and then noted it wasn't committed. Part 0
  fixes that. Do not repeat it. The model-weights cache
  (`~/.cache/yap-engine/weights`, D30) remains the single recorded
  exception and does not get extended today.
- **No cloud (D10).** STT and TTS are local models on this machine. The
  socket stays bound to `127.0.0.1` (D35). No exceptions, not even for a
  "quick test."
- **No LLM. At all. Today.** Not for intent, not for phrasing, not for a
  fallback when `parseIntent` returns `unknown`. `unknown` is an honest
  answer and it ships as one. The LLM is Day 11 and it arrives *after* the
  deterministic path has a measured latency to be compared against.
- **No T2 work.** D33 chose Grounding DINO for the on-demand deep look and
  deliberately did not implement it. That still stands. Day 13.
- **Do not delete the browser-only build or its voice path.** `src/voice/`
  and `src/narration/` keep working in browser-only mode as the
  before-picture. Today adds a second path; it does not remove the first.
- **Do not tune anything before measuring it.** Standing rule since Day 7.

---

## Where things stand (read this, it saves an hour)

- **`?engine=1` works end-to-end on real hardware.** Real camera, real bed
  detection, p50 77ms capture→pixel, camera architecture (A) confirmed —
  Chrome and Python hold the camera simultaneously.
- **`MOTION_THRESHOLD` is 5.0**, tuned against two real clips (D34). Noise
  ceiling measured at 4.22; the one real motion sample reached 6.195.
- **`src/hud/` diff is still zero lines** across the entire engine
  transplant. Protect that number.
- **`uv run python main.py` does not exec-replace itself.** Killing the PID
  it hands back orphans the real process, which keeps holding the WebSocket
  port. **Kill the process group.** Today scripts against `main.py` more
  than any day so far, so this will bite repeatedly if ignored.
- **`inferenceMs: null` means T1 did not run this frame** and
  `tracks`/`detections` are a deliberate carried-forward repeat. This
  matters enormously today — see Part 0.
- **`parseIntent` already knows the phrase "hey yap"** — it is in the `WAKE`
  regex, written on Day 6 before there was any wake word. That is a
  coincidence worth using, not a design that already exists.

---

## Part 0 — The Day 9 fixes, before anything else

Six items. Four are quick. **The first one is not optional and is not
cosmetic — Day 10's demo does not work without it.**

### 0.1 — A question must force a fresh look (the blocker)

Day 9's τ investigation found something more important than τ: **the motion
gate does not open for a seated person's localized gestures.** `motion.py`
averages absolute pixel difference over the whole 160×120 downscaled frame,
so a hand near a face is too small a fraction to clear threshold. Three real
attempts, three frozen boxes, `Inference: 0.0ms` throughout.

Day 9 correctly called this "plausible, even desirable" for an ambient
detector. **For Day 10 it is fatal**, and here is exactly why:

> The Day 10 demo is a person *sitting still* and *asking a question*.
> By construction, the gate is closed. T1 has not re-run in seconds.
> `describeScene` reads held, stale tracks — and YAP confidently describes
> a room as it was some unknown time ago.

The fix is **not** to retune the gate. Lowering the threshold to catch
gestures re-opens the noise floor D34 just measured, and throws away the
6–8%-idle-CPU number the last three episodes are built on.

**The fix is that asking a question is itself a reason to look.** When T3
fires, it forces a fresh T1 run before `describeScene` reads anything — one
detection, on demand, synchronously, in the query path. This is the tier
model working exactly as designed: ambient sensing stays cheap and lazy
*because* the query path can pay for its own freshness. Write it up in
`decisions.md`; it is the sharpest illustration of the T0/T1/T3 split the
project has produced so far.

Report the added latency this costs the query path. It is real (~30–45ms
per D8/D9's in-loop numbers) and it is worth it, but the number goes in the
table, not in a hand-wave.

### 0.2 — Audio hardware check (first fifteen minutes)

Day 7's lesson was that a camera-permission dialog can eat a morning if it
is discovered at hour four. **The microphone and the speakers have the same
property and neither has ever been touched from Python on this machine.**
Before building anything:

- Capture 3 seconds from the mic in Python and confirm non-silent samples.
  Expect a macOS permission dialog. Get it out of the way now.
- Play a known tone or WAV through the speakers **and confirm a human heard
  it.** Not "the call returned successfully" — *heard*. This is the oldest
  open verification gap in the project (nine days), and it closes by someone
  listening, not by an exit code.
- **Then answer the mic-contention question**, which is Day 9's camera
  question wearing a different hat: Chrome's `getUserMedia` (Day 6's
  push-to-talk) and Python both want the mic. Verify whether they can hold
  it simultaneously, the way `scripts/camera-dual-test.mjs` did for video.
  **Recommendation: Python owns the mic exclusively from today**, and the
  browser's mic path becomes browser-only-mode legacy — one owner is simpler
  and the engine is where STT has to live anyway. But verify rather than
  assume, and if they *can* coexist, say so; it is a useful fact for Day 15.

### 0.3 — The τ test that Day 9 identified but did not run

Day 9 named the exact next step: **stand up, step back from the camera, and
walk across frame** while `?engine=1` runs. Full-body motion clears the gate
and produces repeated fresh T1 runs, which is the only condition under which
interpolation can actually be judged. Run it, film it, and give τ a verdict
— unchanged with evidence, or changed with evidence. Either is a result;
a fourth deferral is not.

While you are up: that walk is also **a second real motion sample**, which
D34 explicitly flagged as thin (one sample). Record it into `engine/clips/`
and add its mean-diff distribution to D34's evidence.

### 0.4 — Fix the clip-overwrite script bug

Day 9 lost a 25-second ambient clip to a script bug that overwrote it.
Whatever writes into `engine/clips/` must not silently clobber. Two-line fix,
and today records more clips than any previous day.

### 0.5 — `debug_window.py`'s window, confirmed visible

It runs clean and consumes real JSONL, but no one has ever confirmed the
`cv2.imshow` window actually appears — Day 9's detached-background-process
launch never attached to a window server session. **Launch it from a real
interactive terminal and look at it.** Two minutes.

### 0.6 — The owed shots, into the repo

- Re-take the live HUD screenshot **into `.claude/day9-images/`**, not
  `/tmp`. Day 9's boundary violation, corrected.
- **The microphone half of the bed/microphone shot.** It has been owed since
  Day 8 purely because no microphone was in frame. Today there is a
  microphone in the room by definition — it is the day's whole subject.
  Point the camera at it, let YOLOE label it `microphone`, and take the
  shot the last two episodes have promised.

**Timebox Part 0 to the first two hours.** 0.1 and 0.2 are not cuttable —
the day does not function without them. 0.3–0.6 carry forward with a written
note if they overrun.

---

## Part 1 — T3: the query loop

### Where T3 lives, and the decision that has to be made first

`parseIntent` and `describeScene` are TypeScript, tested, and good
(85 tests pass). Moonshine and Kokoro/Piper are Python. The preemption seam
is Python. The tracks are Python.

**Recommendation: T3 lives in the engine, and `parseIntent`/`describeScene`
get ported to Python.** Audio has to be native, and once mic-in and
speaker-out are in Python, routing the middle of the loop back through a
socket to the browser and back adds latency to the one path where latency is
the entire point.

**Port the tests with the logic — the tests *are* the spec.** And then do
the thing that stops the two copies drifting: extract the intent cases into
**one shared fixture file in the repo** (e.g. `spec/intent-cases.json`) that
*both* `src/voice/parseIntent.test.ts` and the new Python test read. Two
implementations, one spec, one place to add a case. The TS versions stay
alive for browser-only mode and are explicitly frozen as legacy.

If you find a genuinely better structure while doing it, take it — but
**every existing test case must still pass in both languages**, and any case
whose behaviour deliberately changes gets named in the report.

### The loop

```
mic → VAD (always-on, cheap) → Moonshine STT → parseIntent
    → [T3 requests the floor: PreemptionSeam.request()]
    → forced fresh T1 detection (Part 0.1)
    → describeScene(tracks)
    → TTS → speakers
    → [PreemptionSeam.release()]
```

- **VAD is the audio motion gate**, and the symmetry is exact and worth
  saying out loud on camera: T0 for vision is "did any pixels change," T0
  for audio is "is anyone speaking." Neither runs a neural net worth
  worrying about. Use Silero VAD or equivalent — small, CPU, chunked.
  **Never run STT on silence.**
- **`unknown` is a shipped answer.** When `parseIntent` falls through, YAP
  says it did not understand, briefly, and stops. It does not guess, and it
  does not reach for a model. `public-notes.md` already says this is
  pattern-matching, not language understanding — today it has to *behave*
  that way in front of a camera.
- **Grounding is absolute.** `describeScene` reads only tracks. It never
  invents an object and never resolves an uncertain label to one winner
  (D22's `UNIDENTIFIED` discipline, `events.ts`'s honesty rule). If the
  fresh T1 run comes back uncertain, the spoken answer hedges — out loud.

### Preemption, done honestly

`PreemptionSeam.request()` must actually cause T1 to yield, and you must be
able to *show* it: the JSONL should visibly stop producing fresh
`inferenceMs` values for the duration of a query, and resume after. If it
does not show up in the JSONL, it did not happen.

**T0 keeps running regardless** — it is cheap and always-on by design, and
the tier table says so. Do not gate the gate.

---

## Part 2 — Silence is the default

This is the smallest diff of the day and the biggest product change.

- Ambient narration becomes **off by default**. `narrator.config`'s
  `voice_enabled`/narration path gets an explicit ambient-mode switch, and
  the default is off.
- YAP speaks in exactly three cases: **asked**, **a rule fired**, or
  **ambient mode is explicitly on**.
- The HUD must make the mode visible. A viewer — and you, filming — should
  never have to wonder whether it is about to start talking.

Write this in `decisions.md` as a product decision, not a config change,
and be plain about what it means: the narration engine that carried Days
1–6 and most of the series so far is now a mode nobody turns on. That is
not a failure; it is what "on-demand" actually costs, and the honest framing
is that six days of narration work is what *taught* the project that
silence was the right default.

---

## Part 3 — The wake phrase

### What is shipping

**"Hey Yap"** and **"Yappy"** as the wake phrases. Push-to-talk works first,
ships regardless, and stays the filming fallback.

### About "yo"

You asked for "yo" / "Hey yo" as well, and it should be built but **not
enabled by default**, for a specific reason rather than a stylistic one:
"yo" is a single ~150ms syllable that appears inside ordinary speech
constantly — *"you"*, *"your"*, *"yeah"*, *"yoga"*, *"hello"*, and the
first half of *"YouTube"*. A wake word that short cannot be made both
sensitive and precise; every threshold that catches it reliably also fires
on normal conversation. **"Hey yo"** is two syllables and materially safer
than bare "yo", so ship "Hey yo" as an enabled phrase and put bare **"yo"**
behind an opt-in flag with its measured false-accept rate written next to
it.

Then let the measurement decide rather than the argument — see the
acceptance bar below. If "Hey yo" measures clean, keep it on. If it fires
during the ten-minute conversation test, it goes behind the flag with
"yo" and the number is the reason.

**The failure mode being avoided is specific:** a wake word that misfires
on camera is worse than a button that doesn't. This is the roadmap's own
guidance and it is correct.

### How to build it today

**Transcribe-then-match, and describe it as exactly that.** VAD gates →
Moonshine transcribes a rolling ~1.5s buffer → fuzzy-match against a phrase
list. Moonshine is already in the build for STT, so the wake path costs no
new model.

A real keyword spotter (openWakeWord) would keep the always-on tier
genuinely cheaper, **but a custom phrase like "Yappy" needs a trained model**
— synthetic-speech data generation plus a training run, which is hours, not
an afternoon, and it is not today's work. Note it in `decisions.md` as the
real upgrade path with its actual cost, so a later day can pick it up
knowing what it involves.

Put the phrase list in **`engine/wake_phrases.txt`**, mirroring
`prompts.txt` exactly — same user-editable, hot-reloadable, one-per-line
pattern. Adding a wake phrase should be typing a word into a text file. That
is the same episode beat that made the `prompts.txt` reveal land on Day 8,
and it costs nothing to reuse.

Match with tolerance, because STT will not hand you clean text: *"hey yap"*
will come back as *"hey yeah"*, *"hey app"*, *"hay yap"*. Fuzzy-match, and
**write down the real transcriptions you observe** — that list is both the
tuning evidence and a good piece of footage.

### The acceptance bar (this is a measurement, not a vibe)

| Test | Method | Bar |
|---|---|---|
| **False accepts** | 10 minutes of normal conversation / a podcast playing in the room, nobody addressing YAP | **Zero.** One misfire in ten minutes is one misfire per take. |
| **False rejects** | 20 deliberate utterances — near, mid, and across-room | Report the hit rate honestly. |
| **Wake→answer latency** | wake phrase to first spoken word | Report p50/p95. |

**The wake word is allowed to fail this bar.** If it does, it goes behind a
flag, push-to-talk carries the demo, and the report says so. That is a
result, and it is a better one than a wake word that works in rehearsal and
embarrasses you on take four.

### The feedback trap

TTS output goes into the same room as the microphone. Two consequences,
both real:

1. **YAP can wake itself up** by saying a wake phrase, or trigger STT on its
   own voice. Suppress wake matching against text YAP is currently speaking.
2. **But "stop" must still work while it is speaking** — the "it stops
   mid-word" moment *is* the demo, and it requires listening during
   playback. So this cannot be solved by simply muting the mic during TTS.

Simplest honest resolution: push-to-talk stays live during playback and can
always interrupt, while the wake-phrase matcher is suppressed against known
in-flight TTS text. If you find something better, take it — but do not ship
a design where the demo's best moment is impossible.

---

## The measurement table → `.claude/day10-results.md`

| # | Metric | Comparison |
|---|--------|------------|
| 1 | Wake/press → first spoken word, p50/p95 | The number Day 11's LLM path gets compared against |
| 2 | Breakdown: VAD, STT, forced T1, describeScene, TTS first-audio | Where the time actually goes |
| 3 | Forced-fresh-T1 cost (Part 0.1) | vs Day 8/9's ~30–45ms in-loop detection |
| 4 | Preemption visible in JSONL during a query | Yes/no, with the evidence |
| 5 | Idle CPU with mic + VAD always on | vs Day 9's ~6–13% engine |
| 6 | Wake-phrase false accepts / false rejects | The bar above |
| 7 | Audio confirmed audible on real speakers | By a human, not an exit code |
| 8 | τ verdict (Part 0.3) | Unchanged with evidence, or changed with evidence |

Row 1 is the headline. Row 4 is the thesis. Row 7 is nine days overdue.

---

## The demo

Silent room. Silent HUD. Nothing is being narrated, nothing is being said.

*"Hey Yap — what do you see?"*

One beat. A grounded, accurate, one-sentence answer about the actual room.

Then *"stop"*, and it stops mid-word.

**The silence before the answer is the demo.** Do not fill it. Do not add a
thinking sound, a chime, a spinner, or a pulsing HUD element to cover the
latency — the whole point is that the gap is short enough not to need
covering, and if it isn't, that is a number you need to see rather than
decorate.

**Hook:** *"For six days it wouldn't shut up. Today I made it quiet — and
that's what finally made it feel intelligent."*

---

## Build in this order. Cut from the bottom.

1. Audio hardware check — mic in, speakers out, heard by a human (0.2)
2. Forced fresh T1 on query (0.1) — the blocker
3. `parseIntent` + `describeScene` ported to Python, shared fixture, tests green
4. Push-to-talk → STT → intent → describeScene → TTS, end to end
5. Preemption wired, and visible in the JSONL
6. Silence-by-default + the HUD mode indicator
7. Wake phrases + `wake_phrases.txt` + the acceptance bar measured
8. Measurements 1–8 into `day10-results.md`
9. Part 0's remaining items (τ walk test, clip bug, debug window, owed shots)

**Items 1–4 are the day.** If 5 slips, the demo works but the thesis is
unproven. If 6 slips, the demo is impossible — YAP will talk over its own
answer. If 7 slips entirely, push-to-talk carries the episode and the wake
word becomes Day 11's opener; that is an acceptable outcome and the roadmap
already says so.

If items 1–4 do not land, **stop and say so rather than shipping a loop that
half-works.** This is the ⭐ day; a clean deterministic loop with no wake
word is a strong episode, and a flaky wake word on top of a shaky loop is
not.

---

## The honesty rules for today

- **"Zero LLM" is a claim to make loudly and precisely.** Today's answers
  are pattern-matched, not understood. Off-script phrasing falls through to
  `unknown`, and the demo should show that happening at least once rather
  than only rehearsed phrasings.
- **Do not describe transcribe-then-match as a keyword spotter.** It isn't
  one. Say what it is; it works, and the honest description is more
  interesting than the borrowed term.
- **Report the wake word's real numbers even if they are bad.** Especially
  if they are bad.
- **If the forced-fresh-T1 fix makes queries feel slow, say the number.**
  Do not quietly cache your way around it and claim the latency.
- **Speakers: "I heard it" is the verification.** Nine days of "it speaks"
  has never once been heard on real hardware. Close it properly or leave it
  open honestly — do not close it on an exit code.

---

## Verification

- `npx tsc -b`, `npx oxlint src/`, `npm run test`, `npm run build` — all
  clean. D13 stands.
- **The Python and TS `parseIntent` agree on every case in the shared
  fixture.** Both suites run in CI-equivalent form locally.
- `uv run main.py --synthetic` still works, unchanged interface — the
  headless path has saved two separate days already.
- **Browser-only mode still runs with the engine stopped**, voice path
  included, unchanged.
- The socket is still bound to `127.0.0.1`. Check with `lsof`, do not assume.
- `git status` shows nothing outside `engine/`, `src/`, `spec/`, `scripts/`,
  and `.claude/`. No `/tmp` paths anywhere in the results docs.

---

## `.claude/` updates (part of the work, not paperwork)

- **`day10-results.md`** — new. The table, conditions, the observed wake
  transcriptions, the false-accept log.
- **`decisions.md` D36** — a query forces a fresh T1 look. Why the fix is in
  the query path and not in `MOTION_THRESHOLD`, with the CPU number that
  retuning would have cost. This is the strongest illustration of the tier
  model in the project; give it the space D28 got.
- **`decisions.md` D37** — where T3 lives, the Python port, the shared
  fixture, and what happens to the TS originals.
- **`decisions.md` D38** — silence by default, as a product decision.
- **`decisions.md` D39** — the wake phrases: transcribe-then-match and why,
  the chosen phrase list, "yo" behind a flag with its number, and
  openWakeWord's real cost as the named upgrade path.
- **`decisions.md` D34 (amend)** — the second real motion sample from 0.3.
- **`public-notes.md`** — "it understands you" is **not** a claim today.
  Add: wake phrase is transcribe-then-match; answers are pattern-matched;
  ambient narration is now off by default. Move "audio audible on real
  speakers" out of the NOT-verified list only if a human actually heard it.
- **`v2-roadmap.md`** — mark Day 10 shipped, with a "What Day 11 should know
  before starting" block. Day 8 and Day 9 both left one and both paid off.
- **`tasks.md`** — carry forward anything cut, especially from Part 0.

---

## House rules

- Small commits, each one a working state.
- Comments explain *why*, never *what*. Match the density of the existing
  code — `tracker.ts`, `engine/main.py`, and `parseIntent.ts` are the
  references.
- No dependency added without a line in `decisions.md` saying why.
- If something takes longer than its timebox, stop and write down where it
  got stuck. That note is worth more than a half-finished spike — it is how
  Day 9 handed Day 10 the finding that shaped this entire brief.

---

## Report back with

1. **Row 1 of the table** — wake/press to first spoken word, p50/p95, with
   the full breakdown. This is the number Day 11 will be judged against.
2. **Whether audio was actually heard by a human**, and on what.
3. **The wake-phrase numbers** — false accepts over ten minutes, false
   rejects over twenty tries, and which phrases ended up enabled by default.
4. **The real transcriptions Moonshine produced** for each wake phrase.
5. **Proof of preemption** — the JSONL evidence, not the intent.
6. **The forced-fresh-T1 cost**, and whether the query still feels instant.
7. **The τ verdict** from the walk test, finally.
8. **What was cut**, and what Day 11 inherits because of it.
9. **Anything measured today that contradicts the Day 11–15 plan** — Day 11
   adds an 8B model to a loop you will have just finished making fast. If
   today's numbers say that is going to hurt, say so now.
