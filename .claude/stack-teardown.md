# WELLSY — Stack Teardown and Rebuild Assessment

**Written 2026-09-01, after the Day 11 failure and the decision to rebuild.**
**Supersedes the tooling sections of `system-state.md` and `roadmap-phase1.md`.**

This document is a technical audit, not a plan. It records what was measured,
what is portable, and what has to be decided before code is written. Every
number here was taken on this machine or cited from a dated source.

Machine of record: Apple M4 Pro, 24 GB unified memory, macOS 15.5 (Darwin 24.5.0).
**This is the development machine. It is explicitly NOT the target platform.**

---

## 0. The three constraints that changed on 2026-09-01

1. **The deadline is released.** Owner: *"That's fine if it take days to rebuild,
   only thing I want is to make it fluent and perfect... No Bad experience."*
   The 15-day frame is retired. Fluency is now the acceptance bar, not the date.

2. **OS independence is now a hard requirement.** Owner: *"why we are only
   thinking on the basis of Apple infrastructure... ultimately it can be deployed
   to production and then we can go with Linux, Windows or whatever OS."*
   This invalidates the Apple-only recommendations made on 2026-08-31.

3. **The interface must be native, not a web HUD.** Owner: *"I do not want
   web-based interface it looks very cheap... It actually feels like JARVIS is
   running on desktop, not a HUD experience anymore. That school level project
   of showing on camera and just detection."*
   `src/` (5,264 lines of TypeScript) is not frozen. It is deleted.

Constraint 2 is the most expensive. It rules out MLX, `speech-swift`, and
ScreenCaptureKit as *core* dependencies. They may only appear as
platform-accelerated backends behind a portable interface.

---

## 1. Verified defect: screen capture returns the wallpaper

**Status: reproduced on this machine 2026-09-01. Root cause established.
Previous root-cause attribution in `engine/screen_capture.py` was wrong.**

### Evidence

```
$ screencapture -x engine/clips/_probe.png
exit=0
-rw-r--r--@ 1 saketmunda staff 10747568 ... _probe.png
```

The file is a valid 3024x1964 PNG. Its contents: the Finder menu bar and the
desktop wallpaper. **Zero application windows**, with windows demonstrably open
at capture time.

That image is what gets base64-encoded and sent to the VLM. When the owner asked
*"what's on my screen"* and the answer described a wallpaper, **the model was
correct**. It was shown a wallpaper.

### Root cause

macOS Screen Recording (TCC) permission. Without the grant, `screencapture` does
not fail — it strips the window layer and returns the desktop composite. This is
[a documented failure mode for non-bundled CLI executables](https://github.com/trycua/cua/issues/870).

### Why the code cannot detect it

`capture_screen()` raises only when `returncode != 0` or when no file was
written. On a permission-stripped capture, **both guards pass**:

| Guard | Behaviour on stripped capture |
|---|---|
| `result.returncode != 0` | False — exits 0 |
| `not frames` | False — a valid full-resolution PNG is written |

The function returns a garbage frame with full confidence. There is no
detection, no `UNIDENTIFIED` floor, and no provenance flag for it — a direct
violation of standing invariant #6 (never present a fabricated observation as
fact), reached by accident rather than by design.

### Correction to a previous claim

