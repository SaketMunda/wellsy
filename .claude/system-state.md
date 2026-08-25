# YAP — System State

**As of 2026-08-25, end of Day 11.** Machine of record: Apple M4 Pro, 24 GB,
macOS 24.5. Everything runs locally; no third-party network calls at
runtime. Every number below is measured on that machine, not estimated.

This document describes **what exists now**, not how it got here. Step-by-step
history is in `decisions.md` (D1–D44) and the `dayN-results.md` files.

---

## 1. What the product is

A local, always-on perception and conversation system. A camera watches the
room continuously at low cost; when you speak to it, it answers questions
about what it can see — the room through the webcam, or your screen — using a
local vision-language model that actually receives pixels. Everything is
spoken, offline, and logged with provenance.

There are two codebases in the repo. **Only one is live.**

| | Python engine (`engine/`) | Browser build (`src/`) |
|---|---|---|
| Status | **Active product** | Frozen legacy / demo shell |
| Detector | YOLOE (open vocabulary) | COCO-SSD, 80 fixed classes (2017) |
| Voice | Full loop (mic → answer → speaker) | Web Speech API |
| Reasoning | Qwen3-VL-4B, sees pixels | Template bank + WebLLM |
| Role today | Everything | Renders the HUD from engine data over WebSocket |

The browser build still runs standalone with no engine (`npm run dev`), but
it is not where development happens. Its detector, narrator, and intent
parser are superseded by Python equivalents.

---

## 2. Process and thread topology

Multi-process by design, not by accident — decided at D29 (`decisions.md`):
one workload per process, connected by **latest-wins queues of depth 1**.
Frames are dropped, never buffered. A slow consumer sees a stale-but-recent
frame; it never sees a growing backlog.

```
┌──────────────────────┐   mp.Queue(depth 1, latest-wins)   ┌────────────────────────────┐
│ capture process      │ ─────────────────────────────────▶ │ main process               │
│ capture.py           │                                    │ main.py                    │
│  cv2.VideoCapture    │                                    │  T0 motion gate  (1ms/frame)│
│  ~30fps              │                                    │  T1 detect+track (8 Hz cap) │
└──────────────────────┘                                    │  emit() JSONL → stdout      │
                                                            └───┬──────────────┬─────────┘
                                          PreemptionSeam        │              │
                          ┌─────────────────────────────────────┘              │
                          ▼                                                    ▼
              ┌───────────────────────────┐                        ┌────────────────────┐
              │ T3 query threads          │                        │ bridge.py          │
              │  query_loop.py            │                        │  websockets sync   │
              │   • _wake_thread  (mic)   │                        │  127.0.0.1:8765    │
              │   • _ptt_thread   (Enter) │                        │  broadcast @ 8 Hz  │
              │   • greeting.py           │                        └─────────┬──────────┘
              │   • TTS playback thread   │                                  │
              └───────────┬───────────────┘                                  ▼
                          │  HTTP localhost:11434                   browser HUD (React)
                          ▼                                          src/hud/*, canvas
              ┌───────────────────────────┐
              │ Ollama (separate daemon)  │
              │  qwen3-vl:4b, Metal/GGUF  │
              └───────────────────────────┘
```

Capture is a real `multiprocessing.Process` (GIL isolation for the camera).
T3, the bridge, and TTS are threads inside the main process; they are I/O- or
subprocess-bound, so the GIL is not the constraint there.

---

## 3. The tier scheduler

The central design idea. Cost is proportional to how much the moment
warrants, and the expensive tiers only run when something asks for them.

| Tier | What runs | Trigger | Cost |
|---|---|---|---|
| **T0** | Frame differencing at 160×120 grayscale, mean abs pixel delta, threshold 5.0 | **Every frame, unconditionally** | ~1 ms |
| **T1** | YOLOE open-vocab detect + ByteTrack | Motion above threshold, rate-capped to 8 Hz, held warm 1.0 s after last motion | 22–33 ms inference |
| **T2** | Deep look on one track (`tiers.deep_look`) | — | **Stub. Returns `None`.** |
| **T3** | Wake/PTT → STT → intent → answer → TTS | Speech or Enter key | See §7 latency budget |

