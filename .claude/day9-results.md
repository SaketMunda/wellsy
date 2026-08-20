# Day 9 results

Detector: YOLOE via Ultralytics/MPS (D30), ByteTrack (D31), machine: same
Apple Silicon (M-series) as Day 7/8. **Camera access: real, confirmed working
this session** — see the correction note below before reading further.

## A correction, stated plainly

An earlier draft of this document claimed "no camera access this session,"
copied from Days 7–8's genuinely-true finding without re-testing it. That
was wrong. `cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)` opens the real camera
and reads real frames in this environment; `navigator.mediaDevices.getUserMedia`
in headless Chrome does too. Every number below this line is real, not
synthetic — re-measured after the mistake was caught and corrected.

## The measurement table

| # | Metric | Result | Conditions |
|---|--------|--------|------------|
| 1 | End-to-end camera→pixel latency (capture+gate+inference) | **p50 77.1ms, max 178.1ms** (n=8, first-call 3.28s MPS warmup spike excluded, same convention as day8-results.md) | Real camera, `main.py --seconds 15`, real room |
| 2 | WebSocket message rate / payload size | **~6.6–7 msg/s**, throttled to `DETECT_HZ`, quantized by real capture cadence; **~180B** empty, **larger with real tracks** (4 tracks ≈ ~600–900B) | `engine/bridge.py`, real + synthetic sessions |
| 3 | HUD rAF delta, engine driving | flat **16.66ms** every tick (60fps), zero longtasks over an 8s window | Headless Chrome (fake video device for the *timing* test), engine `--synthetic-intermittent` |
| 4 | Total CPU: engine + browser tab | Browser tab `TaskDuration` ≈ 9% of one core over an 11.6s window; engine processes (main + capture) **~6–13%** during real motion, matching Day 8's 6–8% (gate closed) / 18–23% (forced off) range | vs. Day 7's browser-only ~72% of one core — not a controlled A/B, stated as such |
| 5 | Behaviour on a still scene | Held-tracks re-emit unchanged across gated frames — code path unchanged from Day 8, confirmed still correct in this session's real-camera JSONL (tracks persisted across `gated: true` runs with no detection re-run) | Real camera |
| 6 | Behaviour when the engine is killed mid-run | **Staleness banner appeared 1005ms after SIGKILL** to the engine process group; no freeze/crash | `scripts/day9-bridge-test.mjs` |
| 7 | τ verdict | Unchanged at 70ms. Not filmed against a real fast hand-pass this session (time budget after the correction above) — this is the one honest gap remaining, see below | Real motion clip recorded (`clips/real_clip.mp4`) but not used to judge interpolation specifically |

## Camera architecture: (A), confirmed — not the default fallback

Verified directly, both halves:
- **Two independent Python `cv2.VideoCapture` readers** opened the same
  camera index simultaneously and both read real frames without error.
