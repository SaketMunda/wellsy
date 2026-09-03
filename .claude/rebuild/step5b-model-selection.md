# Step 5b — Model selection: close the reasoning-tax debt, on measured numbers

**Read first:** `.claude/rebuild/INVARIANTS.md` (**#8** is the whole point of
this step, plus #11, #15), `.claude/rebuild/step4-results.md` §"§1 latency
table", `step4b-results.md` §"VLM §1 latency", `step5-results.md` §6 and §7,
`spec/phase1-acceptance.md` §1 (the budget table).
**Depends on steps 4, 4b, 5. Blocks step 6 and blocks the hardware purchase.**

## Why this step exists

Three model slots are filled with placeholders and every one of them is either
unshippable or unmeasured:

| Slot | Current | State |
|---|---|---|
| planner | `qwen3:4b` | **33 s TTFT.** Unshippable. Reasoning pass cannot be disabled — six documented attempts failed (step 4). |
| VLM | `qwen2.5vl:3b` | Reasons 0.000 s, works, but chosen under time pressure and never bench-offed. 3.0 s TTFT at 1024px vs a 2.5 s budget — a **measured miss**. |
| fast | `qwen2.5:3b` | 43 ms TTFT, clears the budget, but it is a **2024 model** adopted with the bench-off explicitly deferred. |
| TTS | `kokoro` | Clears the budget, flat delivery. The expressive-speech requirement is unmet and the Qwen3-TTS bench-off was never run (step 2 debt). |

Second reason: **§7's hardware sizing is computed from these models.** The 9.0 GB
co-resident figure, and therefore the "Orin NX 16 GB does not fit" conclusion the
owner is about to spend money against, is arithmetic over a model set that is
being replaced. Do not let a purchase rest on it.

## The rule for this step

**Do not name a model from memory, from a planning document, or from this
prompt.** Establish what is current *now* — release dates, sizes, licences,
whether reasoning is bounded or disableable, whether an Ollama/GGUF/ONNX build
exists that runs on both macOS-arm64 and Linux-CUDA (invariant #14). Then
measure. A model enters the repo only with numbers next to it, and the numbers
of the models it beat are recorded alongside.

Non-negotiable measurement method, unchanged from §1: **timestamp at the first
PCM sample written to the output device** for end-to-end rows; TTFT for model
rows. n ≥ 20, cold and warm separate, p50 and p95, method recorded next to
every number.

## Deliverable 1 — extend the bench harness

`wellsy bench --modality llm` currently reports one composite row. Extend it to
run a named candidate set per slot and emit a comparison table: TTFT p50/p95,
tokens/sec, resident MB, cold-load s, and **thinking-token count per turn**
(the metric that caught `qwen3:4b`; it belongs in the harness, not in a session's
notes). This closes step 5 debt #4.

## Deliverable 2 — planner slot

The blocking one. Requirements: tool-calling that survives a ≥ 3-step plan (A9),
structured-output reliability under the graph's plan schema, and a TTFT that
lets acknowledge-then-deliver actually deliver. Candidates must include at least
one model whose thinking budget is *bounded by a parameter the server honours* —
verify by `curl` against the running server, not by reading a model card.

If no candidate clears the budget with thinking on, the finding is that the
planner path needs a bounded-think or a non-reasoning model with a stronger
plan prompt — report which, with the numbers, rather than shipping a miss.

## Deliverable 3 — VLM slot

Drive it through the real path (`engine/voice/vision.py` → `IntentGate`), not a
synthetic prompt: the 9.4 s → 3.2 s downscale finding shows prompt-processing on
vision tokens dominates, so **token count at each candidate resolution is part
of the measurement**. Produce the ≥ 20-trial VLM TTFT campaign step 5 owes
(debt #2) and state plainly whether the §1 VLM row passes, and at what
resolution — a resolution that passes latency but loses screen-text legibility
is a fail, so check readability of a real screenshot, not just the clock.

## Deliverable 4 — fast slot, and TTS

Fast slot: bench-off against current non-reasoning instruct models, losing
numbers recorded (step 5 debt #3).

TTS: run the two-candidate bench-off step 2 deferred (Qwen3-TTS or whatever is
current) against Kokoro, on **both** latency and expressiveness. Expressiveness
needs a stated judging method — an A/B the owner listens to is acceptable and
should be recorded as such. Kokoro stays if it wins; the requirement stops being
open either way.

## Deliverable 5 — re-derive §7

Recompute the hardware sizing over the models that actually won: per-role
resident MB, co-resident total, the desktop residency strategy, and the Orin
NX 16 GB verdict. This supersedes `step5-results.md` §7 — say so explicitly in
the results doc, because a purchase decision hangs off it.

## Acceptance

1. `wellsy bench --modality llm` runs a candidate set per slot and emits the
   comparison table, exit 0, results under `spec/results/`.
2. Every slot in `engine/agent/models.py` and the voice path defaults to a model
   backed by a measurement in this step's results file.
3. Every §1 row that involves a model is re-measured against the winners — pass
   or documented miss, no blank cells.
4. `.claude/rebuild/step5b-results.md` records winners **and losers** with
   numbers, and carries the re-derived §7.
5. Full suite green. Tree clean.

## Report back

The §1 table with every model row filled, the new §7, and — stated plainly —
whether WELLSY now clears its own latency budget on the paths that matter, or
which rows still miss and why.
