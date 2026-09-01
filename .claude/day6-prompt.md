# Day 6 — "It stops guessing, and it answers back"

You are picking up WELLSY on Day 6. Days 1–5 have shipped. Read `.claude/context.md`,
`.claude/decisions.md` (D1–D19), `.claude/tasks.md`, and `.claude/architecture.md`
before you touch code. This document is the brief for today only.

---

## The goal, stated precisely

Two complaints from real use, and they are the same complaint:

1. **WELLSY says the wrong thing about what it sees.** A bed is reported as a
   `dining table`. A microphone is reported as a `tie`, or a `bottle`.
2. **WELLSY can only talk *at* you.** There is no way to ask it anything. No
   "what are you looking at", no "stop", no "wake up".

Both are the system asserting rather than communicating. Today it learns to
say *"I'm not sure"*, to be told *"you're wrong"*, and to be **asked a
question**.

The headline for the day: **an AI that admits uncertainty reads as more
intelligent, not less.** That's the thesis, and it's also true.

---

## Boundaries

- **No cloud. This is the day it gets hardest to hold.** The browser ships a
  free speech recogniser — `SpeechRecognition` / `webkitSpeechRecognition`. In
  Chrome it **streams your microphone audio to Google's servers**. It is
  therefore banned by D10, no exceptions, not behind a toggle, not "just for
  the demo". Speech-to-text runs locally or it does not ship. Record this as a
  new decision (see below) — it's one of the better beats in the series.
- **Audio never leaves the device, and is never persisted.** No recording to
  disk, no upload, no localStorage of transcripts beyond the in-memory log.
  Say so in the UI near the mic control.
- **Don't touch `src/hud/drawHud.ts`'s visual language or `hudState.ts`'s
  animation timings** beyond what new data (uncertainty, unknown labels)
  genuinely requires. Day 5 is done; this is not a redesign day.
- **`@huggingface/transformers` is already on disk** at v3.8.1, pulled in
  transitively by `kokoro-js`. Promote it to a **direct dependency** in
  `package.json` (a transitive dep you import from is a footgun), but note in
  the write-up that it costs no new library download — only model weights.

### What moves off Day 6

The old Day 6 was a pure performance day (WebGPU backend, adaptive frame
skipping, resolution decoupling). **WebGPU is already #1 on the roadmap's
own cut-if-behind list** — "WebGL is already fast enough" — so it moves out.
Keep only the **latency breakdown panel**, which is now load-bearing: you are
adding two more models today and need to prove they didn't eat the frame
budget. Update `week-roadmap.md` to reflect the reshuffle and say where
adaptive frame skipping now lives (Day 7, with mobile — that's where battery
actually matters).

---

## Where things stand

- Detection: COCO-SSD `lite_mobilenet_v2`, WebGL, `MIN_SCORE = 0.5`,
  `MAX_DETECTIONS = 12`, in a rAF loop (`src/vision/useDetector.ts`).
- Tracking: IoU-or-centre matching with **same-label-required** pairing,
  α = 0.4 smoothing, 20 missed frames of grace (`src/vision/tracker.ts`).
- Events: `appear` / `disappear` / `still_present`, raised from track identity
  (`src/narration/events.ts`). This is the truthful layer; the voice may only
  restyle it, never invent.
- Narration: 250ms sampler, 900ms stability gate, ≥4s between lines, LLM lines
  generated **ahead** of their slot (`useNarrator.ts`, `llmLineGenerator.ts`).
- Voice out: `speechSynthesis` by default, Kokoro local TTS behind a toggle.
  **The Kokoro production-build bug (D13) is still open and is still not
  today's job** — but see the build-verification requirement below, because
  you are about to load two more transformers.js models and that bug is a
  warning about exactly this.
- HUD draw cost is 0.05–0.07 ms across 1–12 targets (D19). Don't regress it.

---

## Problem 1 — the wrong labels

There are **two different failures** here and conflating them will waste your
day. Split them in your head and in the write-up:

**(a) In-vocabulary confusion.** `bed` and `dining table` are *both* COCO
classes. The model has the right vocabulary and picks the wrong word — often
flipping between them frame to frame. This is fixable.

**(b) Out-of-vocabulary objects.** `microphone` is **not one of COCO's 80
classes**. Neither is `headphones`, `monitor`, `guitar`, `pen`, `mug` (only
`cup`), `speaker`. The model has no way to be right — it is forced to name the
nearest of 80 things it knows, and a mic on a stand genuinely does look like a
`tie` or a `bottle` to it. **No threshold, no smoothing, no prompt fixes
this.** It needs a different kind of model, or an honest `UNIDENTIFIED`.

Say both of these on camera. (b) especially — "the model isn't being stupid,
it's being asked a question it cannot answer" is the most interesting thing
in this day.

