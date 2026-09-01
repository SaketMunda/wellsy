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
a stability gate: an object must hold steady for ~a second before WELLSY mentions it.

**The bug worth telling:**
All my labels rendered backwards. I'd mirrored the video for a natural selfie
view, then mirrored the overlay to match — which mirrored the text too. Fix:
mirror the *coordinates*, not the canvas.

**Posts:**
- **X:** "Day 1 of building WELLSY. My browser now sees. 12ms per frame, 60fps, no
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
- **X:** "Day 2 of building WELLSY. It had two jobs running at two speeds — eyes
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
- **X:** "Day 3 of building WELLSY. Yesterday every video frame was independent —
  no memory. Today objects get an ID number and an age. Walk past the camera
  twice, it's still #3. 🧵"
- **LinkedIn:** Frame it as the detection-vs-tracking distinction generally —
  a lot of "this AI feels smart" moments are actually just state being
  carried across time, not a bigger model.
- **Reel caption:** "Yesterday it saw. Today it remembers. That's the whole
  difference between a camera and a system."

**Line:** "Yesterday it saw. Today it remembers."

## Day 4 — "A better voice, still no cloud bill"

**Concept:** Two upgrades — a local LLM for what WELLSY says, a local neural
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
- **X:** "Day 4 of building WELLSY. Gave it a real brain and a real voice —
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
- **X:** "Day 5 of building WELLSY. Didn't touch the model. Added a reticle
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
  subtitled, with your own question shown dim and separate from WELLSY's reply
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
- **X:** "Day 6 of building WELLSY. It used to confidently call my bed a dining
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

## Claims retired Day 7

Days 1–6 were sold on three sentences that stop being true starting with the
V2 pivot (`v2-architecture-research.md`, `v2-roadmap.md`). They are struck
through here, dated, with what replaces them — never quietly deleted. See
decisions.md D28 for the measured reasoning behind the pivot itself.

> ~~"No backend"~~ — **retired Day 7.** V2 runs a local Python engine
> (`engine/`) as a separate process from the browser UI, and Day 14 adds an
> optional private server for the heavy, on-demand work (LLM, depth,
> segmentation, face recognition). The honest replacement: *"the backend is
> a process on your machine, not someone else's server."*

> ~~"Runs entirely in your browser"~~ — **retired Day 7.** The browser stays
> as the HUD/UI layer, but perception moves to a local Python engine talking
> to it over a local connection. Replacement: *"the interface is a browser
> tab; the eyes are a local process."*

> ~~"Video never leaves your device"~~ — **retired Day 7.** True through Day
> 13. From Day 14, an optional private server (hardware the user owns) can
> run the on-demand heavy models over the LAN or WAN. The honest
> replacement: *"your data goes to hardware you own, and nowhere else."*
> Still a strong claim. A different one.

**"No API keys" survives, and is now the strongest remaining claim.** No
third-party service — cloud vision, cloud LLM, cloud TTS/STT — has been
called at any point in this project, Day 1 through the V2 pivot and beyond.
That does not change.

## Claims added Day 7 (live, replacing the above)
- "The backend is a process on your machine, not someone else's server."
- "The interface is a browser tab; the eyes are a local process."
- "Your data goes to hardware you own, and nowhere else." (from Day 14 on,
  when the private-server option ships — until then, "your data never
  leaves this machine" remains literally true)
- "No API keys, no cloud account, no third-party service ever sees a frame,
  a transcript, or a line of narration." — unchanged since Day 1, and now
  the load-bearing privacy claim in place of "runs in the browser."

## Claims added Day 9

The retirement block above was written in advance, on Day 7, before the
engine had a way to actually reach the HUD. Day 9 is where that claim
stops being aspirational: `?engine=1` makes it real — the HUD renders
tracks pushed live from `engine/main.py` over a local WebSocket, not from
the in-browser TF.js model. **The browser-only build is a flag, not the
default** — load the app with no query param and it's still exactly the
Day 1–6 architecture, unchanged, for anyone without the Python engine
running.

- "The interface is a browser tab; the eyes are a local process" (Day 7's
  claim) is now something a viewer can watch happen: open the network tab,
  see a WebSocket connection to `127.0.0.1`, see boxes arrive with no
  camera frame ever encoded or uploaded — the socket carries only numbers
  (coordinates, labels, scores), never pixels.
- Checked for drift, per day9-prompt.md's own instruction: no "runs in your
  browser"-shaped claim crept back in anywhere in this file since Day 7's
  retirement. The Day 1–6 REAL/NOT-real lists below describe the *browser
  build specifically* and are labeled as such — they were not silently
  promoted to describe the whole project.
- **Now claimable, with a real screenshot to back it:** a real camera in a
  real room, real detection, `bed` correctly labeled `bed` (not `dining
  table`, the Day 1–6 confusion this whole arc chased) through the live
  HUD, `?engine=1`, narration reacting to the real tracks. Real
  end-to-end camera→pixel latency measured at p50 77ms. See
  `day9-results.md` for the screenshot and the numbers. **Not yet
  claimable:** the specific "interpolation looks smooth during fast real
  motion" claim — the one item this session's real-hardware testing
  didn't close out (see day9-results.md's τ section for exactly why).

