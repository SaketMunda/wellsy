# Step 5c — Model re-baseline: the 2026 set, measured the same way

**Read first:** `.claude/rebuild/INVARIANTS.md` (**#8** again, plus #11, #14),
`step5b-results.md` **in full** (this step re-runs its method against a new
candidate set and supersedes its §2–§5), `step5b-research.md`,
`spec/model-inventory.md`, `spec/phase1-acceptance.md` §1.
**Depends on 5b, 6b. Blocks step 7 and step 9.**

## Why this step exists

Five weeks passed with no commits. In that window the thing step 5b worked
hardest to prove appears to have been solved upstream.

**5b's central finding:** no flag makes a hybrid/thinking Qwen3 non-reasoning on
Ollama — seven documented attempts across steps 4, 4b and 5b, `think:"low"`
producing a *byte-identical* 4755.9 thinking tokens to no bound at all, and a
77.8 s planner turn against a 4 s budget. The workaround was to ship a model
with no think path at all (`qwen3:4b-instruct-2507`).

**What the world now reports** — all of it from web search, **none of it from a
model card, and none of it verified on this machine**:

| Claim | Why it matters here | Status |
|---|---|---|
| Qwen3.5 (Feb 2026) small sizes — 0.8B/2B/4B/9B — have **reasoning off by default** | Retires the entire 5b workaround. The lever we proved didn't exist may now be the default. | **unverified** |
| Qwen3.5 is **natively multimodal across the whole lineup** — text+image at every size | Could collapse planner+fast+VLM from two resident models into **one**. | **unverified** |
| `qwen3.5:4b` ≈ **3.4 GB**, **262K context** native | Our planner runs at **ctx 4096**. A 64× context change rewrites step 7's design. | **unverified** |
| Tool-calling at the 4B scale reported ≈97.5%, beating models 5× larger | Step 9's convergence puts 24 tools behind this slot. | **unverified** |
| **YOLOE-26** exists (Ultralytics, YOLO26 arch, NMS-free), needs `ultralytics>=8.4.0`; `yoloe-26s` **30.8 vs 27.5 mAP** LVIS vs `yoloe-11s` | We pin `>=8.4.120` — **the floor is already met.** Same `set_classes()` API. | docs-level, needs a run |
| Gemma 4 (Apr 2026) E2B/E4B | `gemma4:e4b` is **already pulled on this box at 9.6 GB** — which likely disqualifies it on the Orin budget before accuracy is even measured. Confirm or kill it fast. | partially local |

Second reason: **§7's hardware sizing is arithmetic over the outgoing set
again.** 5b took it 9.0 → 5.2 GB and flipped the Orin NX 16 GB verdict to
"fits with headroom." If one multimodal model replaces two, that number moves a
third time, and the Orin verdict must be re-derived rather than inherited.

## The rule for this step — unchanged from 5b, and it is the point

**Do not adopt a model from this prompt.** Every row in the table above is a
search result from aggregator blogs, which are exactly the sources invariant #8
exists to distrust. Establish from the **model card, the Ollama registry, or the
upstream repo**: release date, actual pulled size, licence, context window,
whether vision is native or a separate checkpoint, and whether reasoning is
genuinely off — then measure.

**The reasoning-off claim has a decisive instrument and you already own it.**
`engine/inference/llm_bench.py` counts thinking tokens per turn from the
server's real `eval_count`. That counter is what caught `qwen3:4b` and what
proved `think:"low"` inert. Point it at Qwen3.5 and the claim resolves in one
run. If the count is not zero, the claim is false regardless of what any blog
says — and that finding is worth more than the upgrade.

Method, non-negotiable and identical to 5b so the numbers are comparable:
n ≥ 20 warm, cold turn measured separately, p50/p95 nearest-rank, method
recorded beside every number, plan-JSON validity rate for the planner slot.

## Deliverable 1 — verify, and write down what you rejected

Resolve every "unverified" row above at its source. Record the real numbers, the
real sizes, and the licences. **Anything that fails to verify gets recorded as
rejected with the reason** — that record is as much the deliverable as the
adoption is.

Check Ollama's own current version too. We are pinned to the behaviour of
**0.33.2**; 5b's `think:"low"` finding is specific to that server. If the server
moved, the finding needs re-dating, not deleting.

## Deliverable 2 — planner + fast slot

Reuse `wellsy bench --modality llm --slot planner|fast`. Do not rebuild the
harness; 5b already closed that debt.

Incumbent to beat, with numbers already on file: `qwen3:4b-instruct-2507-q4_K_M`
— 32.1/46.8 ms TTFT, 3.99 s full plan, **0** thinking tokens, 20/20 plan-valid,
3.2 GB resident.

Candidates: `qwen3.5:4b` (primary), `gemma4:e4b` (already local — measure its
real resident size first and drop it immediately if 9.6 GB holds, with the
reason recorded). Add a third only if Deliverable 1 surfaces one that verifies.

A model replaces the incumbent only if it wins on a budget that matters, not on
a benchmark. 5b's planner budget is ≤ 4 s to a schema-valid plan; the fast
budget is < 1500 ms p50 to first word.

## Deliverable 3 — the collapse test

**The highest-value question in this step.** If Qwen3.5 is natively multimodal,
can **one** resident model serve planner, fast *and* vision?

Measure it as a vision model with the same method as 5b §4: cold load, cold
TTFT, first-capture processing, warm turn, legibility on real dense UI at the
resolution that clears the budget. The incumbent is
`qwen3-vl:2b-instruct-q4_K_M` — ~1.8 s first-capture, 2.0 GB, perfect
transcription on the 768 px proxy.

**This also closes 5b's owed D3** — the dense-real-screenshot resolution sweep
through `engine/voice/vision.py` → `IntentGate`, which 5b explicitly deferred
and which is the last unmeasured row in §1. Run it on a real screenshot of a
real dense UI, not a synthetic proxy, at 512 px and up.

If one model wins both slots, say what it costs: `SeamLLMService`'s two-model
switch (step 6 increment 6) becomes dead weight, and removing it is a
simplification worth taking — but **do not remove it in this step.** Measure,
recommend, and leave the code to step 9.

If a second candidate is warranted for vision specifically, IBM Granite 3.3 2B
is reported as the strongest sub-7B model on OCRBench. Verify before pulling.

## Deliverable 4 — the detector, the cheapest win available

`engine/perception/detector.py` runs `yoloe-11s-seg.pt`. YOLOE-26 is the same
family, the same `set_classes()` text-prompt API, and **our `ultralytics` floor
already satisfies its requirement** — so this is plausibly a one-string change.

- Swap to `yoloe-26s-seg.pt`, same scale, and measure the T0+T1 fast path
  against the standing budget (< 20/35 ms). **Report the live number, not the
  bench number.** The 13.49/23.95 ms figure is inference on a fixed frame; step
  6c's live baseline measured warm T1 (detect + track on live 1080p frames) at
  **33.32 ms p50 / 41.11 ms p95** for `yoloe-11s`, already over budget. Put
  both detectors' live figures side by side; a bench figure may sit beside them
  but never in place of them.
- Re-run the cold-start cost. Step 6c measured the `yoloe-11s` first call at
  **541.87 ms** live (it corrects the 5b-era **3849.9 ms** note). NMS-free
  inference may change it again.
- Confirm the MPS float64 workaround in `set_prompts()` is still needed. D30
  documented `mobileclip_blt.ts` failing under `map_location="mps"`; if YOLOE-26
  changed the text-encoder path, that workaround may be removable — or may break.
- **Then point it at the misses D30 recorded as structurally unfixable**: the
  spectacles, the held phone. Same prompt list, same scene, side by side with
  `yoloe-11s`. That comparison is the whole reason to care about 30.8 vs 27.5
  mAP, and a number on LVIS is not a substitute for it.

### The motion gate must be held open for the comparison

Step 6c's perception baseline (`step6c-results.md`, session D) found that the
T0 motion gate (`MOTION_THRESHOLD = 5.0` of 255 mean abs-diff, 1.0 s hold)
passed **48 of 2651 frames (1.8 %)** in a 90 s run. Putting on glasses or
holding up a phone does not move enough pixels to open it, so on most frames
the detector never ran and the loop re-emitted stale tracks. A side-by-side
through the gate measures the gate twice and the detectors barely at all.

- **Add a gate-bypass flag to the perception CLI** (e.g. `wellsy --gate-open`):
  T1 runs on every frame. This is verification-harness code and is in scope.
  T0 still runs and is still timed; only its decision is ignored.
  INVARIANTS #5 is about T0 never being skipped, and it is not.
- Run **both** detectors with the gate held open, on the same scene. Better:
  record one clip once (person in frame → glasses on → phone in hand → leaves)
  and run both detectors over the identical frames, so the comparison is not
  two performances shot minutes apart.
- Compare against 6c's gated baseline as well, but label it gated: glasses
  17/47 runs at 0.37–0.84, phone 1/47 at 0.39.

**Do not retune the gate in this step.** Making T1 run at least once every N
seconds regardless of motion is the likely fix for the 1.8 %, but it changes
how WELLSY perceives the room and needs its own test. No current step owns
perception scheduling; it is listed under "Open debt" in `README.md`. Record any
evidence 5c produces for it, and change nothing.

If latency regresses past budget, the finding is "better labels cost X ms" —
report it and let the owner choose. Do not quietly accept a miss.

### The alternative that may beat the upgrade (added 2026-10-14)

YOLOE-26 is a better draw from the **same closed-vocabulary mechanism** D30
identified as the structural limit. A two-stage pattern removes that dependency
instead, and it should be measured against the upgrade rather than assumed
worse:

> **detector localizes → crop → typed question → probability**

The detector never has to produce the right *label*; it only has to produce a
box. The question is then asked of the crop — *"is this person wearing
spectacles?"* as a Predicate. This is the public egg-sorting pipeline (RF-DETR +
tracking → per-crop decision call), and D30's named misses are exactly the case
it addresses.

