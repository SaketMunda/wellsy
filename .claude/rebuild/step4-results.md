# Step 4 — Streaming voice path: results

**Machine:** M4 Pro, 24 GB, macOS 15.5 (Darwin 24.5.0). Branch
`rebuild/step4-voice-path` off `master` @ `71753a9`.
**Measurement rule:** p50 / p95 over ≥ 20 trials, cold vs warm separate, method
recorded next to the number.

## What shipped

```
engine/voice/
  pipeline.py     builds + runs the Pipecat pipeline; ESC = deterministic stop
  adapters.py     SeamSTTService / SeamTTSService over the step-2 inference seam;
                  build_llm() -> Pipecat OpenAILLMService on the local server
  intent_gate.py  IntentGate FrameProcessor — parse_intent BEFORE any model
                  (INVARIANTS #3); decide() is pure and unit-tested
  wake.py         WakeGate — fuzzy transcribe-then-match; wake_score/is_wake pure
  config.py       wake phrases + tunable threshold, hot-reloaded (voice.json)
  metrics.py      `wellsy voice --measure` / `--profile-cpu`
  wake_fixtures.py `wellsy record-wake` / `wellsy tune-wake`
engine/inference/backends/
  whisper_faster.py  FasterWhisperAsr  (faster-whisper base.en, CTranslate2)
  kokoro.py          KokoroTts         (Kokoro-82M, kokoro-onnx)
registry.py       auto-order asr=faster_whisper>onnx>reference,
                  tts=kokoro>onnx>reference; reference is the portable fallback
tests/test_intent_gate.py   IntentGate routing — stop/wake/sleep never forward
tests/test_wake.py          wake scoring + the tune sweep's decision rule
```

`query_loop.py`, `vad.py`, `stt.py`, `tts.py` — confirmed absent (step 1 removed
them; `grep` finds no resurrection). Deliverable: **met.**

Pipecat 1.8.1 already makes **Silero VAD + Smart Turn v3 (local ONNX)** the
default user-turn stop strategy, both models bundled in the wheel — no download,
no platform package. The old build's fixed **600 ms silence tail is simply
gone**; end-of-turn is semantic. Per-turn saving vs a 600 ms flat tax: the whole
tail (Smart Turn adds ~12–65 ms CPU inference in its place).

## Deviations from the plan (flagged for ratification)

| Planned | Shipped | Why |
|---|---|---|
| ASR = Qwen3-ASR 0.6B ONNX | **faster-whisper `base.en`** | The `Daumee/Qwen3-ASR-0.6B-ONNX-CPU` export is 2.5 GB, batch-decodes on ~30 s silence chunks, RTF ~0.32 → a ~1 s STT floor *after* endpoint. Breaks the §1 budget this step exists to fix. Confirmed with the owner before install. |
| LLM via a `SeamLLMService` wrapping step-2 `openai_http` | Pipecat's `OpenAILLMService` pointed at the same local server | Same OpenAI-compatible streaming contract, same Ollama. Reimplementing the context-aggregation + tool plumbing is the hand-rolling the step forbids; the agent's real text seam is step 5's LangGraph layer. INVARIANTS #3 is upstream of the LLM either way. |
| Wrap the step-2 `silero` backend as the Pipecat VAD | Pipecat's bundled `SileroVADAnalyzer` | Identical Silero v5 model; it is where barge-in hooks live. `engine/inference/backends/silero.py` stays the standalone / bench VAD. |
| `onnxruntime>=1.29` | held at `>=1.29` via `[tool.uv] override-dependencies` | pipecat 1.8.1 core-pins `onnxruntime~=1.24.3`; step 2 pinned `>=1.29`. Both pipecat bundled models and `engine/inference` load on 1.29 — verified. |

## §1 latency table