**T0 is never gated.** The gate itself always runs — the thing it suppresses
is T1's own periodic schedule.

**`MOTION_HOLD_SECONDS = 1.0`** is hysteresis. Without it, a person pausing
mid-gesture freezes on screen the instant motion drops below threshold.

`MOTION_THRESHOLD = 5.0` was tuned against two real clips, not synthetic
frames: measured ambient noise floor p50 ≈ 1.0–1.3 with spikes to 4.2; a real
hand movement spiked to 6.2.

### PreemptionSeam (`tiers.py`)

The hand-off between the T1 loop (owns the camera and detector) and the T3
threads (own the mic and speaker). When a query is in flight:

1. T3 calls `request_fresh_look()`.
2. The seam goes `active`; T1's periodic 8 Hz schedule **stops**.
3. The main loop sees the pending request, runs exactly one detection on the
   current frame, and calls `deliver_fresh_look(tracks, inference_ms, frame_bgr)`.
4. T3 gets a *guaranteed fresh* frame + tracks — never a stale answer.
5. `finally:` releases the seam, whatever happened.

Verified end-to-end at Day 10 (60 frames with `preemptionActive: true` and
exactly one non-null `inferenceMs`). The `try/except/finally` around the
release is load-bearing: an earlier version leaked an Ollama exception up
into the wake thread, silently killing it *and* leaving the seam stuck
`active` forever, which froze ambient sensing permanently. That path now has
a regression test (`test_query_loop.py`) driven by an always-raising fake LLM
and an always-raising fake screen capture.

---

## 4. Perception

### 4.1 Camera — open-vocabulary detection

- **Model:** YOLOE `yoloe-11s-seg.pt` via Ultralytics on PyTorch/MPS, plus a
  MobileCLIP-BLT text encoder (~570 MB) for the prompt head.
- **Vocabulary is a text file.** `engine/prompts.txt` — one term per line,
  hot-reloaded on `mtime` change while running, no restart. Currently 18
  terms including `microphone`, `empty office chair`, `blanket`, `headphones`.
  Adding a word makes the model able to name that thing. This is the actual
  fix for the browser build's fixed-80-class ceiling.
- **Rate:** 8 Hz cap. Not 30 — the browser HUD interpolates boxes at render
  rate (τ = 70 ms exponential), so faster detection buys nothing visible.
- **Confidence floor:** anything below `UNCERTAIN_CONFIDENCE = 0.35` is
  relabeled `UNIDENTIFIED` rather than trusted. Open vocabulary does not mean
  open credulity.

### 4.2 Tracking

ByteTrack (via `supervision`), 8 fps configuration. Emits track dicts shaped
to match the browser's TypeScript `Track` type so the WebSocket bridge is
plumbing, not translation:

```
{id, label, score, bbox[x,y,w,h], ageMs, missedFrames,
 labelConfidence, runnerUpLabel, labelVotes{label: count}}
```

Each track holds a rolling window of its last **15** label observations and
votes. `labelConfidence` and `runnerUpLabel` are exposed rather than
collapsed — the HUD and the voice layer both know when a label is contested.

### 4.3 Screen

`screen_capture.py` — `screencapture -x`, **on demand only**. No loop, no
timer, no background thread; the module is one function.

- Captures **every attached display**, not just the primary. (`screencapture`'s
  `files` argument is documented as "1 file per screen"; the single-path
  version silently answered about the wrong monitor every time on a
  multi-display setup.) All captured displays go to the VLM.
- Routed by a fixed keyword list in `query_loop.py` (`"my screen"`,
  `"my monitor"`, `"on my computer"`, …), checked *before* any capture runs.
  Deliberately **not** in `intent.py`, which stays reserved for
  safety-critical intents.
- Scratch file lands in `engine/clips/`, never `/tmp`, and is deleted before
  the function returns. Nothing about screen content is retained beyond a
  provenance line's `frameSource: "screen"`.
- **203.9 ms** for a real 1920×1080 capture.

---

## 5. Voice path

The full chain, in order:

