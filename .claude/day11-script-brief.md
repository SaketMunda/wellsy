# Day 11 script-writer brief — "The brain swap"

Handoff document for a script-writing agent. Everything below is either
directly observed this session (real camera, real hardware, real Ollama
server) or explicitly marked as not yet verified. Full technical record:
`day11-results.md`, `decisions.md` D41–D46. Full original brief:
`day11-prompt.md`.

---

## The one-line pitch

**For ten days YAP guessed at what it saw from a list of object labels. Today it actually looked — a real vision-language model reads the frame itself, catches its own two biggest documented lies from Day 10, and reads real text (receipts, stack traces, product labels) nothing in this build could read before.**

## The 30-second version, if that's all there's room for

Up to Day 10, YAP's brain never saw a pixel — it got a word list
(`person, glasses, blanket`) and a language model guessed a sentence from
those words alone. That guessing produced two real, embarrassing lies:
"you're standing next to the chair" (the person was sitting) and "you're
holding glasses" (nothing was in their hands). Today the brain — Qwen3-VL,
a real vision-language model — sees the actual camera frame. Both specific
lies are gone, re-tested twice on real data. And because it can actually
see, it can now read: a receipt total, a Python stack trace, a product
label, a handwritten note — all things the old label-only pipeline had no
mechanism to do at all, because it never got an image.

---

## What's actually demoable right now, with real evidence

1. **The two Day 10 lies, re-tested, gone.** Same real camera, same real
   tracks (`person`, `glasses`, `blanket`, both 1.0 confidence). Asked
   "what am I doing right now?" — Day 10 said *"you're standing next to
   the chair"* (wrong, they were sitting). Today: *"you're sitting in a
   chair, wearing headphones"* (8B) / *"you're on a call, wearing
   headphones, sitting at a desk"* (4B). Asked "what am I holding?" — Day
   10 said *"you're holding glasses"* (nothing was in-hand). Today: *"I
   don't see anything in your hands"* (8B) / *"you're not holding
   anything"* (4B) — correctly declining even though `glasses` is sitting
   right there in the tracker's confident object list. This is the
   thesis, shown twice, on two model sizes.
2. **Reading test: a real receipt.** "How much?" → *"Total is $17.44."*
   Correct, read off a generated receipt image with real dollar amounts,
   not placeholder text. Good visual: put the receipt image next to the
   spoken answer on screen.
3. **Reading test: a real Python crash.** A genuine `ZeroDivisionError`
   traceback, captured verbatim from a real subprocess, rendered onto a
   terminal-styled image. "What's wrong?" → *"The script tries to divide
   by zero in the divide function, causing a ZeroDivisionError."* Strong
   "it can debug your screen" beat.
4. **Reading test: a product label.** Named the product, weight, roast
   origin, best-by date, "100% Arabica" — all correct, all read off a
   generated label image.
5. **The model choice, told honestly as a real tradeoff, not a spec-sheet
   brag.** The bigger model (`qwen3-vl:8b`) was pulled and measured
   first — 2.7-3.0 seconds just to start talking. Too slow. The smaller
   one (`qwen3-vl:4b`) came in at roughly half that (1.7-2.3s) with
   identical correctness on every test run today, so that's what shipped.
   Good "here's how you actually pick a model, with a stopwatch, not a
   leaderboard" beat.
6. **`say -v Samantha` is gone, on the owner's own live demand mid-build.**
   The robotic macOS voice from Day 9 is replaced with Chatterbox Turbo, a
   real neural TTS model — a sample is in `day11-images/chatterbox-sample.wav`,
   safe to play directly. Good before/after beat: play the old `say` voice
   from an earlier day's clip, then this.
