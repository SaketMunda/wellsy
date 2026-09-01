You're working in the WELLSY repo (`wellsy`) — a build-in-public live vision
overlay: camera → COCO-SSD detection → HUD overlay → spoken narration, all
running in-browser, no backend, no API keys. The `.claude/` directory is the
project's build-in-public workspace (context, research, architecture, plan,
tasks, decisions, demo-script, public-notes, progress-log, day-N-poc,
week-roadmap). **Read the relevant ones before editing anything** — several
were rewritten in the last session and are the current source of truth, not
what any earlier summary of this project says.

Read at minimum before starting: `.claude/architecture.md`,
`.claude/decisions.md`, `.claude/week-roadmap.md` (Day 3 section),
`.claude/tasks.md` (Day 3 section), `.claude/public-notes.md`, and
`src/vision/types.ts`, `src/vision/useDetector.ts`, `src/hud/drawHud.ts`,
`src/hud/HudCanvas.tsx`, `src/narration/events.ts`, `src/narration/useNarrator.ts`.

## Where things stand

Two things have already shipped and are NOT this session's job:
- **Day 1** — the full loop: camera, COCO-SSD detection at ~12ms/frame on
  WebGL, canvas HUD overlay, spoken narration via the Web Speech API.
- **Day 2** — narration is already event-driven and rate-limited:
  `src/narration/events.ts` turns a settled scene into structured events
  (`appear`/`disappear`/`count_change`/`still_present`), and
  `src/narration/useNarrator.ts` samples every 250ms, requires a scene to
  hold for 900ms before acting on it, and speaks at most once every
  `min_seconds_between_lines` (default 4s, `src/narration/config.ts`). A
  `src/demo/` failure-injection layer that existed briefly for an episode 3
  concept was removed — don't reintroduce anything like it.

This session's job is **Day 3 — tracking** (`.claude/week-roadmap.md` and
`.claude/tasks.md`, Day 3 sections), which is unbuilt. Read those two
sections now for the full spec; the summary below is not a substitute.

## What to build — Day 3, IoU tracking

Detection currently answers "what's here *now*" — every frame is independent,
so boxes jitter and nothing has a persistent identity. Tracking answers "is
this the *same* thing as before." Build:

1. **`src/vision/tracker.ts`** — a pure IoU-based matcher:
   `(previousTracks: Track[], newDetections: Detection[]) => Track[]`. Keep it
   free of React/side effects, same discipline as `drawHud.ts` and
   `describeScene.ts` (see decisions.md D7 for why that pattern was chosen).
2. **A `Track` type** — extends the existing `Detection` (`label`, `score`,
   `bbox`) with `id: number`, `ageMs: number`, `missedFrames: number`. Decide
   whether this lives in `src/vision/types.ts` alongside `Detection`/`Frame`
   or in `tracker.ts` itself — follow whichever the existing type
   organization suggests.
3. **Exponential position smoothing**, α ≈ 0.4, applied to box position/size
   so boxes stop jittering frame to frame — this is the visible payoff.
4. **Track persistence** — keep a track alive for ~5 missed frames before
   dropping it, so a brief occlusion or a dropped detection doesn't reset the
   identity.
5. **HUD update** — `src/hud/drawHud.ts` / `HudCanvas.tsx` should render
   track id + age next to the label, e.g. `PERSON #3 · 4.2s`, replacing the
   current bare `label score%` display. Check `drawLabel` in `drawHud.ts`.
