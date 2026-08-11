# Demo Script

## The one-liner
> YAP turns any webcam into a heads-up display that sees what's in front of it
> and tells you what it sees — in real time, entirely on your own device.

---

## Day 1 demo flow (60–90 seconds)

### 0:00 — Cold open, no explanation
Screen already showing the dark HUD, "PERCEPTION OFFLINE".
Click **Start camera**.

> "Watch this."

Let the model load. The wait is honest — say so:
> "It's downloading the vision model. That happens once."

### 0:10 — The moment
Boxes snap onto you and whatever's on your desk. Say nothing for two seconds.
**Let the visual land.** Then:

> "That's my webcam. Nothing is being uploaded anywhere. That's my laptop's
> GPU, running a neural network, thirty times a second."

### 0:25 — Prove it's live
Pick up a cup. Hold up your phone. Move a chair into frame.
New brackets appear.

> "It's not a filter. Every box you see is a real prediction on a real frame."

### 0:40 — Narration
Turn narration on. Let it speak.

> "And it tells me what changed. Not what's there — what *changed*. That
> difference turns out to be the entire hard part."

### 0:55 — The telemetry
Point at the panel.

> "Twelve milliseconds to look at a frame and decide what's in it. Sixty frames
> a second. No server, no API key, no internet after the first load."

### 1:10 — Honest close
> "It knows eighty kinds of object. The boxes still shake, because right now
> every frame is a fresh guess with no memory. That's tomorrow."

---

---

## Day 2 demo flow (60–90 seconds) — "The mouth was drowning"

### 0:00 — Cold open, state the problem
> "Yesterday YAP could see. It just couldn't stop talking about it."

Start the camera, turn narration on, point at the telemetry panel.

> "Detection runs at 60 frames a second — eleven milliseconds a frame. That
> part was never the problem. The problem was the mouth: it used to be chained
> to that same loop. Every frame, it tried to say something. Sixty opinions a
> second, all late, all fighting each other."

### 0:20 — Show the fix is architectural, not cosmetic
Open "boring mode" in the Narrator panel.

> "So instead of narrating frames, it narrates *events*. A chair doesn't need
> commentary sixty times a second — twice: when it shows up, when it leaves.
> This line — " *(point at a log entry)* " — isn't scripted. It's the literal
> event underneath: appear, disappear, count change."

### 0:40 — Prove the rate limit, live
Move objects in and out of frame quickly (pick up a cup, put it down, pick up
a phone) for 15–20 seconds.

> "Watch the log. Boxes update every frame — still live. But the narration log
> only grows about once every four seconds, even though I'm giving it way more
> than that to talk about. It picks the most interesting thing that happened
> and moves on."

### 1:00 — The numbers
Point at telemetry: sample interval, stability window, rate limit.

> "Sample every 250 milliseconds. A scene has to hold for 900 milliseconds
> before it counts as real, so flicker doesn't get a vote. And it will not
> speak more than once every four seconds, full stop. That's the whole fix —
> two clocks that don't touch."

### 1:15 — Honest close
> "The eyes were never slow. The mouth was. Today the mouth got its own
> clock."

---

### Why there's no literal "before" clip
The original frame-chained narrator isn't a separate build to cut back to —
recreating it would mean deliberately regressing working code for a demo,
which this project's rules count as staging a fake failure rather than
showing a real one. The honest version of "before vs after" is the telemetry
itself: `SAMPLE_MS` / `STABLE_MS` / `min_seconds_between_lines` in
[day2-poc.md](day2-poc.md), plus "boring mode" proving each styled line traces
back to one real event. If a literal before/after is wanted later, the
before state is fully described in code comments and `day1-poc.md` — it can be
narrated verbally ("this used to fire every frame") without staging it.

---

## Day 3 demo flow (60–90 seconds) — "It stops shaking"

### 0:00 — Cold open, name the gap
> "Yesterday YAP saw. Every frame was a fresh guess with no memory — which is
> why the boxes shook."

Start the camera. Hold a hand or object still and let a viewer see the
label read `LABEL #id · age` next to the bracket.

