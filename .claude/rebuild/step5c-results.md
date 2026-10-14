# Step 5c results — the 2026 model set, measured the 5b way

**Session date:** 2026-10-14 · **Branch:** `rebuild/step5c-model-rebaseline`
(off `master` @ `fb0b027`) · **Machine of record:** Apple M4 Pro, ~25.8 GB
unified, macOS 15.5, darwin/arm64, two 1920×1080 displays ·
**Server:** Ollama **0.40.3** (5b ran on 0.33.2; 0.40.4 is out, dated 12 Oct) ·
ultralytics 8.4.137 · LangGraph 1.2.11 / langgraph-prebuilt 1.1.0.

**Supersedes `step5b-results.md` §2–§5.** The method is unchanged: n ≥ 20 warm,
cold turn separate, p50/p95 nearest-rank, method string beside every number,
plan-JSON validity for the planner. Every result file is under `spec/results/`
and named below.

---

## 0. Verdicts

| Question | Answer | Section |
|---|---|---|
| Is Qwen3.5 small "reasoning off by default"? | **No.** Its own card says thinking is on by default; measured **4066 / 3922 thinking tokens per turn** and **0/5 valid plans** with no flag. | §1, §2 |
| Can Qwen3.5's reasoning be turned off? | **Yes, on Ollama 0.40.3, but only on some paths:** native `think:false` → 0 tokens; `/v1` honours **only** `reasoning_effort:"none"`. The `think:false` + `chat_template_kwargs` that WELLSY sends today are **ignored** on `/v1`. | §1.3 |
| Planner / fast slot | Qwen3.5-4B (`think` off) matches or beats the incumbent on every budget. **Not switched in this step**: a model-string-only swap measurably breaks the voice loop and both agent roles. The swap and its request-shape change go to step 9 together. | §2 |
| One model for planner + fast + vision? | **Yes, it measures as viable.** Qwen3.5-4B ties `qwen3-vl:2b` on dense-UI latency and legibility at 1024 px, and wins 8/10 vs 7/10 on grounded answers, for **−2.1 GB resident** (RSS). Recommended for step 9; `SeamLLMService`'s switch becomes dead weight. | §3 |
| 5b's owed D3 (512 px dense UI) | **Closed: 512 px is the wrong answer.** It reads 0–3 of 18 strings; 1024 px stays. And 5b's "~1.8 s first-capture" was cache-inflated: the honest new-screen cost is **~2.0–2.1 s**. | §3 |
| YOLOE-26 | **Adopted** (`yoloe-26s-seg.pt`): equal or better on live latency, cold start, phone recall and false positives. Still over the < 20 ms live p50 budget, like YOLOE-11, and the cause is **the 8 Hz GPU idle gap, not the model**. | §4 |
| D30's "unfixable" glasses / phone misses | **They were the T0 gate.** With the gate held open, both detectors see glasses on ~100 % and the phone on ~95–100 % of ticks. | §4.4 |
| Three-arm test (amended): crop → typed question | Local crop→VLM scores **30/30, 0 FP** (P(yes) ≥ 0.93 vs ≤ 0.11) vs YOLOE-26 29/30, at **~2 s per question**: on-demand path only. Hosted arm **deferred to step 8 by the owner**; no pixels left the machine. | §4.6 |
| Orin NX 16 GB | **Fits, re-derived:** ~8.3 GB working set as shipped, ~7.1 GB with the collapse model at 32K context. darwin-only caveats unchanged. | §5 |
| Context for step 7 | Usable context is set by **prefill time and edit discipline, not by the 262K window.** Recommendation in §6. | §6 |

---

## 1. Deliverable 1 — every claim, at its source

### 1.1 The prompt's table, resolved

| Claim (from aggregator search) | Source checked | Result |
|---|---|---|
| Qwen3.5 0.8/2/4/9B have **reasoning off by default** | `huggingface.co/Qwen/Qwen3.5-4B` card; `ollama show` | **REJECTED.** Card: *"Qwen3.5 models operate in thinking mode by default."* `ollama show`: thinking levels `false, true`, **default `true`**. Measured with no flag: 4066 thinking tokens on a one-sentence turn, **empty content** (the 4096 window ran out mid-thought). |
| Natively multimodal at every size | card + Ollama registry | **VERIFIED.** "Causal Language Model with Vision Encoder", early-fusion; one checkpoint. Ollama lists `Text, Image` on every tag; the 4B carries a 333.5M-parameter CLIP projector in the same pull. |
| `qwen3.5:4b` ≈ 3.4 GB, 262K native | registry + card + pull | **VERIFIED, with a correction.** The bare `4b` tag resolves per platform (3.3–4.0 GB). Pinned the GGUF tag **`qwen3.5:4b-q4_K_M`**: 3.3 GB on disk, digest `d8b0f5e9760c`, 4.2B params, context **262,144** (YaRN to ~1.01M). Apache-2.0. Release: Feb 2026 (card citation); Ollama tag refreshed "1 week ago". |
| Tool calling ≈ 97.5 % at 4B, beating 5× larger models | card | **REJECTED as stated.** The card publishes no such figure. It lists **BFCL-V4 50.3**, TAU2-Bench 79.9 for the 4B. Our own planner measurement (20/20 valid 3-step plans, §2) is the number that counts. |
| YOLOE-26, `ultralytics>=8.4.0`, `yoloe-26s` 30.8 vs 27.5 LVIS | `docs.ultralytics.com/models/yoloe/` | **VERIFIED.** Weights `yoloe-26{n,s,m,l,x}-seg.pt`, NMS-free end-to-end head (trails the Non-E2E figure by ≤ 1.1 AP text-prompt), LVIS minival text-prompt 30.8 (26s) vs 27.5 (11s). **New, not in the prompt:** a different text encoder, `mobileclip2_b.ts` (~254 MB, vs `mobileclip_blt.ts` ~570 MB). Licence: the docs page states none; the installed `ultralytics` 8.4.137 package metadata says **AGPL-3.0**, as for YOLOE-11. |
| Gemma 4 E2B/E4B; `gemma4:e4b` 9.6 GB likely disqualifies it | `ollama show`, registry, measured | **Size claim wrong in both directions.** 8.0B params, Q4_K_M, 128K ctx, text+image+audio, thinking default `true`, Apache-2.0. `ollama ps` reported **3.2 GB on one load and 9.0 GB on the next** (same ctx 4096, same runner). Runner RSS was **4.6–4.7 GB both times**. Not disqualified on size; **rejected on measurement** (§2: 0/20 valid plans, slowest planner). |
| Granite 3.3 2B, "strongest sub-7B on OCRBench" | `huggingface.co/ibm-granite/granite-vision-3.3-2b` | **REJECTED, not pulled.** Released **2025-06-11**; the card makes no "strongest sub-7B" claim (OCRBench 0.79); it points to a successor, `granite-vision-4.1-4b`, which exists on Ollama **only as community uploads**. Not in the official library: INVARIANTS #8 fail. Also not needed (§3: Qwen3.5 holds dense UI). |