6. **Narrator update** — `src/narration/events.ts` currently derives
   `appear`/`disappear`/`count_change` from label-count diffing
   (`toSceneState`/set-difference in `describeScene.ts`). Switch it to read
   track enter/exit directly from the tracker's output instead — this should
   be strictly more accurate (two people is not "count_change: person 1→2",
   it's "person #4 appeared") and may simplify `useNarrator.ts`. Confirm the
   4s rate limit and event-priority logic (`byInterest`) still make sense
   once events are per-track rather than per-label-count.

**Timebox, per the plan:** IoU matching only. No Kalman filter, no
re-identification (a track that fully leaves and a new object of the same
class entering later gets a new id — that's fine, don't solve for it).
Tracker tuning is explicitly flagged as the day's biggest risk of running
over — if smoothing/matching parameters are eating time, ship a simple
version and note the rough edges rather than polishing.

## Verification — do this for real, don't assume

Day 1 and Day 2 were both verified against a real running instance (headless
Chrome + fake camera device for Day 1/2, or a real webcam where noted) rather
than just type-checked. Do the same here:
- Run `npm run dev`, start the camera, and actually watch boxes track objects
  as they move — confirm ids persist when an object briefly leaves frame and
  re-enters within the ~5-missed-frame window, and confirm a *new* object
  gets a new id.
- Capture or at least describe precisely a jitter before/after comparison —
  Day 1 boxes vs Day 3 boxes on the same movement, since this is the day's
  headline demo per `week-roadmap.md`.
- Run `npx tsc -b`, `npm run build`, `npx oxlint src/`, `npm run test` and
  confirm all clean.
- Note honestly anything you could NOT verify (e.g. real-webcam testing if
  you're in a headless-only environment) — Day 1 and Day 2's `*-poc.md` files
  are the model for this: they explicitly list what wasn't checked rather
  than implying full coverage.

## Update the `.claude/` workspace

- `.claude/tasks.md` — check off completed Day 3 items; leave a "what to
  film" checklist the way Day 2's did.
- `.claude/week-roadmap.md` — mark Day 3 shipped, following the ✅ SHIPPED
  pattern already used for Days 1–2, with any real numbers/observations
  replacing planning language.
- `.claude/progress-log.md` — append a Day 3 entry in the same five-part
  structure as Day 1/Day 2 (researched / decided / built / still missing /
  can be shown publicly).
- `.claude/decisions.md` — add a decision entry if the IoU matching approach,
  smoothing constant, or missed-frame threshold involved a real tradeoff
  worth recording (follow the existing D1–D10 format: what, why, cost,
  revisit-if).
- Create **`.claude/day3-poc.md`** — verification notes and observed numbers,
  same shape as `day1-poc.md` / `day2-poc.md`.

## Also produce: a social-media explainer document

The plan owner presents this project publicly and needs a document they can
read from and show on screen while explaining Day 3 to viewers — not
internal engineering notes, a **content asset**. Add a Day 3 entry to
`.claude/public-notes.md` following the exact structure the Day 1 and Day 2
entries already use:
- **Concept** (one line)
- **Simple explanation** (2–4 lines, plain language — the existing entries
  are the bar: e.g. Day 1's "a neural network looks at each video frame and,
  in one pass, guesses both what objects are in it and where they are")
- **What viewers should notice** (bullet list of on-screen, self-evidencing
  things — numbers and visible behavior, not claims)
- **What was hard** (the honest engineering story — for Day 3 this is
  probably the IoU-matching/smoothing tuning tradeoff)
- **Posts** (X post, LinkedIn angle, reel caption — match the tone of the
  existing Day 1/Day 2 posts: specific, numbers-forward, no "AI-powered")

Keep it inside the existing "What is REAL / What is NOT real yet" discipline
at the bottom of `public-notes.md` — e.g. don't let Day 3 imply
re-identification or multi-camera tracking, since neither is built.

Also check whether `.claude/demo-script.md` needs a Day 3 section (Day 1 and
Day 2 both have one — a timed on-camera flow, terms to simplify, what makes
it exciting even unfinished). Add one if the file's existing structure
expects it.

## House rules for this project (don't violate these)

- No speculative abstractions, no unrelated refactors, no error handling for
  scenarios that can't happen.
- Default to no code comments; add one only where the *why* is genuinely
  non-obvious — match the terse, explain-the-why style already in
  `useDetector.ts`/`useNarrator.ts`.
- Every public-facing claim must be something you actually watched happen.
  Never imply capability that isn't built (see public-notes.md's REAL /
  NOT-real lists).
- Report back when done in five parts: what was researched, what was
  decided, what was built, what is still missing, what can be shown
  publicly — same as every prior day.