Measure three arms on the **same** scene and the same D30 misses, with the step
6c perception-baseline footage as the before:

1. `yoloe-11s-seg.pt` — the incumbent (6c captured this; do not re-tune it).
2. `yoloe-26s-seg.pt` — the upgrade.
3. `yoloe-11s` or `-26s` for localization only, **plus a typed decision call on
   the crop** (OpenAI Decisions API on `gpt-6-luna`, public beta 2026-10-06,
   image input, $0.10/1M input with output free; or Jev; or a local VLM asked a
   closed question).

Report per arm: does it get spectacles and the held phone right, at what added
latency, and at what cost per call. **Arm 3 does not go in the 8 Hz fast path** —
a ~150 ms network call against a <20/35 ms budget is 6–10× over, and continuous
image crops at 8 Hz are a token cost nobody has sized. Scope it as an on-demand
capability and say which path it belongs in.

If arm 3 wins on the misses, that is a **step 8** architecture change, not a
model swap — report it and let step 8 own it.

## Deliverable 5 — re-derive §1 and §7, third time

Supersede `step5b-results.md` §2–§5:

- The full §1 latency table, every model row re-measured, no blank cells except
  those explicitly owed to a live session (step 6c owns those).
- Measured co-residency (`ollama ps`, ctx as actually configured) for the winning
  set. 5b's figure is 5.2 GB; state the new one and the delta.
