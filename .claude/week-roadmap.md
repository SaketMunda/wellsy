# 7-Day Roadmap

Every day ships something visible. Every day has a story beat.

---

## Day 1 — "It can see" ✅ SHIPPED
**Ships:** Camera → detection → HUD overlay → spoken narration. The full loop.
**Concept:** Single-shot object detection running on the GPU, in a browser.
**Demo:** Boxes lock onto objects; YAP says "I can see 1 person and 1 laptop."
**Unfinished:** Boxes jitter. Only 80 object classes. Desktop only.
**Hook:** *"I gave my laptop eyes in one day. It just told me what's on my desk."*

---

## Day 2 — "The mouth was drowning" (narration latency) ✅ SHIPPED
**Ships:**
- **Events, not frames** — the frame stream collapses into discrete
  `NarrationEvent`s (appear / disappear / count_change / still_present)
  before the narrator ever sees it (`src/narration/events.ts`)
- **Decouple + rate-limit** — narration runs on its own 250ms sampler,
  requires a scene to hold for 900ms before it's "settled", and speaks at
  most once every 4 seconds (`src/narration/useNarrator.ts`,
  `src/narration/config.ts`)
- When several events land in one window, the narrator picks the most
  interesting (`byInterest`: appear > disappear > count_change >
  still_present) and folds a second one in as an aside
- "Boring mode" in the telemetry panel shows the literal event line, proof
  the styled narration traces back to a real detection

**Concept:** Detection — the eyes — runs the browser at 60fps, ~12ms a frame.
That was never the problem. Narration was chained to that same loop: every
frame, it tried to say something. Sixty opinions a second, all late, all
fighting each other. The fix isn't a smarter sentence generator, it's an
architecture change: narrate events, not frames, and put narration on its own
clock, decoupled from detection.

**Demo:** Telemetry panel showing `SAMPLE_MS` (250ms), `STABLE_MS` (900ms),
and the 4s rate limit alongside a live narration log that fires roughly once
every 4+ seconds under normal movement — never on every frame.

**Hook:** *"YAP had two jobs running at two speeds. The eyes kept up. The
mouth was drowning. Here's the fix — talk about events, not frames."*

**Risk:** none — verified against the existing codebase, not built from
scratch. The narrator-personality work already shipped this architecture; this
session's job was confirming it holds and removing anything that still
contradicted it.

---

## Day 3 — "It stops shaking" (tracking + stability) ✅ SHIPPED
**Ships:**
- IoU **tracker** (`src/vision/tracker.ts`) — objects get persistent numeric
  IDs across frames, matched by IoU ≥ 0.3 within the same COCO label
- Box **smoothing** — exponential position/size averaging, α = 0.4 — kills jitter
- Tracks **persist** up to 5 missed frames before being dropped, so a brief
  occlusion or a dropped detection doesn't reset identity
- Track ID + age on the HUD: `KITE #13 · 0.3s` replaces the old bare
  `label score%` display (verified in a live screenshot, see `day3-poc.md`)
- **Narration now reads track enter/exit directly** instead of diffing label
  counts — a second person walking in is `person #4 appeared`, not
  `count_change: person 1→2`

**Concept:** Detection vs **tracking**. A detector answers "what's here *now*".
A tracker answers "is this the *same* thing as before". Everything that feels
intelligent comes from the second question.

**Demo:** Side-by-side — jittery Day 1 boxes vs locked-on Day 3 boxes. Walk out
of frame and back; the ID persists. *(Real-webcam capture still pending — see
"What to film" in `tasks.md`.)*

**Hook:** *"Yesterday it saw. Today it remembers. That's the whole difference
between a camera and a system."*

**Risk:** Landed inside the timebox — one IoU matcher, no Kalman filter, no
re-identification, as planned. The narration switch to track-based events
turned out to make `count_change` unreachable rather than requiring new
logic — see decisions.md for that tradeoff. The one thing not verified this
session: real-webcam behavior (occlusion recovery, a genuinely new object
getting a new ID) — the headless fake-camera device's synthetic pattern
doesn't hold a stable scene long enough to demonstrate either, same
limitation Day 1/2 already noted for narration stability.