### Fix 1a — the 30-minute model experiment (do this first, timeboxed)

`useDetector.ts` loads `base: 'lite_mobilenet_v2'`, the smallest and least
accurate COCO-SSD variant, chosen for speed on Day 1 (D2). Try
`base: 'mobilenet_v2'`. Measure inference ms and FPS on the same scene, and
note anecdotally whether the bed/table confusion improves.

**Timebox this to 30 minutes.** Keep it only if accuracy improves and
inference stays inside budget; otherwise revert and record the measured
numbers as a negative result. A measured negative result is content.

### Fix 1b — per-track label voting (the real structural fix)

The tracker gives every object a **persistent identity across ~30 frames**.
The label is currently taken from whichever detection matched *this* frame.
That throws away 30 votes and keeps only the last one.

Worse: `tracker.ts` refuses to match a track to a detection with a different
label (`if (track.label !== detection.label) continue`). So when the model
flips `bed` → `dining table`, the old track goes unmatched and a **brand-new
track id is minted**. The label flicker is also an identity churn, which is
why the same motionless object can climb through ids.

Build:

- **Cross-label matching, gated on geometry.** Keep the current permissive
  same-label matching. *Additionally* allow a different-label pair to match
  when the geometric overlap is strong (IoU ≥ ~0.5 — tune it). A chair must
  still never inherit a person's id, and that constraint is what the high
  threshold buys you. Test both directions in `tracker.test.ts`.
- **A per-track vote histogram.** `Track` grows something like
  `labelVotes: Record<string, number>`, each frame adding the detection's
  `score` to its label's bucket, with a decay so an object that genuinely
  changes (or a re-used id) can be overtaken. `Track.label` becomes the
  argmax, not the latest.
- **A `labelConfidence` field** — the winning label's share of total votes.
  This is a *different* number from `score` (the model's per-frame
  confidence) and both are real. Don't conflate them.
- **A runner-up.** Keep the second-place label; the HUD and the narration can
  both use it.

Keep `updateTracks` pure — same signature shape, still a plain function of its
inputs, still unit-testable. That property is why Day 5 was cheap; protect it.

### Fix 1c — say "I don't know"

When `labelConfidence` is below a threshold, or the top two labels are within
a small margin of each other:

- **HUD:** render `UNIDENTIFIED` (or `BED / DINING TABLE ?`) instead of
  committing to one. Use the existing uncertain/warn treatment from
  `theme.ts` — don't invent new visual language.
- **Narration:** hedge. "something bed-shaped." / "unclear. rectangular.
  probably furniture." The template bank and the LLM system prompt both need
  an uncertainty case. The LLM must **never** be allowed to resolve the
  uncertainty — it restyles the hedge, it doesn't pick a winner.

### Fix 1d — open vocabulary (the actual microphone fix)

This is the answer to (b), and it's the most interesting engineering of the
day. COCO-SSD is a **bad classifier but a good "there is an object here"
detector** — the box around the mic is correct, only the word is wrong. So
keep the boxes and replace the word:

- Crop the track's box out of the video frame to an offscreen canvas.
- Run **zero-shot image classification** via `@huggingface/transformers`
  (`Xenova/clip-vit-base-patch32`, or SigLIP if it loads cleaner and isn't
  much bigger — **verify what actually loads, don't trust this document**)
  against a **candidate label list**.
- The list = the COCO 80 **plus a user-editable extra list** in the panel:
  `microphone, headphones, monitor, keyboard, water bottle, guitar, mug,
  speaker, whiteboard, plant pot`. The user typing a word into a box and
  watching the mic get correctly named **is the demo**. Persist the list to
  localStorage next to `NarratorConfig`.
- **Latency discipline, this is the part that can ruin the day:** this runs
  **once per track**, when the track has been stable for a beat — never per
  frame, never inside the rAF loop, never on the primary path. Cache by track
  id. Re-check only rarely (e.g. every few seconds, or on a big box-size
  change). One in-flight inference at a time, serialized, exactly like
  `llmLineGenerator.ts` does it. If it isn't done yet, the COCO label stands.
- **If the top candidate doesn't beat the runner-up by a margin, return
  `UNIDENTIFIED`.** Don't trade a confident wrong COCO label for a confident
  wrong CLIP label. The whole point of today is fewer confident lies.
- **Off by default**, behind an engine toggle in `StatusPanel` alongside the
  Day 4 line/voice engine toggles, with load progress and per-inference
  latency shown. Same pattern, same seam, no new architecture.

---

## Problem 2 — talking back

### The shape

```
mic → local ASR → transcript → parseIntent() → either a control action
                                             → or describeScene(tracks) → spoken answer
```

Every arrow in that chain is testable in isolation. Keep it that way.

### Speech in

- **Local Whisper via transformers.js** — `Xenova/whisper-tiny.en` or
  `onnx-community/whisper-base`; prefer the smallest one that transcribes
  short commands reliably, WebGPU where available with a wasm fallback (same
  availability check pattern as `llmLineGenerator.ts`'s WebGPU guard).
- **Push-to-talk ships first.** A key (`T`, added to the shortcut overlay) and
  a visible mic button. Hold to talk, release to transcribe. It is reliable,
  it costs nothing when idle, and it can't be triggered by the TV.
- **Wake word is the stretch, and must be described honestly.** The
  achievable version is: voice-activity detection segments an utterance →
  Whisper transcribes it → the text is matched against `"wellsy"` / `"hey wellsy"`.
  That is **not** a trained wake-word model; it's transcribe-then-match, so
  it costs real CPU continuously and will misfire. Say exactly that in the
  notes rather than implying a Siri-grade always-on keyword spotter.
- **Mic permission is a second `getUserMedia` prompt.** Handle denial the
  same way `useCamera` handles camera denial — a stated reason, not a crash.
  Everything else must keep working with the mic refused.
- **Self-hearing.** WELLSY's own TTS will be picked up by the mic if you're not
  careful, and it will happily answer itself. Gate listening while
  `speechSynthesis`/Kokoro is speaking — except push-to-talk, which must
  still work mid-sentence so `"stop"` can interrupt.

### Intent parsing — deterministic, not the LLM

Write a pure `parseIntent(transcript: string): Intent` and unit-test it. The
LLM **never** decides a control action. A 0.5B model that occasionally
hallucinates is fine for a joke and unacceptable for "stop".

At minimum:

| Intent | Said as | Does |
|---|---|---|
| `wake` | "wake up", "hey wellsy" | narration on |
| `sleep` | "go to sleep", "be quiet", "shut up" | narration off |
| `stop` | "stop" | `stopSpeaking()` immediately, clear the queue |
| `describe_scene` | "what do you see", "what's in front of you" | grounded answer |
| `query_object` | "do you see a laptop", "is there a person" | yes/no + count, from tracks |
| `help` | "what can you do" | lists the intents |
| `unknown` | anything else | says it only handles a few commands — **it does not improvise** |

`stop` must be honoured even while a wake-word/ASR pass is mid-flight.

### Answering — grounded, exactly like Day 2

Add a pure `describeScene(tracks: Track[]): string` in the narration layer.
It reads **only** `frameRef.current.tracks` and produces a literally true
sentence: "three things: a person, a laptop, and something unidentified."
Include the uncertainty from Problem 1 — this function is where "I'm not
sure" gets spoken out loud.

Then: **the LLM may restyle that sentence and nothing else.** Same split as
`events.ts` → personality. If the LLM is off, still loading, times out
(~1.5s), or returns something the sanitiser rejects, **speak the literal
sentence** — the answer is never dropped, and it is never invented.

Note the timing difference from narration: Day 4's generate-ahead exists
because narration must not block a 250ms sampler. A **question is a
request-response** — the user just spoke and expects a beat of silence. It is
fine to await here, with a timeout. Don't contort the answer path into the
prefetch model.

### Wiring into the existing narrator

An answer must **preempt** the narration queue and reset the rate-limit clock
(`lastSpokeAtRef`), or WELLSY will answer you and then immediately talk over its
own answer with a queued observation. Route both through one speak path.

### Showing it

The subtitle track from Day 5 already exists and is the only place most
viewers will see any of this — **no audio has been confirmed audible on any
machine across five days (D13)**. Show the **user's transcript** there too,
visually distinct from WELLSY's line (a `>` prefix, dimmer, right-aligned —
your call, but obviously different). A silent screen recording must read as a
conversation. Add ASR state + last transcription latency to the panel.

---

## Build in this order. Cut from the bottom.

1. Model A/B experiment, timeboxed to 30 minutes, measured
2. Per-track label voting + `labelConfidence` + runner-up (tracker + tests)
3. `UNIDENTIFIED` / hedged labels in the HUD and in narration
4. Push-to-talk local ASR → `parseIntent` → control actions (`stop`, `wake`,
   `sleep`) → spoken + subtitled acknowledgement
5. `describeScene` + `describe_scene` / `query_object`, LLM restyling optional
6. Open-vocabulary relabelling with the user-editable candidate list
7. Latency breakdown panel: capture → inference → track → draw → ASR → LLM → TTS
8. Wake word / always-listening mode

**Items 1–5 are the day.** If 6 doesn't land, the microphone is still
mislabelled and that's fine — you'll have shipped a system that says
"UNIDENTIFIED" instead of confidently saying "tie", which is the honest half
of the fix and demos nearly as well. If 8 doesn't land, push-to-talk is a
complete feature, not a broken one.

Do **not** start 6 or 8 until 1–5 are committed and working.

---

## The honesty rules for today

Day 5 was the day the project could start lying with pixels. Day 6 is the day
it can start lying with words. Three specific traps:

- **"It understands what you say."** It matches a transcript against a fixed
  list of patterns. Off-script phrasing fails. Say that.
- **"It has open-vocabulary vision."** It scores crops against **a list of
  words you typed in**. It cannot name a thing that isn't on the list. That's
  still a genuinely useful and interesting result — describe it accurately
  and it stays impressive.
- **"It has a wake word."** See above — transcribe-then-match, not keyword
  spotting.

Add all three to the NOT-real list in `public-notes.md`, and add the true
claims to the REAL list: audio never leaves the device, speech recognition is
local, the label is a vote across ~30 frames of the same tracked object,
`UNIDENTIFIED` is a real threshold and not a scripted moment.

---

## Performance budget

You are adding **two more models** to a page that already loads three. This
is exactly how a live demo dies.

- Measure **before** and **after**: FPS, inference ms, HUD draw ms. Day 5's
  baseline is 0.050 / 0.049 / 0.070 ms draw at 1 / 5 / 12 targets. **Do not
  regress the detect loop at all** — CLIP and Whisper must live entirely off
  the rAF path, with their own separately-reported latencies.
- Report cold-load and warm-load sizes for both new models the way D13 did
  for Qwen and Kokoro. Nothing is eagerly imported; everything stays behind a
  dynamic `import()` and an opt-in toggle. Main bundle chunk must not grow
  meaningfully — check it and state the number.
- Mobile is Day 7's problem, but every choice today should assume it. If a
  model only works on a desktop GPU, say so now rather than discovering it
  next session.

---

## Verification

- `npm run test` — new unit tests for label voting (including the cross-label
  match gate and the id-churn case it fixes), `parseIntent`, and
  `describeScene`. `npm run lint`, `npm run build` clean.
- **Verify the new models in a production build**, not just `npm run dev`.
  `npm run build && npm run preview`, then actually exercise ASR and CLIP.
  D13 is a standing warning that this dependency family breaks specifically
  under Rollup's bundling, and Day 8 deploys a production build. Finding this
  today is cheap; finding it on Day 8 is not.
- Live-verify in headless Chrome with the fake camera device as previous days
  did, and be explicit about what that **cannot** show: a fake camera has no
  microphone, so ASR needs either a real mic or a synthetic audio input
  (`--use-file-for-fake-audio-capture`). If you can't verify a real spoken
  command, **say so plainly** — that gap goes in the write-up alongside the
  standing "no audio has been heard" caveat.

---

## `.claude/` updates (part of the work, not paperwork)

- `tasks.md` — rewrite the Day 6 section to the real scope, tick what shipped,
  list what was cut and where it went. Move WebGPU/frame-skipping items out
  with a note.
- `week-roadmap.md` — rewrite Day 6, and state how Days 7–8 shifted.
- `progress-log.md` — the day's entry.
- `decisions.md` — continue the D1–D19 numbering, same format. Expect at
  least: no cloud ASR / why the free browser API is disqualified; per-track
  label voting and the cross-label match gate; open-vocabulary relabelling as
  an off-by-default second-stage classifier; deterministic intent parsing
  instead of LLM tool-calling; whatever the model A/B concluded, including if
  it concluded "no change".
- `day6-poc.md` — the verification writeup, in the shape of `day5-poc.md`,
  including everything that could **not** be checked.
- `public-notes.md` — fill in the Day 6 section, plus the REAL / NOT-real
  additions above.
- `demo-script.md` — a Day 6 section. The shot list writes itself: point it at
  the bed and watch it flip labels, turn on voting and watch it settle, point
  it at the mic and watch it say `tie`, type "microphone" into the candidate
  box and watch it correct itself, then hold `T` and ask it what it sees.

---

## House rules

- Small, reviewable commits. Comments explain **why**, never what.
- Pure functions where the logic is real logic — that's what made Days 3 and
  5 cheap to build on.
- New engines go behind the existing toggle seam with honest telemetry. Never
  make a new model the default on first load.
- If something doesn't work, ship the honest version and write down what
  broke. A wrong label you *admit* to is content; a wrong label you hide is a
  bug that surfaces on camera.

## Report back with

1. **What shipped**, against the numbered list above.
2. **What was cut**, and where it went.
3. **The numbers** — before/after FPS, inference, draw cost; ASR latency;
   CLIP latency; model download sizes; bundle size.
4. **What you could not verify**, explicitly.
5. **The one thing that was harder than expected** — that's the day's story,
   and it's usually not the thing this document predicted.