---

## What is REAL (claim freely)
- Live object detection on real camera frames, on-device
- ~12ms inference, real-time framerate (Day 1–6, browser build; see
  day7-baseline.md for measured V2-era numbers)
- Video genuinely never leaves the device — true through the browser build
  and Days 7–13 of V2; see the retirement block above for what changes Day 14
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
- ✅ **Update, Day 10: audio has been confirmed audible, by a human, for
  real.** Nine days open — closed by playing a test line through the room's
  real speakers and having someone actually listen (not an exit code). The
  engine's TTS is macOS's built-in `say`, not the browser's neural Kokoro
  voice — a deliberate, documented trade for reliability over expressiveness
  (decisions.md D39); don't imply the engine build has the same voice as the
  browser build's Kokoro path.
- ❌ Day 10: **the wake phrase is not a trained keyword spotter.** It's
  transcribe-then-match — Moonshine transcribes a rolling audio window and
  the text is fuzzy-matched against a phrase list. Say that plainly if
  asked how it works. A real keyword spotter (openWakeWord) is the named
  upgrade path, not built.
- ❌ Day 10: **the query answers are pattern-matched, not understood.**
  `parseIntent` is a fixed regex list; off-script phrasing ("could you tell
  me what's around") gets an honest "I didn't understand that," never a
  guess. Zero LLM in this path.
- ❌ Day 10: **ambient narration is now off by default.** WELLSY stays silent
  until asked, a rule fires, or ambient mode is explicitly turned on by
  voice ("wake"). Don't imply it narrates continuously anymore — that was
  Days 1–6's behavior, now an opt-in mode.
- ❌ Day 10: **the wake word has a known, live-confirmed problem** —
  it's regularly mis-transcribed as "app." Say so if demoing it; a
  replacement phrase is planned but not yet chosen.
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
- ✅ "It has open-vocabulary vision" — true as of Day 8, **in the new Python
  engine (`engine/`) only**. YOLOE, text-promptable via `engine/prompts.txt`
  — add a word, it can find the thing. But: (1) this is not yet wired to
  the HUD or the microphone/tie demo shown on camera through Day 7 — that's
  the *browser build* (`src/`), which is untouched and still the fixed
  80-class detector as of Day 8 (decisions.md D28 explains why the two
  builds coexist). Don't imply the shipped demo changed; the engine did.
  (2) **finding a word is not understanding a scene** — text-prompting
  means the model can *localize and name* whatever's in `prompts.txt`, not
  that it knows what a microphone is, what it's for, or that a bed implies
  a bedroom. Same caution as the Day 5 "this looks like it understands the
  room, it does not" line — a better vocabulary is still not comprehension.
- ❌ "It has a wake word" — not shipped. Push-to-talk only, as of Day 6. If
  a wake word ships later, describe it accurately when it does:
  transcribe-then-match against "wellsy"/"hey wellsy", not a trained,
  low-power keyword-spotting model — it would cost real CPU continuously
  and misfire, nothing like Siri/Alexa's always-on listener.
- ❌ "It fixed the wrong-label problem" — it fixed *half* of it. The
  in-vocabulary confusion (bed vs. dining table, both real COCO classes) is
  fixed by label voting. The out-of-vocabulary problem (a microphone isn't
  one of COCO's 80 classes at all) is not — the model is still forced to
  guess the nearest of 80 wrong words for anything genuinely outside its
  vocabulary, same as every prior day.
- ❌ "It measures real depth" — not built yet. Planned Day 13
  (`v2-roadmap.md`, Depth Anything V2). Until then the Day 5 rule stands:
  size-as-percent-of-frame, never a fabricated distance (D17).
- ❌ "It recognises faces" / "it knows who you are" — not built yet. Planned
  Day 12. Until then WELLSY has no memory of people across sessions and no
  concept of "known" vs "unknown."
- ✅ "It has open-vocabulary detection" — shipped Day 8, in `engine/` — but
  not via MLX as originally planned. No PyPI package implements an
  open-vocabulary detector on MLX (checked, decisions.md D30); it runs on
  PyTorch/MPS instead, same open-vocabulary capability, different runtime.
  Not camera-verified yet (no hardware access the session it shipped) — the
  actual "microphone stops being a tie" moment is confirmed on synthetic
  test input, not yet on a real microphone. Say "the engine can now be told
  new words" accurately; don't claim the bed/microphone shot exists until
  it's actually been filmed.
- ❌ "It runs on my phone" — desktop/laptop only through Day 13. Mobile
  on-device export is planned Day 14 and is explicitly the day most likely
  to be cut (see v2-roadmap.md's "if it slips" list) — say "planned, not
  shipped" if asked before then, not "coming soon."

- ✅ "It can read" — shipped Day 11: a real Python traceback, a receipt, a
  document page, a product label, and a script-font "handwriting" sample
  were all read correctly by `qwen3-vl:4b` (see day11-results.md). **Say
  what changed accurately**: the detector's job changed from "identify the
  80-ish words in `prompts.txt`" to "corroborate what the VLM actually
  sees" — this is not "the detector got upgraded," it's a different model
  doing the answering entirely. ❌ Don't say "it read a real handwriting
  sample" — the shipped test used a stylized script font, not genuine
  handwritten strokes; real handwriting is still untested.
- ✅ "It looks at the screen" — the code path (`screen_capture.py`) is
  real and tested in isolation (203.9ms for a real capture). ❌ Don't say
  "it read something off my screen" as a finished demo — the actual
  screen→VLM path was never exercised end-to-end this session (a sandbox
  limitation where windows this agent spawns don't render on the
  capturable display, not a bug in the capture code itself — see D42).
- ✅ "It stopped inventing what you're holding" — the two specific Day 10
  failures ("standing next to the chair", "holding glasses" with nothing
  held) were retested verbatim on real camera + real tracks and did not
  reproduce, on both model sizes tried. ❌ Don't say "grounding is solved"
  — two retested cases not recurring is real evidence, not a general proof
  the model can never embellish under different framing.
- ❌ "It answers instantly now" — it doesn't. Real measured first-token
  latency for a VLM-routed question is ~1.7-2.8s (`qwen3-vl:4b`, this
  machine) — noticeably slower than the deterministic fast path's ~17ms.
  The honest framing: simple questions still answer fast (unchanged);
  anything needing real vision costs real seconds, and that's the accepted
  trade, not a hidden regression.

- ✅ "The robotic voice is gone" — `say -v Samantha` was replaced with
  Chatterbox Turbo (real neural TTS, MIT license) mid-Day-11, pulled
  forward from the original Day 14 plan on the owner's explicit call.
  ❌ Don't say "it has emotional/expressive control now" — the
  `exaggeration` parameter is silently ignored by the fast Turbo
  checkpoint (its own logged warning says so); only the slower base model
  supports it, and that hasn't been tested.
- ❌ "It answers instantly" — say this **less** true now than it was
  Wednesday. The new voice costs a real 1.6-3.2 second generation pause
  before any sound starts, for every answer, including the ones that used
  to be instant (`describe_scene`/`query_object`). This is the real,
  accepted trade for not sounding robotic — say the number, don't let the
  demo's silence read as a bug.

## Tone rules
- Show the failures. Wrong labels are content, not shame.
- Always show the telemetry — numbers beat adjectives.
- Never say "AI-powered". Say what it actually does.
- End every day on what's broken. That's the reason to come back tomorrow.
