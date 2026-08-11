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

**Concept:** Perceived intelligence is mostly interface design. The model
didn't change today — nothing in detection or narration got smarter. Every
pixel of difference on screen comes from *presentation*.

**Simple explanation (2–4 lines):**
> Yesterday's boxes were plain rectangles with a label. Today the same
> detections get a reticle that converges on lock, a target that fades out
> instead of vanishing when it's lost, a "primary target" the HUD visibly
> focuses on, and a real confidence ring instead of a bare number. None of
> that required the model to get better at seeing — it required teaching the
> drawing code to remember things across frames it used to forget instantly.

**What viewers should notice:**
- Brackets visibly converge inward when something new is detected, and
  release outward and fade when it's lost — not an instant snap either way
- One target reads as "the subject" — brighter, with a confidence ring and
  a size readout — while everything else quietly dims
- A subtitle line at the bottom of the frame carries the narration even
  with the sound off
- The telemetry panel now shows a `HUD draw` number, not just FPS and
  inference — proof the polish is being measured, not assumed free

**What was hard:**
The actual hard problem wasn't any single animation — it was that the
existing drawing code physically couldn't animate anything. It was a pure
function that took the current frame and painted it, with no memory of what
happened a moment ago. A lock-on animation needs to know *when* a target
first appeared; a lose-animation needs to keep drawing a target the tracker
has already completely forgotten about. The fix was a new, separate layer of
state sitting between detection and drawing — its own short memory, kept
deliberately apart from the tracker's, because "how long should an object
keep its identity" and "how long should its bracket linger on screen after
it's gone" are different questions with different right answers. The other
real decision was refusing a number: a bigger box only means "closer" if you
know how big the real object is and how the camera lens works, and this
project knows neither — so instead of guessing a distance in metres, the
HUD shows the box's honest size as a percentage of the frame.

**Posts:**
- **X:** "Day 5 of building YAP. Didn't touch the model. Added a reticle
  that locks on, a target that fades out instead of vanishing, a real
  confidence ring. Same 80-class detector as day one — just drawn like it
  knows what it's doing. 🧵"
- **LinkedIn:** Frame it as a UX lesson that generalizes: a lot of "this
  product feels smart" moments are interface state and animation timing,
  not model quality — and it's worth being honest with yourself about which
  one you're actually shipping.
- **Reel caption:** "I didn't touch the AI today. It looks twice as smart.
  That gap is entirely design."

**Line:** "Perceived intelligence is mostly interface."

## Day 6 — "It stops guessing, and it answers back"

**Concept:** Two complaints from real use, and they're the same complaint —
the system was *asserting* instead of *communicating*. A bed reported as a
dining table, with total confidence. No way to ask it anything. Today it
learns to say "I'm not sure," to be corrected, and to be asked a question.

**Simple explanation (2–4 lines):**
> Every object's label used to come from whichever single detection matched
> it *this frame* — throwing away everything the system had seen about that
> object a moment ago. Now each tracked object keeps a running vote across
> its recent frames, and when that vote is genuinely torn between two
> answers, it says so instead of picking one and sounding sure. On the voice
> side: hold a key, ask it what it sees, and it answers out loud — using a
> tiny local speech-to-text model, the same "runs on your machine, not in
> the cloud" rule as everything else this week, extended to your voice this
> time instead of your camera.

**What viewers should notice:**
- A bed that used to flicker between two different track ids as the model
  flip-flopped now keeps one id, and if the model genuinely can't decide,
  the label reads `BED / DINING TABLE ?` instead of confidently picking one
- Holding a key and asking "what do you see" gets a real spoken answer,
  subtitled, with your own question shown dim and separate from YAP's reply
- Saying "stop" actually stops it, immediately, mid-sentence
- The telemetry panel now shows a full latency breakdown — inference,
  tracking, drawing, speech recognition, the line-writing model, the voice
  model — every stage timing itself

**What was hard:**
The honest failure has two different shapes and conflating them wastes the
whole day. A bed read as a dining table is the model picking the *wrong
word it actually knows* — fixable, with memory. A microphone read as a tie
is the model being asked a question it structurally *cannot* answer — COCO
has no `microphone` class, so no amount of voting fixes that, only a
different kind of model or an honest shrug. This session shipped the fix
for the first shape and ran out of runway for the second — the microphone
is still going to say `tie` until open-vocabulary relabeling lands, and
saying that plainly, instead of implying both are solved, is the actual
point of splitting them apart in the first place. The other hard part was
architectural, again: the free, built-in browser speech-to-text API streams
your voice to a cloud server to do the recognition. That's exactly the kind
of hidden cloud call this project has refused since Day 1, so it was turned
down on principle and a real local speech model was used instead, at real
engineering cost (recording, resampling, a second permission prompt) that
the free option would have skipped entirely.

