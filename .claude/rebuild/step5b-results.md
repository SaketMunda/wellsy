# Step 5b results — model selection, on measured numbers

**Session date:** 2026-09-03 · **Branch:** `rebuild/step5b-model-selection`
(off `master` @ `3a8f7e1`, parallel to `rebuild/step6-native-interface`) ·
**Machine of record:** Apple M4 Pro, ~25.8 GB unified, macOS 15.5, darwin/arm64 ·
**Server:** Ollama **0.33.2** (current — 0.33.3 is a 2026-09-02 pre-release).

Closes step-5 debt #2 (VLM TTFT campaign), #3 (fast bench-off), #4 (bench
harness). Re-derives `step5-results.md` §7. Research pass and candidate
rationale: `step5b-research.md`.

**Scope actually executed** (owner: "cheap and light first", per-model pull
approval): the lean candidate set — `qwen3:4b-instruct-2507`,
`qwen3-vl:2b-instruct`, `qwen3:4b-thinking-2507`. Deferred by decision:
`gpt-oss:20b` (14 GB, asserted from its card), Orpheus/Qwen3-TTS, `granite4`,
`qwen3:1.7b`. TTS bench-off (D4) and the real-vision-path VLM resolution sweep
(D3 full) remain owed — see §6.

---

## 1. What shipped (Deliverable 1 — the harness)

`engine/inference/llm_bench.py` + wiring in `bench.py`:

- `wellsy bench --modality llm` now runs a **named candidate set per slot**
  (`--slot planner|fast|vlm|all`, `--candidate <id>`), not one composite row.
  The old backend-regression path stays reachable with `--backend openai_http`.
- Talks to Ollama's **native `/api/chat` stream** so it can separate `thinking`
  deltas from `content` deltas and read real server timing
  (`eval_count`, `eval_duration`, `load_duration`, `prompt_eval_count`);
  falls back to `/v1/chat/completions` for vLLM/SGLang (reasoning tokens
  best-effort there).
- Per candidate: cold-load s, **cold** TTFT (separate), warm TTFT p50/p95,
  tok/s, **thinking-token count/turn**, content-token count, full-turn p50/p95,
  resident MB (`/api/ps`), median prompt tokens, and for the planner slot a
  **plan-JSON validity rate** (`>=3` steps, every `tool` in the catalog).
