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
| Qwen3-VL 4B | Ollama `qwen3-vl:4b` (default) | digest `1343d82ebee3`, 3.3 GB | 2026-09-01 | Apache-2.0 | `openai_http` default; VLM via `images=` |
| Qwen3-VL 8B | Ollama `qwen3-vl:8b` | digest `901cae732162`, 6.1 GB | 2026-09-01 | Apache-2.0 | available, not default |
| Qwen3 4B | Ollama `qwen3:4b` / MLX `mlx-community/Qwen3-4B-4bit` | Ollama `359d7dd4bcda` 2.5 GB · MLX rev `main`, 4-bit, ~2.3 GB | 2026-09-01 | Apache-2.0 | used for the MLX-vs-server head-to-head |

**`wellsy bench --modality llm` (trials 20, `/no_think` prompt, cold):**

| backend | model | cold load ms | TTFT p50 / p95 ms | turn p50 / p95 ms | resident MB |
|---|---|---|---|---|---|
| `mlx` | `mlx-community/Qwen3-4B-4bit` | 1716 | **150 / 156** | 635 / 641 | **2479** |
| `openai_http` | Ollama `qwen3-vl:4b` | 21 | **3575 / 30291** | 4307 / 31074 | 0.1 (client only) |

Read this as the INVARIANTS #14 trade-off, measured: MLX is ~24× faster to
first token on this dev machine — and exists on no other platform, which is
exactly why it is opt-in and never auto-selected. `openai_http` p95 is a real
30 s Ollama outlier on `qwen3-vl:4b` (a vision model paying prompt-processing
cost); `qwen3:4b` text-only would be the fairer server comparison and is left
for the master session to run if wanted (`WELLSY_LLM_MODEL=qwen3:4b`).

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
(`$WELLSY_WEIGHTS_DIR` overrides).

---

## Models — scaffolded (interface only, real model deferred)

The ASR and TTS interfaces have two registered backends each and pass the
shared **shape** conformance test, but real model wiring + a bench-off is a
later step (agreed scope for step 2).

| Modality | `onnx` backend | `reference` backend |
|---|---|---|
| ASR | loads an `InferenceSession` if `WELLSY_ASR_ONNX_MODEL` points at an export; `stream()` decode loop deferred | fixed-transcript, portable, streams `Partial`→`Final` |
| TTS | same, `WELLSY_TTS_ONNX_MODEL`; vocoder pipeline deferred | 180 Hz tone generator, portable, streams `PcmChunk` |

Candidates to benchmark when that step lands (verified current 2026-09-01, not
yet adopted):

| Modality | Candidate | Licence | Portable path |
|---|---|---|---|
| ASR | Qwen3-ASR 0.6B / 1.7B | Apache-2.0 | ONNX exports (`Daumee/Qwen3-ASR-0.6B-ONNX-CPU`, `andrewleech/qwen3-asr-*-onnx`); `sherpa-onnx` |
| ASR | Whisper tiny/base | MIT | ONNX; `sherpa-onnx`; faster-whisper (CTranslate2) |
| TTS | Qwen3-TTS (12 Hz) | check at adoption | `qwentts.cpp` GGUF (CPU/CUDA/Metal/Vulkan); ONNX pipelines less mature |
| TTS | Kokoro-82M | Apache-2.0 | ONNX, well-supported — the fast-but-flat fallback |

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