The module docstring attributes this exact symptom (*"desktop wallpaper instead
... the menu bar was visibly present"*) to `screencapture`'s `files` argument
being "1 file per screen." That multi-monitor bug is real and the fix for it is
correct, but **it is not the cause of this symptom**. The wrong root cause was
recorded on Day 11 and the real defect shipped underneath the fix.

### Caveat, stated rather than hidden

The probe above ran in the agent's process tree, which certainly lacks the
grant. This proves the failure mode is real, silent, and undetectable by the
current code. It does not by itself prove the engine's own process tree lacks
the grant. Given the live symptom was observed by the owner, it almost certainly
does — and per-process-tree TCC is already logged as an open problem for the
microphone.

### Required fix

Not a permission grant. A capture layer that:
- uses a supported per-OS API (see §5),
- **verifies the capture is non-degenerate** before it reaches the model,
- fails loudly with a permission message rather than answering about a desktop.

---

## 2. Why it is slow: the runtime is a generation behind, not the models

The model *choices* are mostly defensible. The **runtime layer** is not. There
is not one modern accelerated-inference package in `engine/.venv` — the stack is
PyTorch/MPS plus ONNX plus Ollama-on-llama.cpp, hand-wired with threads.

Verified on this machine:

| Fact | Value |
|---|---|
| Ollama version | 0.33.1 |
| Unified memory | 24 GB |
| Ollama MLX backend | **Gated to 32 GB+** — not active here |
| MLX packages in venv | **none** |
| Own engine code | 3,731 lines Python |
| `query_loop.py` alone | 777 lines (21% of the codebase) |
| `src/` | 5,264 lines TypeScript |

### Measured latency faults (from `day11-results.md` and `day11_bench.py`)

| Stage | Measured | Fault |
|---|---|---|
| STT (Moonshine base, ONNX) | ~1.35–1.40 s warm | Batch. No partials. Latency is paid in full before the next stage starts. |
| LLM (Qwen3-VL-4B via Ollama) | first token 1,693 ms / full 2,201 ms | **Not streaming.** 508 ms discarded on every turn. |
| TTS (Chatterbox Turbo, MPS) | RTF **1.1x–3.3x** | **Slower than realtime.** Generates the whole clip before playing a sample. |
| Turn end | fixed 600 ms silence tail | Flat tax on every single turn. |
| VAD | hand-rolled RMS + adaptive floor | Floor could latch and never recover (fixed post-Day-11). |

**These three stages are serial and fully buffered, so their latencies add.**
That is the architecture, not a tuning problem. It is why the product does not
feel realtime and cannot be made to feel realtime by optimisation.

---

## 3. New standing invariant: portability

> **Invariant #14 — No platform-exclusive API in the core.**
> The engine core must run on macOS, Linux, and Windows from one codebase.
> Platform-specific acceleration is permitted only as a swappable backend behind
> a portable interface, selected at runtime, with a portable fallback that is
> tested on every platform. A component with no portable path does not enter
> the core.

Every recommendation below is graded against this.

### What invariant #14 rules out as core dependencies

| Rejected | Reason |
|---|---|
| **MLX / mlx-lm / mlx-vlm** | Apple Silicon only. No Linux, Windows, or non-Apple hardware. |
| **`speech-swift` / Soniqo** | Swift, macOS/iOS only. |
| **ScreenCaptureKit** | macOS only — permitted as the macOS *backend*, not the interface. |
| **Ollama's MLX backend** | Apple-only, and RAM-gated out on this machine anyway. |
| **CoreML** | Apple only. |

This is a genuine cost. MLX is measurably the fastest path on the development
machine — [20–87% over llama.cpp on sub-14B models](https://willitrunai.com/blog/mlx-vs-ollama-apple-silicon-benchmarks),
which is exactly the model class in use. Portability is being bought with
single-platform peak throughput. That trade is the owner's call and it has
been made.

---

## 4. Portable runtime layer

The core question is what replaces "Ollama + PyTorch/MPS + ONNX, wired by hand."

| Runtime | Platforms | Accelerators | Verdict |
|---|---|---|---|
| **llama.cpp / GGUF** | Linux, Windows, macOS, iOS, Android | Metal, CUDA, Vulkan, ROCm, CPU | **Core LLM/VLM runtime.** Broadest hardware reach of any option. |
| **ONNX Runtime** | Linux, Windows, macOS, mobile, embedded | CUDA, TensorRT, DirectML, CoreML, ROCm, CPU | **Core runtime for the small models** — ASR, TTS, VAD, turn detection. Strongest vendor-neutrality story. |
| **vLLM / SGLang** | Linux + NVIDIA | CUDA | Server-side only. Correct choice for a Linux production deployment; cannot be the only path. |
| **MLX** | macOS/Apple Silicon only | Metal | **Optional macOS backend only.** Never the interface. |
| **ExecuTorch** | Cross-platform incl. mobile | Multiple | Worth tracking for the eventual mobile target; not core today. |

### The shape this forces

One `InferenceBackend` interface per modality (LLM, VLM, ASR, TTS), with:

- a **portable default** — ONNX Runtime for small models, llama.cpp for large,
- **optional accelerated backends** — MLX on Apple Silicon, TensorRT/vLLM on
  Linux+NVIDIA, DirectML on Windows,
- backend selected at runtime by capability detection,
- **the same benchmark harness run against every backend on every platform.**

That harness is not optional. Without it, "OS independent" degrades into "runs
badly everywhere," which is the failure mode this rebuild exists to avoid.

---

## 5. Component recommendations, portability-graded

| Component | Current | Recommended | Portable path |
|---|---|---|---|
| **ASR** | Moonshine base ONNX, batch | **Qwen3-ASR 0.6B/1.7B** — ~1.32% WER, 30–36x realtime | ONNX exports exist ([0.6B](https://huggingface.co/Daumee/Qwen3-ASR-0.6B-ONNX-CPU), [export pipelines](https://github.com/andrewleech/qwen3-asr-onnx)); also `sherpa-onnx` (Linux/Win/macOS/mobile/embedded) |
| **TTS** | Chatterbox Turbo, MPS, RTF 1.1–3.3x | **Qwen3-TTS** — ~97 ms streaming latency, and *instructable* (natural-language tone control) | [Official repo](https://github.com/QwenLM/Qwen3-TTS), ONNX pipelines, a [pure-C engine](https://github.com/gabriele-mastrapasqua/qwen3-tts). Windows-native fork exists. |
| **VAD** | hand-rolled RMS energy | **Silero VAD** | ONNX, runs everywhere |
| **Turn detection** | fixed 600 ms tail | **Pipecat Smart Turn v3** — semantic end-of-turn, 23 languages, no GPU required | Local, portable |
| **LLM / VLM** | Ollama → llama.cpp/Metal | Qwen3-VL 4B/8B — keep the model, replace the runtime | llama.cpp/GGUF directly, or ONNX Runtime GenAI |
| **Detector** | YOLOE + ByteTrack, PyTorch | **Keep.** 16.81 ms p50 measured. | Already portable (PyTorch CUDA/MPS/ROCm/CPU) |
| **Screen capture** | `screencapture` CLI | Per-OS backend behind one interface + **degenerate-capture verification** | `mss` is portable but uses Core Graphics on macOS — **same TCC failure**. macOS needs a ScreenCaptureKit backend. |
| **Orchestration** | 777 lines of hand-rolled threads | **Pipecat** — streaming frames, barge-in, turn detection as primitives | Python, cross-platform |

**Note on TTS:** Qwen3-TTS is both faster than Chatterbox *and* expressive —
natural-language tone instruction ("say this skeptically, accelerating at the
end"). It satisfies the long-standing request for human-like, emotional speech
while *reducing* latency. Kokoro-82M becomes the fast-but-flat fallback, not the
target.

---

## 6. The architectural fork — RESOLVED 2026-09-01 as D49, see §12

This is the single biggest open decision and it is not obvious.

### Option A — Full-duplex speech-to-speech

**NVIDIA PersonaPlex 7B** (built on Kyutai Moshi; code MIT, weights under NVIDIA
Open Model License permitting commercial use). Audio tokens in, audio tokens
out. There is no STT→LLM→TTS chain, so there are no latencies to add.

Measured on FullDuplexBench:

| Metric | PersonaPlex | Moshi | Gemini Live |
|---|---|---|---|
| Average latency | **205 ms** | — | — |
| Speaker-switch latency | **0.07 s** | — | 1.3 s |
| Interruption success | **100%** | 60.6% | 43.9% |

Portability: the reference implementation is PyTorch (portable, CUDA/CPU). The
MLX port is macOS-only and would be an optional backend, not the core.

**Cost:** there is no text bottleneck. Tool calls, memory retrieval, and the
policy gate have nowhere clean to sit between "heard" and "spoke." This
collides directly with the agent roadmap and with standing invariant #3
(`parse_intent` owns `stop`/`wake`/`sleep`).

### Option B — Cascaded but genuinely streaming

Pipecat + portable ASR/LLM/TTS, sentence-chunked so generation and playback
overlap instead of serialising.

**Gets:** roughly 600 ms–1 s to first word. 5–6x better than today, not 20x.
**Keeps:** text as the seam where tools, memory, permissions and the
deterministic safety path live. Invariant #3 survives intact.

### Option C — Both, with a router

S2S for conversation; cascaded for anything that touches a tool or memory.
More work than either. Probably correct.

**This must be decided before any code is written.** It determines the shape of
everything above it.

### Memory arithmetic (24 GB development machine)

PersonaPlex 4-bit (~5.3 GB) + Qwen3-VL-4B (~3.3 GB) + YOLOE + Qwen3-TTS fits.
A 14B text brain resident alongside does not. The ceiling has not moved.

---

## 7. Native interface

`src/` is deleted. A browser HUD is not the product.

| Framework | Rendering | Platforms | Verdict |
|---|---|---|---|
| **Qt Quick / QML via PySide6** | GPU scene graph, not a webview | macOS, Linux, Windows, Android | **Recommended.** Same process as the Python engine — no IPC bridge, no serialisation tax on perception events. Mature, GPU-accelerated, frameless/translucent windows on all three. |
| **Flutter desktop** | Own GPU renderer (Skia/Impeller) | macOS, Linux, Windows | Strong animation story, arguably the best-looking result. **Cost: Dart.** A second language and an IPC bridge to the Python engine. |
| **Tauri** | **WebView** | All | **Rejected.** It is a browser in a window — the exact thing the owner rejected. |
| **Electron** | Chromium | All | Rejected, same reason, worse. |
| **SwiftUI** | Native | macOS only | Rejected under invariant #14. |

**Recommendation: PySide6 + Qt Quick/QML.** The decisive factor is not looks —
Flutter probably wins on looks. It is that the UI runs *in the engine's process*.
A JARVIS-feel interface is driven by a continuous stream of perception events at
8 Hz plus audio-reactive visuals; an IPC bridge between Dart and Python
reintroduces exactly the serialisation and buffering discipline this rebuild is
trying to eliminate.

**Licensing note, flagged rather than buried:** PySide6 is LGPLv3. Fine for
dynamically-linked distribution. A commercial Qt licence is required for static
linking and for some app-store distribution models. Decide before shipping, not
after.

---

## 8. Scrap / keep

### Scrap

| Component | Lines | Reason |
|---|---|---|
| `query_loop.py` | 777 | Hand-rolled thread orchestration. Replaced by Pipecat. |
| `vad.py` | 85 | Energy VAD. Replaced by Silero + Smart Turn. |
| `stt.py` | 79 | Batch. Replaced by streaming ASR. |
| `tts.py` | 227 | Slower than realtime. Replaced. |
| `screen_capture.py` | 108 | Wrong API, silent garbage output. |
| `llm.py` | 160 | Ollama-coupled, non-streaming. |
| `src/` | 5,264 | Web HUD. Not the product. |
| **Total** | **~6,700** | |

### Keep

| Component | Lines | Reason |
|---|---|---|
| `motion.py` | 48 | ~1 ms T0 gate. Works. |
| `detector.py` | 100 | YOLOE open-vocab. 16.81 ms p50. Portable. |
| `tracker.py` | 108 | ByteTrack. Works. |
| `capture.py` | 126 | Process-per-workload, depth-1 latest-wins queue. The right discipline. |
| `tiers.py` | 103 | T0–T3 scheduler + `PreemptionSeam`. Genuinely original; not the source of any latency complaint. |
| `provenance.py` | 97 | The honesty layer. The project's actual differentiator. |
| `intent.py` | 101 | Deterministic safety path. Invariant #3. |
| **Total** | **~680** | |

Roughly a **70% rewrite around a preserved perception core.** Not a greenfield.
The perception numbers are good and none of the latency complaints point at them.

---

## 9. Rename: YAP → WELLSY

238 occurrences across ~38 files. The majority are `.claude/` documentation.
In shipped code: 4 engine files, `wake_phrases.txt`, `package.json`,
`index.html`, and `WEIGHTS_DIR` (`~/.cache/yap-engine`).

Phonetically an improvement: "yap" collided with "app" in a single-syllable,
plosive-final way the ASR repeatedly mis-heard. "Wellsy" is two syllables with a
medial `/s/` that survives a quiet microphone and has no common English
near-neighbour. The soft `/w/` onset will want the fuzzy-match threshold retuned.

---

## 10. Open decisions — blocking

| # | Decision | Blocks |
|---|---|---|
| ~~D49~~ | ~~§6 fork~~ | **RESOLVED 2026-09-01 — cascaded streaming (Option B) now, S2S as a later conversation mode. See §12.** |
| **D50** | UI: PySide6+QML (recommended) or Flutter | Interface work. **Rescoped by D49 — see §12.4.** |
| ~~D51~~ | ~~Target production platform~~ | **RESOLVED by the embodiment goal — Linux/ARM64/CUDA (Jetson) is target #1. See §12.2.** |
| **D52** | Whether a portable-only stack is acceptable given the measured MLX advantage on the dev machine | Accepted in principle via invariant #14; needs confirming once the first cross-platform benchmark exists |

---

## 11. Sources

- [MLX vs Ollama on Apple Silicon (2026) — benchmarks & memory](https://willitrunai.com/blog/mlx-vs-ollama-apple-silicon-benchmarks)
- [Ollama is now powered by MLX on Apple Silicon (preview)](https://ollama.com/blog/mlx)
- [llama.cpp vs MLX — cross-platform runtime comparison](https://cactuscompute.com/compare/llama-cpp-vs-mlx)
- [Comparative study of MLX, MLC-LLM, Ollama, llama.cpp (arXiv)](https://arxiv.org/pdf/2511.05502)
- [NVIDIA PersonaPlex preprint](https://research.nvidia.com/labs/adlr/files/personaplex/personaplex_preprint.pdf)
- [PersonaPlex full-duplex latency reporting](https://winbuzzer.com/2026/01/27/nvidia-personaplex-open-source-voice-ai-full-duplex-xcxwbn/)
- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) · [pure-C engine](https://github.com/gabriele-mastrapasqua/qwen3-tts) · [ONNX export](https://github.com/elbruno/ElBruno.QwenTTS)
- [Qwen3-ASR ONNX](https://github.com/andrewleech/qwen3-asr-onnx) · [0.6B ONNX CPU](https://huggingface.co/Daumee/Qwen3-ASR-0.6B-ONNX-CPU) · [sherpa-onnx](https://k2-fsa.github.io/sherpa/onnx/index.html)
- [Pipecat Smart Turn](https://docs.pipecat.ai/api-reference/server/utilities/turn-detection/smart-turn-overview)
- [ScreenCaptureKit — capturing screen content](https://developer.apple.com/documentation/ScreenCaptureKit/capturing-screen-content-in-macos)
- [screencapture desktop-only defect report](https://github.com/trycua/cua/issues/870)
- [Which Python GUI library in 2026](https://www.pythonguis.com/faq/which-python-gui-library/)
- [ExecuTorch cross-platform voice agents](https://pytorch.org/blog/building-voice-agents-with-executorch-a-cross-platform-foundation-for-on-device-audio/)

---

## 12. Addendum, 2026-09-01 — WELLSY is an agent, and the endgame is a body

Owner statement: *"WELLSY is an agent... it can schedule meetings, do research
for me, do bookings, browse for me, full access of the compute, full autonomous
and robust, a complete robot without physical body, ultimately we can give them
a body by using Chinese Humanoids. Then it will have its own GPU, CPU etc. Maybe
we might not need an interface at all at the end."*

This resolves D49 and D51, and rescopes D50.

### 12.1 D49 — RESOLVED: cascaded streaming (Option B) now, S2S later

An agent requires a **text bottleneck**. Every tool call, every policy decision,
every memory write, and every audit line is text. Full-duplex speech-to-speech
has no such seam by construction — audio tokens go in and audio tokens come out,
with nothing addressable in between.

Choosing S2S as the core would mean an agent that converses beautifully and
cannot be permissioned, audited, or given memory. That is the opposite of the
stated goal.

**Decision:** cascaded-but-streaming core (Pipecat + portable ASR/LLM/TTS,
sentence-chunked so generation and playback overlap). Target ~600 ms–1 s to
first word. `parse_intent` keeps owning `stop`/`wake`/`sleep` — invariant #3
survives.

**PersonaPlex is not discarded.** It becomes an optional *conversation mode*
engaged when no agentic work is in flight, with the router handing control back
to the cascaded path the moment a tool is needed. That is Option C, staged —
and it is deliberately not Phase 1 work.

### 12.2 D51 — RESOLVED: Linux / ARM64 / CUDA is production target #1

The embodiment endgame settles the platform question that invariant #14 left
open. Chinese humanoid platforms run Linux with NVIDIA Jetson onboard:

| Platform | Onboard compute | Stack |
|---|---|---|
| Unitree G1 EDU | Jetson Orin NX, **100 TOPS** | Full ROS 2 / Python / C++ SDK |
| Unitree G1 Comp | Jetson Orin, 157 TOPS | ROS 2 |
| Unitree H2 Plus (NVIDIA reference design, late 2026) | **Jetson AGX Thor**, up to 2070 FP4 TFLOPS | Isaac GR00T |

Consequences:

- **macOS is a development convenience, nothing more.** MLX is now firmly out of
  the core, and the earlier Apple-first research is superseded.
- **The accelerated backend to build first is CUDA / TensorRT via ONNX Runtime
  on Linux ARM64**, not a desktop-Windows path.
- **The compute budget gets tighter at embodiment, not looser.** A Jetson Orin
  NX at 100 TOPS with typically 16 GB is *less* headroom than the 24 GB M4 Pro
  this was developed on. Any design that assumes it can grow into the robot's
  hardware is wrong. Size the models for Orin NX and let the desktop have the
  slack — not the reverse.
- **ROS 2 becomes the eventual integration boundary.** No ROS work now, but the
  perception/agent seam must stay message-shaped. The existing
  process-per-workload topology with depth-1 latest-wins queues maps onto ROS 2
  pub/sub with QoS `KEEP_LAST(1)` almost directly — the drop-don't-buffer
  discipline in `capture.py` is already the right shape and survives into the
  body.

### 12.3 Agent runtime — LangGraph

Confirmed against 2026 sources rather than carried over from the roadmap.

| Option | Verdict |
|---|---|
| **LangGraph** | **Chosen.** Durable checkpointing at every node, native human-in-the-loop `interrupt()`, deepest observability. The interrupt primitive maps 1:1 onto the §13 permission gate and onto §26 autonomy levels — the approval gate *is* the interrupt, not a thing built beside it. |
| Pydantic AI (+ Temporal / DBOS / Prefect / Restate) | Lighter, type-safe, less code. The stronger choice for a single agent with simple state. Rejected because checkpoint-and-resume is load-bearing here, not incidental. |
| Hand-rolled `while` loop | Rejected. This is what `query_loop.py` already is, and it is 777 lines of the reason for the rebuild. |

Verify current versions before pinning (invariant #8).

### 12.4 D50 rescoped — the interface is a client, not the product

The owner expects the interface may eventually disappear. That does not mean
building nothing now; it means **building it so it can be removed without
touching the core.**

- The agent runtime exposes a local API. The UI is one consumer of it. So is a
  future ROS 2 node, and so is a headless daemon.
- Scope for Phase 1: **control surface, approval prompts, audit viewer,
  perception state.** Native, GPU-rendered, not a webview — PySide6 + Qt Quick
  as recommended in §7.
- The ambient JARVIS showpiece is explicitly *not* Phase 1. It is earned once
  the agent is worth watching.

Effort saved here goes into the agent runtime, which is now the product.

### 12.5 Autonomy and full compute access — stated once, plainly

The goal is *"full access of the compute, full autonomous."* The engineering
consequence, recorded so it is not discovered later:

An autonomous agent with unrestricted compute access and no interface has **no
rollback path and no way to report what it did.** The policy gate (§13) and the
audit log (§29) are not friction slowing autonomy down — they are the only
mechanism by which autonomy can be raised safely, because they are the only
evidence that a given class of action can be trusted unsupervised.

**Therefore autonomy is a level, not a switch**, and it rises against the audit
log rather than against confidence. Concretely: risk-0/1 reversible actions run
silently from the start; risk-2 requires approval until the audit log shows a
clean run of them; risk-3 (delete, shell, writes outside allowed roots) stays
gated indefinitely by default. Unannotated tools default to risk 3 and fail
closed (invariant #9).

This is the path to the stated goal, not a detour around it. An agent that
destroys something once, silently, with no interface to report it, is not
robust — it is single-shot.

### 12.6 What this means for the perception core

Unchanged, and now better justified. `motion.py`, `detector.py`, `tracker.py`,
`capture.py`, `tiers.py`, `provenance.py`, `intent.py` (~680 lines) survive the
rebuild *and* survive embodiment. A robot needs a cheap always-on motion gate,
an open-vocabulary detector, stable track IDs, and a provenance layer that
refuses to fabricate — more than a desktop assistant does, not less.

The T0–T3 tier scheduler is the part of this project that most directly
anticipates a body. Keep it.

### 12.7 Sources for this addendum

- [LangGraph — agent orchestration](https://www.langchain.com/langgraph) · [LangGraph in production](https://www.alphabold.com/langgraph-agents-in-production/)
- [Pydantic AI](https://pydantic.dev/pydantic-ai) · [durable agents with Pydantic AI + Temporal](https://temporal.io/blog/build-durable-ai-agents-pydantic-ai-and-temporal)
- [NVIDIA Isaac GR00T open humanoid reference design (Unitree H2 Plus + Jetson Thor)](https://nvidianews.nvidia.com/news/nvidia-open-humanoid-robot-reference-design)
- [Unitree G1 EDU — Jetson Orin NX, ROS 2 SDK](https://robostore.com/collections/g1-edu-humanoid-robots) · [Unitree G1 2026 guide](https://www.zmprobots.com/blog/unitree-g1-complete-guide-2026/)
