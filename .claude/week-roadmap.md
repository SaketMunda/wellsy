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

## Day 2 — "It stops shaking" (tracking + stability)
**Ships:**
- Centroid/IoU **tracker** — objects get persistent IDs across frames
- Box **smoothing** (exponential position averaging) — kills jitter
- Detections **persist** for a few frames after a miss, so things stop flickering
- Track age displayed on the HUD (`PERSON #3 · 4.2s`)

**Concept:** Detection vs **tracking**. A detector answers "what's here *now*".
A tracker answers "is this the *same* thing as before". Everything that feels
intelligent comes from the second question.

**Demo:** Side-by-side — jittery Day 1 boxes vs locked-on Day 2 boxes. Walk out
of frame and back; the ID persists.

**Hook:** *"Yesterday it saw. Today it remembers. That's the whole difference
between a camera and a system."*

**Risk:** Tracker tuning can eat the day. Timebox to a simple IoU matcher.

---

## Day 3 — "It stops babbling" (narration intelligence)
**Ships:**
- Narration timing **tuned against real scenes** (Day 1 numbers are guesses)
- **Spatial language** — "on your left", "in the centre", from bbox position
- **Salience ranking** — talk about the big/close/new thing, not the 6th chair
- **Event narration** built on Day 2 tracks — "someone just walked in"
- Optional richer description mode

**Concept:** The hard part of narration is **when to speak**, not what to say.
Turning a list of labels into something a human wants to hear is a filtering
problem.

**Demo:** Narration off vs on. Walk in — "a person entered from the left."
Pick up a cup — "you're holding a cup."

**Hook:** *"Making an AI talk is easy. Making it shut up at the right time is
the actual product."*

---

## Day 4 — "It looks like the future" (HUD/UX polish)
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

## Day 5 — "It gets fast" (latency)
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

## Day 6 — "It survives reality" (robustness + mobile)
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

## Day 7 — "Ship it" (polish + final demo)
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
1. Day 5 WebGPU (WebGL is already fast enough)
2. Day 4 animation polish
3. Day 6 unit tests
4. Day 3 optional rich-description mode

## Never cut
Day 2 tracking — it's the single biggest quality jump in the week.