> "Watch this number. That's not a score, it's an identity. This object has
> been the same object, continuously, for—" *(point at the age)* "—that long."

### 0:20 — Prove it's not just cosmetic
Move slowly, then move fast, then briefly duck out of frame and back in
within about a second.

> "The box smooths instead of jumping to every raw detection. And if it loses
> me for a frame or two — a blink, a bad angle — it doesn't forget who I am.
> Same ID when I come back."

### 0:45 — A second object, same class
Bring a second instance of something already on screen (a second cup, a
second person if possible).

> "Old system: 'now 2 person.' That's a number, not news. New system: this is
> a *different* person, and it gets its own ID and its own line — 'person #4
> appeared.' The narration didn't get smarter. It just stopped losing
> identity on the way to the sentence."

### 1:05 — Honest close
> "No prediction, no memory of something that fully leaves and comes back
> later — that's a new object as far as YAP's concerned. Simple tracker, on
> purpose. What it buys: the boxes stopped shaking, and the narration finally
> knows who it's talking about."

---

### Why this demo needs a real webcam
The synthetic fake-camera device used for headless verification (`day3-poc.md`)
doesn't hold a stable detection long enough to walk out of frame and back —
its pattern flickers on its own noise. The occlusion-recovery beat above is
real functionality, verified in code and via direct tracker-state logging,
but has not yet been filmed against a real camera. Confirm ID persistence on
a real re-entry before recording this section, and say so on camera if it
doesn't land clean the first time — that's Day 1/2's rule, not a Day 3
exception.

---

## Day 4 demo flow (90–120 seconds) — "A better voice, still no cloud bill"

### 0:00 — Cold open on the network tab
Open devtools, Network tab, empty. Start the camera.

> "Everything you're about to see — the detection, the narration — has made
> zero network requests so far. That hasn't changed today. What's new is
> what happens when I turn on a smarter voice."

### 0:15 — The same scene, three narrators
With `boring mode` and the panel visible, cycle the line-generator engine
between `template` and `local-llm` while an object is in frame.

> "This is Day 2's narrator — a bank of authored lines, sub-millisecond,
> zero download. Watch the network tab stay empty. Now—" *(flip the toggle)*
> "—that's a real half-billion-parameter language model, running in this
> tab, writing a fresh line instead of picking one."

### 0:35 — Watch the download happen, live
Point at the network tab as requests to `huggingface.co` appear.

> "That's the model downloading right now — a few hundred megabytes, once.
> And notice: narration didn't stop or stutter while that happened. It's
> still talking in the old voice until the new one's actually ready — then
> it switches over, live."

Point at the panel's `LLM` status line climbing to `ready`, then the
`LLM latency` number appearing on the next line.

> "That number is real: how long this model took to write that specific
> line, on this machine, right now."

### 0:55 — Prove the caching claim
Reload the page. Reopen the network tab. Switch the engine on again.

> "Same page, same model, but I've already downloaded it once. Watch the
> network tab—" *(nothing happens)* "—and watch the status line—" *(reaches
> `ready` in ~11 seconds instead of ~50)* "—that's the model loading
> entirely from the browser's own cache. Downloaded once. Never again."

### 1:15 — The honest part: a real bug, shown, not hidden
Switch `voice_engine` to `local-tts` and turn voice on.

> "This one's not fully working yet. There's a real bug in the neural voice
> model — I found it building this, and I haven't fixed it. Watch what
> happens instead of it going silent."

Point at the console warning and the fact that speech still comes out (via
`speechSynthesis`).

> "It tried, it failed, it logged why, and it fell back to the built-in
> voice instead of just... not talking. That fallback working correctly is
> arguably the actual result of today, more than the bug itself."

### 1:40 — Honest close
> "Two model swaps today, both fully local. One works end to end — a small
> AI model writing narration, verified with the network cut entirely mid-run
> and it kept talking. One's got a bug I'm showing you instead of hiding.
> Neither one called home."

---

---

## Day 5 demo flow (90–120 seconds) — "Same brain, better face"

### 0:00 — Cold open on the boot sequence
Screen dark. Click **Start camera**.

> "Watch the boot."

Let each line report in for real — camera online, vision model booting,
tracker, narrator.

