# Releases — the content mechanism

**Supersedes the per-day cadence in `public-notes.md` (that file was built for a
7-day series where every day was a release) and retires the per-step "findings
episode" habit.**

Cadence: **1 long-form + 1 short, weekly.** Engineering cadence and posting
cadence are now **decoupled.** Steps do not generate episodes.

---

## The rule: capture always, post on the gate

Work lands silently. Footage is banked continuously. **Nothing goes out until a
release gate opens** — this is how Anthropic and OpenAI operate: they ship
constantly and announce rarely, and the announcement is a capability, never a
version bump.

A step session's content job is **one paragraph deposited in the ledger below.**
Not a script, not a brief, not an episode. It records what became *possible*,
and where the raw capture lives.

## The gate — what earns a release

A release requires **all four**:

1. **Showable in under 30 seconds with no explanation.** If it needs a diagram
   or a preamble to land, it is not a release.
2. **The sentence starts with "WELLSY can now…"** — a new capability, in the
   user's words. Not "we migrated", "we fixed", "we measured", "we chose".
3. **Someone who doesn't write code would care.**
4. **It is irreversible-ish.** It works, live, repeatably — not behind a flag,
   not on one lucky take.

### Never a release, under any framing

Step completions · merges and PRs · test counts · model version bumps ·
refactors · bug fixes · latency tables · dependency upgrades · "we chose X over
Y" · internal architecture · anything whose honest title contains a step number.

The failure case to remember: the Day 12 brief got written around a
`screencapture` permission bug and the owner's verdict was *"that's not mind
blowing… this isn't worthy enough to share."* That bug was real, hard, and
correctly diagnosed. It was still not a release.

---

## Releases — planned

Mapped onto the engineering plan (`.claude/rebuild/README.md`). Numbers are
steps; releases roll several steps up into one announcement.

### R1 — "It does what you ask" ← next
**Steps:** 9 (convergence). **Supporting beats already shipped:** 6c, 5c.
**Gate:** speak a request that needs a real tool — calendar, mail — and it does
it. Approval happens out loud. The orb shows it thinking and acting.
**Why it's a release:** today `wellsy voice` has no tools and `wellsy agent` has
no ears. This is the first time WELLSY is a thing you talk to that *does*
something. Everything before it was a voice demo and an agent demo in one repo.
**Demo beats available:** the tool firing by voice · spoken approval and a
spoken refusal · the read-back catching a wrong date before it commits · the orb
tracking real graph state · (from 5c) naming something the old build couldn't.

### R2 — "It remembers"
**Steps:** 7. **Gate:** cold start, then *"what was I working on yesterday, and
what's the first thing I should do about it?"* — answered correctly from memory.
**Why:** this is Phase 1's actual success criterion, and it is the single most
legible capability jump available. Memory is the thing people find uncanny.

### R3 — "It sounds alive"
**Steps:** 10. **Gate:** side-by-side, old voice and new, no commentary needed.
**Why:** the most immediately felt change of any step, and a standing ask since
Day 4. Audio quality needs no explanation — it either lands in two seconds or it
doesn't.

### Step 8 is not a release
The System-One decision layer is an optimisation of something already working.
Its visible payoff — *"I added a new capability and it worked by voice with no
new code"* — is a strong **beat inside R1 or R2**, and its ideas are excellent
**evergreen** material. It does not get its own announcement.

---

## Track B — the evergreen backlog (what fills the weeks between releases)

This is the mechanism that makes weekly cadence survivable without posting
changelogs. These are **durable explainers**, not updates. They do not expire,
they do not need a release, and they can be shot in any order.

Each one is already paid for by work that happened. Seeded:

| Idea | The hook | From |
|---|---|---|
| No flag can turn off reasoning | Seven attempts. `think:"low"` produced a **byte-identical** 4755.9 thinking tokens to no bound at all. The API accepts the parameter and ignores it. | 5b |
| The test that fails if the UI lies | A test that scans source and fails if any timer or RNG feeds the orb's pulse. Mic closed ⇒ no listening animation, provably. | 6 |
| A model that doesn't generate text | System-One models: typed decisions with probabilities instead of tokens. Why the category appeared, and why two vendors shipped it in three weeks. | D55 |
| It exits 0 and hands you a wallpaper | `screencapture` without permission returns a valid full-resolution PNG of your desktop background. Every guard checked the things that still passed. | 3 |
| The harness had no speaker in the room | Green tests, broken product. It transcribed its own voice and interrupted itself in a loop. | 4c |
| Three looks only count if they're independent | An egg rotates on the belt, so three checks are three views. Three frames of a static scene are one view sampled thrice. | egg teardown |
| Why open-vocabulary beats a newer YOLO | A version number and a capability branch are different axes. | detector |
| The framework that renders nothing | QtQuick3D point rendering on Metal: every point collapses to one pixel. No error, no warning. | 6 |

**Rule for Track B:** one idea, one piece. If it needs two ideas to be
interesting, it isn't ready.

---

## The weekly slots

- **Long-form** = a release when a gate is open; otherwise **one Track B
  explainer.** Default is Track B — releases are the exception, not the beat.
- **Short** = one moment. A single demo beat from the release in progress, or
  one idea from Track B compressed to its hook. Never a summary of the week.

Scripts come from the `series-scripting` and `content-scripting` skills. This
file decides **whether and what**, never how it's written.

---

## Ledger — deposits from completed steps

Step sessions append here. **One paragraph. What became possible, and where the
raw capture lives.** No scripts.

| Step | Date | What became possible | Release | Raw capture |
|---|---|---|---|---|
| 6c | 2026-10-14 | First live run by a human — voice in, answer out loud, orb tracking real state. Demo recorded. | R1 beat | (owner's drive) |
| 5c | 2026-10-14 | YOLOE-26 adopted; Qwen3.5 collapse handed to step 9 with `reasoning_effort`. Detector names things the old build couldn't. | R1 beat | perception baseline |
| 5c follow-up | 2026-10-17 | Put on glasses or pick up a phone in a normal run, sitting still, and WELLSY's detector reports it within ~1-2 s. Before, a still room never woke the detector: the glasses showed up 10 s late and the phone never. This makes the 5c beat above true live. | R1 beat | `runs/step5c/clip.mp4` (+ `heartbeat-0/1.0.jsonl` replays); a live take is still to shoot |
