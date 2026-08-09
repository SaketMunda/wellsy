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