```
sounddevice InputStream (16 kHz mono int16)
  └─ 30 ms frames ─▶ EnergyVad.is_speech()
       └─ pre-roll 0.3s + capture-until-0.6s-silence (cap 6–8s)
            └─ gain normalize ─▶ Moonshine base (ONNX) ─▶ transcript
                 └─ fuzzy wake match (difflib ≥ 0.72)  OR  in conversation window
                      └─ parse_intent()  ── deterministic grammar
                           ├─ stop / wake / sleep / help  → immediate, no model
                           ├─ describe_scene / query_object → tracks only, ~17 ms
                           └─ unknown → VLM (§6)
                                └─ Chatterbox Turbo ─▶ sounddevice output
```

### 5.1 VAD (`vad.py`)

Energy-based, adaptive noise floor, 30 ms frames at 16 kHz.
`SPEECH_RATIO = 2.5` over an EMA floor. Two absolute guards, both added in
response to real captured audio:

- `MIN_ABSOLUTE_SPEECH_RMS = 300` (int16 scale) — a floor-independent gate.
  Without it, in a quiet room the adaptive floor decays toward true silence
  and a fan hum or a breath clears `2.5 × floor`. Real captured wake buffers
  with peak amplitude 0.004–0.023 (a spoken word peaks 0.1–0.9) were being
  classified as speech and handed to STT, which correctly transcribed nothing.
- `STUCK_FLOOR_RECOVERY_DECAY = 0.995` (τ ≈ 6 s) — the floor now adapts
  *during* speech frames too, ~200× slower. Previously it only adapted on
  non-speech frames, so a mic whose ambient RMS started above
  `50.0 × 2.5` classified every frame as speech **forever**, with no path to
  self-correct. The observed symptom was a 90-second session of "speech
  detected, transcribed nothing" — it was capturing continuous room noise.

### 5.2 STT (`stt.py`)

**Moonshine `base`** via `useful-moonshine-onnx`, loaded once and held in
memory. (`moonshine_onnx.transcribe()` reloads from disk on every call —
~1.35 s even warm — which is unusable in a query loop.)

Upgraded from `tiny` after live evidence: `tiny` heard "hey yap" as "app"
consistently and garbled full questions badly enough to misroute intent.

**Gain normalization** on every clip before transcription: peak-normalize
toward `TARGET_PEAK = 0.9`, capped at `MAX_GAIN = 20×`, skipped below a
near-silence threshold so it can't amplify a noise floor into full-scale
garbage. Added because this user's mic runs quiet, and a small model fed a
low-amplitude signal has little headroom above its own quantization noise —
it guesses at whatever sounds close, producing plausible wrong words
("what do you see" → "or do you see") rather than empty output.

### 5.3 Wake and turn-taking (`query_loop.py`)

- **Transcribe-then-fuzzy-match**, not a trained keyword spotter. Phrases live
  in `wake_phrases.txt`, hot-reloaded. `difflib` ratio ≥ 0.72, which tolerates
  "hey app" / "hay yap" / "hey yeah".
- Wake transcription fires **once per detected phrase boundary** (speech → a
  0.35 s pause), with a 0.5 s cooldown. It previously fired on every VAD-positive
  30 ms frame — dozens of transcriptions per second competing with the detector
  for CPU, which is what made answers feel late.
- **Capture starts at speech onset**, not on a timer, with a 0.3 s pre-roll for
  the onset the VAD takes a beat to react to. A fixed rolling window was tried
  and abandoned: whatever its length, most of it is room silence.
- **Conversation window: 10 s.** After any answered command the wake phrase is
  not required again, and the window re-extends on each answer.
- **Push-to-talk:** Enter key, bypasses wake matching entirely.
- **Unprompted greeting** (`greeting.py`): when a `person` track transitions
  absent → present, YAP speaks one JARVIS-style greeting and opens the same
  conversation window — so the first thing you say after walking into frame
  needs no wake phrase. 120 s re-greet cooldown so occlusion doesn't retrigger.
  This is the *only* always-on unprompted speech; ambient narration
  (`ambient.py`, 4 s min interval) is opt-in and off by default.
