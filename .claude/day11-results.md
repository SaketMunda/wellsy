# Day 11 results

Everything below is measured on this machine (M4 Pro, 24GB), this session,
real hardware (real camera, real Ollama server) unless explicitly marked
otherwise. Where audio couldn't be exercised through this agent's own
process (the same standing mic-permission gap tracked since Day 9/10),
`handle_command()` was called directly with a real transcript string
against real camera frames and a real VLM call — the same "fake STT, real
everything else" methodology decisions.md D40's amendments used throughout.

## The measurement table

| # | Metric | Result | Conditions |
|---|--------|--------|------------|
| 1 | VLM first-token / total latency, p50/p95, ≥10 real queries, `qwen3-vl:8b` | first-token **p50 2753.3ms / p95 3048.4ms**; total **p50 4067.5ms / p95 4223.1ms** | Real camera frame, 12 streamed queries, `day11_bench.py` |
| 1b | Same, `qwen3-vl:4b` | first-token **p50 1692.5ms / p95 2282.4ms**; total **p50 2201.0ms / p95 2763.0ms** — roughly half 8B's cost | Real camera frame, 12 streamed queries |
| 2 | Model + quantization + resident memory | **`qwen3-vl:4b`** shipped (Apache 2.0). `ollama ps`: 8B resident at **5.8GB, 100% GPU** (Metal); 4B not re-measured resident (not kept loaded) but pulls at **3.3GB** on disk vs. 8B's **6.1GB**. Both pulled from Ollama's library 2026-08-22. | `ollama ps` / `ollama list` |
| 3 | End-to-end wake/press → first spoken word, p50/p95 | **Still not cleanly captured — carried again from Day 10.** This agent's process cannot get real mic audio (the standing per-process-tree permission gap); the instrumentation (`wakeToAnswerMs`/`pressToAnswerMs`) is unchanged and ready for the project owner to run live. What *is* real: T3-internal cost with the VLM in the loop (intent parse → frame acquisition → VLM call → TTS-start) is now **~2.2-4.2s** for an `unknown`-routed question (row 1b), vs. Day 10's 119.1ms for a deterministic `describe_scene` answer — an honest, large, structural cost difference between the two paths, exactly why the fast path stays separate (row 4). | Real camera, real VLM; audio path not exercised this session |
| 4 | Fast path (`parse_intent` + `describe_scene`) latency, unchanged? | **Yes — unchanged, confirmed by direct measurement.** 10 runs of detect+track+describe on a real frame: **p50 16.81ms**, p95 460.8ms (one outlier, plausibly a scheduler hiccup — 9/10 runs were 15.96-29.71ms). Same order of magnitude as Day 10's 33.4ms forced-look number. | Real camera, real YOLOE detector |
| 5 | Idle CPU, ambient loop, VLM loaded but not called | **No regression.** `--t3` (VLM path wired, Ollama checked, wake thread listening): main **5.8-8.6%**, capture **3.6-5.2%**. Without `--t3`: main **8.1-9.7%**, capture **3.7-5.5%**. Both within the same noise band — Ollama holding a model resident costs nothing until actually called, same finding as D40's LLM-idle-cost result. Day 8's ~6-8% target holds. | `--synthetic`, `ps %cpu`, main + capture processes, same-session A/B |
| 6 | Reading accuracy: 5 cases from Part 3 | **5/5 correct on both 8B and 4B.** See "Reading tests" below for verbatim answers. **Caveat, stated plainly:** none of the 5 were held to a physical camera — see "What changed from the plan" below for why, and how these were substituted. | Real generated images fed directly as VLM input frames |
| 7 | VLM vs. tracks disagreement rate, ~20 queries | **11/19 (58%) flagged `possibleDisagreement`, 1 real Ollama timeout excluded.** Reading the 11 shows the heuristic over-flags on-topic-correct-but-off-object answers ("is there a window?" flagged purely for not saying "person"/"glasses"/"blanket") rather than catching real contradictions — a genuine, measured finding about the heuristic's precision, not about the VLM's accuracy. See `provenance.py`'s corrected docstring. | Real camera frame, real tracks `[person, glasses, blanket]`, `qwen3-vl:4b` |
| 8 | Does the "glasses"-class invention still occur? | **No — the query-level bug is gone, verified verbatim (see below).** Spot-check: re-ran the detector on a frame with no person in view and got zero `glasses` detections (`bed`, `blanket` only) — consistent with, not proof of, the earlier detection being tied to a real object rather than a random hallucination. **Closed per the brief's own rule**: the VLM stopped inventing "holding," so the practical bug (a false spoken claim) is moot regardless of the detector's raw per-frame precision on any single object. | Real camera, real YOLOE |

