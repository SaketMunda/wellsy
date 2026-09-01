# Step 2 — Portable inference backends and the cross-platform benchmark harness

**Read first:** `.claude/rebuild/INVARIANTS.md` (especially #8 and #14),
`.claude/stack-teardown.md` §3, §4, §5 and §12.2, `spec/phase1-acceptance.md` §1
and §3. **Depends on step 1.**

## Why this step exists, and why it comes before any model work

The previous build was slow for a reason that was not the models: the runtime
layer was a generation behind and hard-wired. It ran Ollama on llama.cpp/Metal,
PyTorch/MPS, and ONNX, stitched together by hand, with `llm.py` directly coupled
to `localhost:11434`.

The project is now **OS-independent by requirement**, because the endgame is an
agent running on a humanoid platform — Linux, ARM64, NVIDIA Jetson. macOS is a
development machine, nothing more.

**If the abstraction is not built before the models are wired, "OS independent"
silently becomes "slow everywhere."** That is the entire justification for doing
this before anything that produces a visible capability.

## Deliverable 1 — one interface per modality

Four small interfaces. Keep them genuinely small; this is a seam, not a
framework.

```
wellsy/inference/
  base.py        # the four protocols + BackendCapabilities
  registry.py    # runtime capability detection and selection
  backends/
    onnx.py      # ONNX Runtime  — portable default for small models
    llamacpp.py  # llama.cpp     — portable default for large models
    mlx.py       # OPTIONAL, macOS only, must be import-guarded
```

Required shapes (adapt names to taste, keep the semantics):

- `LlmBackend.stream(messages, tools=None, images=None) -> Iterator[Delta]`
  **Streaming is mandatory, not optional.** The previous build measured Ollama
  first-token at 1,693 ms against a full answer at 2,201 ms — 508 ms discarded
  on every single turn because nothing consumed the stream. There is no
  non-streaming variant in this interface. If a backend cannot stream, it wraps
  its result as a one-element iterator and says so in its capabilities.
- `AsrBackend.stream(audio_chunks) -> Iterator[Partial | Final]`
- `TtsBackend.stream(text_chunks) -> Iterator[PcmChunk]`
- `VlmBackend` — either folded into `LlmBackend` via `images=`, or separate.
  Your call; document which and why.

Every backend reports `BackendCapabilities`: platform, accelerator, whether it
truly streams, max context, resident memory, and the **pinned version plus the
date it was verified** (invariant #8).

## Deliverable 2 — backend selection

`registry.py` detects platform and accelerator at runtime and picks a backend,
overridable by env var and by config. Selection order:

| Platform | Preferred | Fallback |
|---|---|---|
| Linux + NVIDIA | ONNX Runtime (CUDA/TensorRT EP) / llama.cpp CUDA | CPU |
| Linux ARM64 (Jetson) | same — **this is production target #1** | CPU |
| Windows + NVIDIA | ONNX Runtime (CUDA or DirectML EP) / llama.cpp CUDA | CPU |
| macOS Apple Silicon | llama.cpp Metal / ONNX Runtime CoreML EP | CPU |

**MLX is permitted only as an opt-in macOS backend, never as a default and never
imported at module scope.** It is measurably faster on the dev machine
(20–87% over llama.cpp on sub-14B models) which is exactly why it must not be
allowed to become load-bearing.

## Deliverable 3 — the automated portability check

A test that **fails the build** if any module under `wellsy/` outside
`inference/backends/` imports a platform-exclusive package. Banned list is in
INVARIANTS.md #14. Implement by AST-walking the source tree, not by grep, and
not by trusting a review.

## Deliverable 4 — the cross-platform benchmark harness

`wellsy bench` — one command, runs anywhere, no arguments required.

Must emit, per modality and per available backend: **cold-start load ms, p50 and
p95 over ≥ 20 trials, resident memory, RTF where applicable, platform,
accelerator, and pinned version.** Machine-readable output to
`spec/results/bench-<date>-<platform>-<commit>.jsonl` plus a human-readable
table.

This harness is how every later step proves it did not regress. Build it
properly now; it is cheap here and expensive later.

## Model selection — verify, do not copy from this document

The audit recommends these. **Invariant #8 applies: check each is still current,
confirm the license, confirm a genuinely portable path exists, and record the
version and verification date.** Do not install from these names on trust — an
earlier build shipped a TTS model chosen this way and it turned out to be
*slower than realtime*.

| Modality | Candidate | Portable path to verify |
|---|---|---|
| LLM / VLM | Qwen3-VL 4B (8B benchmarked slower for identical correctness) | GGUF via llama.cpp; ONNX Runtime GenAI |
| ASR | Qwen3-ASR 0.6B / 1.7B | ONNX exports exist; also `sherpa-onnx` |
| TTS | Qwen3-TTS — fast **and** instructable (natural-language tone control) | Official repo, ONNX pipelines, a pure-C engine, a Windows-native fork |
| TTS fallback | Kokoro-82M | Fast, flat, well-supported |
| VAD | Silero VAD | ONNX, runs everywhere |

Benchmark at least two candidates per modality against the harness before
choosing. Record the losing numbers too — the reason 4B shipped over 8B last
time is that both were measured.

## Acceptance

1. `wellsy bench` runs on macOS and produces the full table.
2. Each of the four interfaces has ≥ 2 backends, one of which is portable-only,
   and both pass an identical conformance test.
3. `LlmBackend.stream` demonstrably yields a first delta **before** the full
   answer completes — prove it with a timestamped test, and report the gap.
4. The portability check test exists and **fails** when a banned import is
   deliberately introduced (write that negative test).
5. Every adopted model has its version, license, and verification date recorded
   in `spec/model-inventory.md`.
6. No Linux box is available yet. Document exactly what `wellsy bench` will need
   on Linux/CUDA so it runs first time, and make the code path exist even though
   it cannot be executed today. **Say plainly in your report that the Linux path
   is unexecuted** — do not imply it was tested.

## Do not

- Do not wire this into the voice path yet; that is step 4.
- Do not build a plugin system, a config DSL, or a model manager. Four
  protocols, a registry, and a bench command.
- Do not let MLX become the default on any platform.