- **Empty-transcript wake buffers are dumped to `clips/wake_debug/`** (ring of
  20) so a failure can be listened to rather than theorized about.

### 5.4 Intent (`intent.py`)

A **pure, deterministic, regex grammar.** No model, no async, no LLM. It owns
the safety path — `stop`, `wake`, `sleep` — and an LLM must never decide
whether "stop" stops. Falls through to `unknown` on off-script phrasing,
which is what routes to the VLM.

`"stop"` also interrupts mid-utterance: `stop_speaking()` cancels an in-flight
TTS clip. Measured cancel-mid-playback: **114 ms**.

Ported from `src/voice/parseIntent.ts`; both implementations are tested
against the same shared fixture file `spec/intent-cases.json`.

### 5.5 TTS (`tts.py`)

**Chatterbox Turbo** (`ResembleAI/chatterbox-turbo`, MIT), on MPS. Replaced
macOS `say -v Samantha` mid-Day-11 on direct instruction.

Measured on this machine, and it does **not** match the model card:

| | Measured (MPS) | Claimed (CUDA) |
|---|---|---|
| Cold model load | 7693 ms, once at startup | — |
| `"okay."` | 3167 ms | — |
| `"i am listening."` | 1652 ms | — |
| `"yes, one person in view."` | 2269 ms | — |
| Real-time factor | **1.1×–3.3× (slower than realtime)** | 6× faster |

Two device-level fixes, both from live "first words cut off" reports:
`_warm_audio_device()` plays one silent buffer at startup because `sd.play()`
opens a cold PortAudio stream whose first samples get clipped; and
`LEAD_SILENCE_SECONDS = 0.12` is prepended to every clip as a backstop,
because `sd.play()` opens a fresh stream on *every* call, not just the first.

Resemble's invisible watermarker stays enabled. It required pinning
`setuptools<81` (its `perth` submodule imports `pkg_resources`, dropped by
modern setuptools) — disabling the watermarker would have been the easier
fix and the wrong one.

---

## 6. Reasoning

**Model: Qwen3-VL-4B-Instruct (`qwen3-vl:4b`), Apache 2.0, served by Ollama
over `http://localhost:11434/api/chat`, native Metal.** Not Docker, not an API.

Before Day 11 this was a *blind* chain:

```
frame → YOLOE → tracks → describe_scene() string → qwen2.5:7b (never sees pixels) → answer
```

Every grounding failure was that chain inventing detail a word list gave it no
way to know: *"you're standing next to the chair"* (the user was sitting),
*"you're holding glasses"* (the user was holding nothing; `glasses` was merely
a confident label somewhere in frame).

Now `Llm.respond()` takes `frame_bgr` and sends it as a base64 JPEG (q=85) in
Ollama's `images` field. **Tracks are passed as a separately labelled
corroboration block, not as the source of the answer** — the model can
cross-check them or note a mismatch. The few-shot "don't invent furniture"
grounding hack was deleted; it existed to walk a blind model through a problem
a seeing model does not have.

Both prior failures were re-tested verbatim against the real pipeline:

| Question | Day 10 (blind) | Day 11 (seeing) |
|---|---|---|
| "what am I doing right now?" | "You're standing next to the chair" | "You're sitting in a chair, wearing headphones…" |
| "what am I holding?" | "you're holding glasses" | "I don't see anything in your hands." |

The second is the thesis in one line: `glasses` was a confident 1.0 tracked
label in that exact frame, and the model declined to claim it was held,
because it looked at the hands.

### Model selection, measured not assumed

`qwen3-vl:8b` was pulled and benchmarked **first**, over 12 streamed real
queries against a real camera frame:

| | first-token p50 / p95 | total p50 / p95 | disk |
|---|---|---|---|
| `qwen3-vl:8b` | 2753 / 3048 ms | 4068 / 4223 ms | 6.1 GB (5.8 GB resident, 100% GPU) |
| **`qwen3-vl:4b`** ← shipped | **1693 / 2282 ms** | **2201 / 2763 ms** | 3.3 GB |

4B was chosen as the better point on the same curve — identical correctness on
all five reading tests and both grounding retests, at roughly half the latency.
Neither clears a "feels instant" bar. `MODEL_NAME` is a one-line change back.