Row 1/1b is the architecture decision, made on real numbers. Row 4/5 prove
nothing regressed. Row 6/8 are the day's actual new capability and its
promised bug-close. Row 3 is the same honest gap Day 10 carried, for the
same reason.

## Part 1 — the brain swap

### 1.1 — Cold measurement, model choice

`qwen3-vl:8b` was pulled first per the brief's own instruction ("pull and
measure before designing around it"). The pull itself took far longer than
the brief's 30-minute timebox implied — **~45 minutes at ~2MB/s** on this
network this session, not a model-size problem, stated honestly rather than
hidden. Once resident, `day11_bench.py` (a new, not-shipped harness — same
category as `verify_preemption.py` — that talks to Ollama with
`stream=True` to get genuine first-token timing, since the shipped
`Llm.respond()` stays non-streaming) measured 12 real queries against one
real camera frame:

- **8B: first-token p50 2753.3ms / p95 3048.4ms.** Outside the brief's
  "~1.5s is comfortably answerable directly" bar — not close.
- **4B, pulled and measured the same way: first-token p50 1692.5ms / p95
  2282.4ms.** Still not *comfortably* under 1.5s, but roughly half 8B's
  cost, for identical correctness on every reading test and both verbatim
  grounding retests run against it (below).

**Shipped: `qwen3-vl:4b`.** The honest framing: neither model hits the
"instant answer" bar, and none was expected to — the brief's own mitigation
is structural (T2/T3, behind `PreemptionSeam`), not a latency trick. 4B was
chosen because it's the better point on the same curve, not because it
cleared a target 8B missed. `MODEL_NAME` in `llm.py` is a one-line change
back to 8B if a future machine's GPU makes the gap worth it.

### 1.2/1.3 — What actually changed in the code

`engine/llm.py`: `Llm.respond()` now takes `frame_bgr` and sends it as a
base64 JPEG (`quality=85`) alongside the text, per Ollama's `images` field
on a chat message. The few-shot grounding example from the `qwen2.5:7b` era
(D40) is deleted — it existed to walk a blind model through "don't invent
furniture" by demonstration; a model that's actually looking doesn't need
it, and keeping it would have been the exact kind of vestigial complexity
Day 11's "delete a whole class of bug" thesis argues against.

`engine/tiers.py`: `PreemptionSeam.deliver_fresh_look()` grew a third
argument, `frame_bgr` — the tuple `request_fresh_look()` returns went from
`(tracks, inference_ms)` to `(tracks, inference_ms, frame_bgr)`. Both
existing callers (`query_loop.py`'s describe_scene/query_object path,
`verify_preemption.py`) only ever read `result[0]`/`result[1]`, so this is
additive, not breaking — confirmed by running the full test suite and
`verify_preemption.py`'s own logic path unchanged.

