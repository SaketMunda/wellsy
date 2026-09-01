# WELLSY v2 — architecture research: leaving the browser, and becoming JARVIS

**Status:** research + proposal. Nothing decided, nothing built.
**Written:** 2026-08-12, after Day 5. **Revised** 2026-08-13 with the
on-demand ("JARVIS answers, he doesn't narrate") direction, identity memory,
the private-server option, and the voice rewrite.

---

## 1. What is actually wrong (measured from the code, not guessed)

Five separate problems are being felt as one. They have five different fixes,
and only two of them are about the browser.

### 1a. Everything runs on one thread

`grep -rn "Worker|OffscreenCanvas|transferControlToOffscreen" src/` returns
**nothing**. There is not a single Web Worker in this codebase. Which means
all of the following share one JavaScript main thread:

- the detection rAF loop (`useDetector.ts`)
- the HUD draw rAF loop (`HudCanvas.tsx`)
- the 250ms narration sampler (`useNarrator.ts`)
- WebLLM inference (Qwen 0.5B)
- Kokoro TTS synthesis (ONNX Runtime, WASM)
- every React render

Any one of these blocking stalls all the others. That is precisely the
reported symptom — "gets stuck when 2–3 operations are performed in
parallel."

### 1b. Three inference runtimes, one GPU, no coordination

TF.js on **WebGL**, WebLLM on **WebGPU**, ONNX Runtime on **WASM**. Three
runtimes, three memory arenas, three copies of the data, one GPU, no
mechanism to arbitrate between them.

### 1c. Memory pressure in a single tab

Qwen 0.5B ~945MB VRAM, Kokoro ~90MB, TF.js textures on top. Browser tabs are
killed for less.

### 1d. The detector is weak, and that has nothing to do with the browser

COCO-SSD `lite_mobilenet_v2` — the **smallest and least accurate variant** of
a 2017-era architecture, **80 fixed classes**. `microphone` is not one of
them.

**Switching to Python does not fix detection quality. Changing models fixes
detection quality.** Python is worth doing because it makes the good models
reachable — not because Python detects better than JavaScript.

### 1e. The real root cause: it does maximum work at all times

This is the deepest one, and it is the one §2 is about. The system runs
detection at **60 Hz**, a narration sampler at **4 Hz**, an LLM, and a TTS
engine — **permanently**, whether or not anybody wants anything from it. It
computes an answer to a question nobody asked, sixty times a second, and then
speaks it unprompted.

Fixing 1a–1d makes that waste *faster*. It does not make it stop.

---

## 2. The reframe: JARVIS answers. He does not narrate.

> *Tony asks "JARVIS, what am I looking at" — and then JARVIS speaks. He is
> not commentating on the furniture in between.*

This is the most important correction in this document, and it is both a
product fix and a performance fix. Right now WELLSY is an always-on commentator
that happens to have a camera. JARVIS is a system that is **quietly aware,
expensively smart only on request, and almost always silent.**

Two consequences:

**Product:** the promise made to viewers was an Iron Man HUD. An Iron Man HUD
does not chatter. Silence is most of the character.

**Performance:** this is roughly an order of magnitude less compute, and it
dissolves the hang. STT latency is heavy today largely *because* STT is
competing with a 60 Hz detector, an LLM, and a TTS engine that are all running
for no reason. Stop doing unrequested work and the requested work gets the
machine.

### 2a. The attention budget — four tiers

| Tier | What runs | When | Cost |
|---|---|---|---|
| **T0 — always** | frame differencing (motion), voice-activity detection, wake-word spotting | continuously | ~1–3% CPU, no neural nets on the hot path |
| **T1 — ambient sense** | detection + tracking | on motion, at **5–10 Hz**, not 60 | one small model, throttled |
| **T2 — deep look** | depth, segmentation, pose, OCR, open-vocab relabel, face embedding | **on demand**, or when a rule fires | expensive, rare, bounded |
| **T3 — respond** | STT → intent → LLM → TTS | only after wake word / push-to-talk | expensive, rare, user is waiting so latency is *expected* |

Two design notes that make this work:

- **8 Hz detection still looks like 60 FPS.** Day 5's `hudState.ts` already
  interpolates the drawn box toward the latest detection (τ = 70ms, D15). The
  HUD keeps painting at 60 Hz off interpolated state while detection runs at a
  fraction of that. **That work was built for exactly this and nobody has
  cashed it in yet.**
