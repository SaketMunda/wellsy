# Day 9 script-writer brief — "Same face, new engine"

Handoff document for a script-writing agent. Everything below is either
directly observed this session (real camera, real hardware) or explicitly
marked as not yet verified. Full technical record: `day9-results.md`,
`decisions.md` D34/D35. Full original brief: `day9-prompt.md`.

---

## The one-line pitch

**Five days of hand-built HUD design survived a total engine transplant —
different language, different model, different process — because the seam
between "what is true" and "how it's drawn" was drawn in the right place on
Day 2. The proof: `git diff --stat -- src/hud/` is empty.**

## The 30-second version, if that's all there's room for

WELLSY's interface (the brackets, the labels, the narration) hasn't changed
since Day 5. What changed underneath it, today, is everything: Days 1–8
ran a small model in the browser tab; today the eyes moved to a separate
Python process on the same machine, talking to the browser over a local
socket. The interface didn't need to know. And the new engine gets a bed
right that the old one called a dining table.

---

## What's actually demoable right now, with real evidence

All of the below is from **real camera footage this session** (not
synthetic, not a fake video device) — see `day9-images/real-hud-live-camera.png`
for a real screenshot to build B-roll around, and a second one showing a
real bed correctly labeled (referenced in `day9-results.md`, not currently
saved to disk — regenerate with `PORT=<n> node scripts/real-hud-shot.mjs`
against a real camera if you want a fresh one; takes about 15 seconds).

1. **The HUD renders a real Python engine's output, live, through the
   unmodified Day 5 interface.** `?engine=1` on the URL is the entire
   toggle. Screenshot proof: brackets locked on a real person, real
   `GLASSES #5` / `CHAIR #4` labels, real narration line ("a person
   arrives. the ecosystem barely notices...") generated from real tracks,
   telemetry panel reading real numbers (`Inference: 39ms`, `Camera: live`,
   `Model: ready`).
2. **A real bed, correctly labeled `bed`.** This is the callback moment —
   the Day 1–6 browser build called the same physical bed a `dining table`
   (a running joke/complaint across this whole series). Today's engine
   (YOLOE, open-vocabulary) gets it right, on camera, through the same HUD
   that used to get it wrong.
3. **Kill the engine mid-demo, on purpose.** Within ~1 second, an amber
   banner reads "engine signal lost — showing last known frame" and the
   last real boxes stay on screen, honestly marked stale, instead of
   freezing silently or vanishing. This is a good live moment — it's a
   deliberate failure shown working correctly, not something to hide.
4. **The zero-line claim.** `git diff --stat -- src/hud/` really does come
   back empty for Day 9. If the script wants a "receipts" beat, this is the
   cleanest one available — it's a terminal command, not a claim.
5. **Two cameras, one machine, no conflict.** The browser holds the camera
   for display; Python holds it separately for detection. Measured directly
   this session (not assumed): both `getUserMedia` and `cv2.VideoCapture`
   read real frames from the same camera at the same time. Good for a quick
   "here's the two-camera trick and yes it actually works" beat.
6. **Real, measured numbers to put on screen or read aloud:**
   - End-to-end camera→pixel-on-screen latency: **p50 77ms**
   - WebSocket messages: **~7/second**, ~180 bytes each (numbers, not
     pixels — no video ever crosses the socket)
   - Browser tab CPU while the engine drives: **~9% of one core**, vs. the
     original Day 1–6 browser build's **~72% of one core** doing the same
     job (not a controlled A/B — different runtime, different measurement
     method — say that plainly if using this number, per this project's own
     house rule)
   - Staleness banner appears **~1 second** after the engine is killed

## The narrative arc this session actually supports

1. Open on the HUD looking *identical* to Day 5/6 — same brackets, same
   font, same panel.
2. Reveal that the thing actually producing the boxes has completely
   changed — different language (Python vs. JS), different model, running
   as its own process, talking over a local socket.
3. Prove it with the bed. Same physical object, same HUD, different word —
   because the engine underneath got smarter, not because the interface
   was rebuilt.
4. Kill the engine on camera. Show it fail honestly instead of hiding the
   moment something breaks.
5. Close on the zero-line diff and the CPU numbers — the "the seam held"
   thesis, stated as something you can check yourself, not just believe.

## What NOT to claim yet (say this plainly if it comes up, don't dodge it)

- **The 8Hz-vs-60Hz interpolation quality under fast motion is unverified.**
  Three real attempts this session (real camera, real person) found the
  motion gate doesn't reliably trigger on seated gestures (hand to face,
  head turn) — it needs a bigger, full-body movement to test properly, and
  that test hasn't happened yet. If a script wants a "does the smoothing
  actually work" beat, it needs a fresh take: someone standing up and
  walking across frame while `?engine=1` runs, filmed specifically to judge
  whether the box lags.
- **No microphone was in the room this session**, so the second half of the
  classic "bed and microphone" callback (browser called a mic a `tie`) isn't
  shot yet. The bed half is real and shot; the microphone half needs one
  with a mic nearby, ~2 minutes of work.
- **`debug_window.py`'s on-screen preview window** ran without crashing
  against real data but wasn't confirmed visible on screen in this session
  (a background-process quirk, not a product bug) — don't demo it live
  without checking it renders first.
- **The full "detection running at 8Hz and nobody could tell" reveal with a
  recorded frame-graph** is plumbing-verified and numerically true (see the
  CPU/latency numbers above) but hasn't been filmed as its own beat yet.

## Terms to simplify, if the audience is general

| Don't say | Say instead |
|---|---|
| WebSocket bridge | "a live connection between the two programs" |
| Open-vocabulary detector (YOLOE) | "a model you can teach new words, not just the 80 it shipped with" |
| ByteTrack | "keeps track of the same object across frames" |
| `?engine=1` query flag | "a toggle for which brain is driving" |
| Localhost-only socket | "never leaves this machine" |
| Motion gate | "only bothers looking closely when something actually moves" |
| Latency / inference ms | "how long it takes to notice something" |

## Where the assets are

- `.claude/day9-images/real-hud-live-camera.png` — real camera, real
  engine, real HUD, real narration line. Safe to use directly.
- `.claude/day9-results.md` — every number in this brief, with its exact
  measurement conditions, for fact-checking before a script goes final.
- `.claude/decisions.md` D34 (motion threshold, real evidence) and D35 (the
  bridge itself, camera architecture, what was verified vs. assumed).