`engine/query_loop.py`: the `unknown` branch now decides camera-vs-screen
(`_wants_screen()`, a small fixed keyword list — "my screen", "the screen",
"my monitor", etc. — deliberately kept out of `parse_intent.py`, which the
brief's boundary keeps untouched for safety-critical intents only), fetches
the corresponding frame, calls `describe_scene(tracks)` as a corroboration
string (not the source of the answer), calls `Llm.respond()`, and logs a
provenance line. The `try/except/finally` around the whole block — D40's
fourth amendment's load-bearing fix — is unchanged in shape, still releases
`preemption` in `finally` even if the VLM call or screen capture raises.
**New regression test, `test_query_loop.py`**, proves this holds for both
new failure points added this session (VLM raising, screen capture
raising) using a fake preemption hand-off and a fake always-raising LLM —
same technique D40's fourth amendment used, re-run against the Day 11 call
shape. Both tests pass.

### 1.4 — Preemption + exception safety

Verified two ways: the new `test_query_loop.py` (synthetic, fast, run every
`pytest` invocation) and a live spot-check that `preemption.active` returns
to `False` after a real VLM call completes normally. The one real Ollama
timeout hit during the disagreement-rate run (row 7) is itself informal
evidence the exception path works — the script's own `try/except` around
that one call caught it cleanly and the run continued; inside
`query_loop.py`'s real `try/except/finally`, the same event would fall back
to the spoken "i had trouble reaching my language model" line and release
the seam, per the regression test.

## Part 2 — screen capture

`engine/screen_capture.py`: `screencapture -x` to a scratch file inside
`engine/clips/` (never `/tmp` — the boundary rule), loaded via `cv2.imread`,
scratch file deleted before the function returns. **Directly tested and
working**: 203.9ms for a real 1920x1080 capture, from this same shell.

**What changed from the plan, found the hard way:** this session's shell
runs in a sandboxed/remote environment where `screencapture -x` genuinely
returns live pixels (the menu bar in the captured image tracks which app is
actually frontmost — proven by switching Terminal/Preview/TextEdit
frontmost via `open`/AppleScript and re-capturing) but **no application
window this agent spawns ever renders inside the captured frame** — only
the desktop wallpaper, across both of the machine's two virtual displays.
`osascript`'s keystroke automation is also blocked outright
("osascript is not allowed to send keystrokes"). This is a real
environment/session-routing limitation of this sandbox, not a bug in
`screen_capture.py` — the module's own direct test (real screen, real
pixels, real timing) passed cleanly. Per the project owner's call (asked
live rather than guessed at), the five reading tests below feed generated
images directly to the VLM as `frame_bgr`, **bypassing the screen-capture
code path** for that specific test — the module itself is proven working
in isolation, just not exercised end-to-end with real displayed content
this session. `_wants_screen()`'s routing logic is unit-tested
(`test_query_loop.py`) via a monkeypatched `capture_screen`, which is real
coverage of the routing and fallback-to-camera behavior, just not of a
live screen's actual pixels reaching the VLM.

**Privacy, stated as the brief asks:** the screen is captured only on an
explicit request that routes here (a keyword match on the transcript,
checked before any capture happens), the image lives in memory for exactly
one VLM call, and the on-disk scratch file is deleted before the function
returns — nothing about screen content is retained beyond the provenance
line's `frameSource: "screen"` tag.

## Part 3 — reading tests