**Posts:**
- **X:** "Day 6 of building YAP. It used to confidently call my bed a dining
  table. Now it says 'bed, or maybe dining table — hard to say' and it's
  right that it doesn't know. Also: you can talk to it now. Hold a key, ask
  what it sees, it answers. Still zero cloud calls, even for your voice. 🧵"
- **LinkedIn:** Frame it as a broader lesson about confidence calibration —
  a system that reports its own uncertainty honestly is more trustworthy
  and more useful than one that's always sure, even when the underlying
  accuracy hasn't changed at all.
- **Reel caption:** "It used to lie with total confidence. Now it says 'I'm
  not sure' — and somehow that makes it feel smarter, not dumber."

**Line:** "An AI that admits uncertainty reads as more intelligent, not less."

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
- The confidence ring around the primary target is real `Detection.score`,
  drawn as an arc, not decoration (Day 5)
- The relative-size readout (`SIZE n% OF FRAME`) is real division — box
  area over frame area, both real numbers (Day 5)
- The boot sequence's four status lines are read directly off the app's own
  real state (camera/model/tracker/narrator) — no scripted timing (Day 5)
- The lock-on, lose-fade, and primary-focus-transfer animations are driven
  by real elapsed time (frame-rate independent) and real track identity —
  the fade you see on a lost target is the HUD's own short memory of a
  track the detector has already fully forgotten (Day 5)
- A tracked object's label is a real vote across roughly its last 30 frames,
  not just whatever the model said this instant — and when that vote is
  genuinely split, the HUD says `LABEL / RUNNER-UP ?` and narration hedges,
  rather than confidently picking one (Day 6)
- Speech recognition is local — a real Whisper model runs in the browser,
  verified to load and transcribe in an actual production build, not just
  the dev server (Day 6)
- Audio recorded for a voice command never leaves the device and is never
  saved to disk — it's held in memory only for the length of one
  push-to-talk press, then discarded once transcribed (Day 6)
- `stop`, `wake`, `sleep`, `describe_scene`, and `query_object` are
  recognised by a fixed, deterministic pattern matcher, not the LLM — the
  LLM never decides a control action (Day 6)
- The spoken answer to "what do you see" is grounded in the exact same
  track data the HUD draws from — it's the same honesty rule as narration,
  applied to a direct question instead of an ambient comment (Day 6)

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
- ❌ "It understands the room" / "it knows what it's looking at" — Day 5's
  reticles, confidence rings, and boot sequence make the HUD *look* like it
  has scene understanding, identity recognition, memory, or threat
  assessment. It has **none** of that. It's the same 80-class detector as
  Day 1, drawn better — that gap between look and capability is the actual
  finding of Day 5, not a caveat to bury. Say it on camera: *"This looks
  like it understands the room. It does not."*
- ❌ "It knows how far away things are" — no distance estimate is shown or
  computed. The Day 5 confidence ring is the object's detection score; the
  size readout is the box's share of the frame, not a real-world distance —
  a bigger box is not "closer" without knowing the object's real size and
  the camera's focal length, neither of which this project has (D17).
- ❌ "The HUD is intelligent" / "it's paying attention to the primary
  target" — the "primary target" is a fixed formula (box area × how
  centered it is), recomputed every tick. It is not attention, salience
  understanding, or intent — it is one number picking the biggest,
  most-centered box.
- ❌ "It understands what you say" — voice commands are matched against a
  fixed list of patterns (`parseIntent.ts`). Off-script phrasing fails and
  says so, honestly, rather than guessing at intent. This is pattern
  matching, not language understanding.
- ❌ "It has open-vocabulary vision" — it does not, as of Day 6. It can only
  say "unidentified" when its fixed 80-word vocabulary can't settle on an
  answer; it cannot yet supply a *better* word (that's the open-vocabulary
  CLIP work, explicitly cut this session — see decisions.md D22). A
  microphone still gets called a `tie`.
- ❌ "It has a wake word" — not shipped. Push-to-talk only, as of Day 6. If
  a wake word ships later, describe it accurately when it does:
  transcribe-then-match against "yap"/"hey yap", not a trained,
  low-power keyword-spotting model — it would cost real CPU continuously
  and misfire, nothing like Siri/Alexa's always-on listener.
- ❌ "It fixed the wrong-label problem" — it fixed *half* of it. The
  in-vocabulary confusion (bed vs. dining table, both real COCO classes) is
  fixed by label voting. The out-of-vocabulary problem (a microphone isn't
  one of COCO's 80 classes at all) is not — the model is still forced to
  guess the nearest of 80 wrong words for anything genuinely outside its
  vocabulary, same as every prior day.

## Tone rules
- Show the failures. Wrong labels are content, not shame.
- Always show the telemetry — numbers beat adjectives.
- Never say "AI-powered". Say what it actually does.
- End every day on what's broken. That's the reason to come back tomorrow.
