# WELLSY: instructions for every Claude session

- The plan is `.claude/PLAN.md`, the state is `.claude/STATUS.md`, and the master-session rules are `.claude/MASTER.md`. Read them before building.
- Git: every change goes on a branch and a PR; the owner merges. Never commit or push to master.

## Content gate — when to stop and tell me something is worth filming

This replaces any earlier "🎥 Record?" cue. It applies to every session, including the master session.

Default: keep building. Do not stop development to propose videos. Do not number episodes or use "Phase X" in any content suggestion.

After each completed milestone (a feature works end to end, a bug fix changes visible behaviour, or a measurable improvement lands), score it privately against this rubric:

REQUIRED (both must pass, or it is not worth filming):
1. VISIBLE MOMENT — A non-engineer can see or hear something surprising happen within the first 2 seconds of screen time, with no explanation. Examples: Wellsy speaks first, refuses to act, does two things at once, finds something I didn't know, cancels one task while another finishes. Refactors, internal architecture, test passes, config changes and "it's faster" without a before/after are NOT visible moments.
2. STEALABLE PAYOFF — There is one rule, number, pattern or stack choice a viewer can apply to their OWN AI project without using Wellsy. If the only lesson is "Wellsy can now do X", it fails.

BONUS (need at least 2):
3. STAKES — touches money, privacy, embarrassment, wasted time or trust (e.g. sending messages, spending money, deleting things, cost per task).
4. REAL NUMBERS — measured cost, latency or time, from actual runs. Never estimate or invent numbers.
5. BEFORE/AFTER — I can show the old behaviour failing and the new behaviour working in under 10 seconds total.
6. CALLBACK — it fixes or pays off a failure I already posted about (check CONTENT_LOG.md).

If it passes: stop at the end of the current task and output a block titled "🎬 FILM THIS" containing:
- The moment: one sentence describing exactly what happens on screen.
- What to record: the exact request to give Wellsy, and what must be visible (cards, timers, sent mail).
- Viewer payoff: one sentence a stranger could save and reuse.
- 5 hook options, each 7 words max, about the viewer's problem or the surprising moment — not about Wellsy's architecture, not my background.
- Measured numbers available (with how they were measured).
- Cut list: details that are true but don't belong in a 60-second video.
Then wait for me before continuing.

If it fails: do not stop. Append one line to CONTENT_LOG.md: date, what shipped, which criteria it failed, and whether combining it with future work could make it pass. When 2–3 logged items together would pass the gate, flag them with "🎬 FILM THIS (combined)" in the same format.

You may suggest (not build) a small addition, under ~1 hour, that would turn a near-miss into a visible moment. Never change the roadmap or build features only to make content.