- **Priority inversion is explicit.** When a user query is in flight, T1 drops
  its rate (or pauses) to give the machine to T3. A question beats ambient
  awareness, always. This is a scheduling rule, not a hope.

### 2b. The speech policy — silence is the default

WELLSY speaks in exactly three cases. Everything else updates the HUD **silently**.

1. **It was asked.** Wake word or push-to-talk.
2. **A rule fired.** A registered person arrives; an unregistered face
   persists past a threshold; a user-defined watch ("tell me when the
   delivery arrives").
3. **Ambient mode is explicitly on.** This is where Days 1–5's narration
   lives — demoted from *the product* to *an off-by-default mode*. It's still
   a good demo and a good piece of the story. It is not the behaviour.

Everything in `events.ts` survives this change. Events keep being computed —
they feed the HUD, the memory log, and the rule engine. They just stop
automatically becoming speech. The Day 2 architecture was right; the policy
sitting on top of it was wrong.

---

## 3. What changed in the constraints

### Mobile: still required — and the private server is what makes it possible

Confirmed still a requirement, with model substitution allowed per platform.
Combined with the willingness to run a **private server**, this resolves the
hardest open question in the previous draft. The answer is a **split**, and
on-demand is what makes the split cheap:

- **On-device (phone):** camera, T0 motion/VAD, T1 detection + tracking, and
  all HUD rendering. Must be local — box rendering cannot survive a network
  round trip.
- **On the private server:** T2 and T3 — LLM, depth, segmentation, face
  recognition, memory. These are **on-demand only**, so a 50–150ms round trip
  lands inside a budget where the user is already waiting for an answer.

Published mobile numbers, for sizing (not measured here):

| Measurement | Figure |
|---|---|
| YOLO26n detect, iPhone 15 Pro Max | **11.3 ms/frame** |
| YOLO11 CoreML via Neural Engine | 21 → **85 FPS** vs PyTorch on-device |
| Optimized YOLO, INT8, mobile NPU | 12–20 ms, negligible accuracy loss |

At 8 Hz ambient sensing, an 11ms model uses **under 10% of the phone's frame
budget.** The phone is not the problem. The always-on design was.

### The private server changes the honesty claims, not the ethics

D10 was *"no cloud APIs — local LLM and local TTS."* Its real intent was **no
third-party service sees your data**. Your own server honours that intent.
But three things must be said plainly rather than assumed:

- **"Video never leaves your device" becomes false.** That claim is in
  `public-notes.md` and on Days 1–5. It must be retired and replaced with
  something true: *"your data goes to hardware you own, and nowhere else."*
- **Private is not automatically secure.** A self-hosted box beats a cloud API
  only if TLS, authentication, and disk encryption are actually done. An
  unauthenticated LAN service streaming your camera is worse than a reputable
  cloud vendor, not better.
- **Face embeddings are biometric data** (§5). That is the one category where
  moving data off-device carries real legal weight (GDPR Art. 9, BIPA) if this
  is ever used by anyone but you.

---

## 4. Hardware and stack

`Apple M4 Pro · 16 GPU cores · 24 GB unified memory` — a serious local
inference machine. **MLX** (Apple's array framework) is the relevant runtime.

| Workload | Published benchmark |
|---|---|
| YOLO26-nano via MLX, M4 Pro | **124.9 FPS** (up to 170.6 reported) |
| MLX vs PyTorch MPS | **~2.1×** faster |
| MLX-LM vs Ollama/llama.cpp, 30B-class | **~130 vs ~43 tok/s** |

**Every number above and in §3 is from a vendor or third-party blog, on
someone else's machine. None has been measured here.** Phase 0/1 exist to
replace them with ours.

| Layer | Choice | Tier | Why |
|---|---|---|---|
| Runtime | Python 3.13 + `uv` | — | both already installed |
| Frames | PyAV / OpenCV (AVFoundation) | T0 | OpenCV is the plumbing, not the detector |
| Motion gate | frame differencing | T0 | ~1ms; decides whether T1 runs at all |
| Detection | **YOLOE** (open-vocab, text-promptable) via MLX; YOLO26 where speed wins; CoreML on mobile | T1 | text prompts are the actual fix for "microphone → tie" |
| Tracking | **ByteTrack / BoT-SORT** | T1 | replaces the hand-rolled IoU tracker; includes re-ID |
| Depth | **Depth Anything V2** | T2 | real relative depth — retires D17's "no fabricated distances" |
| Segmentation | YOLOE-seg / **SAM2** | T2 | silhouettes instead of rectangles — the biggest visual upgrade available |
| Pose | YOLO26-pose | T2 | orientation, gesture, "facing away" |
| Face | **SCRFD + ArcFace** (InsightFace) | T2 | 512-d embeddings, 99.86% LFW; INT8 is 4× smaller for +0.02% error |
| OCR | on-demand only | T2 | read screens, labels, spines |
| STT | **Moonshine** streaming (~107ms, 27–123MB) | T3 | built for command-and-control; Whisper-large is ~11s on the same audio |
| TTS | **Kokoro** (native) or **Piper** (~40ms first audio) | T3 | in native Python the D13 espeak/Rollup bug simply doesn't exist |
| LLM | **MLX-LM**, Qwen3 8B–14B | T3 | 24GB unified memory makes it trivial; ~20× the browser's 0.5B |
| UI | keep the **React HUD** over a local WebSocket | — | Days 1–5 of HUD design survives the move |

---

## 5. Identity and memory — the one thing that stays always-on

This is the stated exception to §2, and it's the right exception: recognising
who walked in is the one judgement that must happen without being asked.

### The pipeline

```
T1 detects person → face crop → SCRFD (align) → ArcFace (512-d embedding)
                  → cosine match against local registry
                  → known ⇒ greet   |   unknown ⇒ alert   |   unsure ⇒ say nothing
```

Runs **once per new person track**, not per frame — cache by track id, exactly
the pattern already designed for open-vocab relabelling.

### The registry

- **Explicit enrolment only.** You show your face and give a name. Never
  covert, never "learned in the background." That's both an ethics line and a
  usability one — silent enrolment produces a registry full of strangers.
- SQLite + numpy cosine similarity. A gallery of tens of people needs no
  vector database.
- Store: name, embeddings (several per person, different lighting/angles),
  first seen, last seen, greeting preferences, notes.

### The "unsure" band is mandatory

1:N identification is much harder than 1:1 verification, and the failure mode
is **calling someone by the wrong name**, which is worse than not recognising
them. Three bands, not two: match / **unsure → stay silent** / no-match.
Same principle as `UNIDENTIFIED` in the Day 6 plan — the system is allowed to
not know.

### Memory layers

1. **Person registry** — who, and what WELLSY knows about them.
2. **Episodic log** — timestamped events. Enables "what happened while I was
   out", "when did you last see my keys".
3. **Session context** — what was just said, so a follow-up question
   ("what about behind me?") makes sense.

### On "Threat detected"

Worth one honest paragraph, then it's your call and I'll build whichever you
pick.

An unregistered face is not a threat. It's a face that isn't in a registry of
maybe three people — so it's your mother, a courier, or a friend, essentially
every time. Announcing "threat detected" makes the **first factually false
statement this system has ever made**, in a project whose defining rule has
been that it never claims more than it knows. And it's the clip that travels
worst: a demo where a guest walks in and gets called a threat reads very
differently to an audience than it does in the edit.

**Recommendation:** keep the feature, change the words. Default to
`UNREGISTERED · NOT IN REGISTRY` — which is precise, and on a red-amber HUD
plate it lands with *more* menace than "threat" because it sounds like a
system that means it. Then add **an opt-in theatrical mode** that swaps the
wording to "threat detected" for filming. You get the Marvel beat, on purpose,
labelled, without the system lying by default.

---

## 6. The voice — why the current narration is wrong

The complaint is correct, and diagnosing it precisely matters because most of
it is **not** a prompt problem.

### What's actually wrong, in order of impact

1. **It speaks when it shouldn't.** Most of the "waste of words" is §2's
   problem, not the writing's. Fix the speech policy and the majority of bad
   lines simply never happen.
2. **It has one register.** Qwen-**0.5B** can hold exactly one instruction
   about tone, and ours says "deadpan, dry, unimpressed" — so it is
   relentlessly deadpan, dry, and unimpressed, about a chair. An 8B model can
   hold "concise and factual, *with rare* dry wit," which a 0.5B genuinely
   cannot.
3. **The system prompt asks for a joke every time.** Look at
   `llmLineGenerator.ts` — *"Roast the habitat"*, four sarcastic examples,
   zero examples of a plain, useful answer. It is doing exactly what it was
   told. This one is our fault, not the model's.

### How JARVIS / FRIDAY / KAREN actually talk

- **Answer first, in one clause.** "Three people, sir. Two I don't recognise."
- **Elaborate only when asked.** No unrequested context.
- **Address the principal.** Deferential, not servile.
- **Volunteer only what changes a decision.**
- **Precision over colour** — names, numbers, states.
- **Wit is rare, dry, and reactive.** It lands *because* it's roughly one line
  in twenty, usually when the user does something reckless or absurd. It is
  never a comment on furniture.

### Implementing restraint as code, not as a wish

A prompt that says "be funny only sometimes" will not hold. Build it:

- **Two personas, selected by a gate.** `FACTUAL` (default) and `WRY`. Not
  one prompt begging for balance.
- **A humour gate**, evaluated before generation. `WRY` is permitted only when
  a cooldown has elapsed (say ≥ 10 minutes since the last wry line) **and** a
  trigger holds: the user made a joke, an absurd repetition (the fifth cup),
  WELLSY itself just failed at something, or a long absence ended. Otherwise:
  `FACTUAL`. Testable, tunable, and it makes the humour land because it is
  rare.
- **Length caps by intent.** Acknowledgement ≤ 4 words ("Camera online, sir.")
  · factual answer ≤ 1 sentence · briefing only when asked for one.
- **Grounding survives unchanged.** `describeScene(tracks)` produces the true
  sentence; the LLM restyles and never invents. With a stronger model that
  rule matters *more*, not less.

---

## 7. The trap to avoid: rebuilding the same bug in Python

**Python has a GIL. It is the same shape of problem as the browser main
thread.** Porting all five workloads into one Python process reproduces the
exact stalling behaviour in a new language.

Architecture is **process-per-workload**, not thread-per-workload:

```
┌──────────────┐  shared memory (frames, never copied)
│ capture  T0  │──────────────┐
└──────────────┘              ▼
┌──────────────┐      ┌───────────────┐   JSON over local WS   ┌──────────┐
│ vision   T1  │◄─────┤   frame bus   │───────────────────────►│ React HUD│
│ det+track    │      │ latest-wins   │                        └──────────┘
└──────────────┘      └───────────────┘
┌──────────────┐              ▲
│ deep-look T2 │──────────────┤   (on demand only)
│ depth/seg/   │              │
│ pose/face    │              │
└──────────────┘              │
┌──────────────┐              │
│ audio+STT T3 │──────────────┤
└──────────────┘              │
┌──────────────┐              │
│ LLM+TTS  T3  │──────────────┘
└──────────────┘
```

Three non-negotiable rules:

1. **Latest-wins queues, depth 1. Drop frames, never buffer them.** A queue
   that grows is latency that grows; a stale frame is worthless. The correct
   response to falling behind is to throw work away.
2. **The vision process never blocks on the LLM or TTS.** Day 2 (narrate
   events, not frames) and Day 4 (generate-ahead) were right and carry over.
3. **T3 preempts T1.** A question in flight outranks ambient awareness.

---

## 8. Deployment topologies

| | **A — All local (Mac)** | **B — Private server + clients** | **C — Cloud** |
|---|---|---|---|
| Target | Phases 1–6 | Phase 7, mobile | ✗ |
| Heavy models | on the Mac | on your server | — |
| Latency | best | +5–20ms LAN, +30–150ms WAN | — |
| Mobile | ✗ | ✓ — this is what unlocks it | — |
| Claim | "nothing leaves the device" | "only hardware you own" | ruled out by D10's intent |

B is the destination; A is how you get there without building a server first.
The on-demand design is what makes B viable: if heavy work only runs when
asked, network latency lands in a budget where the user is already waiting.

---

## 9. Phased plan

### Phase 0 — Prove the diagnosis before spending a week (½ day)
Benchmark the current build honestly: FPS, inference ms, main-thread long-task
duration, and specifically what frame timing does when LLM and TTS fire.
Capture the stall. **Also measure what idle *should* cost** — that's the §2
baseline. Optionally test 1a directly by moving detection to a Web Worker.
Every number in §3/§4 is someone else's; this produces ours.

### Phase 1 — Python vision core with the tiered scheduler (1–2 days)
Camera → motion gate → YOLOE via MLX @ 8 Hz → ByteTrack → JSON to stdout.
Headless. **Build the tier scheduler on day one** — retrofitting an attention
budget onto an always-on loop is exactly the mistake being corrected. Question
to answer: real FPS on this machine, real idle CPU, and is the bed/microphone
visibly fixed?

### Phase 2 — Bridge to the existing HUD (1 day)
Local WebSocket, Python pushes tracks, React renders. `hudState.ts` and
`drawHud.ts` should need almost no change — they consume a `Frame` and we own
that shape. **Verify the 8 Hz-detection / 60 Hz-render illusion holds.**

### Phase 3 — The query loop, with zero LLM (1–2 days)
Wake word / push-to-talk → Moonshine → `parseIntent` → `describeScene` →
TTS. **Deterministic answers only.** This proves the interaction model at
minimum latency, before any LLM is in the path to blame. This is the phase
that makes it feel like JARVIS.

### Phase 4 — LLM + the voice spec (1 day)
MLX-LM 8B, `FACTUAL`/`WRY` personas, the humour gate, length caps.
Ambient narration returns here as an off-by-default mode.

### Phase 5 — Identity and memory (1–2 days)
SCRFD + ArcFace, enrolment flow, three-band matching, registry, episodic log,
the greeting rule and the unregistered-person rule.

### Phase 6 — The Marvel perception layer (2+ days)
Depth (highest value — it makes distance real), segmentation masks, pose,
OCR. On demand, T2, never on the hot path.

### Phase 7 — Mobile + private server
CoreML/ExecuTorch export for on-device T1; server for T2/T3; auth and TLS
before anything leaves the LAN.

### Phase 8 — Package and ship
Tauri or py2app; weights fetched on first run.

---

## 10. Open decisions

1. **"Threat detected" wording** — §5. Recommendation: precise by default,
   theatrical as an opt-in mode.
2. **Wake word implementation** — a real keyword spotter (openWakeWord et al.)
   vs transcribe-then-match. The former is what keeps T0 genuinely cheap;
   needs its own research pass before Phase 3.
3. **What the series says about the pivot.** The "no backend / video never
   leaves your device" claims from Days 1–5 must be explicitly retired in
   `public-notes.md`, not quietly dropped. The pivot is good content — *"I
   promised an Iron Man HUD and built a chatty box; here's what was actually
   wrong with that"* is a stronger episode than another polish day.
4. **Does ambient mode survive at all?** Recommendation: yes, off by default —
   it's five days of work, it demos well, and it's the honest before-picture.

---

## 11. What this does not fix

- **Still not a product.** It becomes a fast, accurate, local perception
  system that answers questions. Distribution, onboarding, and a reason to
  open it twice remain unsolved.
- **Latency is not free in Python.** The wins come from MLX, from the
  attention budget, and from process isolation — not from the language. Bad
  architecture in Python is exactly as slow as bad architecture in JavaScript.
- **Face recognition will misfire** in bad light, at angles, with masks. The
  three-band design contains it; it does not eliminate it.
- **No audio has been confirmed audible** on any machine across five days
  (D13). That gap survives the migration and should close in Phase 3, on real
  speakers.

---

## Sources

- [Best Object Detection Models 2026 — Roboflow](https://blog.roboflow.com/best-object-detection-models/)
- [YOLOE: Real-Time Seeing Anything — Ultralytics](https://docs.ultralytics.com/models/yoloe)
- [Running YOLO26 Natively on Apple Silicon with MLX — webAI](https://www.webai.com/blog/running-yolo26-natively-on-apple-silicon-with-mlx)
- [CoreML Export for YOLO26 — Ultralytics](https://docs.ultralytics.com/integrations/coreml)
- [On-Device AI Inference in 2026: sub-20ms on mobile](https://www.alephzerolabs.com/blog/on-device-ai-2026-sub-20ms/)
- [InsightFace — SCRFD + ArcFace](https://github.com/deepinsight/insightface)
- [Choosing a face recognition model: 1:1 vs 1:N and thresholds — InsightFace](https://www.insightface.ai/guides/choose-face-recognition-model-and-evaluate)
- [Best Local STT Models 2026: Moonshine vs Parakeet vs Whisper](https://www.onresonant.com/resources/local-stt-models-2026)
- [Moonshine — low-latency streaming ASR](https://github.com/moonshine-ai/moonshine)
- [llama.cpp vs MLX vs Ollama vs vLLM on Apple Silicon 2026](https://contracollective.com/blog/llama-cpp-vs-mlx-ollama-vllm-apple-silicon-2026)
- [Kokoro vs Piper vs XTTS v2 — local TTS latency](https://contracollective.com/blog/kokoro-vs-piper-vs-xtts-local-text-to-speech-m5-max-2026)
- [aiortc — WebRTC for Python](https://github.com/aiortc/aiortc)