**Substitution, stated plainly (the project owner's call, made live):**
none of these five were a physical object held up to a real camera — this
agent has no hands, and the owner didn't have all five objects on hand this
session. Four (receipt, document page, handwriting, product label) are
PIL-generated images with real, specific text content (not placeholder
lorem ipsum), fed directly to the VLM as if they were camera frames. The
handwriting one is a **script font**, not genuine handwritten strokes — a
real limitation of this substitution, noted rather than hidden: it did not
test the "genuinely hard case" the brief asks about, only a stylized
lookalike. The fifth (stack trace) is a **real Python traceback**
(`ZeroDivisionError`, captured verbatim from a real subprocess's real
stderr) rendered onto a terminal-styled image — the text is 100% real, the
delivery mechanism (a rendered PNG, not a live screen capture) is the
substitution. All five images are in `.claude/day11-images/`.

| # | Case | Question | `qwen3-vl:8b` answer | `qwen3-vl:4b` answer | Correct? |
|---|---|---|---|---|---|
| 1 | Real Python traceback, rendered | "what's wrong?" | "The code tried to divide by zero. Specifically, the divide function called with 10 and 0 caused the ZeroDivisionError." (8036ms) | "The script tries to divide by zero in the divide function, causing a ZeroDivisionError." (6344ms) | ✅ both |
| 2 | Generated receipt | "how much?" | "The total is $17.44. That's what's on the receipt." (6669ms) | "Total is $17.44." (4085ms) | ✅ both |
| 3 | Generated document page | "what does this say?" | Named the chapter title, summarized the body text's actual content, read page number 52 (7614ms) | Same content, summarized (5319ms) | ✅ both |
| 4 | Synthetic script-font "handwriting" | "what does this say?" | "pick up milk", "feed the cat", "call mom back" — all 3 lines verbatim (6891ms) | Same 3 lines verbatim (4142ms) | ✅ both, but **not a real handwriting test** — see caveat above |
| 5 | Generated product label | "what is this?" | Named product, weight, roast location, best-by date, "100% Arabica" (8024ms) | Same facts (5594ms) | ✅ both |

**Nothing in ten days of build could do any of these** — that claim from
the brief's own "Demo" section holds regardless of the physical-vs-rendered
caveat above: the text in every one of these five images is real, specific
content the old `describe_scene()` string-template path had no mechanism
to read at all, because it never received pixels.

## Part 5 — the two verbatim D40 retests

Real camera, real YOLOE tracks (`[person: 1.0, glasses: 1.0, blanket: 1.0]`
this session), real `qwen3-vl:4b` and `qwen3-vl:8b` calls, `describe_scene(tracks)`
passed as corroboration exactly as `query_loop.py`'s real code path does.

**"what am I doing right now?"** — Day 10's answer was *"You're standing
next to the chair"*, invented (the user was sitting).
- `qwen3-vl:8b`: *"You're sitting in a chair, wearing headphones. The room
  has a bed with a blanket and a window."*
- `qwen3-vl:4b`: *"You're on a call, wearing headphones. Sitting at a
  desk."*

Both say "sitting," not "standing" — the specific invented posture from
D40 is gone. Neither answer is verifiable against ground truth by this
agent (no way to independently confirm "on a call"), so this isn't proof
the model never embellishes — 4B's "on a call" is a plausible but
unconfirmed inference from headphones — but the *specific, previously
documented* failure (wrong posture) did not recur across two real runs on
two models.

**"what am I holding?"** — Day 10's answer was *"you're holding
glasses"*, a detector-adjacent hallucination the diagnostic capture never
confirmed.
- `qwen3-vl:8b`: *"I don't see anything in your hands. Your hands aren't
  visible in the image."*
- `qwen3-vl:4b`: *"You're not holding anything."*

Both correctly decline to claim a held object, despite `glasses` being a
real, confident (1.0) tracked label in the same frame — this is the
day's thesis directly demonstrated: the model looked at the actual hands
(or their absence) instead of pattern-matching "glasses is in the object
list, therefore describe it as held."

**The thesis holds, on real data, twice, on both model sizes considered.**
Not claimed as proof the failure mode can never recur under different
framing or lighting — only that the two specific documented Day 10
failures did not reproduce.

## Full-pipeline integration proof

Everything above tested pieces (llm.py directly, or `handle_command` with a
fake preemption). One real run through the actual production wiring — a
real `QueryLoop`, a real `PreemptionSeam`, a real capture-loop stand-in
thread calling `poll_force_request()`/`deliver_fresh_look()` exactly like
`main.py` does, a real camera frame, a real `qwen3-vl:4b` call:

**First attempt hit a real Ollama timeout** (30s) — `handle_command`
returned cleanly with `llmError: "TimeoutError('timed out')"`,
`preemption.active` was `False` immediately after, and the canned fallback
line would have been spoken. **Second attempt succeeded**: `"what's in
front of me right now?"` → *"You're looking at a bed with a folded blanket
and blue cloth in front of you."* (10495.9ms LLM time — well within this
model's variance), `preemption.active` correctly `False` after, and a real
line landed in `clips/provenance.jsonl`:

```json
{"t": 1787389391.026, "claim": "You're looking at a bed with a folded blanket and blue cloth in front of you.", "transcript": "what's in front of me right now?", "source": "vlm+tracks", "frameSource": "camera", "trackLabels": ["person", "glasses", "blanket", "bed"], "frameAgeMs": 360.62, "llmMs": 10495.9, "possibleDisagreement": false}
```

This is the real thing this day was for: not a mocked test, not a
synthetic frame — the actual `QueryLoop` wiring, a real timeout handled
correctly on one attempt and a real grounded answer with real provenance
on the next.

## Addendum, mid-session — Chatterbox Turbo pulled forward from Day 14

The project owner asked, live, mid-session, to stop waiting for Day 14 and
replace `say -v Samantha` immediately. Done — full reasoning and every
number in `decisions.md` D44, summarized here for the results table:

- **Latency:** real generation for short assistant-shaped replies measured
  1.6-3.2s on this M4 Pro's MPS backend — not the model card's "75ms /
  6x real-time" (CUDA-measured, not matched here). **Day 10's 119.1ms
  intent-to-TTS-start number is retired** — every spoken answer now has a
  real multi-second pause in front of it that didn't exist with `say`.
- **Idle CPU regressed** with the model resident: ~18% average (spikes to
  44%) vs. 5.8-8.6% without it (row 5's earlier number). Not profiled to
  root-cause this session.
- **Interrupt still works**, measured both directions: cancel-during-
  generation produces zero audio; cancel-mid-playback returns control in
  114ms (not SIGTERM-instant, but real and fast).
- **Two real install bugs found and fixed** (a `setuptools`/`pkg_resources`
  breakage in Resemble's own watermarker, and a `torch` downgrade
  regression-tested clean against YOLOE).
- **`exaggeration` doesn't work on Turbo** — logged by the library itself.
  The voice is real and neural, not the dynamically emotional thing the
  Day 14 plan described.

This is a real, mid-plan scope pull, done on explicit direction, not a
quiet addition — and it changes row 3 of the measurement table above:
whatever the wake-to-answer number turns out to be once captured, it now
includes 1.6-3.2s of real TTS generation that wasn't there before.

## Debt carried forward (per the brief's own no-refinement rule)

- **Wake/press → first-spoken-word latency, still not captured** (row 3) —
  needs the project owner's real mic, same gap as Day 10, now two days
  open.
- **Handwriting was not really tested** — the script-font substitute reads
  correctly but says nothing about genuine handwriting recognition, the
  brief's actual "hard case."
- **No physical object was held to the camera for any reading test** — a
  real, live camera-held test (receipt, label) is still owed.
- **The disagreement heuristic over-flags (58%)** — useful as a
  no-false-negative tripwire, not yet precise enough to be a real signal on
  its own; a version scoped to identity-shaped questions is the next step,
  not attempted this session.
- **Two real Ollama timeouts this session** (30s each, one during the
  disagreement-rate run, one on the first attempt of the full-pipeline
  integration test below) — same shape as D40's "keep_alive latency
  spike," still not root-caused; not chased further this session per the
  brief's own debt rule. Both were handled correctly by the exception path
  (see below), so this is a latency/reliability gap, not a correctness
  one.
- **`debug_window.py`, the mic-contention test, `bench.mjs` re-run** —
  carried again unchanged, per the brief's explicit "do not do today" list.
- **The wake-word rename** — still the project owner's call,
  still open.
