# Day 11 — "It stops identifying and starts understanding"

**The brain swap.** Rip out the label → template → LLM chain and put a real
vision-language model behind T2/T3. Give it a second pair of eyes (the
screen). Make it read.

Read `.claude/v2-roadmap.md`'s ENDGAME REWRITE section before starting —
it explains why the plan changed at Day 11 and what the remaining four days
must hit. Read `jarvis_friday_edith_combined_ai_system_spec.md` §7 (Layers
A/B), §19 (Provenance) and §23 (Screen and Vision Intelligence): those three
sections are what today is scored against.

---

## Why this day exists

Days 1-10 built one capability ten times. The audit against the spec put the
build at ~15% of it, almost all inside §7 Layer A. Today is the first of four
days that must land somewhere other than that corner.

There is also a concrete engineering reason, not just a product one. The
current answer path is a **telephone game**:

```
frame → YOLOE (80-ish text-prompted classes) → tracks
      → describe_scene() string template
      → qwen2.5:7b, which never sees the image
      → answer
```

Every grounding bug in `decisions.md` D40's amendments is a symptom of that
chain, not of the LLM:

- *"you're standing next to the chair"* — the model was reasoning about a
  **word list**, so it filled in posture it had no way to know.
- *"you're holding glasses"* — a detector false positive, laundered into a
  confident sentence by a model with no way to check.
- The whole few-shot-prompt arms race in `engine/llm.py` exists to stop a
  blind model inventing things.

**A model that looks at the actual frame does not have this failure mode.**
Today is not "swap the LLM for a bigger LLM." It is deleting an entire class
of bug by removing the layer that caused it.

---

## Boundaries

- **Everything stays in this repo.** No `/tmp`, no scratch directories, no
  session temp. Clips, screenshots, JSONL, results — all inside `yap-hud/`.
  The one standing exception is the model-weights cache (D30). Day 9 broke
  this rule and Day 10 had to clean it up; do not be the third occurrence.
- **Local only.** No cloud APIs, ever. Ollama on this machine, or MLX. A
  private server the user owns is acceptable later; a third-party API is not.
- **`parse_intent` is not touched for `stop`, `wake`, `sleep`.** An LLM must
  never decide whether "stop" stops (D6/D25). If anything, the safety path
  gets *more* deterministic today, not less.
- **The VLM is T2/T3 only.** It runs behind `PreemptionSeam`, on demand,
  never on the 8Hz ambient loop. T0/T1 (motion gate + YOLOE + ByteTrack)
  are untouched and stay cheap — the ~6-8% idle CPU number from Day 8 must
  survive this day.
- **No memory, no tools, no permissions today.** Those are Days 12 and 13.
  Resist the pull.
- **Verify the model choice before writing it.** Qwen3-VL-8B is this brief's
  recommendation as of 2026-08-22, checked this month — but check it holds
  when you start, and state release dates for anything you substitute. See
  `memory/yap_no_stale_tech.md`. Shipping a stale default is a firing
  offence on this project.

---

## Where things stand

From `.claude/day10-results.md`, `decisions.md` D36-D40 and `tasks.md`:

- **The query loop works end to end on real hardware.** `engine/query_loop.py`:
  mic → VAD → Moonshine → `parse_intent` → forced-fresh-T1 → `describe_scene`
  → `say` → speakers. One real success measured at **119.1ms** for
  intent→TTS-start.
- **`PreemptionSeam` is wired and proven** (D36). `request_fresh_look()` /
  `poll_force_request()` / `deliver_fresh_look()`. Forced T1 costs **33.4ms**
  real inference, **71.2ms** wall-clock round trip. Budget the VLM against
  that number, not against zero.
- **`engine/llm.py` currently calls Ollama `qwen2.5:7b`** over
  `http://localhost:11434/api/chat`, temperature 0.2, with a few-shot
  grounding example. It is text-only and blind.
- **Ollama is already installed and used on this machine**, native (Metal via
  llama.cpp), not Docker. Models are pre-pulled. This is why D40 chose it
  over MLX.
- **A real, still-unexplained bug is open:** the "glasses" false positive was
  never diagnosed because `clips/detect-log.jsonl` was requested and never
  captured. **Today probably makes it moot** — but see item 6 below, because
  "probably" is not evidence.
- **`uv run python main.py` does not exec-replace itself.** Kill the process
  group, not the PID `uv run` returns, or the real process keeps the
  WebSocket port.
- **Mic permission on this machine is per-process-tree.** Terminal.app, VS
  Code's integrated terminal and an agent's own process each need a separate
  grant. Every real audio test to date had to be run by the project owner in
  Terminal.app directly. Plan around this — do not lose an hour rediscovering
  it.
- **Open, needs the project owner and blocks nothing today:** "yap"
  transcribes as **"app"**, repeatedly, live. The wake phrase needs renaming.
  Surface it, don't solve it unilaterally, don't let it eat the day.

---

## Part 1 — Qwen3-VL behind T2/T3

**1.1 Get the model running and measure it before designing around it.**

