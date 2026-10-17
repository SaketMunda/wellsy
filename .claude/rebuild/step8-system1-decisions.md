# Step 8 — A System-One decision layer: Jev primary, local fallback

**Read first:** `.claude/decisions.md` **D55 and D55 (amended)** — the amendment
is the operative one; online APIs are permitted by owner override.
`.claude/rebuild/INVARIANTS.md` (**#6, #10, #11, #14**), `step6-results.md`
increment 5 §"What this does NOT yet do", `engine/honesty/intent.py`,
`engine/voice/intent_gate.py`, `engine/inference/` (copy its seam pattern).
**Depends on 5c, 9.**

## Why this step exists

Two problems in this codebase are one problem.

**1. Every capability needs a hand-written intent.** `parse_intent` recognises
`stop`, `wake`, `sleep`, `describe_scene`, `query_object`, `move_orb` — each a
bespoke parser. The owner's own complaint from step 6 increment 5: WELLSY should
act on free-form requests without a hand-written intent for each. Step 9 lands
convergence using the planner's native tool-calling; this step makes routing
cheap, fast and measurable instead of a 4-second planner hop for *"move left."*

**2. Confidence is asserted, not measured.** The policy gate decides and the
audit log records it, but there is no *number* behind it. Invariant #11 — an
inference is never auto-promoted to a fact — has nothing to threshold on, and
step 7's memory rows need a `confidence` field no instrument currently fills.

A System-One layer answers both: a typed decision with a calibrated probability,
one round trip, no token generation.

## The contract

- **Input:** `state` (text or structured) plus declared typed questions —
  `Choice` (one of N), `Score` (bounded range), `Bool`.
- **Output:** per question, a typed value **and a calibrated probability**.
- **No prose, no rationale.** If an explanation is needed that is the LLM's job;
  this layer decides whether to spend it.

## Deliverable 0 — can we call it at all? (do this first, time-box it)

Jev is early-access behind a waitlist. Reported reachable via **OpenRouter** and
**Vercel AI Gateway**, which may bypass the waitlist entirely. Establish, before
writing any integration:

- Is there a working route to `jev-latest`? Direct, OpenRouter, or Gateway.
- What does the real request/response schema look like — not what a blog says.
  `POST /v1/systemone`, `state` + `questions`, typed values with probabilities.
- Real measured latency from this machine, not the vendor's 70–500 ms claim.
  **Network latency is the whole question**: a hosted call that costs 400 ms
  round-trip is slower than the local fast model's 53 ms TTFT, which would make
  the hosted path pointless for routing and useful only where its calibration
  earns the wait.
- Cost per decision at our actual call volume.

**If there is no route within the time-box, do not wait on a waitlist.** Build
Deliverable 2 on the local backend, ship it, and leave the Jev adapter as a
stub. The step's value does not depend on the vendor.

## The field moved — a second vendor, and images (added 2026-10-14)

**OpenAI Decisions API**, public beta **2026-10-06**, on `gpt-6-luna`. Three
output types that map onto the contract above almost exactly: **Predicates**
(probability a statement is true), **Choices** (select from options with
confidence), **Scores** (evaluate against a numeric range). $0.10 per 1M input
tokens, **output tokens free**, ~150 ms in DevDay coverage. **It accepts image
input.**

Two consequences for this step:

1. **The seam must accept image crops, not just text state.** A typed question
   over a cropped region is the highest-value use available to this project —
   see step 5c's three-arm detector comparison. Design the interface for
   `state: text | structured | image` from the start; retrofitting it is worse.
2. **Two hosted candidates now exist, plus local.** Bench them against each
   other in Deliverable 0, not just "can we reach Jev."

**Neither vendor has published calibration data.** OpenAI has not published
accuracy or calibration figures for the endpoint, and secondary coverage
disagrees on whether the returned scores are calibrated probabilities at all.
Jev's calibration claim is also vendor-reported. Deliverable 4 applies to both,
with no discount for the logo.

**One pattern to steal, and one not to.** The public egg-sorting pipeline
(detector + tracker → per-crop decision → *three* agreeing looks before acting)
is sound where the three looks are **independent** — the egg rotates on the
belt. Three consecutive frames of a static scene are three *correlated* samples:
consensus over them inflates confidence without adding information. If temporal
consensus is adopted here, independence must be established by construction
(changed angle, distance or scene), and the honesty test must fail if correlated
samples are counted as independent evidence.

## Deliverable 1 — the seam, three backends

`engine/decide/`: the typed interface above, following `engine/inference/`'s
existing portable-backend pattern. Do not invent a second pattern.

- **`jev` backend** — hosted (TypeSafe).
- **`openai_decisions` backend** — hosted (`gpt-6-luna`), **the one that takes
  images**. Follow `engine/inference/backends/openai_http.py`'s conventions.
- **`local` backend** — GLiClass (Knowledgator, arXiv 2508.07662: bidirectional
  encoder, label-conditioned, ~10× faster than cross-encoders, CPU-capable,
  ~187M–399M; note the published table has the *smaller* model scoring higher
  on average, so size is not the selector) or GLiNER2's schema-driven interface
  (arXiv 2507.18546). Verify licence and a Linux/CUDA path at the source.
- **`deterministic` backend** — fixed answers, for tests. The suite must never
  need a model download or a network call.

**Why the local backend is not optional** (D55 amended, point 2): D51 makes a
Jetson-class body production target #1, and a body that cannot decide without
connectivity does not ship. Build it now; retrofitting a fallback later is the
expensive order. It does not have to be the default.

**Explicitly poisoned:** anything from the aggregator pages describing a
self-hosted Jev clone "powered by GLiFormer 400M." **GLiFormer does not
verify.** If search surfaces it again, that is the same bad source, not
corroboration.

Budgets, measured n ≥ 20, p50/p95, method recorded:
- Local backend resident ≤ 500 MB.
- **Routing decision ≤ 50 ms p95 local.** For the hosted backend, report the
  real number and let it decide its own role — if Jev costs 400 ms, it belongs
  on decisions worth 400 ms, not on *"move left."*

## Deliverable 2 — the egress record (cheap now, impossible later)

The owner has deferred the guardrail/firewall and that is fine. **The log is not
deferrable**, because a guardrail cannot be written later against data nobody
captured.

Every outbound call records: timestamp, destination, the **exact payload**, byte
count, latency, and what came back. One append-only JSONL under the existing
audit-log conventions. Add a single `wellsy egress --since` view.

That is the entire scope here — no policy, no blocking, no redaction. Just the
record that makes the later firewall writable, and that answers "what has left
this machine?" with a file instead of a guess.

## Deliverable 3 — intent without a parser per capability

Replace the **fallback**, not the fast path.

**Hard rule: the deterministic intents stay local and model-free.** `stop`,
`wake`, `sleep`, `move_orb` keep firing on the committed transcript with nothing
in the loop. `stop` is a safety control on a measured 617/700 ms budget — it
does not go behind a network hop or a classifier. This is D55-amended point 1
and it is a latency constraint, not a preference.

What changes is the path after a deterministic match fails. Today it falls
through to a bare chat LLM (and after step 9, to the planner). Instead: a
`Choice` question over the tool catalog plus `none`, returning a label and a
probability. Above threshold, route directly. Below, fall through.

Two things must be true:
- **Adding a capability must not require a new parser.** Prove it: add one tool
  to the catalog, show it becomes voice-reachable with no new parsing code. That
  demonstration is the deliverable, not the classifier.
- `none` must be a real, well-calibrated outcome. A router that always routes
  somewhere is worse than the fallthrough it replaced.

## Deliverable 4 — calibration, the actual hard part

**A probability that is not calibrated is a lie with a number on it.** Jev
*claims* calibration; that claim gets verified here on our decisions, not taken
from the vendor. Same work is owed for the local backend.

- Build a small labelled set from **real** utterances — the transcripts in
  `step4c-*` and the step 6c live session, not invented strings.
- Measure calibration, not just accuracy: reliability by confidence bucket and
  expected calibration error. Report the curve, per backend.
- **Derive every threshold from that curve.** No hand-picked 0.8.
- Report false-accept and false-reject separately. Their costs differ sharply: a
  false accept runs the wrong tool, a false reject only falls through.

If calibration is poor, **ship the layer for routing and do not wire it to the
policy gate.** Say so, with the curve.

## Deliverable 5 — confidence into the gate, one direction only

**This constraint matters more than the feature:** the layer may **raise**
caution and may never **lower** it.

- It may escalate — push a borderline action into the approval gate that policy
  alone would have allowed.
- It may **never** auto-approve, relax or bypass anything policy would have
  gated. The deny path stays deterministic.
- Nothing behind a network call gets final authority over sending mail.
  Autonomy stays recomputed from the audit log, never a persisted flag.

Every decision writes an audit row: question, options, chosen value,
probability, threshold compared against, backend used, and which way it moved
the outcome. D55-amended records that a no-rationale decision is a real
reduction in explainability — the row is what partially offsets it, so it must
be complete.

Then supply the `confidence` field step 7's memory rows need and the number
invariant #11 thresholds for `inferred` vs `stated`.

## Deliverable 6 — extend the honesty test

A test that fails if a confidence value reaching the audit log or a memory row
was **not** produced by a real decision call — no default, no placeholder, no
`0.5` stand-in when a backend is absent or the network is down. If the backend
is unavailable the honest behaviour is to fall back to `local`, then to
deterministic, and **record that it degraded** — never to emit a plausible
number. Same discipline as the orb's amplitude test.

## Out of scope

- Not a replacement for the planner. This layer decides; the LLM reasons.
- The guardrail/firewall itself — owner-deferred. Only the log lands here.
- Not the memory store (step 7). This step only supplies the confidence number.
- **No new hand-written intents.** If this step ends with more bespoke parsers
  than it started with, it failed.

## Acceptance

- [ ] Deliverable 0 answered: a real route to Jev or a recorded "no access,
      proceeding local," with measured latency either way.
- [ ] `engine/decide/` seam accepting text **and image** state; `jev`,
      `openai_decisions`, `local` and `deterministic` backends; banned-import
      test green.
- [ ] Both hosted backends benched against each other and against local:
      latency, cost per decision, and calibration.
- [ ] Local resident size and both backends' p50/p95 measured.
- [ ] Egress JSONL capturing every outbound payload; `wellsy egress --since`
      works.
- [ ] Deterministic intents provably unregressed — §1 deterministic row
      re-measured.
- [ ] A new tool made voice-reachable with **no new parsing code**, demonstrated.
- [ ] Calibration curve + ECE per backend; thresholds derived from it;
      false-accept and false-reject stated separately.
- [ ] Gate integration escalate-only, proven by a test that fails if a decision
      can relax a policy outcome.
- [ ] Honesty test extended: no fabricated confidence; degradation recorded.
- [ ] `step8-results.md` written; PR open.

## The standing rules

Numbers or nothing, with a sharper edge here: a number that cannot be trusted is
worse than no number, because the rest of the system will believe it. If the
calibration does not hold up — vendor or local — come back with the curve and a
recommendation not to ship it. That is a successful outcome for this step.