> "None of that's fake progress. Those four lines are the app's actual
> status, in order, as it actually happens."

### 0:15 — The same scene, two HUDs
Cut to (or narrate over) a Day 1 screenshot/clip: bare rectangle, `label
score%`. Then the live Day 5 HUD on the same kind of object.

> "Same model. Byte-identical. I didn't touch it today. Everything different
> here is drawing code."

### 0:30 — Acquire, hold, lose
Bring an object into frame. Point at the brackets converging inward.

> "Watch it lock on — that's not instant, it converges over about a third of
> a second. And when it leaves—" *(pull the object out of frame)* "—it
> doesn't just vanish. It releases and fades. That fade is the HUD's own
> memory — the detector's already forgotten this object exists; the screen
> hasn't, for about another third of a second."

### 0:50 — Primary target and the honest numbers
Point at the brighter, ringed target vs a dimmer secondary one.

> "This is the target it's focused on — biggest, most centered box, picked
> fresh every frame. That ring is real confidence, not decoration. And
> this—" *(point at the size readout)* "—is deliberately not a distance in
> metres. I don't have the data to say how far away anything is. I have the
> data to say how much of the frame it fills. So that's what it says."

Bring a second, similarly sized object into frame; let focus visibly
transfer between the two rather than cut.

> "Focus transfers. It doesn't jump."

### 1:15 — The subtitle track
Mute the audio. Point at the bottom of the frame.

> "Nobody's confirmed hearing this thing talk yet, across five days now.
> This is why that's survivable — the line's right there, readable, sound
> off, exactly how most people are about to watch this video."

### 1:35 — The number that proves it wasn't free
Point at the telemetry panel's `HUD draw` figure.

> "All of that, and the draw cost is a tenth of a millisecond. The polish
> didn't eat the frame budget — that's the number Day 6 is about to hold me
> to."

### 1:50 — Honest close
> "I didn't make it smarter today. I made it look like it already was. That
> gap — between what it looks like it understands and what it actually
> does — is the whole point of today, not something to paper over."

---

## Day 6 demo flow (90–120 seconds) — "It stops guessing, and it answers back"

### 0:00 — Cold open on a confidently wrong label
Point the camera at a bed (or narrate over a captured clip/screenshot if a
real bed isn't in reach — see the note at the end of this section).

> "Yesterday, this was a dining table. Then a bed. Then a dining table
> again. Same object. It never moved."

### 0:15 — The fix, shown as a settling label
Let the label hold on one word, or — if simulating — show the
`BED / DINING TABLE ?` hedge render.

> "Now it keeps a vote across the last thirty-ish frames instead of trusting
> whatever it saw one frame ago. And when the vote is genuinely split — not
> often, but sometimes — it says so instead of guessing." *(point at the
> amber `BED / DINING TABLE ?` label and the real `LBL 52%` readout)*
> "That percentage is the actual vote share. Not a decoration."

### 0:35 — The other half of the problem, stated honestly
> "This doesn't fix everything. Point it at a microphone—" *(if available)*
> "—and it's still going to call it a tie or a bottle. That's not the model
> being dumb. It's being asked a question it structurally cannot answer —
> microphone isn't one of the 80 words it knows. Different problem, not
> today's fix."

### 0:55 — Push-to-talk
Hold `T`.

> "New this session: you can talk to it." *(ask, out loud)* "What do you
> see?"

Release the key. Let the answer come back — spoken, and subtitled.

> "That's a real local speech-to-text model, transcribing what I just said,
> entirely on this machine. Watch the subtitle track—" *(point at the
> dim, right-aligned line above YAP's answer)* "—that's my question. That's
> YAP's answer. Both real, both on screen, sound off."

### 1:20 — "Stop" actually stops it
Ask a question that triggers a longer answer, then say "stop" mid-sentence.

> "And if I say stop—" *(cuts off immediately)* "—it stops. Immediately.
> Not 'finishes its thought first.' That one's not allowed to be
> approximate."

### 1:40 — The honesty beat
> "One important thing this is *not*: it doesn't understand what I'm
> saying. It's matching my words against a short list of things it knows
> how to do — what do you see, stop, wake up, a handful of others. Off
> that script, it tells you so instead of guessing at what I meant."