Pull Qwen3-VL-8B (Q4) through Ollama and time a real single-image query on a
real camera frame from this machine. Do this **first**, in the first thirty
minutes, before any integration work. The number decides the architecture:

- If first-token latency is comfortably inside ~1.5s, it can answer questions
  directly.
- If it is slow, it stays a deep-look tier and the fast deterministic path
  (`parse_intent` → tracks → `describe_scene`) keeps answering the simple
  questions instantly, exactly as it does today.
- If 8B is too slow on this M4 Pro, **drop to Qwen3-VL-4B and report the
  number** rather than quietly shipping something that stutters on camera.

Report first-token latency and total latency, p50 and p95, over at least 10
real queries. Not one lucky run.

**1.2 Replace the blind path, keep the fast path.**

The new shape:

```
                        ┌─ parse_intent → stop/wake/sleep       (deterministic, instant, unchanged)
utterance ─ intent ─────┤
                        ├─ parse_intent → describe/query_object (fast path: forced T1 + describe_scene)
                        │
                        └─ everything else ────────────────────► Qwen3-VL
                                                                  ├─ the actual frame (JPEG)
                                                                  ├─ the track list (as corroboration, not as the source)
                                                                  └─ the question
```

`engine/llm.py` becomes a **vision** call: image + question, not a word list
+ question. Keep the module's honest docstring tradition — say what changed
and why, including that the few-shot grounding hack is being removed because
the reason for it is gone.

**Keep `describe_scene` alive.** It is the fast path and it is deterministic.
This is not a deletion day for it — it is a demotion from "the source of all
answers" to "the instant answer for simple questions."

**1.3 Grounding, structurally.**

The tracks still matter — they are the cheap, calibrated, always-current
signal. Pass them alongside the image as **corroboration**, and make the
disagreement case explicit: if the VLM says something the tracks contradict,
that is interesting and should be logged, not silently smoothed over.

Every answer carries provenance (§19): what was claimed, from which source
(VLM / tracks / both), at what timestamp, with what freshness. A JSONL line
per answer, into `engine/clips/`. This is the same discipline as
`labelConfidence`, `runnerUpLabel` and the staleness banner — the project's
one real strength, extended to the new layer.

**1.4 Preemption, unchanged.**

The VLM call runs inside `preemption.request()` / `release()`, in a
`try/except/finally` — D40's fourth amendment found that an unhandled
exception here silently killed the wake thread *and* left the seam stuck
`active` forever, freezing ambient T1. That `finally: release()` is load-
bearing. Do not regress it, and add a test that proves it still holds with
the new call in place.

---

## Part 2 — The second pair of eyes: screen capture

**This is the first genuinely new input type since Day 1**, and §23 of the
spec is currently at zero.

- On-demand screen capture (`screencapture -x`, or ScreenCaptureKit if it is
  cleaner) — **never continuous**, never on the ambient loop. It is a T2
  action, triggered by intent.
- Route intents that are clearly about the screen — *"what's on my screen,"
  "what's this error," "why is this failing," "read that"* — to the screen
  frame instead of the camera frame.
- Ambiguity is a real product question: *"what's this?"* could mean either.
  Pick a default, state it in the results doc, and make it overridable by
  saying "on my screen" or "in front of me." Do not build a disambiguation
  dialogue today.
- **Privacy is a credibility beat, not a disclaimer.** The screen is captured
  only on an explicit request, never stored beyond the answer, never sent
  anywhere. Say it out loud in the episode.

---

## Part 3 — Make it read

Reading is the single most visible capability gain available today. Nothing
in ten days of build can read one word.

Test and record real results, into the repo, for:

1. A **terminal stack trace** on screen — *"what's wrong?"*
2. A **receipt or bill** held to the camera — *"how much?"*
3. A **document or book page** — *"what does this say?"*
4. **Handwriting** — the honest hard case; report the failure if it fails.
5. A **label / product packaging** held up at a normal distance.

For each: the real image (into `.claude/day11-images/`), the real question,
the real answer verbatim, and whether it was correct. **Wrong answers get
recorded, not retried until they look good.**

---

## Part 4 — The measurement table

Into `.claude/day11-results.md`. Every number from this machine, this
session, marked real or synthetic. No fabricated rows — an honest "not
measured" beats a guess, as on every previous day.

| # | Metric | Why |
|---|---|---|
| 1 | VLM first-token and total latency, p50/p95, ≥10 real queries | Decides whether it is an answerer or a deep-look tier |
| 2 | Model + quantization + resident memory | The 8B-vs-4B decision, on evidence |
| 3 | End-to-end wake/press → first spoken word, p50/p95 | **Day 10's row 1, never cleanly captured. Capture it today.** The instrumentation already exists in `query_loop.py` |
| 4 | Fast path (`parse_intent` + `describe_scene`) latency, unchanged? | Prove the simple questions did not get slower |
| 5 | Idle CPU, ambient loop, VLM loaded but not called | The ~6-8% Day 8 number must survive |
| 6 | Reading accuracy: 5 cases from Part 3, correct/incorrect | The episode's actual claim |
| 7 | VLM vs. tracks disagreement rate over ~20 queries | New, and interesting either way |
| 8 | Does the "glasses"-class invention still occur? | See item 6 below |