---

## Day 4 — "Giving it a real voice" (local LLM + local TTS) ✅ SHIPPED
**Ships:**
- **A local LLM** (WebLLM, Qwen2.5-0.5B-Instruct, 4-bit) replacing the
  template-based line generator, generate-ahead so the 250ms narration
  sampler never awaits it — `src/narration/llmLineGenerator.ts`
- **A local neural TTS voice** (Kokoro-82M via `kokoro-js`, `q8`) behind the
  existing `speech.ts` seam, `speechSynthesis` retained as the default and
  the automatic fallback on any failure
- **Engine toggles + honest telemetry** in `StatusPanel` — line-generator
  engine, voice engine, live load progress, per-line/per-synth latency, all
  switchable live for the three-way demo
- Both models dynamically imported; main bundle chunk unchanged (~1.31MB)

**Cut this session** (agreed order, none reached): `STABLE_MS`/rate-limit
tuning against real footage, spatial language from bbox position, salience
ranking. Carried to Day 5+ — see `tasks.md`.

**Concept:** Two upgrades, same constraint. The hard part of narration is
still **when to speak**, not what to say (Day 2's fix stands). But *how* it's
said matters too — and the answer isn't a cloud API. The harder problem
turned out to be architectural, not the model choice: `LineGenerator` is
synchronous and an LLM isn't. The fix is **generate-ahead** — start inference
the instant an event is queued, well before its narration slot, and let the
existing stability gate + rate limit absorb the latency. If the line isn't
ready in time, it falls back to a template rather than the narrator going
silent or stuttering.

**Demo:** Same scene, three narrators back to back — Day 1's flat English,
Day 2's rate-limited-but-templated personality, Day 4's local-LLM line.
Latency numbers on screen throughout, plus a live network tab: switch the
engine on, watch a real multi-hundred-MB download happen, reload the same
page and watch it load in ~11s from cache instead with zero re-download.

**Hook:** *"A better voice usually means a cloud bill. Ours doesn't — it
still runs entirely on the device, even the part that sounds human."*

**Risk, resolved and unresolved:** The LLM path is fully verified — real
download, real caching, real offline inference, a genuine quality ceiling
(0.5B doesn't always nail the deadpan tone; recorded honestly, not hidden).
The TTS path found a real bug: Kokoro's phonemizer throws on synthesis in
this environment (root-caused to a `SharedArrayBuffer`/cross-origin-isolation
gap, partially fixed, not fully resolved — decisions.md D13), and correctly
falls back to `speechSynthesis` rather than going silent. **No audio has
been confirmed audible from any machine this project has run on, across all
four days** — that gap is still open and is the most honest thing to say on
camera. See `day4-poc.md` for the full verification writeup, including what
could not be checked (mobile, peak memory, actual heard audio).

---

## Day 5 — "It looks like the future" (HUD/UX polish) ✅ SHIPPED
**Ships:**
- A **HUD render-state layer** (`src/hud/hudState.ts`) sitting between the
  detection frame and the painter — the thing that makes everything below
  possible, since `drawHud` alone had no way to hold state across frames
- Target lock-on **animations**: brackets converge inward over ~300ms on
  acquire, release outward and fade over ~300ms on loss, subtle per-target
  breathing motion while tracking (phased per id, not synced)
- **Render-time box interpolation** (τ = 70ms exponential) — the drawn box
  eases toward the latest detection instead of holding still and jumping
- A **primary target** treatment — area × centrality picks the subject;
  the rest dim; focus **transfers** with an eased 250ms ramp, not a cut
- A real **confidence ring** (`Detection.score`, not decoration) and an
  honest **relative-size readout** (`SIZE n% OF FRAME`) — no fabricated
  distance in metres, see decisions.md D17
- Live **subtitle track** (DOM, not canvas) at the bottom of the frame,
  carrying the actual narration line — the only place most viewers will see
  it, since no audio has been confirmed audible from any machine yet (D13)
- A **boot sequence** replacing the flat loading curtain — four lines
  (camera/model/tracker/narrator), each bound to a real state value
- **Keyboard shortcuts** (`Space`/`N`/`B`/`V`/`?`) + a shortcut overlay
- **HUD draw-time telemetry** in the panel, for Day 6 to benchmark against

**Concept:** Perceived intelligence is mostly **interface design**. The model
didn't change today — the way it presents itself did.

**Demo:** Day 1's bare `label score%` rectangle vs Day 5's converging
reticle + confidence ring + honest size readout, same model underneath —
verified live in headless Chrome (fake-camera device), see `day5-poc.md`.

**Hook:** *"Same AI as yesterday. Feels ten times smarter. That gap is design."*

**Risk, resolved and unresolved:** The stateless-painter problem was the real
architectural risk and is fully resolved — `drawHud` is still pure, all new
memory lives in `hudState.ts`, frame-rate independence verified by driving
real elapsed `dtMs`. The real risk turned out to be visual, not
architectural: the first pass animated correctly and still looked like a
rectangle with a circle around it, so `drawHud.ts` was rewritten around a
much denser instrument vocabulary (D19) — graduated tick rings, chamfered
brackets, elbow leader lines into real data cards, labelled frame-edge
rulers — with the model and state layer untouched. Draw cost measured
across target counts: **0.050 / 0.049 / 0.070 ms at 1 / 5 / 12 targets**,
essentially flat. Real-webcam verification of a clean single-object
acquire→hold→lose arc and real movement (not the fake camera's churn) is
still owed, the same recurring caveat as Days 1–4.

---

## Day 6 — "It stops guessing, and it answers back" (uncertainty + voice) ✅ SHIPPED
**Reshuffled from the original plan:** the *old* Day 6 (WebGPU backend,
adaptive frame skipping, resolution decoupling) moved to **Day 7**, where it
joins mobile — a battery/latency budget genuinely matters most on a phone,
and "WebGL is already fast enough" was already #1 on the roadmap's own
cut-if-behind list. The **latency breakdown panel** stayed on Day 6, because
adding two more models (Whisper, and the LLM/TTS pair already shipped Day 4)
to a page that loads three models needed proof the frame budget survived.

**Ships:**
- **Per-track label voting** (`src/vision/tracker.ts`) — a track's label is
  now a decayed vote across ~30 frames of the same tracked object, not
  whichever detection matched last. A **cross-label match gate** (IoU ≥ 0.5)
  fixes the real bug: the model flipping `bed` ↔ `dining table` used to mint
  a brand-new track id every flip; now the id survives and the vote settles.
- **`UNIDENTIFIED` / hedged labels** — below a `labelConfidence` threshold,
  the HUD shows `BED / DINING TABLE ?` instead of committing to one word,
  and narration hedges with a dedicated line bank. The LLM may restyle the
  hedge, never resolve it — enforced mechanically, not just prompted.
- **Push-to-talk local voice input** — hold `T` or the mic button, local
  Whisper (`Xenova/whisper-tiny.en` via `@huggingface/transformers`)
  transcribes on-device, a deterministic `parseIntent` (never the LLM)
  turns it into `wake`/`sleep`/`stop`/`describe_scene`/`query_object`/`help`,
  and a revived `describeScene` answers grounded in the same tracks the HUD
  draws from.
- **Voice answers preempt ambient narration** and land in the same subtitle
  track, with the user's own transcript shown separately (dim, italic, `>`
  prefix) so a silent screen recording reads as an actual exchange.
- **Latency breakdown panel** — inference/track/draw/ASR/LLM/TTS, each a
  real measured number, no fabricated capture timestamp.

**Concept:** Two complaints, one root cause: the system was **asserting**
instead of **communicating**. It said a bed was a dining table with total
confidence, and it could only talk at you. Today it learns to say "I'm not
sure," and it learns to be asked. The genuinely interesting finding: an AI
that admits uncertainty reads as *more* intelligent, not less — a torn
`BED / DINING TABLE ?` reads as more trustworthy than a smug wrong `TIE`.

**Demo:** The `BED / DINING TABLE ?` hedge rendering live in amber with a
real `LBL nn%` confidence readout; holding `T`, asking "what do you see,"
and getting a spoken, subtitled, grounded answer; saying "stop" mid-line and
watching it actually stop.

**Hook:** *"Yesterday it looked smarter. Today it got more honest — and
somehow that reads as smarter too."*

**Risk, resolved and unresolved:** Local ASR is the day's real bundler-risk
bet — Whisper via `@huggingface/transformers` was the same dependency
family D13 warned had a known Rollup-production-build bug (Kokoro's
phonemizer). Verified in an actual production build this time, not just
dev: Whisper loaded and transcribed cleanly with zero console errors.
Whether it transcribes a *real spoken command* correctly was **not**
verified — the fake-camera device used for all headless verification this
week provides no real microphone input, the same shape of gap as "no audio
confirmed audible" since Day 4. Open-vocabulary relabeling (the actual fix
for a genuinely out-of-vocabulary object like a microphone) was not
attempted this session — cut cleanly per the day's own explicit
prioritization, carried to Day 7+. See day6-poc.md.

---

## Day 7 — "It survives reality" (robustness + mobile + the moved performance work)
**Ships:**
- **Phone camera** support — rear camera, portrait, touch controls
- Graceful handling: permission denied, no camera, tab backgrounded, model fail
- **Low light / motion blur** behaviour, honestly demonstrated
- Backgrounded-tab **pause** to stop cooking the battery
- **WebGPU backend** with WebGL fallback — measured, not assumed (moved
  from the original Day 6 plan; a mobile battery budget is where this
  actually matters most, per the Day 6 reshuffle)
- **Adaptive frame skipping** — detect less often when the scene is static
  (moved from Day 6)
- **Input resolution tuning** (detect at 640px, display at 1280px) (moved
  from Day 6)
- (Stretch, carried from Day 6) **Open-vocabulary relabeling** — crop a
  track's box, classify it with CLIP against a user-editable candidate
  list, replace a confidently-wrong COCO word (`tie` for a microphone) with
  either the right word or an honest `UNIDENTIFIED` — the actual fix for
  the out-of-vocabulary half of Day 6's label problem
- (Stretch, carried from Day 6) **Wake word** — voice-activity detection +
  continuous transcription + string match, described honestly as
  transcribe-then-match, not a trained keyword spotter

**Concept:** Demos work in one room with good light. Products work everywhere.
The gap between them is entirely edge cases — and, per this reshuffle, entirely
the performance budget a phone actually has to live inside.

**Demo:** YAP running on a phone, walking around a real space, WebGPU vs
WebGL numbers on screen.

**Hook:** *"Every demo works on the demo machine. Today I tried to break it —
and I tried to make it fit in a pocket."*

---

## Day 8 — "Ship it" (polish + final demo)
**Ships:**
- Deploy to a public URL (static host — it's a static app)
- README with GIF, honest capability/limitation list
- A polished 60–90s demo recording
- Series wrap-up write-up

**Concept:** Retrospective — what real-time perception costs, what's genuinely
hard, what's now easy that wasn't three years ago.

**Demo:** The full thing, clean, on a public link anyone can open.

**Hook:** *"7 days, no backend, no API keys. Here's the link — open it and your
laptop starts seeing."*

---

## Cut-if-behind list (in cut order)
1. Day 7 WebGPU, moved from the original Day 6 plan (WebGL is already fast enough)
2. Day 5 animation polish
3. Day 7 unit tests
4. Day 4 optional rich-description mode
5. Day 6 open-vocabulary CLIP relabeling and wake word — already cut once,
   see decisions.md D22/D24 and tasks.md's Day 6 cut list

## Never cut
Day 3 tracking — it's the single biggest quality jump in the week.
