You're working in the WELLSY repo (`wellsy`) — a 7-day build-in-public live vision
overlay (camera → COCO-SSD detection → HUD overlay → spoken narration, all
browser-only). The `.claude/` directory is the project's build-in-public
workspace: context.md, research.md, architecture.md, plan.md, tasks.md,
decisions.md, demo-script.md, public-notes.md, progress-log.md, day1-poc.md,
week-roadmap.md, plus an `ep03-cue-sheet.md` that documents a "broken mode"
demo layer. Read whichever of these are relevant before editing them — don't
overwrite without reading first.

## Where things actually stand (git log, not the stale docs)

The `.claude/` docs (week-roadmap.md, tasks.md, plan.md) still describe the
*original* plan and are now out of date relative to the code:

```
369f431 Day 1: working live vision HUD POC
b0aaca0 Give the narrator a personality layer
2e1bf70 Fix silent voice output
1c41e53 Add demoMode: a directable failure layer for episode 3
33f0d93 Merge narrator-personality
b9c34ff Merge master into ep03-broken-mode
e7fb4c1 Merge ep03-broken-mode
```

So two things shipped after Day 1 that the roadmap doesn't reflect yet:

1. **A narrator "personality" rewrite** (`src/narration/`) that replaced the
   Day 1 narrator with an event-driven architecture:
   - `src/narration/events.ts` — `createEventTracker()` turns a settled scene
     into structured `NarrationEvent`s (`appear` / `disappear` / `count_change`
     / `still_present`), each carrying confidence, duration, previous_count.
     No opinions, just facts.
   - `src/narration/useNarrator.ts` — samples the frame every 250ms
     (`SAMPLE_MS`), requires the scene to hold for 900ms (`STABLE_MS`) before
     accepting it as settled, feeds settled scenes to the event tracker, queues
     events, and **rate-limits speech to one line per
     `config.min_seconds_between_lines`** (default **4 seconds** —
     `src/narration/config.ts:18`). When multiple events land in one window it
     picks the most interesting via `byInterest` (appear > disappear >
     count_change > still_present) and folds a second one in as an aside.
   - `src/narration/generateLine.ts`, `templates.ts` — turns the winning event
     into an in-character line (the "personality" on top of the facts).
   - This is, in other words, **already the events-not-frames + decoupled +
     rate-limited architecture** — narration was never actually chained to the
     60fps detect loop; it runs on its own `setInterval` sampler.

2. **A demo/failure-injection layer for "episode 3"** (`src/demo/`):
   `controller.ts`, `brokenLine.ts`, `brokenTemplates.ts`, `config.ts`,
   `useDemoMode.ts`, `DemoIndicator.tsx`, `demo.test.ts`. Only active behind
   `?demo=broken` in the URL — a normal session never touches it. It's wired
   into `src/App.tsx` (`useDemoMode`, `<DemoIndicator>`), `src/hud/HudCanvas.tsx`
   (`demo.tick(...)`), and `src/narration/useNarrator.ts` (`demo` param —
   `demo.takePending`, `demo.isSuppressed`, `demo.current()`, `demo.brokenLine`,
   `demo.bufferLog`). `.claude/ep03-cue-sheet.md` is the shot list for it
   (hotkeys 1/2/3/4/0/9 for mislabel/lag/ghost/denial/redemption/reset).

## What needs to happen, in order

### 1. Reschedule the roadmap — push everything out by one day

The plan owner decided the *current* Day 2 (tracking) needs to move to Day 3,
and every day after it shifts by one:

| was | becomes |
|---|---|
| Day 2 — tracking | Day 3 |
| Day 3 — narration tuning | Day 4 |
| Day 4 — HUD polish | Day 5 |
| Day 5 — performance | Day 6 |
| Day 6 — robustness | Day 7 |
| Day 7 — ship | Day 8 |