---

## Part 5 — The debt, and the new rule about debt

The Endgame rewrite's first rule: **no day is spent refining a previous day.**
Debt is carried and stated on camera, not repaid at the cost of a new
capability. So, explicitly:

**Do today, because they are cheap and inside today's work:**
- Row 3 of the table (the wake-to-answer number) — the instrumentation is
  already shipped, it costs one clean run.
- **Re-test the two Day 10 grounding failures verbatim** against the new
  path: *"what am I doing right now?"* and *"what am I holding?"* with nothing
  in hand. If the VLM still invents, that is a real finding and it belongs in
  the results doc in bold — the thesis of this day would be wrong, and saying
  so is worth more than hiding it.
- The `glasses` question (table row 8). If the VLM stops inventing it, the
  bug is moot and gets closed with that reasoning stated. If it persists,
  capture `clips/detect-log.jsonl` at last.

**Do not do today:**
- `debug_window.py` on-screen confirmation (carried since Day 9)
- The mic-contention dual-open test
- Owed screenshots from Day 9/10
- The browser-side ambient indicator, the `bench.mjs` re-run
- Ollama's `keep_alive` latency spike — *unless* it reappears with the new
  model, in which case it is a one-line fix and today's problem

Carry the rest forward in `tasks.md`, visibly.

---

## Build order

1. **Pull Qwen3-VL and measure it cold** (30 min, hard timebox). The number
   shapes everything after it.
2. **Wire it into `engine/llm.py` as a vision call**, image + question.
3. **Route `unknown` intents to it**, keep `parse_intent`'s safety path and
   the `describe_scene` fast path intact.
4. **Provenance logging** — one JSONL line per answer.
5. **Preemption + `try/except/finally` regression test.**
6. **Screen capture as a source**, intent routing for screen questions.
7. **The five reading tests**, real images into the repo.
8. **The measurement table**, including the two verbatim Day 10 retests.
9. **`.claude/` updates.**

**Items 1-3 are the day.** If nothing else lands, a VLM answering real
questions about a real frame is the episode. If item 6 slips, the camera path
alone still proves the swap — screen capture is the roadmap's designated cut
for this day, and cutting it should be said on camera, not quietly.

---

## Honesty rules

- **Report the latency, whatever it is.** If the 8B model is too slow and the
  build drops to 4B, that is the story of the day and it is a good one.
- **Do not claim the grounding bugs are fixed until the verbatim retests pass.**
  "It should fix it" is a hypothesis. The retest is evidence.
- **Do not call Qwen3-VL "understanding."** It is a vision-language model
  producing text conditioned on an image. The project's credibility is that
  it never claims more than it knows — that rule applies to describing the
  build itself, not only to what the build says.
- **Count what actually changed.** Report the real diff stat for
  `engine/llm.py`, `engine/query_loop.py`, and anything in `src/`. If the HUD
  needed changes this time, say so — the zero-diff streak is not a target
  worth protecting by lying about it.
- **State the release date of every model in the stack after today**, in the
  results doc. That table is now a permanent fixture on this project.

---

## Verification before calling it done

- `--synthetic` mode still runs.
- Browser-only mode (no `?engine=1`) still runs untouched.
- WebSocket still bound to `127.0.0.1` only — check with `lsof`, not by
  reading the source.
- "stop" still stops, mid-word, with the VLM in the loop.
- The seam is never left stuck `active` — prove it with a fake VLM that
  always raises, the same test D40's fourth amendment used.
- Ambient T1 still runs at 8Hz and idle CPU has not regressed.
- **No `/tmp` paths anywhere in the results docs or the code.**

---

## `.claude/` updates

- **D41** — Qwen3-VL replaces the label→template→LLM chain. Record the real
  latency numbers, the 8B-vs-4B decision, and the structural argument (the
  telephone game caused D40's grounding bugs). Note explicitly what D40 got
  right and what it can now retire.
- **D42** — screen capture as a perception source: on-demand only, the
  camera-vs-screen routing default, and the privacy rule.
- **D43** — provenance for VLM answers, extending D22's discipline.
- Amend **D40** with the outcome of the two verbatim retests, whichever way
  they go.
- `tasks.md` — close what closed, carry what carried, visibly.
- `public-notes.md` — the reading capability, and the honest note that the
  detector's role changed rather than the detector being "upgraded."
- `v2-roadmap.md` — a "What Day 12 should know" block on Day 11, in the same
  form as every previous day.

---

## Report back

1. The VLM latency numbers, and which model shipped.
2. Whether the two Day 10 grounding failures survived the swap — verbatim
   answers, both of them.
3. The five reading tests, with the failures included.
4. The wake-to-answer number, finally.
5. Whether idle CPU held.
6. What was cut, and why.
7. Anything found that Day 12 (memory, identity, context engine) needs to
   know before it starts.
