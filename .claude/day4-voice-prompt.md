# Day 4 — "Giving it a real voice" (local LLM + local TTS)

You're working in the WELLSY repo (`wellsy`) — a build-in-public live vision
overlay: camera → COCO-SSD detection → HUD overlay → spoken narration, all
running in-browser, no backend, no API keys. The `.claude/` directory is the
project's build-in-public workspace. **Read the relevant files before editing
anything** — they are the current source of truth, not any summary of this
project you may have been given.

Read at minimum before starting: `.claude/decisions.md` (**D1 and D10 are
binding constraints on this day**), `.claude/week-roadmap.md` (Day 4 section),
`.claude/tasks.md` (Day 4 section), `.claude/architecture.md`,
`.claude/public-notes.md`, and the whole of `src/narration/` —
`generateLine.ts`, `templates.ts`, `speech.ts`, `useNarrator.ts`, `events.ts`,
`config.ts`, `narrator.test.ts`.

## The hard constraint — read this first

**No cloud APIs. Not for the LLM, not for the TTS, not as an optional mode,
not behind a user-supplied API key.** This is decisions.md D10 and it is a
product constraint, not a preference. If the local path proves hard, the
fallback is a *smaller local model* or *staying on templates* — never a
network call. Do not propose one, do not scaffold one "for later."

The project also targets mobile as a first-class platform (Day 7). Model
choice is governed by what is viable on a phone, not what is impressive on a
dev laptop. When choosing between two models, **the smaller one that still
clears the quality bar wins.**

## Where things stand

Shipped, and NOT this session's job to redo:
- **Day 1** — camera, COCO-SSD detection (~12ms/frame, WebGL), canvas HUD,
  spoken narration via Web Speech.
- **Day 2** — narration is event-driven and rate-limited. `events.ts` turns a
  settled scene into structured `NarrationEvent`s; `useNarrator.ts` samples
  every 250ms, requires 900ms of stability, and speaks at most once every
  `min_seconds_between_lines` (default 4s).
- **Day 3** — IoU tracker (`src/vision/tracker.ts`) gives objects persistent
  ids with smoothed boxes; narration reads track enter/exit directly.
  `count_change` is now unreachable-but-retained (decisions.md D12).

Note: the Day 4 task "event narration from Day 3 tracks" is **already done** —
it shipped on Day 3 as a side effect of the tracking switch. Don't rebuild it.

## What to build

### 1. A local LLM behind the existing `LineGenerator` seam

`src/narration/generateLine.ts` already exports the exact interface you need:

```ts
export interface LineGenerator {
  generateLine(event: NarrationEvent): string;
  foldLine(event: NarrationEvent): string;
  reset(): void;
}
```

`createLineGenerator()` is the template implementation. Add a second
implementation backed by a small on-device LLM. **Keep the template generator
fully working** — it is the fallback when the model hasn't loaded, isn't
supported, or fails, and it's also the A/B comparison for the demo.

**The async problem — this is the real work of the day.** The interface above
is synchronous, and template generation is sub-millisecond. An LLM is neither.
You must pick an approach and record it in `decisions.md`:
- **Widen the interface to async** and have `useNarrator.ts` await generation,
  accepting that the line arrives some ms after the event settles; or
- **Generate ahead** — start inference the moment an event settles and let the
  existing 900ms stability window plus the 4s rate limit absorb the latency, so
  the line is ready before its slot arrives; or
- something better you can justify.

Whichever you choose, the non-negotiable behaviours are: **the detect loop and
the draw loop must never block on the LLM**, and if a line isn't ready by the
time its slot comes up, the narrator falls back to a template rather than going
silent or speaking late into the next event.

**The model must speak in character.** `src/narration/templates.ts` is the
character bible — deadpan, terse, dry. Read it before writing any prompt. A
generic-assistant voice ("I can see a person in the frame!") is a regression
even if it's technically an LLM. Also enforce the existing
`line_max_words` ceiling (default 14, `config.ts`) on LLM output — truncate or
re-roll rather than letting a long line through — and honour `spice_level`
(0 clean / 1 default snark / 2 mild swears) in the prompt.

### 2. A local neural TTS behind the `speech.ts` seam

`src/narration/speech.ts` currently wraps Web Speech `speechSynthesis`. Its
public surface is `speak(text)`, `stopSpeaking()`, `primeSpeech()`,
`pickVoice()`. Add a local neural TTS implementation behind that same surface,
with `speechSynthesis` retained as the fallback.

Read the comment block at the top of `speech.ts` before touching it — it
documents three real browser quirks (async voice loading, the user-gesture
requirement, and Chrome discarding a `speak()` queued in the same tick as
`cancel()`) that were each found the hard way. **Any replacement still has to
satisfy the user-gesture requirement for audio playback**, and `stopSpeaking()`
must actually cut off in-flight synthesis, not just stop the next line.

### 3. Config + UI so the comparison is demoable

Add engine toggles to `NarratorConfig` (`src/narration/config.ts`) — something
like a line-generator engine (`template` | `local-llm`) and a voice engine
(`system` | `local-tts`), defaulting to whatever is safe on first load. Surface
them in `StatusPanel` alongside the existing controls. This is not polish: the
Day 4 demo is *the same scene narrated three ways, switched live on camera*,
and it can't be filmed without these toggles.

Also surface the honest numbers in the panel: model load state/progress,
per-line inference latency, and TTS synthesis latency. The claim of the day is
"local," and a number on screen is what makes it a claim rather than a boast.