### What it can read

Five reading tests, 5/5 correct on **both** model sizes: a real Python
traceback (`ZeroDivisionError` — diagnosed the cause, not just transcribed),
a receipt (correct total), a document page (title, body summary, page number),
a three-line note, a product label (name, weight, roast origin, best-by date).

**Caveat kept on the record:** none were held to a physical camera; four were
generated images fed directly as `frame_bgr`, and the "handwriting" one was a
script *font*, not real strokes. A live camera-held test is still owed.

---

## 7. Latency budget, end to end

```
speech onset
  ├─ VAD capture + 0.6s silence tail ................  600 ms+ (unavoidable, turn-final)
  ├─ Moonshine base transcription ..................  ~15–20 ms warm
  ├─ parse_intent ..................................  <1 ms
  │
  ├─ IF deterministic (describe_scene / query_object):
  │    fresh look via PreemptionSeam ...............  ~17 ms p50 (detect+track+describe)
  │
  ├─ IF unknown (VLM path):
  │    frame/screen acquisition ....................  ~0–204 ms
  │    Qwen3-VL-4B full answer .....................  2201 ms p50 / 2763 ms p95
  │
  └─ Chatterbox Turbo generation ...................  1652–3167 ms
                                                      ─────────────────────
                                     first audible word ≈ 4.5–6 s (VLM path)
                                                        ≈ 2.5–4 s (fast path)
```

**The single structural cause: nothing streams.** STT is batch. `Llm.respond()`
is non-streaming. TTS generates the entire clip before playing a sample. Three
full-buffer stages in series, so their latencies **add** instead of
overlapping. The streaming benchmark harness (`day11_bench.py`) already proves
Ollama returns a first token at 1693 ms rather than a full answer at 2201 ms;
the shipped path does not use it.

Day 10's headline 119.1 ms intent→TTS-start number is **retired** — it was
measured against `say`, which produced audio within milliseconds.

### Runtime footprint

| State | main proc | capture proc |
|---|---|---|
| Ambient, no VLM wired | 8.1–9.7 % | 3.7–5.5 % |
| Ambient, `--t3`, VLM resident but uncalled | 5.8–8.6 % | 3.6–5.2 % |
| With Chatterbox model resident | **~18 % avg, 44 % spikes** | — |

Ollama holding a model resident costs effectively nothing until called. The
Chatterbox regression is real, measured, and not yet root-caused.

---

## 8. Honesty and provenance layer

The project's actual differentiator, and it is enforced structurally rather
than by prompt wording.

- **`UNIDENTIFIED` floor** — a low-confidence detection is relabeled, never
  resolved to a guess. Both in the detector (0.35) and in the voice layer
  (`scene.py`, 0.6), where uncertain tracks are grouped and spoken as
  "unidentified" rather than named.
- **`labelConfidence` / `runnerUpLabel` are on the wire**, so every consumer
  knows when a label is contested.
- **`inferenceMs: null` is meaningful** — it distinguishes "T1 ran this frame"
  from "this is a re-emitted repeat". Tracks are deliberately re-emitted
  unchanged on gated frames so a still scene keeps showing what was last seen
  instead of blinking empty.
- **No fabricated numbers.** No distance readouts were ever shipped, because
  a monocular camera cannot produce them honestly.
- **`provenance.py`** — one JSONL line per spoken answer to
  `clips/provenance.jsonl`:

```json
{"t": 1787389391.026,
 "claim": "You're looking at a bed with a folded blanket and blue cloth in front of you.",
 "transcript": "what's in front of me right now?",
 "source": "vlm+tracks", "frameSource": "camera",
 "trackLabels": ["person","glasses","blanket","bed"],
 "frameAgeMs": 360.62, "llmMs": 10495.9, "possibleDisagreement": false}
```

