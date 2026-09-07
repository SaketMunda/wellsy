# Step 5b — Research & run plan (no benchmarking yet)

**Session date:** 2026-09-03 · **Branch:** `master` (read-only session) ·
Scope this pass: *"Research + plan only"* per owner. No weights pulled, no
campaigns run. Every model below is a **candidate**, not an adoption — nothing
enters `engine/agent/models.py` or the voice path until it has ≥ 20-trial
numbers next to it (INVARIANTS #8, step 5b acceptance 2).

Supersedes nothing yet. Feeds `step5b-results.md`, which will carry the numbers
and the re-derived §7.

---

## 0. Verification method

- **Ollama tag lists:** scraped live from `ollama.com/library/<model>/tags`
  2026-09-03. Sizes cross-checked against the model cards; exact **resident MB
  is a bench-time `ollama ps` measurement** and is left blank here on purpose.
- **Thinking-control behaviour:** `curl` against the **running local server**
  (`http://localhost:11434`, Ollama **0.33.2**, the pinned version) —
  step 5b Deliverable 2 requires "verify by curl, not by reading a model card."
- **Licences / architecture / portability:** HF model cards + upstream repos.
- Web search on the model landscape was **heavily SEO-polluted** (fabricated
  "Qwen3.5", "Gemma 4", "Qwen3.8-27B", future-dated arXiv ids). Nothing from a
  search result is used below unless it was confirmed against a primary source
  (ollama.com registry, github.com/ollama/ollama releases, huggingface.co/Qwen).

---

## 1. Environment facts established this pass

| Fact | Evidence | Consequence |
|---|---|---|
| **Ollama 0.33.2 is current.** Latest tag is 0.33.3 (pre-release, 2026-09-02); 0.33.2 stable 2026-08-27. | `github.com/ollama/ollama/releases`, `curl /api/version` | **Upgrading Ollama is not a lever.** No release note 0.33.0→0.33.3 mentions a thinking budget / bounded think / think-token limit. The step-4 reasoning-tax debt is not an Ollama-version bug we can patch by bumping. |
| **`think: false` does not stop qwen3:4b generating chain-of-thought.** With `think:false` the `thinking` field is empty but `content` fills with `"We are to say hi in exactly 3 words. The simplest way..."` and hits `num_predict`. | `curl /api/chat` model=`qwen3:4b` `think:false` 2026-09-03 | Confirms step 4 / 4b: on the hybrid `qwen3:4b` Ollama swaps in a generic template and the reasoning prefix is still paid. A **flag will not fix the planner** — the fix is a model that is non-reasoning *by construction* (an `-instruct` build) or one with a server-honoured effort dial. |
| **`think: "low"` / `"high"` / `"max"` are accepted by the API** (no error; reasoning routed to the `thinking` field). OpenAI `reasoning_effort` maps onto `think` (Ollama since ~0.21.3). | `curl /api/chat` model=`qwen3:4b` `think:"low"` 2026-09-03 | **A lever step 4/4b never tried.** Their six attempts were `think:false`, `reasoning_effort:none`, `chat_template_kwargs.enable_thinking:false`, `/no_think` in system + user, and the `qwen3:4b-nothink` tag — **not the string effort levels.** Whether `"low"` actually *bounds* the thinking token count on the hybrid `qwen3:4b` (generic template) is unknown and is a **measurement for Deliverable 2**, not a claim. |

---

## 2. Planner slot — candidate shortlist

Requirements (step 5b D2): 3+-step tool-calling plans (A9), structured output
under the graph's plan schema, TTFT that lets acknowledge-then-deliver deliver
(planner budget ~3–4 s to first token; ≤ 6-step plan in ≤ 4 s wants ≳ 50 tok/s
and no unbounded reasoning prefix). Must include **≥ 1 candidate with a thinking
budget bounded by a server-honoured parameter**, verified by curl.

| # | Candidate (Ollama tag) | ~Download | Params | Licence | Reasoning control | Portability | Why shortlisted |
|---|---|---|---|---|---|---|---|
| P1 | `qwen3:4b-instruct-2507` (q4_K_M) | ~2.5 GB | 4B dense | Apache-2.0 | **None — non-reasoning by construction.** July-2025 refresh, no `<think>` path. | Ollama → portable ✔ | The "non-reasoning model + stronger plan prompt" route the step names as the likely answer. Newer than `qwen2.5:3b`, same class, no template games. |
| P2 | `qwen3:4b-thinking-2507` (q4_K_M) | ~2.5 GB | 4B dense | Apache-2.0 | Always reasons; **test `think:"low"`/`"high"` for a bounded prefix** (curl D2). | Ollama → portable ✔ | If a *bounded* think clears the budget, this is the reasoning planner. If it can't be bounded, it's the control that proves the finding. |
| P3 | `qwen3:4b` (hybrid, already local) | in place | 4B dense | Apache-2.0 | Template-locked by Ollama (confirmed §1). `think:"low"` accepted — bounded? unknown. | Ollama → portable ✔ | Incumbent-adjacent baseline; carries the 33 s TTFT number to beat. |
| P4 | `gpt-oss:20b` | ~14 GB | 20B (MoE, ~3.6B active) | Apache-2.0 | **Native `reasoning_effort` low/med/high, server-honoured** — this is the "bounded by a parameter the server honours" candidate. | Ollama → portable ✔ | Satisfies the D2 must-have. **But 14 GB resident** → cannot co-reside with VLM + fast on Orin NX 16 GB (§5). Measure on M4 Pro as the "what a real effort dial buys" data point, expect to reject on the working-set test. |
| P5 | `granite4:3b` / `granite4:micro` | ~2 GB | 3B dense (hybrid-Mamba) | Apache-2.0 | Non-reasoning instruct. | Ollama → portable ✔ | IBM Granite 4 (2026), Mamba-hybrid → low KV-cache growth on long tool transcripts. Fast-slot candidate too (§4); cross-entered here as a small non-reasoning planner. |

**Not shortlisted:** `qwen3:1.7b` / `0.6b` (too weak for a 3-step tool plan — verify only if P1/P5 fail structured output); `qwen3:30b-a3b-instruct-2507` (~19 GB resident, Orin-infeasible); `phi4-mini:3.8b` (2024-era, no advantage over P1); `deepseek-r1` distills (unbounded reasoning, same disease).

**Expected finding (to be confirmed, not assumed):** no ≤ 4B candidate clears
the planner budget *with thinking on and bounded*; the planner ships as
**P1 `qwen3:4b-instruct-2507` + a stronger plan prompt**, with P4's numbers
recorded as "a real effort dial exists but only above the Orin working set."

---

## 3. VLM slot — candidate shortlist

Drive through the **real path** `engine/voice/vision.py` → `IntentGate` (not a
synthetic prompt). Vision-token count at each candidate resolution is part of
the measurement (the 9.4 s→3.2 s downscale finding = prompt-processing on vision
tokens dominates). A resolution that passes latency but loses screen-text
legibility is a **fail** — check a real screenshot for readability, not just the
clock. Budget: wake→first word (VLM) < 2500 ms p50 / < 3500 ms p95.

| # | Candidate (Ollama tag) | ~Download | Params | Licence | Reasoning control | Why shortlisted |
|---|---|---|---|---|---|---|
| V1 | `qwen3-vl:4b-instruct` (q4_K_M) | ~3.3 GB | 4B | Apache-2.0 | **Non-reasoning by construction** — the `-instruct` build, no `<think>`. | Directly retires the step-4b VLM debt: that debt was `qwen3-vl:4b` (hybrid) reasoning uncontrollably. Same weights family, instruct-tuned, strong on document/screen OCR. Needs Ollama ≥ 0.12.7 (have 0.33.2 ✔). |
| V2 | `qwen3-vl:2b-instruct` (q4_K_M) | ~1.9 GB | 2B | Apache-2.0 | Non-reasoning. | The Orin-friendly option. Measure whether 2B holds screen-text legibility at the resolution that clears latency; if it does, this is the pick for the 16 GB working set. |
| V3 | `qwen2.5vl:3b` (already local) | in place | 3B | Apache-2.0 | Non-reasoning (2024-era). | The step-5 interim VLM. Baseline to beat; carries the "chosen under time pressure, never bench-offed" tag. |
| V4 | `qwen3-vl:8b-instruct` (q4_K_M) | ~6.1 GB | 8B | Apache-2.0 | Non-reasoning. | Upper-bound reference: does 8B legibility justify the resident cost on the M4 Pro? Almost certainly Orin-infeasible co-resident; measure as the ceiling. |

**Not shortlisted:** `moondream` (1.9B but weak on dense text / screen UI per its
own card — legibility risk); `gemma3:4b` vision (viable general VLM, but Qwen3-VL
is the stronger document/OCR line and keeps the stack in one family — hold as
fallback if V1/V2 disappoint on readability); `qwen3-vl:*-thinking` (reintroduces
the exact debt being retired).

**Resolution sweep to run:** native, 1024px, 768px, 512px longest-edge — record
vision-token count + TTFT + a human legibility check on a real screenshot with
small text at each.

---

## 4. Fast slot — candidate shortlist

Bench-off vs the incumbent, **losing numbers recorded** (step 5 debt #3).
Budget: wake→first word < 1500 ms p50 / < 2500 ms p95; needs TTFT < ~1 s and
≳ 30 tok/s to keep the TTS buffer fed under ASR+TTS+VAD contention.

| # | Candidate (Ollama tag) | ~Download | Params | Licence | Notes |
|---|---|---|---|---|---|
| F1 | `qwen2.5:3b` (already local) | in place | 3B | Apache-2.0 | **Incumbent / interim.** 2024-era. Carries 0.19 s TTFT / 88.7 tok/s (1 warm turn, step 5 §6). The number to beat. |
| F2 | `qwen3:4b-instruct-2507` (q4_K_M) | ~2.5 GB | 4B | Apache-2.0 | Current same-class non-reasoning model. If it holds TTFT < 1 s it replaces F1 on recency grounds (INVARIANTS #8) and **unifies fast+planner on one model** (§5 lever a). |
| F3 | `qwen3:1.7b` | ~1.4 GB | 1.7B | Apache-2.0 | Smaller, faster TTFT, lighter resident — but hybrid template. Measure whether the ack-line + short replies survive the quality drop. |
| F4 | `granite4:micro` / `granite4:3b` | ~2 GB | 3B | Apache-2.0 | 2026 model, Mamba-hybrid → flat KV growth. Real recency alternative to Qwen. |
| F5 | `llama3.2:3b-instruct` | ~2 GB | 3B | Llama 3.2 Community Licence | Widest ecosystem, but **non-Apache licence** and 2024-era — include only as a reference point, not a likely pick. |

**Strong candidate outcome:** F2 wins and becomes the single model for both
fast and planner (non-reasoning), collapsing two slots into one resident model.

---

## 5. TTS slot — candidate shortlist + the portability problem

Run the two-candidate bench-off step 2 deferred, on **latency and
expressiveness**. Expressiveness needs a stated method — an **A/B the owner
listens to**, recorded as such. Kokoro stays if it wins.

| # | Candidate | Params | Licence | Runtime path | Portability verdict (INVARIANTS #14) |
|---|---|---|---|---|---|
| T1 | **Kokoro-82M** (incumbent, `kokoro-onnx` 0.6.1) | 82M | Apache-2.0 | ONNX, ORT provider auto | **Portable ✔** macOS-arm64 + Linux-CUDA both proven (step 4). RTF 0.202, TTFA 345/406 ms. Flat delivery — the requirement it fails. |
| T2 | **Qwen3-TTS-12Hz-1.7B** (`Qwen/Qwen3-TTS-12Hz-1.7B-*`, rel. 2026-01-22) | ~1.7B (2B BF16 ≈ 3.4 GB) | Apache-2.0 | **vLLM-Omni or `transformers` + CUDA/FlashAttn2.** No ONNX, no GGUF, **no documented CPU path.** | **Fails the portable gate as-is.** vLLM does not run on Apple Silicon; `transformers` MPS path is unverified and likely far off the 97 ms streaming claim. Would need a measured macOS-arm64 path before it can be the default. Claims 97 ms first-packet streaming + NL voice control + emotion — matches the owner's "human-like + emotional" ask (memory) — so it is worth a **CUDA-side measurement** even if it can't be the cross-platform default this step. |
| T3 | **Orpheus-TTS** (Llama-3B backbone, 150M–3B) | 3B (also 150M/400M/1B) | Apache-2.0 | GGUF via llama.cpp / Ollama-compatible; SNAC decoder (ONNX-able) | **Plausibly portable** — llama.cpp runs everywhere. Heavier than Kokoro (~2 GB @ 3B), inline paralinguistic tags for emotion. The realistic cross-platform expressive upgrade if Kokoro loses. |
| T4 | **Chatterbox** (0.5B) | 0.5B | MIT | PyTorch; ONNX export community-only | Rejected once already on **CPU cost** (step 4 / stack-teardown). Re-measure only if the owner wants it re-litigated. |

**Recommended framing for the bench-off:** T1 Kokoro vs **T3 Orpheus** on the
portable path (both can run macOS-arm64 + Linux-CUDA), plus a **T2 Qwen3-TTS
CUDA-only reference** so the owner hears the ceiling. The "emotional TTS day" in
the roadmap (memory `wellsy_future_tts_emotion`) is where T2 gets a real
portable-path effort; this step's job is just to close the "is Kokoro good
enough / what's the bar" question with numbers + an A/B.

---

## 6. §7 re-derivation — what changes

The step-5 §7 "9.0 GB co-resident → Orin NX 16 GB does not fit" is arithmetic
over `{qwen2.5:3b, qwen3:4b, qwen3-vl:4b}`. The likely winning set is:

| Role | Likely winner | ~Resident (to measure) |
|---|---|---|
| fast + planner (unified, non-reasoning) | `qwen3:4b-instruct-2507` q4 | ~3.2 GB (one model, not two) |
| VLM | `qwen3-vl:2b-instruct` or `4b-instruct` q4 | ~2.2 / ~3.6 GB |
| ASR + TTS + VAD | faster-whisper base.en + Kokoro + Silero | ~1.3 GB (unchanged) |

If fast+planner unify, the co-resident LLM/VLM figure drops from **9.0 GB to
~5.4–6.8 GB**, which **changes the Orin NX 16 GB verdict** — it may fit with
headroom. That is the single most important number this step produces and the
purchase hangs on it, so it gets re-measured with `ollama ps`, cold and warm,
not estimated. Deliverable 5 writes the new §7 and says explicitly that it
supersedes step-5 §7.

---

## 7. Deliverable-by-deliverable run plan

### D1 — bench harness extension
`engine/inference/bench.py` today benches **backends** for a modality
(`registry.backends_for`), one composite `llm` row via `WELLSY_LLM_MODEL`. It
cannot bench a candidate *set*. Plan:

- New module `engine/inference/llm_bench.py` (keep `bench.py` for the
  modality/backend regression table). Slot→candidate config as a dict literal at
  the top, editable, each entry `{slot, tag, note}`.
- Drive each candidate directly over `POST /v1/chat/completions` (stream) via
  `httpx` — lets us read `choices[].delta.reasoning` / `message.thinking`, count
  content tokens vs thinking tokens, and stamp TTFT precisely.
- Per candidate, per run: TTFT, tok/s (content, after first), **thinking-token
  count this turn** (the metric that caught `qwen3:4b` — belongs in the
  harness), full-turn wall. Query `ollama ps` once warm for resident MB, and
  time the cold `/api/generate` load for cold-load s.
- `n ≥ 20`, cold run and warm runs recorded separately, p50 + p95, method string
  written into each row. Emit a comparison table + JSONL under `spec/results/`.
- Wire as `wellsy bench --modality llm` running the candidate set (acceptance 1);
  keep `--slot planner|vlm|fast` to run one.
- Closes step 5 debt #4.

### D2 — planner campaign
- Pull P1, P2 (and P4 for the effort-dial data point) — **owner approval list in
  §8**.
- Curl-probe each: does `think:"low"`/`"medium"`/`"high"` change the thinking-
  token count monotonically? Record the raw counts. That is the "bounded by a
  parameter the server honours" check.
- Run each through the **real graph** (`engine/agent/graph.py`) on a ≥ 3-step
  plan fixture (A9 shape) — structured-output reliability under the plan schema,
  not just TTFT. Record plan validity rate over the 20 trials.
- Verdict: which candidate clears ~3–4 s to first token *and* emits a schema-
  valid ≥ 3-step plan. If none with thinking on/bounded → report "planner ships
  non-reasoning (P1) + stronger plan prompt", with P4's bounded-think numbers
  alongside as the counterfactual.

### D3 — VLM campaign
- Pull V1, V2 (V4 optional ceiling) — §8.
- Feed real captures through `engine/voice/vision.py` → `IntentGate` at the
  resolution sweep (native/1024/768/512). Record vision-token count + TTFT +
  legibility (owner or a text-diff on a known screenshot) at each.
- State plainly: does the §1 VLM row pass, at what resolution, and does that
  resolution keep screen text legible. Produces the ≥ 20-trial VLM TTFT campaign
  step 5 owes (debt #2).

### D4 — fast campaign + TTS bench-off
- Fast: F1..F4 through `llm_bench.py`, losers recorded (debt #3).
- TTS: Kokoro vs Orpheus on the portable path — latency (`wellsy bench
  --modality tts` style, first-PCM-sample timestamp) + an owner A/B on a fixed
  script with emotional range. Qwen3-TTS CUDA-only reference clip if a CUDA box
  is available. Record the A/B as the stated judging method.

### D5 — re-derive §7
- `ollama ps` resident MB for every winning role, cold + warm.
- Co-resident total for the winning set; desktop residency strategy; Orin NX
  16 GB verdict recomputed. Write it into `step5b-results.md` and say it
  supersedes step-5 §7.

### Acceptance close-out
- Every §1 row involving a model re-measured against winners — pass or
  documented miss, no blank cells.
- `step5b-results.md` records winners **and** losers with numbers + the new §7.
- Full suite green, tree clean.

---

## 8. What needs the owner

1. **Weights to pull** (approve per model — owner asked for per-model sign-off):

   | Priority | Tag | ~Size | For |
   |---|---|---|---|
   | 1 | `qwen3:4b-instruct-2507` (q4_K_M) | ~2.5 GB | planner P1 + fast F2 (one model, two slots) |
   | 1 | `qwen3-vl:4b-instruct` (q4_K_M) | ~3.3 GB | VLM V1 |
   | 2 | `qwen3-vl:2b-instruct` (q4_K_M) | ~1.9 GB | VLM V2 (Orin-friendly) |
   | 2 | `qwen3:4b-thinking-2507` (q4_K_M) | ~2.5 GB | planner P2 (bounded-think test) |
   | 3 | `granite4:3b` (or `micro`) | ~2 GB | planner P5 / fast F4 |
   | 3 | `gpt-oss:20b` | ~14 GB | planner P4 (effort-dial reference; expect Orin-reject) |
   | 3 | `qwen3-vl:8b-instruct` (q4_K_M) | ~6.1 GB | VLM ceiling reference |

   Already local, no pull: `qwen2.5:3b`, `qwen2.5vl:3b`, `qwen3:4b`,
   `qwen3-vl:4b`, `qwen3-vl:8b`, `qwen3:4b-nothink`.

2. **TTS A/B listen** (D4) — a fixed script with emotional range, Kokoro vs
   Orpheus (vs Qwen3-TTS reference). Owner picks; the pick is the recorded
   judging method.

3. **Ratify the portability call on Qwen3-TTS** — it fails INVARIANTS #14 as
   shipped (CUDA-only). Proposed: it is *not* a candidate for this step's
   cross-platform default, but gets a CUDA-side reference measurement and is the
   headline act for the later "emotional TTS" day. Confirm that's acceptable.

4. **Decide P4 scope** — is `gpt-oss:20b` worth the 14 GB pull just to document
   "a real effort dial exists but not at Orin size", or skip and assert it from
   the model card?

---

## 9. Risks / open questions

- **`think:"low"` on hybrid `qwen3:4b` may not bound anything** — Ollama's
  generic template might ignore the effort level even though the API accepts it.
  D2's curl probe settles it; don't pre-assume either way.
- **Unifying fast+planner on `qwen3:4b-instruct-2507`** assumes its TTFT stays
  < 1 s under the 24-tool catalog + plan prompt. `qwen2.5:3b` does 0.19 s; a 4B
  model may be 2–3× that. Measure before designing §7 around the unification.
- **Qwen3-VL instruct legibility at 512px** — the resolution that clears latency
  may be the one that loses small screen text. If 4b-instruct needs ≥ 768px to
  read a UI, the §1 VLM row may still miss on Orin.
- **Orpheus RTF on CPU** — 3B backbone; if RTF > ~0.5 on the Linux/CPU fallback
  it breaks the same budget that killed Qwen3-ASR 0.6B. Measure RTF before
  adoption (step 4 "Do not" rule).
- Linux/CUDA path is still **unexecuted** (model-inventory §Linux). All numbers
  this step produces will be macOS-arm64 unless a CUDA box appears; the Orin
  verdict is therefore a projection from M4 Pro residency + known Jetson
  overheads, and must say so.