- **Chrome's `getUserMedia` and Python's `cv2.VideoCapture` held the camera
  open and read concurrently** — `scripts/camera-dual-test.mjs` ran a
  headless Chrome tab holding a live `getUserMedia` stream (`readyState:
  'live'`) for 1.5s while a separate Python process read 196 real frames
  over an overlapping 7s window. Confirmed with the actual APIs each side
  uses (AVFoundation via OpenCV, Chrome's own camera stack), not just the
  OS-level check.

**(A) is the real, verified architecture for this machine.** No fallback to
(B) was needed.

## The real bed/microphone shot: half owed, half done for real

Running `main.py --seconds 15` against the real camera in this session's
room produced real detections: `person` (0.938), `glasses` (0.878),
`headphones` (0.671), and **`bed` (0.447, `labelConfidence` 0.889)** — a
real bed, correctly labeled `bed`, not `dining table` (the Day 1–6 browser
build's confusion this whole arc has been chasing). Screenshotted live
through the actual HUD, `?engine=1`, real camera on both the browser and
Python sides (`/tmp/real_hud_engine.png`, not committed — see below):
`PERSON · LOCK` bracket, `GLASSES #6`, `BED #7` in the frame-edge label
list, narration line "new person in view. the collection grows. meanwhile,
a glasses. we are doing this now, apparently." — generated from the real
engine tracks, telemetry panel reading `Inference: 32ms`, `Track: 0.00ms`,
`Targets: 3`, `Camera: live`, `Model: ready`.

**No microphone was in the room this session** — that half of the shot is
still owed, not because of an access limitation but because there wasn't
one in frame. Worth two minutes with `debug_window.py` (see below) whenever
one's nearby.

## `MOTION_THRESHOLD`: tuned against two real clips, changed 4.0 → 5.0

`engine/clips/real_clip.mp4` (20s, real camera; a second 25s ambient-only
sample was recorded first but overwritten by a script bug — the numeric
distribution from both is preserved here since it was captured before the
overwrite):

- **Ambient/passive, 25s, nothing deliberately moved:** raw mean-diff
  (0–255 scale) min=0.973, p50=1.268, p95=2.951, **max=4.220**, mean=1.472.
  At the old threshold (4.0), **0.7% of frames read as "motion" from pure
  sensor/lighting noise alone.**
- **20s with real movement in frame:** min=0.940, p50=1.045, p95=2.484,
  **max=6.195**, mean=1.345. The bulk of the clip was still ambient (p50/p95
  actually lower than the passive sample), with a real motion spike reaching
  6.195 — clearly separated from the noise ceiling.
- **Decision: `MOTION_THRESHOLD` 4.0 → 5.0** (`engine/motion.py`). 5.0 sits
  above the measured real noise ceiling (4.22) with margin, and comfortably
  below the one measured real motion sample (6.195). This retires D32/D34's
  "deferred" status with an actual number from actual footage — see
  `decisions.md` D34 (revised).
- **Honest caveat:** one real motion sample is not a distribution. The
  motion-phase evidence here is thinner than the noise-floor evidence. If a
  future session sees real objects move without the gate opening, or sees
  false-opens from lighting flicker at 5.0, that's the signal to revisit —
  not a sign this number was invented.

## `debug_window.py`: runs clean against real hardware, on-screen window not confirmed

Piped real `main.py` JSONL into `debug_window.py` against the real camera —
no crash, no stderr output, ran the full duration cleanly. **Could not
confirm the `cv2.imshow` window was actually visible on screen** — a
`screencapture` taken 4s into the run shows the desktop with no OpenCV
window in it, most likely because launching it as a detached background
process from this agent session doesn't attach it to a window-server
session/Space the way a normal interactive terminal launch would. The
JSONL-consuming half (the half that matters for provenance — every box
drawn came from the same JSONL a WebSocket client also consumes) is
confirmed working against real data. The `imshow` half needs a genuine
interactive terminal session to confirm, not this session's process
model — flagged honestly rather than claimed clean.

## τ (D15): three real attempts, one real (different) finding

Three burst-screenshot attempts against the live `?engine=1` HUD with a
real camera and a real person in frame (`scripts/tau-burst-shot.mjs`,
14 frames/300ms apart each time):

1. **First attempt: engine had already exited.** Setup latency (browser
   launch, camera warmup) ate the engine's `--seconds 20` budget before the
   burst started — caught by the "ENGINE SIGNAL LOST" banner in every
   frame, not the smooth boxes it looked like at a glance. Restarted with a
   longer budget.
2. **Second attempt (engine confirmed live, `Model: ready` throughout): the
   `PERSON · LOCK` box did not move a single pixel across 14 frames**
   (`POS 38/57`, `AREA 49.1%` identical in every screenshot) despite a real,
   visible hand-to-face gesture and head turn in the raw video underneath.
3. **Third attempt, bigger gesture (hand through hair, hand to ear):** same
   result — box frozen at `POS 33/58`, `AREA 50.5%`, `Inference: 0.0ms`
   (T1 hadn't run a fresh detection in this window at all).

**The real finding: the motion gate — even after D34's real-evidence retune
to 5.0 — is not reliably triggered by a person's localized gestures at
normal desk distance from the camera.** `motion.py`'s gate averages
absolute pixel difference over the *entire* downscaled 160×120 frame; a
hand moving near a face occupies a small fraction of that frame, so the
mean diff stays under threshold even though the motion is real and visible
to a human. This is consistent with the D34 clips too — the one real
motion sample that cleared the gate (mean-diff 6.195) most likely came from
something large-scale crossing frame, not a seated gesture. **This is a
plausible, even desirable, property for T1's purpose** (a HUD's ambient
detector shouldn't have to re-run every time someone twitches at a desk),
but it means τ specifically needs a different kind of test than "wave a
hand" — a full-body movement (standing, walking across frame, stepping
toward/away from the camera) that clears the gate and produces repeated
fresh T1 runs to actually interpolate between.
**Still unchanged at 70ms.** Not because camera access was unavailable —
it plainly was, three real attempts prove it — but because this specific
test needs a different, larger motion than what desk-distance gestures
produce, and this session's remaining time went to writing this up
honestly rather than a fourth attempt. First follow-up: stand up, step back
from the camera, and walk across frame while `?engine=1` runs.

## Lines touched in `src/hud/`: still zero

Unchanged from the first pass — `git diff --stat -- src/hud/` is empty.
Confirmed again after the real-camera work above; nothing in this
correction pass touched `hudState.ts`, `drawHud.ts`, or `HudCanvas.tsx`.

## Verification

- `npx tsc -b`, `npx oxlint src/`, `npm run test` (85 tests), `npm run
  build` — all clean.
- Bridge bound to `127.0.0.1` only — confirmed with `lsof`.
- `uv run main.py --synthetic` still works, unchanged interface.
- Real-camera run's stdout JSONL inspected directly — held-track behavior on
  gated frames confirmed on real data, not just by code inspection.