7. **The engine now greets you.** Walk into frame, no wake phrase needed —
   it opens with a real JARVIS-style line ("Good morning, sir. What's on
   the agenda today?" or similar, time-of-day aware) and immediately
   listens for a follow-up. Verified live this session: real camera, real
   detection, real person, real greeting spoken, real audio out real
   speakers.
8. **Real numbers to put on screen or read aloud:**
   - VLM answer latency (start-of-question to spoken answer), shipped
     model: **p50 ~2.2s / p95 ~2.8s** — slower than Day 10's instant
     fast-path answers, and said that plainly on screen rather than hidden
   - The old fast path (`describe_scene`, no VLM involved) is
     **unchanged: ~17ms**, still used for anything the fixed command
     grammar already covers — the VLM is only for the questions that used
     to get a shrug
   - Idle cost of having the VLM loaded but not talking: **no
     regression**, same 6-9% CPU band as every prior day
   - **5 out of 5** reading tests correct, on **both** model sizes

## The narrative arc this session actually supports

1. Open by replaying the two Day 10 lies as the "before" — the receipts
   are right there in `day10-results.md`, quote them directly.
2. Reveal what changed: the brain now gets the actual picture, not a word
   list. One sentence of "why" is enough — a person describing a photo
   doesn't need the photo described to them in words first.
3. Re-run both broken questions live (or from this session's real
   transcript) and show both wrong answers gone.
4. Pivot to "and because it can see, it can read" — receipt, stack trace,
   label, in quick cuts, each with the real spoken answer overlaid.
5. Land the model-choice beat as a "how the sausage gets made" moment —
   pulled 8B, timed it, it was too slow, dropped to 4B, timed that too.
   Real stopwatch, not a spec sheet.
6. Close on the two owner-driven pivots that weren't originally planned
   for today — the voice swap and the proactive greeting — framed as "the
   plan is a guide, not a cage": both landed same-day because a real
   person using the thing said "this is annoying, fix it now."

## What NOT to claim yet (say this plainly if it comes up, don't dodge it)

- **None of the five reading tests used a real physical object held to the
  camera.** Four are generated images (real text, not lorem ipsum) fed
  straight to the model; the "handwriting" one is a script font, not
  actual handwritten strokes — a real gap, not yet closed. If the script
  wants a "held object" beat, it needs a fresh take with an actual receipt
  or label in someone's hand.
- **Screen reading ("read my screen") is code-complete and unit-tested but
  not proven end-to-end with a live screen this session** — this agent's
  sandbox can capture real pixels but no window it opens ever renders
  inside them, a routing quirk of the dev environment, not a bug in the
  feature. Worth a fresh live test on the owner's own machine before
  claiming "reads your screen" on camera.
- **Wake-to-first-spoken-word latency is still not captured**, same gap
  carried since Day 9/10 — this agent has no real microphone access in
  this environment. What's real: the VLM-only cost once a question is
  already heard (~2.2-2.8s). Don't present a single "press to answer"
  number as measured; it isn't yet.
- **The disagreement/self-check heuristic over-flags 58% of the time** —
  it's a real safety net, not yet a precise signal. Don't claim "it
  double-checks itself reliably"; claim "it never lets a wrong answer
  through silently," which is true and provable, and is the honest, more
  interesting claim anyway.
- **Chatterbox's idle CPU is worse than before** (~18% average vs ~6-9%
  baseline), not yet root-caused. If the voice-swap beat goes in, say
  "this cost something, and here's what" rather than only the upside.
- **A same-day bug, found live and fixed, is fair game as a beat but not
  as a finished demo:** running the engine live, the new voice sometimes
  played distorted, and one live question got "I had trouble reaching my
  language model" instead of a real answer. Root cause, found by reading
  the actual code rather than guessing: the camera's own detection model
  was still running full-speed on the same Mac GPU while the new voice was
  mid-generation, so three things fought over one graphics chip at once.
  Fixed by pausing detection while the voice is speaking — same trick the
  engine already used elsewhere for a different reason. **Not yet
  confirmed fixed on real hardware/real speakers** — this agent can't
  hear; that's the owner's call to make on the next live run. If this goes
  in the script, frame it as "shipped, diagnosed live, fixed same session,
  awaiting the owner's own ears to confirm" — not as a closed loop.

## Terms to simplify, if the audience is general

| Don't say | Say instead |
|---|---|
| Vision-language model (VLM) | "a brain that can actually see the picture, not just a list of words" |
| `qwen3-vl:4b` / `qwen3-vl:8b` | "the smaller model" / "the bigger model" |
| Grounding / hallucination | "making things up" / "actually checking before it speaks" |
| First-token latency | "how long before it starts talking" |
| Provenance logging | "a paper trail for every answer it gives" |
| `PreemptionSeam` / T2/T3 | "the part of the engine that takes over when you ask a real question" |
| MPS / GPU contention | "the Mac's chip trying to do three things at once" |
| Disagreement flag | "a self-check that flags anything it's not sure lines up" |

## Where the assets are

- `.claude/day11-images/chatterbox-sample.wav` — real generated audio,
  safe to play directly as the "new voice" beat.
- `.claude/day11-images/hud-engine-mode-live.png` / `hud-engine-mode.png`
  — real browser HUD screenshots from this session.
- `.claude/day11-images/receipt.png`, `stack_trace_screen.png`,
  `label.png`, `document.png`, `handwriting.png` — the five reading-test
  source images, real content as described above (handwriting is a script
  font, not real handwriting — see caveats).
- `.claude/day11-images/glasses-check-frame.jpg` — the real frame used for
  the "what am I holding" retest.
- `.claude/day11-results.md` — every number in this brief, with its exact
  measurement conditions, for fact-checking before a script goes final.
- `.claude/decisions.md` D41 (the brain swap), D42 (screen capture), D43
  (provenance), D44 (Chatterbox pull-forward), D45 (proactive greeting),
  D46 (the live contention bug, found and fixed same session).
