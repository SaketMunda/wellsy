# WELLSY — Model & Runtime Inventory

**Every adopted model and inference runtime, with its pinned version, licence,
portable path, and the date the pin was verified (INVARIANTS #8).** Started in
rebuild step 2. A row here means "in use or wired"; candidates that were only
looked at go under *Evaluated, not adopted*.

Machine of record for all numbers below: Apple M4 Pro, 24 GB, macOS 15.5
(darwin/arm64). Numbers are p50 / p95 over ≥ 20 trials from `wellsy bench`
unless noted. **No Linux/CUDA numbers exist yet — that path is unexecuted (see
§Linux).**

---

## Runtimes

| Runtime | Version | Verified | Licence | Portable path | Role |
|---|---|---|---|---|---|
| ONNX Runtime | 1.29.0 | 2026-09-01 | MIT | CPU + CoreML EP (macOS); CUDA/TensorRT/ROCm/DirectML EP elsewhere | Small models — VAD now; ASR/TTS when wired |
| Ollama (local server) | 0.33.2 | 2026-09-01 | MIT | HTTP `/v1/chat/completions`, streaming; runs on Linux/Win/macOS | LLM/VLM host for the `openai_http` backend |
| mlx-lm / mlx | 0.31.3 / 0.32.2 | 2026-09-01 | MIT / MIT | **none — Apple Silicon only** | `mlx` LLM backend: opt-in, never default (INVARIANTS #14) |
| httpx | 0.28.1 | 2026-09-01 | BSD-3-Clause | pure Python | transport for `openai_http` |

`llama-cpp-python` 0.3.35 (2026-08-17) was verified current but **not adopted
this step** — the portable LLM path is the OpenAI-compatible HTTP client, which
also covers `llama-server`, vLLM and SGLang. An in-process llama.cpp backend
can be added later without changing the interface.

---

## Models — adopted

### LLM / VLM

| Model | Served as | Version / digest | Verified | Licence | Notes |
|---|---|---|---|---|---|
| Qwen3 4B Instruct 2507 | Ollama `qwen3:4b-instruct-2507-q4_K_M` | digest `0edcdef34593`, 2.5 GB | 2026-09-03 | Apache-2.0 | **step 5b default for agent `fast` + `planner` AND the voice-path LLM** (`models.py`, `adapters.build_llm`, `metrics.py`). Non-reasoning *by construction* (the `-instruct` build has no `<think>` path). Warm TTFT 21 ms (fast turn) / 32 ms (planner prompt); full schema-valid 3-step plan in ~4.0 s; **20/20 plan-JSON validity**; 3.2 GB resident (`ollama ps`, ctx 4096). One model, two agent roles. |
| Qwen3-VL 2B Instruct | Ollama `qwen3-vl:2b-instruct-q4_K_M` | digest `ea422f1e7365`, 1.9 GB | 2026-09-03 | Apache-2.0 | **step 5b `openai_http` / VLM default** (`DEFAULT_MODEL`), VLM via `images=`. Non-reasoning `-instruct` build — retires the `qwen3-vl:4b` hybrid reasoning-tax debt. 2.0 GB resident; first-capture image processing ~1.8 s (768 px synthetic, `coldTTFT−load`); transcribed every line incl. 0.5-scale small print, matching `qwen2.5vl:3b`. **Owed: real-vision-path resolution sweep (step 5b debt D3).** |
| Qwen2.5 3B | Ollama `qwen2.5:3b` | 2026-09-01 | Apache-2.0 | **Beaten incumbent** (step 5b fast bench-off). 15 ms warm TTFT, 2.0 GB — faster/lighter than the winner but 2024-era (INVARIANTS #8). Kept pulled as a fallback. |
| Qwen2.5-VL 3B | Ollama `qwen2.5vl:3b` | digest `fb90415cde1e`, 3.2 GB | 2026-09-03 | Apache-2.0 | Step-5 interim VLM, **beaten** by `qwen3-vl:2b-instruct` (4.1 GB resident vs 2.0, 91 vs 140 tok/s, same legibility). Fallback. |
| Qwen3-VL 4B | Ollama `qwen3-vl:4b` (+ `4b-instruct` on the shelf) | digest `1343d82ebee3`, 3.3 GB | 2026-09-01 | Apache-2.0 | Hybrid `4b` reasons uncontrollably on Ollama 0.33.2 (step 4b). `qwen3-vl:4b-instruct` (3.3 GB) is the non-reasoning fallback if D3 finds `2b-instruct` loses dense-UI text. |
| Qwen3 4B (hybrid / thinking-2507) | Ollama `qwen3:4b`, `qwen3:4b-thinking-2507-q4_K_M` | `359d7dd4bcda` / — | 2026-09-03 | Apache-2.0 | **Rejected for the planner.** ~78 s/turn, 4756 reasoning tokens/turn. `think:"low"` accepted by the API but **byte-identical** think-token count — no flag or effort level disables reasoning on this stack (step 5b §2). |
| Qwen3-VL 8B | Ollama `qwen3-vl:8b` | digest `901cae732162`, 6.1 GB | 2026-09-01 | Apache-2.0 | available; same reasoning-tax problem as hybrid 4B |

**`wellsy bench --modality llm` (trials 20, `/no_think` prompt, cold):**

| backend | model | cold load ms | TTFT p50 / p95 ms | turn p50 / p95 ms | resident MB |
|---|---|---|---|---|---|
| `mlx` | `mlx-community/Qwen3-4B-4bit` | 1716 | **150 / 156** | 635 / 641 | **2479** |
| `openai_http` | Ollama `qwen3-vl:4b` | 21 | **3575 / 30291** | 4307 / 31074 | 0.1 (client only) |

Read this as the INVARIANTS #14 trade-off, measured: MLX is ~24× faster to
first token on this dev machine — and exists on no other platform, which is
exactly why it is opt-in and never auto-selected. `openai_http` p95 is a real
30 s Ollama outlier on `qwen3-vl:4b` (a vision model paying prompt-processing
cost).

**Superseded for role selection by step 5b** — `wellsy bench --modality llm`
now runs a per-slot candidate set (`--slot planner|fast|vlm`); current winners
and losers are in `.claude/rebuild/step5b-results.md` §2-4. The row above stays
as the MLX-vs-server INVARIANTS #14 datapoint.

**Streaming proof (`tests/test_llm_streaming.py`, acceptance #3), cold:**

| backend | first answer delta | remaining deltas | streamed over |
|---|---|---|---|
| `mlx` | **~197 ms** | 29 of 30 | ~312 ms |
| `openai_http` | ~3.3–5.4 s (see above) | 31–32 of 32–33 | ~435 ms |

Both: ≥2 text deltas, last strictly after first — incremental delivery, nothing
waits for the full completion. Lines appended to
`spec/results/streaming-<date>.txt`.

### VAD

| Model | Backend | Version | Verified | Licence | Bench (5 s audio, cold) |
|---|---|---|---|---|---|
| Silero VAD v5 | `silero` (ONNX, CoreML EP) | snakers4/silero-vad `master`, v5 `silero_vad.onnx` (2.33 MB) | 2026-09-01 | MIT | cold 25–52 ms · p50 **12–27 ms** / p95 12–28 ms · RTF 0.002–0.006 · resident 6–26 MB |
| — (RMS energy) | `energy` (pure NumPy) | wellsy-energy-vad 1 | 2026-09-01 | — (ours) | cold 0.01 ms · p50 **0.7–1.5 ms** / p95 0.8–1.6 ms · RTF ~1e-4 · resident ≤2 MB |

(ranges span two cold runs; Silero's CoreML-EP first-call cost and p50 vary
with concurrent machine load.)

Weight file: `~/.cache/wellsy/weights/silero_vad.onnx`
(`$WELLSY_WEIGHTS_DIR` overrides). The step-4 voice pipeline uses **Pipecat's
bundled** `SileroVADAnalyzer` (same v5 model, shipped inside the wheel); this
`silero` backend remains the standalone / bench VAD.

### ASR — adopted step 4

| Model | Backend | Version | Verified | Licence | Bench (5 s synthetic, cold) |
|---|---|---|---|---|---|
| faster-whisper `base.en` | `faster_whisper` (CTranslate2, int8 CPU / fp16 CUDA) | faster-whisper 1.2.1 | 2026-09-01 | MIT (lib) / MIT (model) | cold 14.6 s (incl. first-run model fetch) · p50 **261 ms** / p95 276 ms · RTF **0.052** · resident 626 MB |
| — (fixed transcript) | `reference` | wellsy-reference-asr 1 | 2026-09-01 | ours | shape only |

**Why not Qwen3-ASR 0.6B:** its only CPU-ONNX export
(`Daumee/Qwen3-ASR-0.6B-ONNX-CPU`) is 2.5 GB (two 571 MB INT8 decoders), does
**batch** autoregressive decode on ~30 s silence-split chunks, and runs at
RTF ~0.32 on desktop — a ~1 s STT floor paid *after* endpoint, which breaks the
§1 budget this step exists to fix. Verified 2026-09-01; not adopted. Smart Turn
v3 owns end-of-turn, so `base.en`'s lack of word-level partials costs little.
`WELLSY_ASR_MODEL` overrides the Whisper size.
Weights: `$WELLSY_WEIGHTS_DIR/faster-whisper/` (auto-fetched once).

### TTS — adopted step 4

| Model | Backend | Version | Verified | Licence | Bench (~4 s output, cold) |
|---|---|---|---|---|---|
| Kokoro-82M | `kokoro` (kokoro-onnx, ORT provider auto) | kokoro-onnx 0.6.1 / model-files-v1.0 | 2026-09-01 | Apache-2.0 | cold 509 ms · p50 **819 ms** / p95 827 ms · **RTF 0.202** (~5× realtime) · resident 697 MB |
| — (180 Hz tone) | `reference` | wellsy-reference-tts 1 | 2026-09-01 | ours | shape only |

RTF measured before adoption (step 4 "Do not"). `stack-teardown.md` §5's
fast-but-flat portable baseline; an expressive, instructable model (Qwen3-TTS)
is a later day and the seam does not change when it lands. Needs `espeak-ng`
(system package) for phonemisation. Weights:
`$WELLSY_WEIGHTS_DIR/kokoro-v1.0.onnx` + `voices-v1.0.bin`.
`WELLSY_TTS_VOICE` / `WELLSY_TTS_SPEED` override.

### Voice pipeline runtime

| Component | Version | Verified | Licence | Portable path | Role |
|---|---|---|---|---|---|
| Pipecat | 1.8.1 | 2026-09-01 | BSD-2-Clause | pure Python, cross-platform | streaming frame pipeline, interruptions, turn detection |
| Smart Turn v3 | `smart-turn-v3.2-cpu.onnx` (bundled in pipecat wheel) | 2026-09-01 | (per pipecat) | ONNX, CPU ~12–65 ms, 23 languages, no GPU | semantic end-of-turn — replaces the fixed 600 ms tail |
| PyAudio / PortAudio | pyaudio 0.2.14 | 2026-09-01 | MIT | PortAudio, cross-platform | `LocalAudioTransport` mic + speaker |

`onnxruntime` is held at `>=1.29` for the whole tree via
`[tool.uv] override-dependencies` — pipecat core-pins `~=1.24.3`; both bundled
models and `engine/inference` load on 1.29, verified in step 4.

---

## Agent runtime — adopted step 5

| Component | Version | Verified | Licence | Portable path | Role |
|---|---|---|---|---|---|
| LangGraph | 1.2.11 | 2026-09-01 | MIT | pure Python | agent state machine; `interrupt()` == the approval gate (D53) |
| langchain-mcp-adapters | 0.3.2 | 2026-09-01 | MIT | pure Python | MCP tools → LangChain tools. **Core-pins `mcp<2.0.0`** |
| mcp (Python SDK) | 1.29.1 | 2026-09-01 | MIT | pure Python, stdio | protocol rev **2025-06-18**. NOT the 2026-07-28 rewrite (mcp 2.x) — the adapter doesn't support it yet |
| langchain-openai | 1.6.0 | 2026-09-01 | MIT | HTTP `/v1/chat/completions` | `ChatOpenAI` for the two model roles |

MCP servers are **ours** (`engine/agent/servers/pim.py`, `fs.py`, FastMCP/stdio)
— the community macOS Apple-app servers failed INVARIANTS #8 (2-commit repos,
Node/bun runtime, no Mail, no safety flags). PIM backend is platform-neutral
(`WELLSY_PIM_BACKEND`: `portable` default JSON store, `macos` `osascript`).

### Model roles — step 5b winners (n≥20 warm unless noted; `spec/results/llm-bench-*.jsonl`)

| Role | Model (default) | Resident (`ollama ps`, ctx 4096) | Warm TTFT p50 / p95 | Notes |
|---|---|---|---|---|
| fast **+** planner | `qwen3:4b-instruct-2507-q4_K_M` | **3.2 GB** (one model, both roles) | 21 / 24 ms (fast) · 32 / 47 ms (planner) | non-reasoning; full plan 4.0 s; 20/20 plan-valid |
| VLM | `qwen3-vl:2b-instruct-q4_K_M` | **2.0 GB** | ~1.8 s first-capture proc (768 px proxy) | non-reasoning; D3 sweep owed |

**Both co-resident (measured together) = 5.2 GB** — down from step-5's 9.0 GB
for three models. Agent-runtime python tree unchanged: **204.7 MB**. Re-derived
Jetson Orin NX 16 GB analysis (now **fits, all roles resident**):
`.claude/rebuild/step5b-results.md` §5, which **supersedes `step5-results.md` §7**.

Losers with numbers: `qwen2.5:3b` (fast, 15 ms but 2024-era), `qwen3:4b` /
`qwen3:4b-thinking-2507` (planner, ~78 s/turn, `think:"low"` non-functional),
`qwen2.5vl:3b` (VLM, 4.1 GB / 91 tok/s). Full table: step 5b results §2-4.

---

## Linux / CUDA path — **UNEXECUTED**

No Linux box was available for step 2. The code path exists and is chosen by
`engine/inference/registry.detect_platform()` (`accelerator == "cuda"`,
`Platform.is_jetson` for ARM64+CUDA), but **nothing below has been run**.

To make `wellsy bench` work first-time on Linux/CUDA (incl. Jetson / production
target #1):

1. **ONNX Runtime GPU:** `pip install onnxruntime-gpu` (x86-64) or the NVIDIA
   Jetson wheel from the Jetson Zoo (aarch64) — the `onnxruntime` wheel in the
   default deps is CPU-only there. Requires matching CUDA + cuDNN; TensorRT EP
   additionally needs TensorRT. `detect_accelerator()` already prefers
   `CUDAExecutionProvider` / `TensorrtExecutionProvider` when present, so the
   `silero` backend picks them up with no code change.
2. **LLM server:** run `llama-server` (CUDA build), vLLM, or SGLang exposing
   `/v1/chat/completions`, then `export WELLSY_LLM_BASE_URL=http://<host>:<port>/v1`
   and `WELLSY_LLM_MODEL=<id>`. The `openai_http` backend is unchanged.
3. **MLX:** not installed and not selectable off Apple Silicon — `mlx`'s
   `is_available()` returns `False` on Linux. Nothing to do.
4. Run `wellsy bench`; it writes
   `spec/results/bench-<date>-linux-<arch>-<commit>.jsonl`. Compare the VAD
   p50/p95 against the macOS row above and the perception fast path against
   `bench/detector_bench.py`'s recorded baseline.

The `bench-*.jsonl` schema is platform-tagged, so macOS and Linux results sit
side by side in `spec/results/` without collision.
