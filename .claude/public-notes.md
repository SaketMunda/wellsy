# Public Notes — build-in-public content

## The series premise (one line)
> 7 days. Building an AI that sees the world through a camera and describes it
> in real time. No backend, no API keys — it runs in your browser.

---

## Day 1 — "I gave my laptop eyes"

**Concept:** Real-time object detection in the browser.

**Simple explanation (2–4 lines):**
> A neural network looks at each video frame and, in one pass, guesses both what
> objects are in it and where they are. That "one pass" is why it's fast enough
> for live video — older approaches had to scan an image hundreds of times.
> It runs on your graphics card, in a browser tab. Nothing is uploaded.

**What viewers should notice:**
- Boxes track objects as they move — it's live, not a filter
- 12ms inference, 60 FPS, on screen
- It speaks only when something *changes*

**What was hard:**
The narration. Making an AI describe a scene takes ten minutes. Making it
describe a scene *without being unbearable* is the actual work — every frame
it'd say something, and low-confidence boxes flicker so it stutters. Solved with
a stability gate: an object must hold steady for ~a second before YAP mentions it.

**The bug worth telling:**
All my labels rendered backwards. I'd mirrored the video for a natural selfie
view, then mirrored the overlay to match — which mirrored the text too. Fix:
mirror the *coordinates*, not the canvas.

**Posts:**
- **X:** "Day 1 of building YAP. My browser now sees. 12ms per frame, 60fps, no
  server, no API key. Every box is a real prediction on a real frame. 🧵"
- **LinkedIn:** Lead with the privacy/latency angle — on-device inference is the
  interesting engineering claim, not "I used an AI model".
- **Reel caption:** "I gave my laptop eyes in one day 👁️ It just told me what's
  on my desk. Runs entirely in the browser — nothing uploaded."

---

## Day 2 — "The mouth was drowning"

**Concept:** Two loops running at two speeds. Detection — the eyes — runs the
browser at 60 frames a second, ~12ms a frame. That part was never the problem.
Narration was chained to that same frame loop: every frame, it tried to say
something. Sixty opinions a second, all late, all fighting each other.

**Simple explanation (2–4 lines):**
> A detector can look at a frame every 11 milliseconds. A sentence takes longer
> than that to say, let alone to be worth hearing. Narrating every frame means
> narrating the same chair sixty times a second — not intelligence, just noise
> at high frequency. The fix has two parts: talk about *events*, not frames
> (a chair doesn't need commentary 60 times a second — twice: when it shows up,
> when it leaves), and put narration on its own clock, decoupled from
> detection, capped at one line every four seconds, picking the most
> interesting thing when several happen at once.

**What viewers should notice:**
- Boxes still update live, every frame — detection didn't slow down
- The narration log adds a new line roughly every 4+ seconds, never faster
- "Boring mode" in the telemetry panel shows the literal event
  (`appear` / `disappear` / `count_change`) behind each styled line — proof
  it's driven by real detections, not a script

**The bug worth telling:**
Sixty opinions a second, all late, all fighting each other — the mouth was
drowning. Fixed with two changes: collapse the 60fps frame stream into
discrete events (appear / disappear / count change), and give narration its
own 250ms sampler with a 900ms stability gate and a 4-second rate limit,
completely decoupled from the detect loop.

**Posts:**
- **X:** "Day 2 of building YAP. It had two jobs running at two speeds — eyes
  at 60fps, mouth trying to keep up. Fixed by teaching it to talk about
  *events*, not frames, and giving it its own clock. One line, every 4
  seconds, on purpose. 🧵"
- **LinkedIn:** Frame it as an architecture lesson that generalizes beyond
  this project — decoupling a high-frequency producer from a low-frequency
  consumer, with rate-limiting and priority selection at the boundary.
- **Reel caption:** "Yesterday it could see. It just couldn't stop talking
  about it. Today it learned when to shut up."

**Line:** "Sixty opinions a second, all late, all fighting each other."