### 4. Loading must not regress the startup story

The bundle is already ~1.3MB (TF.js) and flagged as a known issue. Models must
be **dynamically imported / lazily fetched**, never bundled into the main
chunk, and the camera + detection + template narration must all work fully
before either model has finished loading. Confirm `npm run build` doesn't show
a main-chunk regression.

### 5. Then, if time remains (cut in this order — cut the last one first)

- Narration timing tuned against real footage — `STABLE_MS`, `SAMPLE_MS`, and
  `min_seconds_between_lines` are still Day 1 guesses
- Spatial language from bbox position ("on your left", "in the centre")
- Salience ranking — the big/close/new thing, not the 6th chair

**The LLM and the TTS are the day.** Everything in this section is trim. If
the two model swaps are eating the timebox, ship them and skip all three —
that's the agreed scope decision (`tasks.md`, Day 4).

## The claim you must be precise about

"Runs entirely on the device" is the headline, and there is one honest
nuance that must not be glossed: **the models are downloaded once over the
network, then cached.** That is a network request, on first load. What's true
is that *inference* is local, *video never leaves the device*, and after the
first load it works with no network at all.

State it that way everywhere — in the code comments, the docs, and especially
in `public-notes.md`. Then verify it: load once, go offline (devtools offline
mode or actually disconnect), reload, and confirm narration and speech still
work end to end. **That test is the demo.** If caching doesn't survive a
reload, that's a bug to fix, not a caveat to write around.

## Verification — do this for real, don't assume

Every prior day was verified against a running instance, not just
type-checked. Do the same:
- Run `npm run dev`, start the camera, and actually **listen to it**. Note:
  speech audio has never once been confirmed out loud in this project across
  Days 1–3 (see `day2-poc.md`) — you may be the first to hear it. If you're in
  a headless environment and genuinely cannot, say so explicitly and loudly in
  the report and in `day4-poc.md`; do not let a day about *how it sounds* be
  reported as verified on the basis of a passing type-check.
- Measure and record real numbers: model download size, cold load time, warm
  (cached) load time, per-line LLM inference latency, TTS synthesis latency,
  peak memory. Compare each against the template/`speechSynthesis` baseline.
- Test the offline reload described above.
- Test on a phone if one is reachable. If not, say so — mobile viability is
  the stated basis for the model choice, so an unverified guess must be
  labelled as one.
- Run `npx tsc -b`, `npm run build`, `npx oxlint src/`, `npm run test` — all
  clean. Keep the existing tests passing: `narrator.test.ts` and
  `tracker.test.ts` must not be weakened to accommodate async. Test the new
  generator/TTS adapters with a fake model, not the real one — unit tests must
  stay fast and deterministic.

## Update the `.claude/` workspace

- `.claude/tasks.md` — check off completed Day 4 items; leave a "What to film
  for Day 4" checklist in the same shape as Day 2's and Day 3's.
- `.claude/week-roadmap.md` — mark Day 4 shipped following the ✅ SHIPPED
  pattern, replacing planning language with real numbers and observations.
- `.claude/progress-log.md` — append a Day 4 entry in the same five-part
  structure as Days 1–3.
- `.claude/decisions.md` — this day will produce real decisions: which LLM and
  which TTS and *why those over the alternatives you rejected*, and how the
  sync/async problem was resolved. Follow the existing D1–D12 format
  (decided / why / cost / revisit-if). Record what you measured, not what the
  model card claims.
- Create `.claude/day4-poc.md` — verification notes and observed numbers, same
  shape as `day1-poc.md` / `day2-poc.md` / `day3-poc.md`, including an explicit
  list of what could *not* be verified.

## Also produce: the social-media explainer

The project owner presents this publicly and needs a document to read from and
show on screen — a content asset, not engineering notes. Add a **Day 4 entry to
`.claude/public-notes.md`** following the exact structure Days 1–3 already use:

- **Concept** (one line)
- **Simple explanation** (2–4 lines, plain language — the existing entries are
  the bar)
- **What viewers should notice** (on-screen, self-evidencing things — the empty
  network tab, the latency numbers, the three-way voice comparison — not claims)
- **What was hard** (the honest engineering story — most likely the sync→async
  narration problem, or the size/quality tradeoff in model selection)
- **Posts** (X post, LinkedIn angle, reel caption — match the existing tone:
  specific, numbers-forward, no "AI-powered")

Respect the "What is REAL / What is NOT real yet" discipline at the bottom of
that file. Day 4 must not imply the model understands the scene, has memory
across sessions, or answers questions — none of that is built.

Then add a **Day 4 section to `.claude/demo-script.md`**, matching the existing
per-day structure. The intended flow: network tab open from the first second,
the same scene narrated three ways switched live (Day 1 flat English → Day 2
templated personality → Day 4 local LLM + local TTS), latency numbers visible
throughout, closing on the offline-reload test.

## House rules (don't violate these)

- No speculative abstractions, no unrelated refactors, no error handling for
  scenarios that can't happen.
- Default to no code comments; add one only where the *why* is genuinely
  non-obvious — match the terse style already in `useDetector.ts`,
  `useNarrator.ts`, and `speech.ts`.
- Every public-facing claim must be something you actually watched or heard
  happen. If you didn't hear the voice, don't write that it sounds good.
- Prefer the smaller model. Twice.
- Report back in five parts: what was researched, what was decided, what was
  built, what is still missing, what can be shown publicly.
