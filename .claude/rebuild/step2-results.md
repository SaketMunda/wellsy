# Step 2 — results (for the master session)

Branch `rebuild/step2-backend-abstraction`, off `master` @ `30453ab`.
Machine: Apple M4 Pro, 24 GB, macOS 15.5 (darwin/arm64). All numbers from
`wellsy bench` / the test suite on this machine, 2026-09-01.

## What shipped

```
engine/inference/
  base.py         four runtime_checkable protocols (Llm/Asr/Tts/Vad),
                  BackendCapabilities, stream payloads, lazy platform probes
  registry.py     detect_platform(), select() (env > config > auto),
                  available_backends(), get_backend(), describe()
  portability.py  AST source-tree checker + standalone `python -m` entrypoint
  bench.py        `wellsy bench` — cold load / p50 / p95 / RTF / resident MB,
                  JSONL + human table
  backends/
    openai_http.py  LLM/VLM — OpenAI-compatible streaming HTTP (portable)
    mlx.py          LLM — Apple MLX, opt-in, lazy import, never auto-selected
    silero.py       VAD — Silero v5 ONNX (portable)
    energy.py       VAD — RMS energy, pure NumPy (portable reference)
    onnx.py         ASR/TTS — ONNX session loader, decode loop deferred
    reference.py    ASR/TTS — portable reference (fixed transcript / tone)
tests/
  test_portability.py          13 — tree is clean + negative tests
  test_backend_conformance.py  19 — ≥2 backends/interface, shape + streaming
  test_llm_streaming.py         2 — timestamped first-delta proof
spec/
  model-inventory.md            versions, licences, verification dates, numbers
  results/bench-*.jsonl         machine-readable, platform-tagged
  results/streaming-*.txt       the streaming-gap report lines
```

`engine/cli.py` gained a `bench` subcommand alongside the step-3 `doctor` /
`screen` ones — same dispatch pattern, every existing perception flag intact.

## Acceptance

| # | Criterion | Result |
|---|---|---|
| 1 | `wellsy bench` runs on macOS, full table | **PASS** — table + JSONL, run twice cold |
| 2 | Each interface ≥2 backends, ≥1 portable-only, shared conformance | **PASS for LLM + VAD** (both backends drive real streams). ASR/TTS have 2 registered backends passing the shape conformance; `reference` also streams; the `onnx` real decode loop is deferred (agreed scope). |
| 3 | `stream()` yields first delta before completion, timestamped, gap reported | **PASS** — see below |
| 4 | Portability check + negative test | **PASS** — injecting `import mlx` into `engine/honesty/intent.py` fails `pytest tests/test_portability.py` and `python -m engine.inference.portability` (exit 1); reverted clean |
| 5 | Adopted models recorded with version + licence + date | **PASS** — `spec/model-inventory.md` |
| 6 | Linux/CUDA path documented, code present, marked unexecuted | **PASS** — `model-inventory.md` §Linux; `detect_platform()`/`is_jetson` exist; **not run — no Linux box** |

## Streaming proof (acceptance #3)

`/no_think` prompt, "write two sentences about the sea":

| backend | model | first answer delta | remaining deltas | streamed over |
|---|---|---|---|---|
| `mlx` | `mlx-community/Qwen3-4B-4bit` | **~197 ms** | 29 of 30 | ~312 ms |
| `openai_http` | Ollama `qwen3-vl:4b` | ~3.3–5.4 s | 31–32 of 32–33 | ~435 ms |

The test enforces: ≥2 text deltas, last strictly after first — the answer is
delivered incrementally, nothing waits for the whole completion. A
non-streaming path (Day 11) would have withheld all ~30 deltas until the end.
`openai_http` TTFT is high because `qwen3-vl:4b` pays a vision-model
prompt-processing cost even with reasoning off — prompt-processing, not
buffering. Lines are appended to `spec/results/streaming-2026-09-01.txt`.

## `wellsy bench` (trials = 20, cold, canonical run)

`spec/results/bench-2026-09-01-darwin-arm64-30453ab.jsonl`:

| modality | backend | status | accel | cold ms | p50 ms | p95 ms | RTF p50 | resident MB | extra |
|---|---|---|---|---|---|---|---|---|---|
| llm | mlx | ok | metal | 1716 | 635 | 641 | – | **2479** | TTFT p50 **150** / p95 156 ms |
| llm | openai_http | ok | remote | 21 | 4307 | 31074 | – | 0.1 | TTFT p50 3575 / p95 30291 ms |
| asr | onnx | unavailable | – | – | – | – | – | – | no `WELLSY_ASR_ONNX_MODEL` |
| asr | reference | ok | cpu | 0.02 | 0.01 | 0.02 | ~0 | 2.9 | |
| tts | onnx | unavailable | – | – | – | – | – | – | no `WELLSY_TTS_ONNX_MODEL` |
| tts | reference | ok | cpu | 0.01 | 0.39 | 0.55 | 1e-4 | 0.1 | |
| vad | energy | ok | cpu | 0.01 | 1.49 | 1.60 | 3e-4 | ~0 | |
| vad | silero | ok | coreml | 52 | 27.2 | 27.9 | 0.0055 | 6.4 | |

An earlier cold run (pre-MLX-cache, pre-`/no_think`) produced the same table
shape with `llm/mlx` unavailable and `openai_http` p50 3742 ms — both runs cold,
both full tables, so the "run twice" verification holds.

The MLX-vs-server gap (TTFT 150 ms vs 3575 ms) is the INVARIANTS #14 tension,
measured: MLX wins big on the dev machine and runs nowhere else — hence opt-in,
never auto-selected. `openai_http` p95 is a genuine 30 s Ollama outlier on the
vision model, not a client timeout.

## Deviation flagged for ratification

The portable LLM backend is **`openai_http`** (OpenAI-compatible streaming HTTP:
Ollama / llama-server / vLLM / SGLang), not in-process `llama-cpp-python` as
Deliverable 1's `llamacpp.py` name implied. Rationale is in the plan file and
`model-inventory.md`. Invariants #2 (private local server OK) and #14 (bans
*Apple-only* Ollama backends, not a portable HTTP client) are satisfied. If the
master session wants an in-process llama.cpp backend too, it drops in beside
`openai_http` with no interface change.

## What the build revealed

1. **Step-3 work is already in the tree, untracked** (`engine/capture/`,
   `bench/capture_bench.py`, `tests/test_capture_*`, `.claude/rebuild/
   step3-results.md`, and `pyproject.toml` / `engine/cli.py` edits). Someone ran
   step 3 in parallel. I built around it: my portability checker's
   `SANCTIONED_DIRS` exempts both `engine/inference/backends` **and**
   `engine/capture/screen`, and it supersedes the self-described stopgap in
   `tests/test_capture_portability.py` (its own docstring says "step 2 builds
   the full source-tree AST checker"). I did **not** touch or commit the step-3
   files — the commit adds only step-2 paths.
2. `runtime_checkable` protocols with a data member (`capabilities`) reject
   `issubclass()` — only `isinstance()` works. Conformance uses `isinstance` on
   the constructed instance plus explicit class-attr checks.
3. `qwen3-vl:4b` spends 15–20 s on reasoning tokens before the first answer
   token on a bare prompt; `/no_think` is needed in tests/bench to measure the
   runtime rather than the reasoning. Recorded in-line where it is used.
4. Silero v5 ONNX I/O differs from v4 (`state` `[2,B,128]` + scalar `sr` input,
   `stateN` output) — handled in `silero.py`.

## Not done (deferred, per agreed scope / the step's "Do not")

- Real ASR/TTS model wiring + a 2-candidate bench-off (Qwen3-ASR 0.6B, Kokoro /
  Qwen3-TTS). Interface + a portable reference backend are in place.
- No voice-path wiring (step 4). No in-process `llama-cpp-python`. No plugin
  system / config DSL / model manager. MLX is never a default.
- Linux/CUDA path is code-complete but **unexecuted**.