### 1.2 Also surfaced, and rejected

- **`qwen3.6`, `qwen3.8`** (both in Ollama's 0.40.0 notes): **27B and up only**
  (18–24 GB at q4). Above the Orin working set; not candidates.
- **Ollama 0.40.0 runs Qwen3.5, Gemma 4 and Qwen3.6 on MLX by default on Apple
  Silicon.** INVARIANTS #14 bans Apple-only Ollama backends from the core, so
  every 5c row records the runner. **All measured models ran on `llamacpp`**
  (the portable GGUF path) because the `-q4_K_M` GGUF tags were pinned; the
  `-mlx` / `-nvfp4` / `-mxfp8` tags are the MLX ones. No documented opt-out
  env var exists (`ollama serve --help`, 0.40.3); pinning GGUF tags is the
  control. **A bare `qwen3.5:4b` pull on a Mac may resolve to an MLX build.**
  Never use a bare tag in this repo.

### 1.3 The server moved: Ollama 0.33.2 → 0.40.3, and 5b's finding re-dated

| 5b finding (0.33.2) | Re-measured on 0.40.3 | Status |
|---|---|---|
| `think:"low"` inert on `qwen3:4b-thinking-2507` | **4755.9 thinking tokens/turn, byte-identical again** (n=3; content first token at 94.2 s) | **Still true** |
| No flag makes hybrid `qwen3:4b` non-reasoning | `think:false` now empties the `thinking` field (counter reads **0**), but the reasoning **moves into `content`**: 4947 content tokens/turn, "Okay, let's tackle this problem step by step…", **0/5 valid plans**, 97.5 s (n=5) | **Still true.** The flag changes the channel, not the behaviour |
| — | Qwen3.5 native `/api/chat` `think:false`: **0 thinking tokens, answer-only content** (34-token sentence; 20/20 valid plans) | **New: a real off-switch exists for Qwen3.5** |
| — | Qwen3.5 **`/v1/chat/completions`** with WELLSY's current `extra_body` (`think:false`, `chat_template_kwargs.enable_thinking:false`): **1099 reasoning chars, no content in 300 tokens.** Identical to sending nothing (1077). **`reasoning_effort:"none"`: 0 reasoning, first word 160 ms.** | **New: on `/v1` only `reasoning_effort` works** |
| — | `qwen3:4b-instruct-2507` and `qwen3-vl:2b-instruct` accept `reasoning_effort:"none"` harmlessly (200, normal answers) | one request shape can serve all three |

**Instrument caveat, new.** `llm_bench`'s thinking-token counter reads the
server's `thinking` channel. On 0.40.3 a hybrid model with `think:false` reads
**0** while it reasons in `content`. A zero now needs the content checked
beside it (token count, plan validity). Every zero in §2 has that check.

`ollama ps` is **not a reliable memory figure** on 0.40.3: it matched runner
RSS for Qwen3 (3.0 vs 3.1 GB), under-reported `qwen3-vl:2b` (1.9 vs 2.8 GB)
and swung 3.2 ↔ 9.0 GB on Gemma 4 between two loads at the same context. 5c
reports both.

---

## 2. Deliverable 2 — planner and fast slots

`wellsy bench --modality llm --num-ctx 4096` (harness: `engine/inference/llm_bench.py`;
5c added `contentTtft`, `runner`, `--num-ctx`, `--think`). Same workloads as
5b, same 16-tool catalog, temperature 0. The incumbent was **re-measured on
0.40.3** so every row shares a server. Files:
`spec/results/llm-bench-5c-{planner,fast}-*.jsonl`.

### Planner (≤ 4 s to a schema-valid plan)

| Candidate | think | cold load | TTFT p50/p95 | full plan p50/p95 | tok/s | think tok | plan-valid | `ps` | runner | n |
|---|---|---|---|---|---|---|---|---|---|---|
| `qwen3:4b-instruct-2507-q4_K_M` (incumbent) | — | 1.31 s | 31.1 / 32.6 ms | **3.91 / 3.97 s** | 73.4 | 0 | **20/20** | 3028 MB | llamacpp | 20 |
| **`qwen3.5:4b-q4_K_M`** | `false` | 1.07 s | 67.9 / 70.2 ms | **3.47 / 3.47 s** | 59.7 | **0** | **20/20** | 3034 MB | llamacpp | 20 |
| `qwen3.5:4b-q4_K_M` | default | 1.07 s | 84.9 / 138.3 ms¹ | **80.0 / 81.2 s** | 49.1 | **3922** | **0/5** | 3034 MB | llamacpp | 5 |
| `gemma4:e4b` | `false` | 6.01 s | 91.5 / 94.7 ms | 4.76 / 4.91 s | 53.8 | 0 | **0/20** | 9041 MB² | llamacpp | 20 |
| `qwen3:4b` (hybrid), re-date | `false` | 1.82 s | 405 / 459 ms | 97.5 / 97.9 s | 51.0 | 0³ | 0/5 | 3028 MB | llamacpp | 5 |
| `qwen3:4b-thinking-2507`, re-date | `"low"` | 0.81 s | 410 / 464 ms¹ | 98.8 / 98.9 s | 50.3 | **4756** | 3/3 | 3028 MB | llamacpp | 3 |

¹ first *thinking* token; first content never arrived (Qwen3.5 default) or
arrived at 94.2 s (thinking-2507). ² runner RSS 4.6 GB, see §1.3. ³ reasoning
emitted as content (4947 tok); see §1.3. Reasoning rows at n=5/3 as in 5b:
each trial is ~80–100 s and the miss is ~20×, so more trials add nothing.

**Gemma 4 E4B's 0/20 is a real failure, not a harness artefact.** At
temperature 0 it drops the outer closing brace on every plan (`…}}]` with no
final `}`), so the JSON never parses. Its decomposition and arguments are
otherwise sensible. Rejected: invalid output, slowest plan, largest and
least stable footprint.

### Fast (< 1500 ms p50 to first word)

| Candidate | think | cold load | first-content p50/p95 | full turn p50/p95 | tok/s | think tok | `ps` | n |
|---|---|---|---|---|---|---|---|---|
| `qwen3:4b-instruct-2507-q4_K_M` (incumbent) | — | 3.82 s | **24.2 / 26.7 ms** | 0.65 / 0.75 s | 67.0 | 0 | 3028 MB | 20 |
| **`qwen3.5:4b-q4_K_M`** | `false` | 2.20 s | **70.9 / 85.9 ms** | 0.67 / 0.74 s | 57.6 | **0** | 3034 MB | 20 |
| `qwen3.5:4b-q4_K_M` | default | 1.33 s | **never** (n=5) | 86.7 / 87.3 s | 47.0 | **4066** | 3034 MB | 5 |
| `gemma4:e4b` | `false` | 2.66 s | 84.7 / 87.0 ms | 0.68 / 0.69 s | 57.4 | 0 | 9041 MB² | 20 |

### Decision

**Qwen3.5-4B with reasoning off clears both budgets with margin.** The planner
plan is 0.44 s faster at p50 (3.47 vs 3.91 s; the incumbent's p95 of 3.97 s
sits 30 ms from the line). The fast slot is +47 ms to first word, which is
inside the budget by ~20×. Same resident size. On these two slots alone it
is a lateral move. **Its value is §3 (one model for all three slots) and §6
(cheaper long context).**

**The defaults are not changed in this step, deliberately:**

- The voice loop (`adapters.build_llm`) and the agent's `fast` role
  (`models.get_model`) send `think:false` + `chat_template_kwargs` over
  `/v1`, which Qwen3.5 **ignores** (§1.3). With a string-only swap, every
  voice answer becomes a silent ~80 s reasoning run with no spoken word.
- The agent's `planner` role sends **no** think flag on purpose ("planner
  keeps reasoning on"). That is exactly the row measured at **0/5 valid plans,
  80 s**.
- The fix is `reasoning_effort:"none"` in both request builders: a request-shape
  change, which this step's scope reserves for step 9 ("Code changes beyond a
  model identifier … belong to step 9"). Swapping the string without it ships a
  regression; swapping both belongs in one tested change.

So the incumbent stays the default, and the model inventory records Qwen3.5 as
**measured, recommended, blocked on step 9's request-shape change**.

---

## 3. Deliverable 3 — the collapse test, and 5b's D3 closed

### 3.1 Method (and two harness bugs found and fixed mid-step)

`bench/vlm_screen_sweep.py`. **Real dense UI:** one 1920×1080 capture of a
VS Code + Jupyter window (display 2 of 2, taken through `wellsy screen`, kept
local in `runs/step5c/screens/`; display 1 showed personal identifiers and was
not used). The image goes through **`engine.voice.vision._to_jpeg`** with
`MAX_EDGE_PX` set per row, so the model gets the exact JPEG bytes `IntentGate`
would append. The transport is native `/api/chat`, the only endpoint that
returns `prompt_eval_count` / `prompt_eval_duration`. Per cell: cold
(model unloaded) + 20 warm "What's on my screen right now?" turns
(`num_predict` 48), then **three** sampled full transcriptions scored
against 18 ground-truth strings read off the screenshot by eye: the 30 px
notebook heading down to the ~11 px status bar.

Two bugs in the first attempt, both fixed before the numbers below:

1. **Cache-busting failed.** Changing one source pixel was averaged away by the
   downscale and quantised away by JPEG q85, so most "new" images were
   byte-identical and server-cached (warm prefill 8 ms, p95 4.1 s). That is
   precisely the inflation 5b warned about. The fix: a 16×16 block perturbed
   *after* downscale. Every warm turn below is a genuinely new image.
2. **Temperature 0 is not what production sends.** `adapters.build_llm` sends
   no temperature, so the model defaults apply. Greedy decoding looped
   ("Update\n" × 1500). Production sampling is used below, so legibility is
   three reads, all reported.

### 3.2 Results — `spec/results/vlm-screen-sweep-5c.jsonl`

| Model | Edge | Sent | Prompt tok | Cold load / first word | **Warm first word p50/p95** | Image prefill p50/p95 | Legibility (3 reads, /18) |
|---|---|---|---|---|---|---|---|
| `qwen3-vl:2b-instruct` | native | 1920×1080 | 2064 | 1.07 / 5.92 s | 4884 / 4949 ms | 4777 / 4853 ms | 10, 13, 7 |
| `qwen3-vl:2b-instruct` | **1024** | 1024×576 | **1056** | 1.57 / 3.31 s | **2120 / 2197 ms** | 2086 / 2161 ms | **9, 6, 9** |
| `qwen3-vl:2b-instruct` | 768 | 768×432 | 1056 | 1.31 / 3.07 s | 2176 / 2228 ms | 2144 / 2202 ms | 0, 0, 0 |
| `qwen3-vl:2b-instruct` | 512 | 512×288 | 1056 | 1.57 / 3.34 s | 2188 / 2225 ms | 2152 / 2196 ms | 0, 3, 0 |
| `qwen3.5:4b` (`think:false`) | native | 1920×1080 | 2068 | 1.33 / 8.47 s | 7996 / 8177 ms | 7917 / 8099 ms | **15, 18, 11** |
| `qwen3.5:4b` (`think:false`) | **1024** | 1024×576 | **604** | 1.32 / 2.87 s | **2018 / 2197 ms** | 1991 / 2176 ms | **12, 9, 6** |
| `qwen3.5:4b` (`think:false`) | 768 | 768×432 | 364 | 1.58 / 2.56 s | 1371 / 1823 ms | 1330 / 1779 ms | 6, 3, 5 |
| `qwen3.5:4b` (`think:false`) | 512 | 512×288 | 172 | 1.85 / 2.40 s | 806 / 916 ms | 782 / 892 ms | 1, 1, 1 |

Warm thinking characters: **0** in every Qwen3.5 cell (measured, not assumed).

**Grounded answers at the shipped 1024 px**, 10 sampled answers each to the
real question (`num_predict` 90 = `VLM_MAX_TOKENS`); "grounded" = names an
editor **and** the notebook/chatbot/memory topic.
`spec/results/vlm-screen-answers-5c.json`:

| Model | Grounded | Typical miss |
|---|---|---|
| `qwen3-vl:2b-instruct` | **7/10** | calls the editor "Jupiter Notebook"; "a development environment with Python code" |
| `qwen3.5:4b` | **8/10** | "a computer coding IDE open" |

### 3.3 What it means

- **D3 closed: 512 px is wrong.** On `qwen3-vl` the server scales anything
  below 1024 up to the same 1056-token floor: **no time saved, the text
  destroyed** (0–3/18). On Qwen3.5 512 px is fast (806 ms) and blind (1/18).
  **`MAX_EDGE_PX = 1024` stays** (6c's value). Nothing to change.
- **5b's VLM number was cache-inflated.** "~1.8 s first-capture" came from
  re-sending one synthetic image. The honest cost of a new screen question
  with the model resident is **~2.0–2.1 s to first word at 1024 px**, for
  either model. That is one display; `wellsy run` sends both (6c), which
  roughly doubles the image prefill.
- **One model can serve all three slots.** At 1024 px Qwen3.5 matches
  `qwen3-vl:2b` on latency (2018 vs 2120 ms p50, same p95), on legibility
  (within sampling spread) and slightly on grounding (8/10 vs 7/10). It does
  this with **43 % fewer image tokens** (604 vs 1056), so a two-display
  question fits the 3000-token budget `SeamLLMService` enforces with room to
  spare. It also has the best native-resolution read of the sweep (up to 18/18).
- **Cost of collapsing:** −2.1 GB runner RSS (§5); `SeamLLMService`'s
  text↔VLM model flip (step 6 increment 6) becomes dead weight. The vision
  turn's own short prompt and history-free context stay; only the model
  switch goes. **Not removed here**; step 9 owns it, together with the
  `reasoning_effort` change in §2.

---

## 4. Deliverable 4 — the detector

### 4.1 Harness added

- **`wellsy --gate-open`**: T1 runs on every 8 Hz tick regardless of the T0
  verdict. T0 still runs every frame and is still timed and emitted
  (INVARIANTS #5); only its decision is ignored. The decision is now the pure
  `cli.t1_should_run()`, tested in `tests/test_perception_gate_open.py`.
  The 8 Hz `DETECT_HZ` cadence is unchanged, so "every frame" means every
  T1 tick, which is the schedule 6c's warm figure was measured under.
- `wellsy --detector <weights>`, `--record PATH`, `--clip PATH` (replay at
  the file's frame rate through the same latest-wins queue).
- `bench/detector_clip_compare.py`: every detector over the **identical frames**
  of one clip, on the 8 Hz grid.

**The clip:** `runs/step5c/clip.mp4` (local, gitignored), 1707 frames at
1920×1080, recorded once with the owner in frame to 6c's script, with spoken
cues: sit → glasses on → phone up in hand → leave. The header says 30 fps; the
camera delivered ~28.5 fps (1707 frames in 60 s), so clip time runs ~5 % fast.
That is immaterial to a side-by-side because both detectors see the same frames.

### 4.2 Latency — live figures first

**Live** (`wellsy --gate-open --detector X --seconds 45 --debug`, real camera,
1080p, ABBA order; per-frame T0+T1 = `gateMs + inferenceMs` on frames where T1
ran, warm = after the first call; `runs/step5c/live-*.jsonl`):

| Detector | Run | Warm T1 p50 / p95 | **T0+T1 p50 / p95** | Cold first call | n |
|---|---|---|---|---|---|
| `yoloe-11s` | 6c session D (**gated**) | 33.32 / 41.11 ms | — | 541.87 ms | 47 |
| `yoloe-11s` | A | 32.48 / 37.42 ms | **33.91 / 39.05 ms** | 369.6 ms | 333 |
| `yoloe-11s` | D | 30.27 / 35.99 ms | **31.59 / 37.30 ms** | 330.3 ms | 329 |
| `yoloe-26s` | B | 30.84 / 34.47 ms | **32.14 / 35.85 ms** | 546.6 ms | 319 |
| `yoloe-26s` | C | 29.98 / 32.54 ms | **31.36 / 33.89 ms** | 335.1 ms | 334 |
| *budget* | | | **< 20 / < 35 ms** | | |

**Cold start, fresh process each** (`detector_clip_compare.py`, three runs per
detector, alternating): `yoloe-11s` **330.8 / 338.1 / 334.6 ms**, `yoloe-26s`
**328.1 / 333.9 / 330.7 ms**; load 1.2–1.4 s vs 1.1–1.2 s. Indistinguishable.
NMS-free did not move the first call. Both are below 6c's 541.87 ms, and
live run B (546.6 ms) shows that figure is reachable on a bad first frame, so
**cold first call ≈ 330–550 ms** for either.

**Bench figure, beside, never instead:** the same clip back-to-back (no idle
gap) gives warm detect+track **~16 ms p50** for both (`yoloe-11s`
16.08–16.27 / p95 21.4–21.9; `yoloe-26s` 15.92–16.35 / p95 17.2–20.6 ms).

**Verdict:** both detectors **miss the < 20 ms p50 live budget**; YOLOE-26 is
~1–2 ms better at p50 and ~2–5 ms better at p95, and is the only one that met
< 35 ms p95 in a run (C). **Better labels did not cost latency; they came with
slightly less.**

### 4.3 Why live is 2× the bench, measured

Three controlled runs of `yoloe-26s` on identical clip frames:

| Condition | Warm p50 / p95 |
|---|---|
| back-to-back calls, one process | **15.41 / 16.52 ms** |
| same calls with a **117 ms sleep** between (the 8 Hz gap), one process, no capture worker | **40.04 / 45.78 ms** |
| the live loop (`wellsy --gate-open --clip`, capture process, 8 Hz) | 32.15 / 35.40 ms |

The detector is not the bottleneck and the camera is not either. **At 8 Hz the
GPU idles between calls, and each call pays to come back up** (Metal/MPS on
this machine). The live §1 perception row cannot pass at this cadence on any
detector. Recorded for the perception-scheduling owner (§7); nothing changed.

### 4.4 D30's named misses, side by side (`spec/results/detector-clip-compare-2026-10-14.jsonl`)

Gate held open, identical frames. Ticks with the label in each 4 s window
(32 ticks per window):

| Label | Detector | 0 | 4 | 8 | 12–24 | 28 | 32 | 36 | 40 | 44 | 48 | 52+ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| glasses | `yoloe-11s` | 0 | 0 | 14 | **32 ×4** | 23 | 32 | 32 | 32 | 32 | 9 | 0 |
| glasses | `yoloe-26s` | 0 | 0 | 15 | **32 ×4** | 25 | 32 | 32 | 32 | 32 | 9 | 0 |
| cell phone | `yoloe-11s` | 0 | 0 | **1 (FP)** | 0 | 32 | 32 | 29 | 29 | 17 | 0 | 0 |
| cell phone | `yoloe-26s` | 0 | 0 | 0 | 0 | 32 | 32 | 31 | 32 | 24 | 1 | 0 |
| person | both | 32 | 32 | 32 | 32 ×4 | 32 | 32 | 32 | 32 | 32 | 24 | 0 |

Scores: glasses 0.36–0.91 (11) vs 0.39–0.92 (26); phone 0.36–0.95 vs 0.37–0.94.

- **The misses D30 called structurally unfixable are not detector misses.**
  Once T1 runs, both models see glasses on essentially every tick they are worn
  and the phone on 29–32 of 32 ticks while it is up. 6c's gated baseline
  (glasses 17/47 runs at 0.37–0.84, phone **1/47** at 0.39) was measuring the
  gate.
- YOLOE-26 is marginally better: more phone ticks on the way down (24 vs 17,
  31 vs 29), no early phone false positive, same glasses. That margin is what
  30.8 vs 27.5 LVIS buys on this scene. Real, small.
- **Label behaviour changed:** YOLOE-11 called the seat `gaming chair`
  (0.35–0.91); YOLOE-26 calls it `chair` and never fires `gaming chair`. Both
  terms are on the prompt list, so nothing is lost; worth knowing for anyone
  keying on the label.

### 4.5 MPS float64 workaround

- `yoloe-11s` + `mobileclip_blt.ts`: `get_text_pe` on MPS **still fails**
  (`TypeError: Cannot convert a MPS Tensor to float64`). The workaround is
  still needed for 11.
- `yoloe-26s` + `mobileclip2_b.ts`: **text embedding works on MPS directly**
  (float32 on `mps:0`). The CPU detour **still works** too.

Kept as is (harmless for both encoders); the docstring now says it is no
longer required for the default model. Removing it is step 9's call.

### 4.6 The three-arm comparison (prompt amended 2026-10-14)

The master session added an arm mid-step: **detector localizes → crop → typed
question → probability**. It was run **locally**. The hosted option (OpenAI
Decisions API on person crops) was **deferred to step 8 by the owner**
(2026-10-14): INVARIANTS #2 still reads "no third-party cloud receives pixels",
D55's override covered Jev/text and deferred the egress-control layer to step
8, and no API key was configured. **No pixel left the machine in 5c.**

`bench/detector_crop_decide.py`, `spec/results/detector-crop-decide-5c.jsonl`.
28 frames (one per 2 s of clip time). **Ground truth labelled by eye** from
contact sheets of exactly those frames, independent of every arm: glasses worn
11–49 s (20 positives, 8 negatives incl. 3 empty-room frames); phone in hand
29–47 s (10 positives, 18 negatives). Arms 1–2 = the detector label present
at ≥ 0.35. Arm 3 = YOLOE-26 `person` box + 15 % pad → `vision._to_jpeg` →
local VLM, one token, **P(yes) from first-token `top_logprobs`** (Ollama 0.40.3),
threshold 0.5. Model resident.

| Arm | Glasses (20+ / 8−) | Phone (10+ / 18−) | Misses | Added latency |
|---|---|---|---|---|
| 1 `yoloe-11s` label | 19 / 0 FP | 8 / 0 FP | glasses at 29 s (phone over face); phone held low at 45, 47 s | none (inside the 8 Hz pass) |
| 2 `yoloe-26s` label | **20 / 0 FP** | 9 / 0 FP | phone held low at 47 s | none |
| 3 crop → `qwen3.5:4b` | **20 / 0 FP** | **10 / 0 FP** | — | **1966 / 2210 ms** per question (n=50) |
| 3 crop → `qwen3-vl:2b` | **20 / 0 FP** | **10 / 0 FP** | — | 1781 / 2163 ms per question (n=50) |

Probability separation, arm 3: Qwen3.5 P(yes) **≥ 0.953** on every glasses
positive and 0.000 on negatives; **≥ 0.935** vs **≤ 0.105** for the phone.
`qwen3-vl:2b` saturates (1.000 / 0.000, phone negatives up to 0.340): it is
separable, but it looks less like a calibrated probability.

**Reading it honestly:**

- On D30's misses, **arm 3 wins on the hardest case** (a phone held low in the
  lap) and ties elsewhere. The detectors already get almost everything once
  T1 runs (§4.4), so the margin arm 3 buys is 1–3 frames in 28.
- It costs **~2 s per question**, ~100× the detector. As the amendment
  required, it **does not go in the 8 Hz path.** It belongs to the **on-demand
  query path** ("am I wearing my glasses?", "what am I holding?"), where it
  rides the already-resident VLM at zero extra memory.
- Caveats: 28 frames of **one static scene, one person**. These are correlated
  samples, not 28 independent ones (step 8's own warning applies). The
  probabilities are separable here, not shown calibrated.
- Per the amendment, an arm-3 win is **a step-8 architecture question, not a
  model swap.** Handed over: the local backend already answers typed image
  Predicates with usable P(yes); step 8 should bench hosted backends against
  *this* number, not against the detector.

### 4.7 Decision

**`MODEL_NAME = "yoloe-26s-seg.pt"`**, the one-string change
(`engine/perception/detector.py`). Equal or better on every measured axis:
live latency, cold start, phone recall, false positives, a 114 MB lighter
process (952 vs 1066 MB RSS). The 254 MB text encoder replaces the 570 MB one
in the weights directory.

---

## 5. Deliverable 5 — §1 and §7, third time

### 5.1 §1 latency table, every model row re-measured

| Path | Target p50 / p95 | Measured (5c, as shipped) | Verdict |
|---|---|---|---|
| Wake → first word, deterministic | < 800 / < 1200 ms | 617 / 700 ms (step 4; no model in path) | **PASS** |
| Wake → first word, LLM (fast), `qwen3:4b-instruct-2507` | < 1500 / < 2500 ms | 615 / 622 ms composed (6b `wellsy voice --measure`, n=20); model TTFT on 0.40.3 **24.2 / 26.7 ms** (5b: 21.3 / 23.8) | **PASS** |
| ↳ same, with Qwen3.5 (`think` off) | | model TTFT **70.9 / 85.9 ms** → ≈ 662 ms composed | would PASS |
| Planner delivers, `qwen3:4b-instruct-2507` | 3–4 s | **3.91 / 3.97 s** (ack at ~615 ms) | **PASS** (30 ms margin at p95) |
| ↳ same, with Qwen3.5 (`think` off) | | **3.47 / 3.47 s** | would PASS, 0.5 s margin |
| Wake → first word, VLM, `qwen3-vl:2b`, **1024 px real dense UI, new image, resident** | < 2500 / < 3500 ms | ASR 267 + **2120** + TTS TTFA 345 ≈ **2.73 s p50**; ASR 276 + **2197** + TTS 406 ≈ **2.88 s p95** (composed; one display; screen-capture time not included) | **MISS p50** by ~230 ms · PASS p95 |
| ↳ same, with Qwen3.5 | | 267 + **2018** + 345 ≈ **2.63 s p50** | would MISS p50 by ~130 ms |
| ↳ Qwen3.5 at 768 px | | 267 + 1371 + 345 ≈ 1.98 s | PASS, at **3–6 / 18** legibility. Owner's trade, not taken |
| VLM, cold (model not resident) | | +1.1–1.6 s load + first new image ≈ 3.3 s | MISS → keep resident (unchanged) |
| Barge-in / `stop` | see §1 | live-only, owed (A14) | owed |
| **Perception fast path (T0+T1), live**, `yoloe-26s` | < 20 / < 35 ms | **32.14 / 35.85 · 31.36 / 33.89 ms** (gate open, 8 Hz) | **MISS p50** (cause §4.3) · p95 at the line |
| ↳ bench (same clip, back-to-back) | | ~16 ms p50 | beside, not instead |

**The VLM row is a correction, not a regression.** 5b's PASS rested on a
cache-inflated 1.8 s. The honest figure misses p50 by a few hundred ms. This
matches the knowingly-accepted VLM miss on record since step 4b, and 6c's live
two-display answers (~4–5.4 s). Levers, none taken here: Qwen3.5's 43 %
smaller image token count matters most when two displays are sent; a
crop-to-focused-window capture; or the 768 px trade above.

No blank model cells except the live-only acoustic rows.

### 5.2 Co-residency, measured (`ollama ps` + runner RSS, models pinned with `keep_alive:-1`)

| Set | ctx | `ollama ps` sum | **Runner RSS sum** |
|---|---|---|---|
| **A — as shipped:** `qwen3:4b-instruct-2507` + `qwen3-vl:2b-instruct` | 4096 | 4913 MB (5b: 5.2 GB) | **5877 MB** (3100 + 2777) |
| **B — collapse:** `qwen3.5:4b` alone | 4096 | 3034 MB | **3746 MB** |
| **C — collapse at a working context** | 32768 | 4147 MB | **4647 MB** |
| perception process, `yoloe-26s` (11s) | — | — | **952 MB** (1066) |

Delta: as shipped vs 5b, −0.3 GB on `ollama ps` (same models; the server's
accounting moved). **5b quoted `ollama ps` only, which under-counts the VLM
runner by ~0.9 GB**; RSS is the figure to plan on. Collapse vs shipped:
**−2.1 GB at ctx 4096**, and still −1.2 GB at 8× the context.

### 5.3 Orin NX 16 GB — re-derived, not inherited

Working set = LLM/VLM runner RSS + ASR/TTS ~1.3 GB (5b, unchanged:
faster-whisper 0.63 + Kokoro 0.70 + Silero 0.02) + agent runtime ~0.2 GB +
perception 0.95 GB:

| Configuration | Working set | Left of 16 GB for OS, framebuffer, ROS 2, slack |
|---|---|---|
| As shipped (A), ctx 4096 | **~8.3 GB** | ~7.7 GB |
| Collapse (B), ctx 4096 | **~6.2 GB** | ~9.8 GB |
| Collapse (C), ctx 32K | **~7.1 GB** | ~8.9 GB |
| Incumbent planner at ctx 32K + VLM (for contrast) | ~12.4 GB (7.1 + 2.8 + 2.45) | ~3.6 GB |

**Verdict: fits, all roles resident, in every shipped or recommended
configuration.** It is tighter than 5b said (8.3, not 6.7 GB), because 5b used
`ollama ps`. The one configuration that does **not** fit comfortably is a
long context on a pure-attention planner. That is a second, independent reason
for the collapse model if step 7 wants more than 4K.

**Caveats carried forward from 5b, unchanged:** every number is
darwin/arm64; the Linux/CUDA path is still unexecuted; CUDA reserves compute
buffers differently from Metal's unified-memory mmap, so the Jetson figure is
a **projection until someone runs `ollama ps` and `ps -o rss` on the board.**
Perception on Jetson is CUDA torch, not MPS; its 0.95 GB is also a projection.

### 5.4 Re-measured at larger context — `bench/llm_context_sweep.py`

Planner prompt preceded by a realistic tool-call transcript filling 75 % of the
window, a fact planted at the top. Plan-valid and needle are **n=1 per row**.
`spec/results/llm-context-sweep-2026-10-14-*.jsonl`:

| ctx | prompt tok | Qwen3.5 `ps` / RSS | incumbent `ps` / RSS | Qwen3.5 cold prefill | incumbent cold prefill | Qwen3.5 valid / needle | incumbent valid / needle |
|---|---|---|---|---|---|---|---|
| 4K | ~2.7K | 3.0 / 4.0 GB | 3.0 / 3.1 GB | 5.0 s | 4.7 s | ✓ / ✓ | ✓ / ✓ |
| 16K | ~11.2K | 3.5 / 4.4 GB | 4.9 / 4.9 GB | 22.3 s | 32.1 s | ✗ / ✓ | ✓ / ✓ |
| 32K | ~22.7K | 4.1 / 5.0 GB | 7.3 / 7.3 GB | 54.9 s | 96.8 s | ✓ / ✓ | ✓ / ✓ |
| 64K | ~45.8K | 5.6 / 6.4 GB | **12.1 / 11.9 GB** | 164.8 s | 340.9 s | ✗ / ✓ | ✓ / ✓ |
| 128K | 92.5K | 7.6 / 8.0 GB | not run (≈19 GB KV by arithmetic) | **514.6 s** | — | ✗ / ✓ | — |

The arithmetic predicted it, and it measured: Qwen3.5 has attention in only
8 of 32 layers (24 are Gated DeltaNet with a fixed-size state), so its KV
grows ~4.5× slower than Qwen3's.

---

## 6. Deliverable 6 — the context finding step 7 is waiting on

**Recommendation: build step 7 for a ~4K-token assembled context per turn that
grows append-only within a session up to ~32K tokens, with retrieval kept and
compaction at the boundary. Do not design for the 262K window. On this
hardware the binding constraint is prefill time and edit discipline, not
memory and not window size.**

The measurements behind it:

1. **Cold prefill is the real budget.** Qwen3.5 ingests a fresh context at
   ~540 tok/s at 4K, falling to ~180 tok/s at 92K (incumbent: ~570 → ~130
   tok/s). Any context that is new to the server costs **~2 s per 1K tokens**
   before the first word. A 4 s planner budget therefore allows **~1.5–2K
   tokens of uncached context per turn**. That is what retrieval must fit, the
   same order as 5b's 4096-token design.
2. **Cached context is nearly free, if and only if it is append-only.**
   (`bench/llm_append_reuse.py`, `spec/results/llm-append-reuse-5c-*.jsonl`,
   history of 0.6 × ctx, then three appended turns.)

   | Model | ctx | Turn 0 (cold) first word | Appended turns 1 / 2 / 3 first word |
   |---|---|---|---|
   | Qwen3.5 | 16K (9.3K tok) | 21.3 s | **0.65 / 0.27 / 0.26 s** |
   | Qwen3.5 | 32K (18.6K tok) | 42.3 s | **0.91 / 0.31 / 0.32 s** |
   | incumbent | 16K (9.2K tok) | 25.0 s | 0.17 / 0.17 / 0.23 s |
   | incumbent | 32K (18.4K tok) | 61.8 s | 0.26 / 0.27 / 0.33 s |

   **But any edit to earlier history is expensive on Qwen3.5.** With the same
   history and a changed last user turn, first word took **1.24 s (4K), 2.68 s
   (16K), 3.56 s (32K), 11.83 s (64K), 5.03 s (128K)**, against 0.17–0.44 s for
   the incumbent. A recurrent state cannot be rolled back; llama.cpp
   re-processes from its last checkpoint, so the cost is non-monotonic in depth.
3. **Memory is not the constraint.** Qwen3.5 at 32K is 4.6 GB RSS, cheaper
   than as-shipped at 4K (§5.2). The pure-attention incumbent at 64K is 12 GB.
   If step 7 runs on the incumbent, the window must stay ≤ ~16K.
4. **Overflow fails silently.** When a prompt exceeded `num_ctx`, Ollama
   0.40.3 **dropped the history messages without an error**, keeping the
   system prompt and the last turn (first sweep attempt: 2.7K tokens of history
   became a 184-token prompt). A context engine cannot rely on the server to
   refuse; it must count and enforce its own ceiling. 6c's 3000-token fit in
   `SeamLLMService` is the right instinct.
5. **Recall at depth held, planning quality did not, n=1.** The planted fact
   was recalled at every depth by both models. Qwen3.5's plan JSON failed
   validation at 16K, 64K and 128K; the incumbent's held to 64K. That is a
   flag for step 7 to measure properly before trusting long contexts with
   planning, not a result.

**What that means for the design in `step7-memory-context.md`:**

- Keep sqlite-vec retrieval and the hard token ceiling. The tight-retrieval
  design is still right; the window grew, the prefill speed did not.
- **Order the assembly for the prefix cache:** identity → core memory blocks
  → session transcript (append-only) → retrieved blocks and the new turn
  **last**. Volatile content after the stable prefix. Never rewrite,
  reorder or strip earlier messages mid-session. Today's `SeamLLMService`
  front-trimming to 3000 tokens and vision-turn image stripping are both
  edits; on Qwen3.5 each costs a re-prefill. Step 9 should know this.
- **Session window ~32K, compaction at the boundary.** Compaction is one
  deliberate cache miss, so compact to something small (≤ 2K).
- Provenance-tagged larger blocks become affordable **only in the cached,
  append-only part.** A 262K-style "dump everything in" costs 8.6 minutes
  to first word cold.
- Production runs at ctx 4096 today (server default; `/v1` ignores `num_ctx`,
  per 6c). A larger session window needs `OLLAMA_CONTEXT_LENGTH` or the
  native API. That is a config decision for step 7 or 9.

**LangGraph seam (resolved version 1.2.11, prebuilt 1.1.0), checked in the
venv:** `create_react_agent` exposes **`pre_model_hook` / `post_model_hook`**;
`StateGraph.add_node` exposes **`defer`** and **`cache_policy`**;
`langgraph.cache.memory.InMemoryCache` exists. WELLSY's agent
(`engine/agent/graph.py`) is a hand-built `StateGraph`, not
`create_react_agent`. The hooks are therefore not directly attached; the
equivalent seam is a node placed before the model node, which is where the
context engine's assembly and redaction belong. `langchain.agents.create_agent`
(the newer middleware API) is not installed.

---

## 7. Evidence for perception scheduling (owner: none yet; README "Open debt")

The gate was **not retuned** (`MOTION_THRESHOLD = 5.0`, 1.0 s hold, untouched).
Evidence produced by 5c:

- **On the recorded performance, T0 opened on 61 of 1707 frames (3.6 %), and
  58 of those were the owner leaving the frame.** Peak motion per 4 s window,
  in /255: glasses going on **4.1**, phone raised **3.1–3.8**, sitting 0.9–5.4.
  Under the shipped gate T1 would not have run while the glasses or phone came
  into view. 6c's 1.8 % reproduces in kind.
- During recording, the live gated fraction was **94.9 %** over 58 s, and
  98–100 % during the 45 s gate-open timing runs (static scene).
- With T1 forced on, recall of the "unfixable" objects is ~95–100 % (§4.4).
  **The fix is scheduling, not a detector.**
- **Latency side:** T1 at 8 Hz costs ~31–34 ms live because of the GPU idle
  gap (§4.3); back-to-back it costs ~16 ms. A "T1 at least every N s"
  scheduler will pay the idle-gap price per call. A budget that wants < 20 ms
  needs either sustained cadence or a keep-warm strategy, and that trade is
  the owning step's to measure.

---

## 8. Code changes

| File | Change |
|---|---|
| `engine/perception/detector.py` | **`MODEL_NAME = "yoloe-26s-seg.pt"`**; `load_model(name=)` for harnesses; docstrings for the new encoder |
| `engine/cli.py` | harness flags `--gate-open`, `--detector`, `--clip`, `--record`; T1 decision extracted to `t1_should_run()` (behaviour unchanged by default) |
| `engine/perception/capture.py` | clip replay at the file's frame rate + optional recording, same latest-wins queue |
| `engine/inference/llm_bench.py` | 5c candidates; `contentTtft*` (first speakable token), `runner` / `contextLength` from `/api/ps`, `--num-ctx`, `--think` filter |
| `engine/inference/bench.py` | passes `--num-ctx` / `--think` through `wellsy bench --modality llm` |
| `bench/detector_clip_compare.py` | **new**: identical-frame detector side-by-side |
| `bench/detector_bench.py` | `--detector` |
| `bench/detector_crop_decide.py` | **new**: three-arm comparison (detector labels vs crop → local VLM P(yes)) |
| `bench/vlm_screen_sweep.py` | **new**: D3 through `vision._to_jpeg` |
| `bench/llm_context_sweep.py`, `bench/llm_append_reuse.py` | **new**: context and prefix-reuse sweeps |
| `tests/test_llm_bench.py` | +3 tests (content vs thinking TTFT + runner; `num_ctx` reaches the payload; `--think` filter) |
| `tests/test_perception_gate_open.py` | **new**: 4 tests; default unchanged, flag runs T1, T0 runs before the decision |
| `README.md`, `spec/model-inventory.md` | detector weights; adopted / measured / rejected rows |

Not changed, on purpose: LLM/VLM defaults (`models.py`, `adapters.py`,
`openai_http.py`); request shapes; `SeamLLMService`; the motion gate; the MPS
workaround; TTS; ASR.

---

## 9. What step 9 inherits

1. **The Qwen3.5 collapse, as one change:** default → `qwen3.5:4b-q4_K_M`
   (pinned GGUF tag, never bare) for voice, fast, planner and VLM, **plus**
   `reasoning_effort:"none"` in `adapters.build_llm` and `models.get_model`
   (both roles), **plus** removing `SeamLLMService`'s model flip. Test it by
   asserting zero `reasoning` deltas on `/v1`, not by the `thinking` counter
   alone (§1.3 caveat).
2. Prefer append-only context; front-trimming and image-stripping are cache
   edits (§6).
3. Optional: drop the CPU detour in `detector.set_prompts` now that the
   default encoder runs on MPS (§4.5).

**Step 8 inherits** the three-arm result (§4.6): a local crop → typed-question
baseline of 30/30 at ~2 s, the hosted comparison the owner deferred to it, and
the fact that the decide seam needs image state.

## 10. Debt carried forward

- Linux/CUDA and Jetson numbers: unexecuted, as in 5b.
- §1 acoustic rows (device-timestamped first word, barge-in, `stop`): live-only, owed.
- Screen-capture latency is not in the composed VLM row (A8 debt).
- Long-context **plan quality** at n ≥ 20 per depth: step 7.
- Gemma 4's `ollama ps` 3.2 ↔ 9.0 GB swing is unexplained; immaterial since it
  is rejected.
- Ollama 0.40.4 shipped during the step; nothing here was run on it.

## 11. Suite / tree

`.venv/bin/python -m pytest -q` → **221 passed** (214 + 7 new), after all
changes above.

Acceptance:
- [x] Every claim resolved at source; rejections recorded with reasons (§1).
- [x] Thinking-token count for every candidate from `eval_count`, with the
      content-channel check beside every zero (§1.3, §2).
- [x] Planner and fast, n ≥ 20, against the incumbent re-measured on the same server (§2).
- [x] Collapse test run; one model measures viable; D3 closed at 512 px and
      up on a real dense UI (§3).
- [x] YOLOE-26 live beside 6c's 33.32 / 41.11 ms, cold beside 541.87 ms, and
      side by side with `yoloe-11s` on D30's misses with the gate open, same
      clip (§4).
- [x] Amended three-arm test: detector labels vs crop → local VLM on D30's
      misses, by-eye ground truth, latency and path stated; hosted arm
      deferred to step 8 by the owner (§4.6).
- [x] Motion gate untouched; evidence recorded for the owning step (§7).
- [x] §1 re-derived; co-residency measured; Orin verdict re-derived with the
      darwin caveat (§5).
- [x] Step-7 context recommendation as its own section (§6).
- [x] `step5c-results.md` written; `spec/model-inventory.md` updated; PR opened.