Update `.claude/week-roadmap.md`, `.claude/tasks.md`, and `.claude/plan.md` to
reflect the new numbering (renumber the day headings/sections, keep each
day's content as-is — only the day number changes for the pushed days).
Cross-check `.claude/public-notes.md`'s per-day hooks/lines too, since it also
enumerates Day 2–7 by number.

The new Day 2 gets its own content — see step 2.

### 2. New Day 2 = the narration-latency bug-and-fix story

The plan owner is recording a Day 2 episode around this script:

> "WELLSY had two jobs running at two speeds. Detection — the eyes — runs in the
> browser at 60 frames a second. Eleven milliseconds per frame. That part was
> never the problem."
>
> "The narration was chained to the frame loop. Every frame, it tried to say
> something. Sixty opinions a second, all late, all fighting each other. The
> mouth was drowning."
>
> **Fix 1 — events, not frames:** stop narrating frames, narrate events. A
> chair doesn't need commentary 60 times a second — twice: when it shows up,
> when it leaves. Collapse the frame stream into discrete events (appear /
> disappear / count change); the narrator only ever speaks to those.
>
> **Fix 2 — decouple + rate-limit:** the loops don't touch. Detection renders
> boxes in real time. Narration runs on its own clock — one line every four
> seconds max, and if several things happen at once it picks the most
> interesting and moves on.

Your job: **treat this as "apply the fix if it's there."** Based on the code
tour above, the event-tracker + rate-limit architecture in
`src/narration/events.ts` + `src/narration/useNarrator.ts` already *is* this
fix — confirm that by actually reading those two files plus
`src/narration/config.ts` end to end (don't take this prompt's summary as
ground truth, verify it), and check for anything that still couples narration
to the raw per-frame detect loop rather than the 250ms sampler / event
tracker / 4s rate limit. If you find a real gap (e.g. some code path that
still fires on every detection frame instead of on settled events), fix it.
If the architecture already matches the script faithfully, don't rewrite
working code to match a narrative — just verify and move on.

Then write this up as Day 2 in the `.claude/` workspace, in the same voice and
structure as the existing Day 1 material:
- `.claude/week-roadmap.md` — new Day 2 section: ships / concept / demo / hook,
  using the script's framing ("events, not frames" / "decouple + rate-limit").
- `.claude/public-notes.md` — Day 2 entry: concept, simple explanation, what
  viewers should notice, the bug story, posts. Follow the existing Day 1 entry's
  format exactly.
- `.claude/demo-script.md` and/or a new `.claude/day2-poc.md` — a recordable
  demo flow that shows the *before* (if you can still demonstrate it — e.g. a
  git-stash or a config toggle that removes the stability gate/rate limit
  temporarily to show frame-chained narration) and the *after* (the shipped
  behavior: one line, roughly every 4s, only on real events). If reconstructing
  a literal "before" isn't practical without regressing working code, script
  the demo around showing the telemetry (SAMPLE_MS, STABLE_MS,
  min_seconds_between_lines, event log with event `type` visible via the
  "boring mode" toggle in `StatusPanel`) as the evidence instead of staging a
  fake regression.
- `.claude/tasks.md` — mark the new Day 2 items appropriately (done, since the
  fix is already in the codebase, verified during this session).
- `.claude/progress-log.md` — append a Day 2 entry once the above is done,
  following the same five-part structure as the Day 1 entry (researched /
  decided / built / still missing / can be shown publicly).

### 3. Remove the demo/failure-injection layer — it's not needed anymore

Since Day 2's story no longer needs a staged "broken mode" episode, remove the
demo layer entirely:

- Delete `src/demo/` (all files: `controller.ts`, `brokenLine.ts`,
  `brokenTemplates.ts`, `config.ts`, `useDemoMode.ts`, `DemoIndicator.tsx`,
  `demo.test.ts`, `types.ts`).
- Remove its wiring:
  - `src/App.tsx` — drop the `useDemoMode` import/call, the `demo` variable,
    `<DemoIndicator>`, and the `demo` props passed to `HudCanvas`/`useNarrator`.
  - `src/hud/HudCanvas.tsx` — drop the `DemoController` import, the `demo`
    prop, and the `demo ? demo.tick(...) : ...` branch (just use
    `frameRef.current` directly).
  - `src/narration/useNarrator.ts` — drop the `demo: DemoController | null`
    param and every `demo?.` branch (`takePending`, `isSuppressed`,
    `demo?.current()`, `demo?.brokenLine`, `demo?.bufferLog`). Simplify back to
    reading `frameRef.current` directly and always using
    `generatorRef.current.generateLine(...)`. Also drop the now-dead
    `lagged`/`kind` fields on `LogEntry` if nothing else uses them — check
    `StatusPanel.tsx` first, since it may render them.
  - Delete `.claude/ep03-cue-sheet.md`.
  - Grep the whole repo for `demo` (case-insensitive, excluding `node_modules`)
    afterward to make sure nothing dangling references the removed module —
    check `src/hud/StatusPanel.tsx`, `src/hud/drawHud.ts`, and `src/App.css`
    for any demo-indicator styling/props too.
- After deleting, run `npx tsc -b` and `npm run build` to confirm nothing
  references the removed module, and `npx oxlint src/` to confirm lint is
  clean. Fix whatever the compiler surfaces rather than leaving stubs.

### 4. Verify and prepare for the Day 2 demo recording

Once the demo layer is gone and the narration architecture is confirmed:
- Run the app (`npm run dev`), start the camera, and actually watch the
  narration log and telemetry panel for a minute or two to confirm: narration
  fires only on real appear/disappear/count-change events, roughly one line
  per 4s+ under normal movement, and the "boring mode" toggle in
  `StatusPanel` shows the literal event line (proof it's driven by real
  detections, not scripted).
- Note actual observed numbers (inference ms, FPS, sample interval, rate
  limit) in `.claude/day2-poc.md` the same way `.claude/day1-poc.md` records
  Day 1's verified numbers — don't claim anything you didn't watch happen.
- Leave `.claude/tasks.md` with a clear "what to film" checklist for the Day 2
  recording, mirroring how Day 1's carried-forward tasks were tracked.

## Constraints, carried over from how this project has been run so far

- Keep changes modular, no speculative abstractions, no unrelated refactors.
- Don't add tests/error-handling for scenarios that can't happen.
- Default to no code comments; only add one where the *why* is genuinely
  non-obvious (the existing code already does this well — match its style).
- `.claude/public-notes.md` has firm rules: show failures as content, always
  cite real telemetry, never say "AI-powered," never overclaim (see its REAL
  vs NOT-REAL lists) — the Day 2 writeup must follow the same honesty bar.
- Report back in five parts when done, matching how Day 1 was reported:
  what was researched, what was decided, what was built, what is still
  missing, what can be shown publicly. Explicitly flag anything you could not
  verify (e.g. speech audio, since some environments have no TTS voices).