### 1:55 — The number that proves it wasn't free
Point at the Latency breakdown panel.

> "Two more models loaded onto this page today. Inference, tracking,
> drawing — every number here is exactly what it was yesterday. The new
> stuff runs entirely off to the side."

### 2:10 — Honest close
> "It used to lie with total confidence. Now it says 'I'm not sure' — and
> somehow that reads as more intelligent, not less. That's today's whole
> thesis, and I think it's actually true."

---

### Why this demo leans on a simulated hedge render for one beat
A real bed/dining-table-confusable scene wasn't available in this session's
verification environment (headless, fake-camera device with a synthetic
test pattern — no furniture in it at all). The `BED / DINING TABLE ?` render
shown/described above was captured by feeding the real `drawHud.ts` module a
hand-built but realistic `HudState` directly — genuine code, synthetic
input, not a mockup — see day6-poc.md. Say this plainly if shooting before a
real ambiguous-object scene is confirmed on camera, the same way Day 5 was
honest about leaning on the fake-camera device for its acquire/hold/lose arc.

### Why this demo doesn't claim a verified real spoken command
The fake-camera device used for all of this week's headless verification
has no real microphone input. What's confirmed: the ASR pipeline loads and
runs cleanly in a production build (a real bundler risk this exact
dependency family has hit before — see decisions.md D13/D24). What's *not*
confirmed: that a real spoken "what do you see" gets transcribed correctly.
Say this the same way Day 4 said "no audio confirmed audible" — plainly, not
as a caveat to bury.

---

### Why this demo leans on screenshots and the fake-camera device for some beats
Real-webcam verification of a clean single-object acquire→hold→lose arc
under natural motion (not the fake camera's synthetic churn, and not a
manual stop/restart) is still owed — same caveat this project has flagged
every day so far. If shooting before that's confirmed, say so on camera
rather than implying it's been tested end to end; `day5-poc.md` records
exactly what was and wasn't verified.

---

### Why this demo leans on the network tab, not the speakers
Every verification session for this project, across all four days, has run
headless with no audio output — nobody has yet confirmed YAP is *audible*,
only that the code correctly drives `speechSynthesis`/Kokoro and produces the
right log entries. Say this on camera rather than implying it's been heard:
"I haven't personally listened to this talk yet — here's what I can show
you instead," then lean on the network tab and the latency numbers, which
are independently checkable without trusting anyone's ears.

---

## Terms to simplify

| Don't say | Say instead |
|---|---|
| COCO-SSD | "a model trained to spot 80 everyday objects" |
| Single-shot detector | "it figures out what and where in one look" |
| Inference latency | "how long it takes to look at one frame" |
| WebGL backend | "it runs on the graphics card" |
| Bounding box | "the bracket around the thing" |
| requestAnimationFrame loop | "it runs every frame" |
| Temporal tracking | "does it remember it saw that a second ago" |

---

## What makes this exciting even though it's unfinished

1. **It's visibly real.** The boxes move because the world moves. You cannot
   fake that on camera, and viewers know it.
2. **It runs on the machine you're looking at.** No cloud, no key. That's a
   surprisingly strong hook right now.
3. **The numbers are on screen.** 12ms, 60 FPS. It's self-evidencing.
4. **The flaws are interesting.** Jittery boxes aren't an embarrassment —
   they're a cliffhanger for Day 2.

---

## Recording notes

- **Good light.** Detection quality lives and dies here.
- **Have props ready** in reach: cup, phone, book, chair, laptop, bottle. All
  COCO classes; all reliably detected.
- **Record system audio** so the narration is captured.
- Keep the **telemetry panel in frame** — it's most of the credibility.
- Don't cut the model-loading wait. Showing the unglamorous part builds trust.
- Best single shot for a thumbnail: brackets locked on your face + the FPS
  counter visible.

---

## If it fails live
Say what you see. "It thinks my headphones are a cell phone." That's more
compelling than a clean run — it shows the seams, and the seams are the content.
Never re-record to hide a wrong label; narrate it instead.