- **The Orin NX 16 GB verdict, re-derived from the new arithmetic** — not
  inherited from 5b. Carry 5b's caveats forward explicitly: the numbers are
  darwin/arm64, the Linux/CUDA path is still unexecuted, and the Jetson figure
  remains a projection until someone runs `ollama ps` on the board.
- **Re-measure at the context the agent actually runs**, not 4096, if the winner
  offers more. 5b flagged this and it is now the load-bearing question.

## Deliverable 6 — the context finding step 7 is waiting on

State plainly, as its own section: **what usable context does the winning
planner have, and what does that mean for a memory and context engine?**

`step7-memory-context.md` specifies retrieval over a sqlite-vec store. The right
design for a 4096-token planner (aggressive retrieval, tight trimming) is not
the right design for a 262K one (fewer, larger, provenance-tagged blocks). Step
7 should not start until this answer exists. One section, stated as a
recommendation with the measurement behind it.

Also note for step 7's benefit: LangGraph added **pre/post model hooks** (for
context trimming and redaction), node caching, and deferred nodes in 2026. We
pin `>=1.2.11`. Check what the resolved version actually provides — those hooks
are the natural seam for the context engine.

## Out of scope — named so they are not quietly absorbed

- **TTS.** The expressive-voice ask is real and long-standing
  (`.claude/v2-roadmap.md` names Chatterbox Turbo as the target with Kokoro-82M
  as the fallback, and the rebuild shipped the fallback). It is step 10, with
  its own bench-off. Do not swap the voice here.
- **ASR.** `faster-whisper base.en` is English-only, and the README records that
  **Qwen3-ASR was already rejected on measured numbers.** It does not return as
  a fresh idea — only with a specific reason it would measure differently now,
  and then as its own step.
- **No refactors.** This step changes model strings, measures, and writes
  numbers down. Code changes beyond a model identifier and whatever a
  verification harness needs belong to step 9.

## Acceptance

- [ ] Every claim in the table above resolved at its source; rejections recorded
      with reasons.
- [ ] Thinking-token count for every candidate, from the server's real
      `eval_count` — the reasoning-off claim settled with a number.
- [ ] Planner and fast slots measured, n ≥ 20, against the 5b incumbent's
      recorded figures.
- [ ] Collapse test run; one-model-or-two answered with numbers. 5b's owed D3
      (dense real UI, 512 px) closed.
- [ ] YOLOE-26 measured on the fast path (**live** figures, beside 6c's
      33.32/41.11 ms), on cold start (beside 6c's 541.87 ms), and **side by
      side with `yoloe-11s` on D30's named misses, with the motion gate held
      open** (gate-bypass flag added; same clip or same scene for both).
- [ ] Motion gate untouched; any evidence on the 1.8 % gated fraction recorded
      in `step5c-results.md` for the owning step.
- [ ] §1 re-derived in full; co-residency measured; **Orin verdict re-derived,
      not inherited**, with the darwin-only caveat restated.
- [ ] The step-7 context recommendation written as its own section.
- [ ] `step5c-results.md` written; `spec/model-inventory.md` updated; PR open.

## The standing rules

Numbers or nothing. A model enters this repo only with numbers beside it and the
numbers of what it beat recorded alongside. If a claimed upgrade does not
reproduce, **that is the result** — write it down and keep the incumbent. 5b's
best output was not a model choice, it was proving a vendor's parameter did
nothing; this step should be equally willing to come back empty.