## Day 3 — "It learned to remember"

**Concept:** Detection vs tracking. A detector answers "what's here *now*". A
tracker answers "is this the *same* thing I saw a second ago?". Everything
that feels intelligent comes from the second question.

**Simple explanation (2–4 lines):**
> Every frame of detection used to be independent — no memory, no identity, so
> two boxes on the same object one frame apart were, as far as the system was
> concerned, two different objects that happened to overlap. A tracker matches
> this frame's boxes to last frame's by how much they overlap, gives the match
> a persistent number, and smooths its position instead of snapping to the
> raw, noisy detection every time. That's the whole trick — no prediction, no
> re-identification, just "is this probably the same thing."

**What viewers should notice:**
- Boxes hold steady instead of flickering/jittering frame to frame
- Each box now carries a number and an age — `PERSON #3 · 4.2s` — not just a
  label and confidence score
- The narration log says "person #4 appeared" when a second person walks in,
  not a vaguer "now 2 person"

**What was hard:**
Deciding what to leave out. A real tracker could predict motion (Kalman
filter) or re-identify an object that fully leaves and comes back — neither
is built. The honest version is simpler: IoU overlap, same object class
required, a short grace window (5 missed frames) so a single dropped
detection doesn't reset an identity, and that's it. The other real decision
was narration: switching it to read tracker identity directly instead of
counting labels made one of its four event types (`count_change`) structurally
unreachable — the fix for one problem quietly retired part of another system,
which is the kind of thing worth stating in tradeoffs, not hiding.

**Posts:**
- **X:** "Day 3 of building YAP. Yesterday every video frame was independent —
  no memory. Today objects get an ID number and an age. Walk past the camera
  twice, it's still #3. 🧵"
- **LinkedIn:** Frame it as the detection-vs-tracking distinction generally —
  a lot of "this AI feels smart" moments are actually just state being
  carried across time, not a bigger model.
- **Reel caption:** "Yesterday it saw. Today it remembers. That's the whole
  difference between a camera and a system."

**Line:** "Yesterday it saw. Today it remembers."

## Day 4 — "A better voice, still no cloud bill"

**Concept:** Two upgrades — a local LLM for what YAP says, a local neural
voice for how it says it — both running entirely on-device, same promise as
Day 1.

**Simple explanation (2–4 lines):**
> The narrator's lines came from a fixed template bank until today. Now
> there's a small AI model — about 500 million parameters, roughly a
> thousandth the size of the big cloud models — running directly in the
> browser to write fresh lines instead. Same for the voice: a real neural
> text-to-speech model instead of the robotic default your OS ships with.
> Both download once (a few hundred MB, shown live in the network tab), get
> cached, and after that run with zero network calls — same story as the
> camera never leaving the device, just extended to the mouth.

**What viewers should notice:**
- The network tab, showing a real download the first time an engine is
  switched on — this isn't a claim, it's traffic you can watch
- A second load of the same page landing on "ready" in ~11 seconds instead
  of ~50, with the network tab staying empty — the caching claim, provable
- While the model downloads, narration doesn't go silent or stutter — it
  keeps talking in the old templated voice until the new one is ready, then
  switches over live
- Live latency numbers on the panel for both the line-writing model and the
  voice model — not adjectives, milliseconds

**What was hard:**
The model choice was the easy part — read what's actually in a local model
library, pick the smallest one that clears the bar. The real problem was
architectural: the existing line generator is a plain synchronous function,
and an AI model is not — it takes real time to think. The fix wasn't to
make the whole app wait on it. It was to start the model thinking the
moment something happens, hand it several seconds of head start using
timing the narrator already had for other reasons, and if it's not done
thinking by the time it's due to speak, say the old reliable line instead
and let the AI's answer catch up next time. And the honest part: the neural
voice hit a real bug during testing — a dependency inside it failed to
speak. Instead of hiding that, the system silently falls back to the
built-in voice and logs why. That fallback *working exactly as designed*
is arguably the most interesting result of the day, and it is going in the
video, not around it.

