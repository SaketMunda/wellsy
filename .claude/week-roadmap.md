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

## Day 4 — "Giving it a real voice" (local LLM + local TTS)
**Ships:**
- Narration timing **tuned against real scenes** (Day 1 numbers are guesses)
- **Spatial language** — "on your left", "in the centre", from bbox position
- **Salience ranking** — talk about the big/close/new thing, not the 6th chair
- **Event narration** built on Day 3 tracks — "someone just walked in"
- A **local LLM** replacing the template-based line generator for richer,
  less repetitive narration — small enough to run on-device, sized for
  mobile latency, not desktop-only
- A **local neural TTS** voice replacing the default `speechSynthesis` output
  — expressive, not robotic, still fully offline

**Concept:** Two upgrades, same constraint. The hard part of narration is
still **when to speak**, not what to say (Day 2's fix stands). But *how* it's
said matters too — and the answer isn't a cloud API. Everything in YAP has
been on-device from Day 1: no backend, no API keys, video never leaves the
machine. A better voice can't be the thing that breaks that promise. So the
upgrade is a tiny local LLM for line generation and a local TTS engine for
speech — both picked for the smallest footprint that still sounds like a
person, because this has to run on a phone, not just a laptop with a GPU.

**Demo:** Same scene, three narrators back to back — Day 1's flat English,
Day 2's rate-limited-but-templated personality, Day 4's local-LLM line read
by local TTS. Latency numbers on screen the whole time, so "local" isn't a
claim, it's a number with no network tab activity to contradict it.

**Hook:** *"A better voice usually means a cloud bill. Ours doesn't — it
still runs entirely on the device, even the part that sounds human."*

**Risk:** Tiny local LLMs and local TTS are meaningfully heavier than the
current template narrator — model size, load time, and inference latency all
need to hold up on real mobile hardware, not just a dev laptop. If the
quality/latency bar isn't hittable in the timebox, fall back to a smaller
local model, not a cloud call (see decisions.md D10).

---

## Day 5 — "It looks like the future" (HUD/UX polish)
**Ships:**
- Target lock-on **animations** (brackets converge on acquire)
- **Confidence rings**, distance-ish estimate from box size
- A **primary target** treatment — the thing YAP is focused on
- Live **subtitle track** at the bottom of the frame
- Keyboard shortcuts, cleaner controls

**Concept:** Perceived intelligence is mostly **interface design**. The model
didn't change today — the way it presents itself did.

**Demo:** Day 1 HUD vs Day 4 HUD, same model underneath. Deliberately makes the
point that polish is a lever, not a distraction.

**Hook:** *"Same AI as yesterday. Feels ten times smarter. That gap is design."*

---

## Day 6 — "It gets fast" (latency)
**Ships:**
- **WebGPU backend** with WebGL fallback — measured, not assumed
- **Adaptive frame skipping** — detect less often when the scene is static
- **Input resolution tuning** (detect at 640px, display at 1280px)
- A latency **breakdown panel**: capture → inference → draw
- Before/after benchmark numbers

**Concept:** Real-time is a **budget**. 30 FPS = 33ms per frame for everything.
Optimisation is deciding where those milliseconds go.

**Demo:** The FPS counter climbing. Real numbers on screen.

**Hook:** *"33 milliseconds. That's the entire budget for seeing, thinking, and
drawing. Here's where every one of them went."*

**Risk:** WebGPU may not be a win on all hardware. If so, report that honestly —
a negative result is still content.

---

## Day 7 — "It survives reality" (robustness + mobile)
**Ships:**
- **Phone camera** support — rear camera, portrait, touch controls
- Graceful handling: permission denied, no camera, tab backgrounded, model fail
- **Low light / motion blur** behaviour, honestly demonstrated
- Unit tests for `describeScene` (the pure logic)
- Backgrounded-tab **pause** to stop cooking the battery

**Concept:** Demos work in one room with good light. Products work everywhere.
The gap between them is entirely edge cases.

**Demo:** YAP running on a phone, walking around a real space.

**Hook:** *"Every demo works on the demo machine. Today I tried to break it."*

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
1. Day 6 WebGPU (WebGL is already fast enough)
2. Day 5 animation polish
3. Day 7 unit tests
4. Day 4 optional rich-description mode

## Never cut
Day 3 tracking — it's the single biggest quality jump in the week.