- **`possibleDisagreement`** flags when the tracker reports confident objects
  and the VLM's answer mentions none of them. **Measured over 19 real queries
  it fires 58 % of the time** — reading those flags shows it trips on answers
  that are correct but off-object ("is there a window?" → "Yes, there's a
  window…" gets flagged for not saying "person"). It has no false negatives
  against cases it can detect at all, so it works as a tripwire for human
  review, and it is documented as exactly that — not as proof of error.

---

## 9. Interfaces and wire formats

**stdout JSONL**, one line per frame (off by default post-Day-11 — it read as
error noise; `--debug` re-enables it, and `debug_window.py` consumes it):

```json
{"t": 1787389391.0, "motion": 0.02, "gated": false,
 "captureMs": 1.2, "gateMs": 0.9,
 "detections": [{"label":"person","score":0.91,"bbox":[x,y,w,h]}],
 "tracks": [{...}], "inferenceMs": 22.4}
```

A `[gated-fraction]` summary lands on **stderr** every 30 frames, keeping
stdout pure JSONL for piping.

**WebSocket** (`bridge.py`) — `ws://127.0.0.1:8765`, **localhost only, never
`0.0.0.0`**. One producer, N browser clients, no protocol version, no schema
library. Payload is a superset of the stdout record plus coordinate-contract
fields the client needs to rescale boxes into its own video element's pixel
space, plus `EngineVoiceExchange` records (transcript + answer + timestamp).
Sends are best-effort per client: a slow client is dropped, never buffered
into — the same drop-don't-buffer rule as the frame queues, applied at the
socket.

**Browser HUD** (`src/hud/`) renders from that feed. Detections never enter
React state; they land in a ref, and a canvas draw loop reads them at 60 fps.
`hudState.ts` holds render-side memory the tracker deliberately does not:
300 ms bracket acquire/release, 250 ms primary-target transfer, and a 70 ms
exponential interpolation constant so 8 Hz boxes read as smooth motion rather
than stepping.

**CLI:**

```
uv run python main.py                       # real camera, until Ctrl+C
  --t3                 # enable the voice loop (mic, wake, PTT, TTS)
  --synthetic          # generated frame, no camera needed
  --no-detect          # T0 only — isolates gate cost
  --no-ws              # stdout JSONL only
  --debug              # per-frame JSONL back on
  --seconds N  --camera-index N  --enable-yo  --ws-port N
```

---

## 10. Dependency and model inventory

| Component | Choice | License | Where it runs |
|---|---|---|---|
| Detection | YOLOE `yoloe-11s-seg` + MobileCLIP-BLT (Ultralytics) | AGPL-3.0 | PyTorch / MPS, in-process |
| Tracking | ByteTrack (`supervision`) | MIT | in-process |
| STT | Moonshine `base` (`useful-moonshine-onnx`) | MIT | ONNX Runtime, in-process |
| VLM | Qwen3-VL-4B-Instruct | Apache-2.0 | Ollama daemon, Metal/GGUF |
| TTS | Chatterbox Turbo (Resemble AI) | MIT | PyTorch / MPS, in-process |
| Audio I/O | `sounddevice` / PortAudio | MIT | — |
| Transport | `websockets` (sync server) | BSD | background thread |
| HUD | React 19 + Vite 8 + canvas | — | browser |

Python ≥ 3.13, managed by `uv`. `torch` is pinned to 2.6.0 by
`chatterbox-tts`; the downgrade from 2.13.0 was regression-tested against
YOLOE (3849.9 ms first call = cold Metal kernel compile, then a steady
21.8–22.2 ms — matching pre-downgrade performance).

**Model weights live outside the repo** at `~/.cache/yap-engine/weights` —
the single recorded exception to the repo-only boundary. `HF_HOME` is
redirected there in `main.py` *before* any import that could trigger a
download, and `detector.py` chdirs into it because Ultralytics' asset
downloader silently falls back to the current working directory.

**Tests:** 4 Python (`test_intent`, `test_scene`, `test_greeting`,
`test_query_loop`) + 6 TypeScript (vitest). `verify_preemption.py` and
`day11_bench.py` are harnesses, not shipped code.

---

## 11. What does not exist

Measured against `jarvis_friday_edith_combined_ai_system_spec.md`. Roughly
**15 % of the spec is implemented, almost all of it in §7 Layer A
(Perception)**.

| Spec area | State |
|---|---|
| §7C Memory — working / episodic / semantic / procedural / relationship / project | **Zero of six.** No SQLite, no memory file, nothing persists. `query_log` is an in-process list; the only conversation state is a 10 s deadline float. |
| §8 Context Engine | Does not exist. |
| §9 Situational awareness state | Does not exist. |
| §11 Agent loop (11 steps) | Does not exist. |
| §12 Tool orchestration / registry | Does not exist. Zero tools. |
| §13 Permission architecture, risk levels 0–3 | Does not exist. No permission check anywhere in `engine/`. |
| §16 Proactive engine | Only the appear-greeting and opt-in ambient narration. No scoring, no benefit/urgency/interruption model. |
| §20/21 Multi-agent + orchestrator | Does not exist. |
| §24 Streaming STT, barge-in | Batch STT. "stop" cancels TTS (114 ms) but there is no true barge-in during listening. |
| §24 Speaker identity | Does not exist. No face recognition. |
| §14 Personality engine | A prompt string, not config. |
| §15 Communication modes | One mode. |
| T2 deep look | Stub returning `None`. |

Cross-session continuity — the §35 Phase-1 success criterion, *"the AI should
feel like it knows the user"* — is **at zero**. YAP remembers nothing between
runs, or between minutes.

---

## 12. Known defects and open debt

**Not measured yet**
- **End-to-end wake → first spoken word has never been cleanly captured.**
  Open two days. The instrumentation (`wakeToAnswerMs` / `pressToAnswerMs`)
  exists and is ready; the agent's process cannot obtain real mic audio —
  macOS mic permission is granted **per process tree**, so Terminal.app, the
  VS Code integrated terminal, and an agent process each need separate grants.
- `bench.mjs` re-run for the browser build.

**Real, unresolved**
- **Two 30 s Ollama timeouts** observed in one session, same shape as an
  earlier `keep_alive` latency spike. Not root-caused. Both were handled
  correctly by the exception path (fallback line spoken, seam released), so
  this is a reliability gap, not a correctness one.
- **Chatterbox idle CPU regression** (~18 % avg, 44 % spikes). Not profiled.
- **`exaggeration` does not work on Chatterbox Turbo** — logged by the library
  itself. The voice is neural and real, but not dynamically emotional.
- **The disagreement heuristic over-flags at 58 %.** A version scoped to
  identity-shaped questions is the honest next step.
- **Wake phrase "yap" transcribes as "app"** live and repeatedly. A rename is
  the owner's open decision.
- **Screen capture was never exercised end-to-end with real displayed
  content** — the module is proven in isolation (real pixels, real timing) and
  its routing is unit-tested, but the agent's sandbox could not render spawned
  windows into a capture.
- **No physical object has been held to the camera for a reading test.**
- `debug_window.py` on-screen confirmation, open since Day 9.
- Mic-contention dual-open test (engine + browser), never run.
- Untuned first-guess constants, flagged as such in-source:
  `MIN_ABSOLUTE_SPEECH_RMS`, `REGREET_COOLDOWN_SECONDS`,
  `MIN_INLINE_COMMAND_WORDS`, HUD τ.

---

## 13. Standing invariants

Rules that constrain every future change:

1. **Repo-only.** All project files live inside this repository. Never `/tmp`,
   never a session scratchpad. The single exception is model weights at
   `~/.cache/yap-engine/weights`.
2. **Local only.** No third-party cloud services at runtime. A private server
   the owner controls is acceptable; a vendor API is not.
3. **`parse_intent` owns `stop` / `wake` / `sleep` deterministically.** No
   model may ever decide whether "stop" stops.
4. **Drop frames, never buffer.** Every queue is depth 1, latest-wins, at
   every layer including the WebSocket.
5. **T0 is never gated.** The gate always runs.
6. **Never fabricate a number or a label.** Below the confidence floor is
   `UNIDENTIFIED`; unknown is `null`; every spoken claim writes a provenance
   line.
7. **The seam always releases.** `finally:` is load-bearing, and has a test.
8. **Verify a model is current before adopting it.** No component ships on a
   default recalled from training memory.
