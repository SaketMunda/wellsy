# Step 6c — Live verification: the run that has never happened

**Read first:** `.claude/rebuild/INVARIANTS.md` (**#6** is the whole point),
`step6-results.md` increments 5–7 (what `wellsy run` is supposed to do),
`step6b-consolidation.md` §Deliverable 4 (what it measured and what it could
not), `step4b-runbook.md` (the acoustic-run protocol — reuse it, don't reinvent
it), `spec/phase1-acceptance.md` §1.
**Depends on 6b. Blocks nothing — run it first anyway.**

## Why this step exists

**`wellsy run` has never been executed by a human being.**

Every latency number in this repo came from a file-injection or
component-compose harness. Step 4's numbers had no speaker in the room — which
is exactly how the echo regression shipped. Step 6b measured the orb's CPU and
composed 615 ms from stage timings, then said so plainly: the
device-timestamped end-to-end needs a mic and a speaker, and the session had
neither.

So the single most important fact about this system is unknown: **what it is
like to talk to.** Not whether the tests pass — they do, 190 of them — but
whether a person speaks to it and it behaves.

This step requires a human at the machine. It is the oldest owed acceptance in
the project.

## The one rule that makes this step work

**You are measuring, not fixing.**

When something misbehaves — and it will — **write it down and keep going.**
Do not open the file. Do not fix it. A session that stops to fix the first bug
produces one fix and zero footage; a session that logs ten findings produces the
next three steps' worth of work and an honest record of what the system is
actually like.

The only exception is a crash that prevents the rest of the protocol from
running at all. Then fix the minimum to proceed, and record that you did.

## Deliverable 1 — the live run, on the record

`wellsy run`. Orb up, speakers on (**not** headphones — the open-air path is the
design, per step 4c; headphones are a diagnostic only). Screen-record the whole
session, audio included.

Work this protocol in order and log the outcome of every line:

**Presence**
1. Does the orb appear? Where, and at what size? Is it legible over your actual
   wallpaper, not a test background?
2. Switch Spaces. Open a fullscreen app. Does it survive both? (acceptance #1)
3. Does it stay click-through — can you work normally underneath it?

**Voice, the deterministic path**
4. Wake phrase, then something trivial. Does the orb's pulse track your voice
   while you speak, or does it animate on its own? (This is the honesty
   invariant, live. The test proves the code can't fake it; this proves the
   wiring is real.)
5. `"Wellsy, stop"` during a long answer. **Expected to fail** — step 4c shipped
   the half-duplex gate and left spoken barge-in owed. Confirm the ESC key does
   work. Record the gap honestly rather than discovering it on camera later.

**Voice, the model path**
6. Ask a question that needs the LLM. Time to first word, by feel. Does the
   acknowledge-then-deliver pattern read as responsive or as a stall?
7. Ask it who it is / whether it has a camera. Step 6 increment 5 rewrote the
   identity prompt specifically to stop "I'm a text-based assistant." Confirm it
   holds, and note *any* remaining denial of its own capabilities.

**Vision**
8. Ask what is on your screen, with real windows open — the original defect.
   Does it describe your actual screen or your wallpaper?
9. Ask about something in the room via the camera.
10. If the VL model is not resident, confirm it refuses out loud
    (*"my vision model isn't loaded right now"*) rather than dying. Step 6
    increment 6 fixed a 400 that tore down the whole session; verify the fix
    holds live.

**The orb as an instrument**
11. `"move to the bottom-right"`, `"get out of my way"`, `"centre"`. Does it
    move, and how long after you stop speaking?
12. Drive a gated action to an approval prompt. Approve one. Deny one. Confirm
    **both** land in the audit log. (acceptance #4, #5 — step 6 only ever
    exercised approve.)

**Teardown**
13. `Ctrl-C`. Clean exit, or `zsh: suspended`?

**At least ten turns, continuous, open-air.** That is step 4c's carried debt and
this closes it or proves it isn't closed.

## Deliverable 2 — the device-timestamped latency row

The §1 number everyone has been composing instead of measuring.

`wellsy voice --measure-acoustic` (step 4b's runbook has the protocol). Wake →
**first PCM sample written to the output device**, n ≥ 20, p50 and p95, method
recorded next to the number. Deterministic path and LLM path separately.

Compare against 6b's composed figures — deterministic 563.5 ms p50, LLM 615.0 ms
p50. **If the real number is worse, that is the finding**, and it is a more
valuable one than a pass. Composed timings omit device buffering, driver
latency, and the gate's own overhead; the gap between 615 ms and reality is a
number this project should know.

Run it with the orb co-running. Step 6's acceptance #6 wants zero regression and
only the CPU half was ever checked.

## Deliverable 3 — the orb on video, per state

Screen-record the orb in each state: asleep, idle, listening, thinking, acting,
speaking, awaiting_approval, refusing (acceptance #8). Capture it over a
fullscreen app and across a Spaces switch.

Note honestly whether `awaiting_approval`'s amber and `refusing`'s collapse
actually read as different things, and whether the curl field still lumps
vertically the way increment 3 recorded. This is the input to the art pass, and
it is the first time anyone will have seen the states side by side.

## Deliverable 4 — the perception baseline (this footage cannot be re-shot)

**Step 5c replaces the detector.** After it lands, `yoloe-11s-seg.pt` is gone
from the running build and the current labelling behaviour never exists again.
Capture it now, on video, as the before-half of a comparison that is otherwise
impossible to make honestly.

- Run the perception path with the **current** `engine/prompts.txt`, unmodified.
  Record the live label stream on camera.
- Point it deliberately at **D30's named misses**: spectacles on a face, a phone
  held in a hand. Record the misses. Do not retune the prompt list to make them
  land — a tuned baseline is worthless as a comparison.
- Record the T0+T1 fast-path numbers alongside, and the cold-start cost on first
  call (the 5b-era note records 3849.9 ms; confirm or correct it).
- Save the prompt list, the model name, and the exact commit SHA next to the
  footage, so 5c's side-by-side is a real comparison and not two different
  scenes shot a month apart.

**Also tag the baseline before anything changes:**

```
git tag -a baseline-2026-10 -m "The 1-month-mark build: YOLOE-11, qwen3:4b-instruct-2507, qwen3-vl:2b-instruct. 190 tests."
```

That tag is what makes the before-state reproducible. Any later session can
check out exactly what was running when this footage was shot, which is the
difference between a comparison and a claim.

## Deliverable 5 — the writeup

`.claude/rebuild/step6c-results.md`:

- **The protocol table** — every numbered line above, what happened, pass/fail/
  partial. No blanks; "did not test" is a legitimate entry and a silent omission
  is not.
- **The latency row**, with its method.
- **A findings list, ranked by how much it hurts the experience** — not by how
  hard it is to fix. This list becomes the scope of later steps, so its ordering
  matters more than its length.
- **The honest paragraph:** what is it actually like to talk to? Step 6's own
  results doc said *"too early to say whether it feels like a creature — the orb
  has not rendered yet."* It has now. Answer the question.
- Which of step 6's "Still owed" items this closed, and be strict.

## Acceptance

- [ ] `wellsy run` executed live, open-air, ≥ 10 continuous turns, screen+audio
      recorded.
- [ ] All 13 protocol lines logged with outcomes.
- [ ] Approve **and** deny both exercised into the audit log.
- [ ] Device-timestamped §1 rows, n ≥ 20, p50/p95, method recorded, orb
      co-running.
- [ ] Orb recorded in every state, plus fullscreen and Spaces.
- [ ] Perception baseline recorded on the **current** detector, prompt list
      unmodified, D30's misses deliberately captured.
- [ ] `baseline-2026-10` tag created before any model change.
- [ ] `step6c-results.md` written, findings ranked by experience impact.
- [ ] Nothing fixed that wasn't blocking — findings logged instead.

## A note on the footage

The owner records this project publicly. This session produces the first
recording of the system being *used* rather than described, so keep the capture
clean: no editor windows, no terminal spew where the orb should be, and let the
failures stay in the take. The gap between 190 green tests and the first live
run is the most honest thing this project has to show.