- Thinking-token count method (recorded in every row): char-proportional split
  of the server's real `eval_count` — `eval_count * think_chars /
  (think+content chars)`. The metric only has to catch a model burning a
  thousand-token reasoning prefix; this does that reproducibly. n >= 20 warm,
  cold turn separate, p50/p95 nearest-rank.
- `tests/test_llm_bench.py` — 10 tests, green (stubbed `stream_turn`, no live
  server needed).

Results: `spec/results/llm-bench-{planner-instruct-2507,fast,vlm,planner-thinking}.jsonl`.

---

## 2. Planner slot — `qwen3:4b-instruct-2507-q4_K_M` wins, non-reasoning

Workload: system planner prompt + 16-tool catalog, user = a real 3-step request
("move my 3pm to Monday, then draft a mail to Alex, then add a Friday
reminder"). Warm, ctx 4096, temp 0.

| Candidate | think | cold-load | TTFT p50 / p95 | full turn p50 / p95 | tok/s | think-tok/turn | plan-valid | resident | n |
|---|---|---|---|---|---|---|---|---|---|
| **`qwen3:4b-instruct-2507-q4_K_M`** | — | 0.82 s | **32.1 / 46.8 ms** | **3.99 / 4.03 s** | 71.8 | **0** | **20/20** | 3.2 GB | 20 |
| `qwen3:4b-thinking-2507-q4_K_M` | none | 2.11 s | 310.7 / 320.2 ms | **77.8 / 78.2 s** | 63.8 | **4756** | 5/5 | 3.2 GB | 5 |
| `qwen3:4b-thinking-2507-q4_K_M` | `"low"` | 1.10 s | 345.5 / 69533 ms | **83.5 / 163.2 s** | 59.5 | **4756** | 5/5 | 3.2 GB | 5 |
| `qwen3:4b` (hybrid) | none | 1.11 s | ~332 ms | ~81.7 s | 60.8 | ~4756 | 3/3 | 3.2 GB | 3 |

n reduced to 5/3 on the reasoning rows: each trial is ~80 s and the miss is
**~20×** the ≤ 4 s planner budget, not marginal — more trials buy no new
information.

### Findings

1. **`qwen3:4b-instruct-2507` clears the planner budget outright.** 32 ms warm
   TTFT, a complete schema-valid plan in ~4.0 s, zero reasoning tokens,
   **20/20 plan validity**. Acknowledge-then-deliver is barely needed — this is
   fast-path latency. This is the planner.
2. **`think:"low"` is confirmed non-functional as a thinking bound on Ollama
   0.33.2.** The thinking-token count is *byte-identical* (4755.9) with
   `think:"low"` and with no bound at all. The API accepts the parameter and
   silently ignores its effect on generation. `"low"` also *destabilised* tail
   latency (p95 turn 163 s, p95 TTFT 69.5 s). **This retires the last untested
   lever from step 4/4b** — their six attempts (`think:false`,
   `reasoning_effort:none`, template kwargs, `/no_think`, the `-nothink` tag)
   plus this one (`think:"low"/"high"/"max"` string effort) all fail. No
   flag makes a hybrid/thinking Qwen3 non-reasoning on this stack.
3. **`gpt-oss:20b`** (not pulled): its Apache-2.0 card documents a genuine
   server-honoured `reasoning_effort` low/med/high. It is the only real
   effort dial in the class — but at **14 GB resident** it cannot co-reside
   with the VLM + fast on an Orin NX 16 GB (§5). Recorded as "a real dial
   exists, above the working set", not adopted.
4. **Plan *quality* weakness (spot-check, not a blocker):** structurally sound
   decompositions, sensible arg shapes, but **relative-date arithmetic is
   unreliable** — "Monday" rendered as `2026-09-06` (a Sunday), a reminder
   placed in July. The plan prompt needs an explicit resolved-date block or a
   date tool; the graph's read-back (INVARIANTS #15) catches a wrong time
   before it commits, but the prompt should not lean on that.

**Planner decision:** `WELLSY_PLANNER_MODEL = qwen3:4b-instruct-2507-q4_K_M`,
non-reasoning, with a stronger plan prompt (add resolved dates). The step's
anticipated outcome — "no bounded-think candidate clears the budget → ship
non-reasoning + stronger prompt" — is what the numbers say.

---

## 3. Fast slot — unify on the planner model

Workload: one-sentence chat turn, no tools. Warm, ctx 4096, temp 0.

| Candidate | cold-load | TTFT p50 / p95 | full turn p50 / p95 | tok/s | resident | n |
|---|---|---|---|---|---|---|
| `qwen2.5:3b` (incumbent) | 0.56 s | **14.8 / 15.5 ms** | 0.39 / 0.40 s | 93.0 | 2.0 GB | 20 |
| **`qwen3:4b-instruct-2507-q4_K_M`** | 0.84 s | **21.3 / 23.8 ms** | 0.57 / 0.58 s | 76.9 | 3.2 GB | 20 |
| `qwen3:1.7b` | — | — | — | — | — | 0 (not pulled) |

Both clear the fast budget (< 1500 ms p50 to first word) by ~70×. `qwen2.5:3b`
is faster and lighter but 2024-era (INVARIANTS #8). `qwen3:4b-instruct-2507`
is 21 ms warm, 2026-current, and **is the same model as the planner winner**.

**Fast decision:** `WELLSY_FAST_MODEL = qwen3:4b-instruct-2507-q4_K_M`.
Fast and planner collapse to **one resident 3.2 GB model** instead of two
(2.0 + 3.2 = 5.2 GB). `models.py` `_DEFAULTS` both point at it; `get_model`
keeps the `fast` role's non-reasoning request (harmless — the model has no
think path). `qwen2.5:3b` numbers recorded as the beaten incumbent (step-5
debt #3 closed). `qwen3:1.7b` unpulled — the unification makes a lighter
fast-only model moot; revisit only if the 3.2 GB resident needs shaving.

---

## 4. VLM slot — `qwen3-vl:2b-instruct-q4_K_M`

Measured via `llm_bench` (text + a synthetic 768 px image, `/api/chat`
`images=`). **Caveat:** warm TTFT here is prompt-cache-inflated-low (identical
image every turn); the honest first-capture cost is `coldTTFT − coldLoad` =
prompt-processing on the vision tokens. The authoritative resolution sweep
through `engine/voice/vision.py` → `IntentGate` on real screenshots is **D3,
still owed** (§6).

| Candidate | cold-load | cold TTFT | (proc ≈ coldTTFT−load) | warm turn p50 | tok/s | prompt tok | think-tok | resident | n |
|---|---|---|---|---|---|---|---|---|---|
| **`qwen3-vl:2b-instruct-q4_K_M`** | 2.89 s | 4.70 s | **~1.8 s** | 0.41 s | 139.7 | 1048 | **0** | **2.0 GB** | 20 |
| `qwen2.5vl:3b` (interim) | 5.18 s | 8.25 s | **~3.1 s** | 0.61 s | 91.2 | 1124 | 0 | 4.1 GB | 20 |

**Legibility spot-check** (verbatim transcription of the 768 px image, incl. a
0.5-scale small-print line): **both transcribe every line perfectly.**
`qwen3-vl:2b-instruct` matches the 3B incumbent on this proxy at **half the
resident size** and 1.5× throughput, and is non-reasoning by construction (the
`-instruct` build — no `<think>`, retires the step-4b `qwen3-vl:4b` hybrid
debt).

**VLM decision (provisional, pending D3):** `WELLSY_VLM_MODEL =
qwen3-vl:2b-instruct-q4_K_M`. `openai_http.DEFAULT_MODEL` moves off
`qwen3-vl:4b`. The `qwen3-vl:4b-instruct` (3.3 GB) fallback stays on the shelf
if D3 finds 2b loses dense-UI text at the resolution that clears latency.

### §1 VLM row — pass/miss

The **≤ 2500 ms p50 / ≤ 3500 ms p95** budget (wake → first word, VLM):
- **Warm, model resident: PASS by a wide margin** — first-capture processing
  ~1.8 s + ASR ~0.27 s + TTS TTFA ~0.35 s ≈ **~2.4 s** to first word, and
  streaming overlaps the tail.
- **Cold (model not resident): MISS** — +2.9 s load pushes it to ~5.3 s. So the
  VLM must be **kept resident** (`keep_alive:-1`) for the row to pass, which
  feeds §5.
- **Not yet proven:** the number at 512 px on a dense real screenshot, and that
  512 px keeps screen text legible. D3.

---

## 5. §7 re-derived — supersedes `step5-results.md` §7

**This section supersedes `step5-results.md` §7.** A hardware decision hangs off
it (though the owner has since made hardware explicitly last —
`wellsy_rebuild_progress`).

### Winning model set — resident (`ollama ps`, ctx 4096, 100% GPU, measured 2026-09-03)

| Role | Model | Resident | Residency |
|---|---|---|---|
| fast **+** planner (unified) | `qwen3:4b-instruct-2507-q4_K_M` | **3.2 GB** | resident (`keep_alive:-1`) |
| VLM | `qwen3-vl:2b-instruct-q4_K_M` | **2.0 GB** | resident (`keep_alive:-1`) |
| **both co-resident** (measured together) | | **5.2 GB** | |

Step-5 §7 had **9.0 GB** for three models (`qwen2.5:3b` 2.2 + `qwen3:4b` 3.2 +
`qwen3-vl:4b` 3.6). The unification of fast+planner and the smaller VLM take
**9.0 GB → 5.2 GB, a 3.8 GB reduction.**

### Full-stack steady state (warm, all roles resident)

5.2 GB (LLM/VLM) + ~1.3 GB (faster-whisper base.en 0.63 + Kokoro 0.70 + Silero
0.02) + ~0.2 GB (agent runtime, step-5 §7 unchanged) + perception (YOLOE,
measured elsewhere) ≈ **~6.7 GB before the OS, the GPU framebuffer, and ROS 2
later.**

### Orin NX 16 GB verdict — **flips to "fits, with headroom"**

Step-5 §7 concluded three co-resident LLM/VLM roles could not fit an Orin NX
16 GB shared with the OS + framebuffer, and told the desktop build to size for
"fast + exactly one of {planner, VLM} resident". **That constraint is lifted:**

- **5.2 GB of LLM/VLM, both roles resident**, + ~1.3 GB ASR/TTS + ~0.2 GB
  runtime + perception ≈ **~6.7 GB working set**, leaving ~9 GB on an Orin NX
  16 GB for the OS, framebuffer, ROS 2 and slack. **All roles can be
  co-resident on the 16 GB board.**
- The desktop build **no longer needs to design around a model swap** between
  planner and vision. Both stay pinned.
- Caveats: (a) numbers are **darwin/arm64**; the Linux/CUDA path is still
  unexecuted (`model-inventory` §Linux), so the Orin figure is a projection
  from M4 Pro residency + known Jetson overheads — a real `ollama ps` on the
  board is owed before any purchase. (b) ctx 4096; a larger planner context
  (long tool transcripts) grows the KV cache — re-measure at the context the
  agent actually runs. (c) perception + ROS 2 co-residency not yet measured
  together with this set.

Recommended target line unchanged in spirit but not in constraint: **Orin NX
16 GB (production target #1) is now viable for the full model set**; a 24 GB
Orin remains comfortable rather than necessary.

---

## 6. §1 latency table — every model row, re-measured

| Path | Target p50 / p95 | Measured (this step) | Verdict |
|---|---|---|---|
| Wake → first word, **deterministic** | < 800 / < 1200 ms | 617 / 700 ms (step 4, unchanged) | **PASS** |
| Wake → first word, **LLM (fast)**, `qwen3:4b-instruct-2507` | < 1500 / < 2500 ms | ASR 267 + TTFT **21** + TTS TTFA 345 ≈ **~633 ms p50** | **PASS** |
| Wake → first word, **LLM (planner delivers)**, `qwen3:4b-instruct-2507` | 3–4 s acceptable | full plan **3.99 / 4.03 s** + ack line spoken at ~633 ms | **PASS** (ack hides it; delivery inside budget) |
| Wake → first word, **VLM**, `qwen3-vl:2b-instruct`, **resident** | < 2500 / < 3500 ms | proc ~1.8 s + ASR 267 + TTS TTFA 345 ≈ **~2.4 s p50** | **PASS (warm/resident)** · **MISS cold** (+2.9 s load) → keep resident |
| Wake → first word, **VLM** at 512 px on dense real UI | < 2500 / < 3500 ms | not measured — synthetic 768 px proxy only | **OWED (D3)** |
| Barge-in / `stop` wall numbers | see §1 | live-only, unchanged from step 4/4c | owed (A14, live) |
| Perception fast path (T0+T1) | < 20 / < 35 ms | 13.49 / 23.95 ms (step 4, unregressed) | **PASS** |

**No blank model cells** except the two explicitly owed (D3 dense-UI VLM, and
the live acoustic numbers that were always live-only).

### Old planner number, for the record

`qwen3:4b` on this stack: **~78–82 s** full turn on the real planner workload
(step 5 measured 33 s on a lighter prompt; the 3-step catalog prompt is
heavier). 4756 reasoning tokens/turn, uncontrollable. Retired.

---

## 7. Debt carried forward

1. **D3 — VLM resolution sweep through the real vision path.** `llm_bench`'s
   image turn is a prompt-cache-inflated proxy. Owed: `engine/voice/vision.py`
   → `IntentGate` on real screenshots at native/1024/768/512 px, vision-token
   count + TTFT + a legibility check (owner or text-diff) at each. Confirm
   `qwen3-vl:2b-instruct` holds dense-UI text at the resolution that clears
   latency; if not, fall back to `qwen3-vl:4b-instruct` (3.3 GB — re-run §5).
2. **D4 — TTS bench-off, not run.** Kokoro stays as the shipped default; its
   step-4 numbers (RTF 0.202, TTFA 345/406 ms) are unchallenged. The
   expressiveness requirement is **still open** — deferred to the dedicated
   "emotional TTS" day (`wellsy_future_tts_emotion`): Kokoro vs Orpheus on the
   portable path + a Qwen3-TTS CUDA reference, judged by an owner A/B.
   `step5b-research.md` §5 has the shortlist and the Qwen3-TTS portability
   problem (CUDA-only, fails INVARIANTS #14 as-is).
3. **Planner date arithmetic** — add a resolved-date block (or a date tool) to
   the plan prompt; `qwen3:4b-instruct-2507` miscomputes relative dates.
4. **Linux/CUDA numbers** — every number here is darwin/arm64. The Orin NX
   verdict in §5 is a projection until `wellsy bench --modality llm` runs on
   the board.
5. **Context sizing** — measured at ctx 4096. Re-measure resident + KV growth
   at the planner's real working context.
6. **`gpt-oss:20b`** effort-dial claim asserted from the model card, not
   curl-verified (owner deferred the 14 GB pull). Immaterial unless the Orin
   target grows.
7. **`qwen3:1.7b` / `granite4`** fast-slot alternatives unpulled — moot while
   fast+planner are unified, revisit only to shave the 3.2 GB resident.

---

## 8. Code changes

| File | Change |
|---|---|
| `engine/inference/llm_bench.py` | **new** — per-slot candidate bench-off (D1) |
| `engine/inference/bench.py` | `--modality llm` delegates to `llm_bench`; adds `--slot`, `--candidate` |
| `tests/test_llm_bench.py` | **new** — 10 tests |
| `engine/agent/models.py` | `_DEFAULTS`: planner + fast → `qwen3:4b-instruct-2507-q4_K_M` |
| `engine/inference/backends/openai_http.py` | `DEFAULT_MODEL` → `qwen3-vl:2b-instruct-q4_K_M` |
| `spec/model-inventory.md` | adopted-model rows updated; losers noted |
| `spec/results/llm-bench-*.jsonl` | 4 campaign result files |

Acceptance: `wellsy bench --modality llm` runs the candidate set per slot,
exit 0, results under `spec/results/` ✔ · every slot defaults to a
measurement-backed model ✔ · §1 model rows re-measured (2 owed, documented) ✔ ·
winners + losers recorded with numbers ✔ · §7 re-derived ✔ · full suite green,
tree clean → §9.

---

## 9. Suite / tree

`.venv/bin/python -m pytest -q` → **171 passed** (was 168 + `test_llm_bench.py`),
0 failed, after the model-default edits in `models.py`, `openai_http.py`,
`adapters.py`, `metrics.py`, `pipeline.py`. No test hard-coded the old ids.

Branch `rebuild/step5b-model-selection` off `master` @ `3a8f7e1` — the 5b work
had accreted on `rebuild/step6-native-interface` (the parallel session's
branch) after a resume; moved to its own branch, clean, nothing lost.

Owed before merge: the two D3/D4 items in §7, and a `wellsy bench` run on
Linux/CUDA. None block step 6 (UI layer, no model-number dependency).