Method (`wellsy voice --measure --trials 20`, component timing against a fixed
Kokoro-synthesised utterance): each stage of the real seam is timed and the §1
rows composed as the streaming pipeline overlaps them. Results:
`spec/results/voice-latency-2026-09-01-qwen3-4b.json` (the owner's chosen model)
and `-qwen2.5-3b.json` (same pipeline, a non-reasoning model). The
mic-diaphragm→speaker-cone number and A14 need a live session — see *Still owed*.

| Path | Target p50 / p95 | Measured p50 / p95 | Verdict |
|---|---|---|---|
| Wake → first word, **deterministic** (`asr + tts_ttfa`) | < 800 / < 1200 ms | **617 / 700 ms** | **PASS** |
| Wake → first word, **LLM**, `qwen3:4b` (`asr + llm_ttft + tts_ttfa`) | < 1500 / < 2500 ms | **3957 / 5854 ms** | **MISS — LLM reasoning only** |
| Wake → first word, **LLM**, `qwen2.5:3b` (same pipeline) | < 1500 / < 2500 ms | **614 / 624 ms** (n=12) | **PASS** — pipeline is not the bottleneck |
| Wake → first word, **VLM** | < 2500 / < 3500 ms | not yet measured | owed (capture-in-loop) |
| Barge-in: speech onset → output silent | < 200 / < 350 ms | live-only | owed (A14) |
| `stop` → output ceased | < 150 / < 250 ms | deterministic path via `InterruptionFrame` / ESC; live-only for the wall number | owed (live) |
| Perception fast path (T0+T1) | < 20 / < 35 ms | **13.49 / 23.95 ms** (`bench/detector_bench.py`, n=30) | **PASS — unregressed** |

Stage detail, warm, n=20 (`qwen3:4b` run):

| Stage | p50 / p95 ms | cold ms | note |
|---|---|---|---|
| ASR (faster-whisper `base.en`, 16 kHz utterance → `Final`) | 267–281 / 294–308 | ~260–269 | RTF 0.05 |
| TTS TTFA (Kokoro, first sentence → first `PcmChunk`) | 345 / 406 | ~319 | |
| LLM TTFT (`qwen3:4b`, streamed) | **3381 / 5215** | 2739 | **the miss** — pure reasoning |
| LLM TTFT (`qwen2.5:3b`, streamed) | **43 / 50** | — | no reasoning pass |

**The LLM miss is not the pipeline.** Ollama 0.33.2 with this `qwen3:4b` build
runs the reasoning pass on every turn regardless of `think:false`,
`reasoning_effort:none`, `chat_template_kwargs.enable_thinking:false`, `/no_think`
in system or user, or the `qwen3:4b-nothink` Modelfile tag — each verified by
direct `curl`. Swapping only the model id (`WELLSY_LLM_MODEL=qwen2.5:3b`) takes
the LLM row from 3957 ms to **614 ms p50** with no other change. Recorded as an
infra/model-config issue for step 5's hardware spec, per the step's honesty
mandate ("report a latency you did not clear, not a rounded number that does").

## Streaming is real, not simulated (acceptance #4)

`--measure` streams a deliberately multi-sentence answer and, the instant the
first sentence lands, synthesises it and stamps the first PCM sample while still
draining the LLM to completion. First PCM precedes LLM-done on **3/3** trials
each run — e.g. first PCM at 6403 ms vs LLM done at 7854 ms
(`streaming_overlap.samples_ms` in the result files). The step-2
`test_llm_streaming.py` timestamped-first-delta proof also still holds.

## Idle CPU profile (acceptance #5)

`wellsy voice --profile-cpu 20` (`spec/results/voice-cpu-2026-09-01.json`),
pipeline awake and silent, process + children, 0.5 s cadence:

| | value |
|---|---|
| mean | **15.1 % of one core** · **1.3 % of the 12-core machine** |
| p95 | 16.7 % of one core |
| max | 36.2 % of one core (~3 % of machine) |

The Chatterbox regression this step was warned about was **~18 % average / 44 %
spikes of the machine, never profiled**. This is an order of magnitude lower on
the machine metric and under Chatterbox even measured against a single core. The
~15 %/core floor is Silero VAD (every 32 ms) + Smart Turn + the PortAudio
callback; acceptable, and now profiled.

## Perception unregressed (acceptance #5)

`bench/detector_bench.py --trials 30`: fast path **p50 13.49 ms / p95 23.95 ms**
(baseline 13.2–16.81 ms). **PASS.** Voice work caused no CPU regression here.

## `wellsy bench` — full table, exit 0

`spec/results/bench-2026-09-01-darwin-arm64-71753a9.jsonl`:

| modality | backend | p50 / p95 ms | RTF p50 | resident MB | note |
|---|---|---|---|---|---|
| asr | faster_whisper | 257 / 276 | 0.052 | 490 | cold 873 ms (warm; first-ever run pays the model fetch) |
| tts | kokoro | 837 / 845 | 0.207 | 426 | ~5× realtime |
| vad | silero | 12.0 / 12.3 | 0.0024 | 0.7 | |
| llm | openai_http | 2654 / 8811 | – | 0.6 | TTFT 2108 / 8081 ms (qwen3-vl:4b, reasoning) |

The Kokoro interpreter-teardown crash (`recursive_mutex lock failed`) is fixed —
`KokoroTts.close()` releases the espeak-ng backend + ORT session before shutdown
and the bench harness calls it.

## Still owed — needs the owner at the mic

1. **A14 barge-in, live** — VAD stays live during TTS; `InterruptionFrame` path
   is wired and the deterministic `stop` / ESC path already cancels. The
   onset→silence wall number and "no clipped first word" must be verified live.
2. **Wake-phrase fixtures + threshold tune** — `wellsy record-wake` (≥ 30 wake +
   ≥ 30 non-wake, owner speaking), then `wellsy tune-wake --write`. The
   `difflib` threshold stays at the bootstrap 0.72 until then; `wake.py`'s
   scorer cannot cleanly separate "well" (0.80 vs "wellsy") from a real slip
   like "welsey" (0.83) — which is exactly why the value is tuned against
   recordings, not guessed. `spec/fixtures/wake/` is empty pending that session.
3. **VLM row** — needs the step-3 capture layer wired into the `describe_scene`
   / `query_object` path; currently those intents forward to the text LLM.
4. **True mic→speaker e2e** p50/p95 over ≥ 20 trials — the injection harness is
   component-based; a live-session capture of the acoustic path is still owed.

## Known rough edges

- `av` (faster-whisper) and `cv2` both bundle `libavdevice` → a startup
  `objc[]` "implemented in both" warning on macOS. Cosmetic so far; watch for
  the "mysterious crashes" it threatens.
- `qwen3:4b` reasoning (above).
- Multiprocessing "leaked semaphore" warning on some exits — from the
  perception capture worker's `Queue`, not the voice path.