**Posts:**
- **X:** "Day 4 of building YAP. Gave it a real brain and a real voice —
  both running on-device, zero cloud calls. Watched the network tab do
  nothing while it kept talking. Also found a real bug in the new voice
  and shipped the video with the bug still in it. 🧵"
- **LinkedIn:** Frame it as the general pattern for adding a slow AI model
  behind a fast synchronous interface without blocking the caller — start
  the work early, cache the result, fall back cleanly if it's not ready.
  Applies far beyond a webcam toy.
- **Reel caption:** "It downloads once. Then it never calls home again.
  Watch the network tab do nothing while it keeps talking."

**Line:** "A better voice usually means a cloud bill. Ours doesn't."

## Day 5 — "Same brain, better face"
> I didn't touch the model today. It feels twice as smart. That gap is design.

**Line:** "Perceived intelligence is mostly interface."

## Day 6 — "33 milliseconds"
> At 30fps you get 33ms to capture, think, and draw. Optimisation is just
> deciding where those milliseconds go.

**Line:** "Real-time isn't a feature, it's a budget."

## Day 7 — "Trying to break it"
> Demos work in one room with good light. Products work in the dark, on a
> phone, with the camera denied.

**Line:** "Every demo works on the demo machine."

## Day 8 — "Here's the link"
> 7 days, no backend, no API keys, no cost. Open the link and your laptop starts
> seeing.

---

## What is REAL (claim freely)
- Live object detection on real camera frames, on-device
- ~12ms inference, real-time framerate
- Video genuinely never leaves the device
- Narration is generated from actual detections
- Everything on screen comes from a real model
- Objects get a persistent ID and age, matched frame to frame by IoU overlap,
  with position/size smoothing to kill jitter (Day 3)
- A local LLM (Qwen2.5-0.5B) writes narration lines, and a local neural TTS
  model (Kokoro-82M) exists behind the voice toggle — both run in the
  browser, both download once and are then cached (Day 4)
- The models are downloaded once over the network, then cached — inference
  itself runs with zero network calls after that, verified by cutting the
  network entirely mid-session and watching new narration lines keep
  appearing (Day 4)

## What is NOT real yet (never overclaim)
- ❌ "Runs entirely on the device" without the nuance — the model *weights*
  are fetched over the network the first time (a few hundred MB), then
  cached. Say "video never leaves the device" and "inference is local and
  offline after the first load" — both true — not "no network, ever."
- ❌ "It has a real voice now" — the local neural TTS (Kokoro) has a live,
  unresolved bug and has not actually been heard to speak as of Day 4. What's
  true and demoable: it downloads, loads, and the app never goes silent —
  it falls back to the built-in voice automatically. Don't claim more.
- ❌ "Nobody's heard YAP talk yet" isn't a caveat to bury — say it plainly if
  asked. No audio has been confirmed audible on any machine this project has
  run on, across all four days, because every verification session so far
  has been headless with no speaker.
- ❌ "It understands scenes" — it detects **objects**. It doesn't know "kitchen"
  or "someone is cooking".
- ❌ "It recognises anything" — **80 fixed classes**. No text, no faces, no brands.
- ❌ "It predicts motion" — no Kalman filter or velocity estimate. A track's box
  freezes at its last known position during a brief miss, it doesn't extrapolate.
- ❌ "It remembers objects that left" — no re-identification. An object that
  fully leaves frame and a new object of the same class entering later gets a
  brand-new ID, not the old one back.
- ❌ "Production ready" — it's a 7-day build.
- ❌ Don't imply a custom-trained model. It's an off-the-shelf model, well
  integrated. **The engineering is the pipeline, not the network** — say that,
  it's a more honest and more interesting claim anyway.

## Tone rules
- Show the failures. Wrong labels are content, not shame.
- Always show the telemetry — numbers beat adjectives.
- Never say "AI-powered". Say what it actually does.
- End every day on what's broken. That's the reason to come back tomorrow.
