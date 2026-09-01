# Step 3 — Capture layer with degenerate-capture verification

**Read first:** `.claude/rebuild/INVARIANTS.md` (#6 and #14),
`.claude/stack-teardown.md` **§1 in full**, `spec/phase1-acceptance.md` **A8**.
**Depends on step 1.**

## The defect this step exists to fix — read this carefully

The owner asked *"what's on my screen"* with several windows open. The system
answered by describing the **desktop wallpaper**. This was reported as the model
being stupid. It was not.

Reproduced on the development machine on 2026-09-01:

```
$ screencapture -x _probe.png
exit=0
-rw-r--r--@ 1 ... 10747568 bytes _probe.png
```

A valid 3024x1964 PNG was written. Its contents: the Finder menu bar and a
wallpaper photograph. **Zero application windows**, with windows open at capture
time. That image was base64-encoded and sent to the vision model, which
described it accurately. The model was right.

**Root cause:** macOS Screen Recording (TCC) permission. Without the grant,
`screencapture` does not fail — it silently strips the window layer and returns
the desktop composite. This is a documented failure mode for non-bundled CLI
executables.

**Why the old code could not catch it:** it raised only on non-zero exit or when
no file was written. On a permission-stripped capture *both guards pass* — the
process exits 0 and writes a valid full-resolution image. The function returned
garbage with full confidence, with no `UNIDENTIFIED` floor and no provenance
flag. That is an accidental violation of invariant #6.

**A previous session recorded the wrong root cause** for this exact symptom,
attributing it to `screencapture`'s multi-monitor `files` argument. That
multi-monitor bug is real and its fix was correct, but it is a different bug,
and the real defect shipped underneath the fix. Do not repeat the mistake:
**verify the capture, do not reason about why it should be fine.**

## Deliverable 1 — portable capture interface

```
wellsy/capture/
  base.py         # CaptureSource protocol, CaptureResult, CaptureError
  camera.py       # portable (OpenCV) — largely a port from step 1
  screen/
    __init__.py   # backend selection by platform
    macos.py      # ScreenCaptureKit
    linux.py      # PipeWire (Wayland) / X11
    windows.py    # Windows.Graphics.Capture
    portable.py   # mss — fallback
  verify.py       # THE IMPORTANT PART
```

Note that `mss` is cross-platform but uses Core Graphics on macOS and therefore
**inherits the identical TCC failure**. It is a fallback, not a fix. macOS needs
a real ScreenCaptureKit backend. Per invariant #14 these are backends behind one
interface; nothing outside `screen/` may import a platform package.

## Deliverable 2 — capture verification (this is the step)

Before any capture reaches a model, it must be verified non-degenerate. A
capture that cannot be verified **raises with an actionable permission message**;
it never returns.

Signals to implement — combine them, do not rely on one:

- **Permission probe.** Query the platform's screen-recording authorization
  directly where an API exists (macOS: `CGPreflightScreenCaptureAccess`).
  This is the cheapest and most direct signal — do it first.
- **Window-list cross-check.** Ask the window server how many on-screen windows
  belong to other applications. If it reports windows and the capture shows
  none, the capture is stripped. This is the highest-signal check.
- **Wallpaper correlation.** Capture once, compare against the known desktop
  picture. A near-exact match with windows reportedly open is a stripped
  capture.
- **Content heuristic, last and weakest.** Very low edge density and no text-like
  structure across the whole frame is suspicious. Useful as corroboration only —
  **never as the sole basis for a refusal**, since a legitimately empty desktop
  looks the same.

Surface the outcome honestly: `CaptureResult` carries `verified: bool`, the
method that verified it, and the timestamp. `provenance.py` records it. A model
never receives an unverified frame.

**Also carry forward the real multi-monitor fix:** capture every attached
display and hand them all to the model, labelled by display index. A
single-display machine gets exactly one frame.

## Deliverable 3 — first-run permission experience

The failure must be legible to a human, because it will recur — TCC is granted
**per process tree**, so the terminal, the IDE's integrated terminal, and a
packaged app each need a separate grant. This is already a logged problem for
the microphone on this project.

- `wellsy doctor` — checks camera, microphone, and screen-recording permission
  for the *current* process tree and prints exactly what to grant and where.
- On a verification failure at runtime, the spoken and logged response is
  *"I can't see your screen — screen recording permission isn't granted for this
  process"*, never a description of a wallpaper.

## Acceptance

Scenario **A8** from `spec/phase1-acceptance.md`, both halves, is the bar:

1. **Permission granted:** capture contains real window contents; a text-bearing
   window is captured legibly enough to read back.
2. **Permission revoked:** the system **refuses and names the missing
   permission.** It must not describe the desktop, wallpaper, or menu bar as if
   it were the screen. Test this by actually revoking the grant, not by mocking.
3. A regression test using the stored `_probe.png`-style wallpaper-only capture
   as a fixture: `verify()` must reject it. **Write this test first.**
4. Multi-monitor: every display captured, correctly ordered and labelled.
   If only one display is available, say so in the report rather than claiming
   the multi-display path was verified.
5. `wellsy doctor` correctly reports permission state for its own process tree.
6. Capture latency measured, p50/p95 over ≥ 20 trials, per platform available.
   Prior recorded baseline: 203.9 ms for a 1920x1080 capture.
7. Camera path unregressed against the step 1 benchmark.

## Do not

- Do not shell out to `screencapture`. It is the wrong API and it is the bug.
- Do not treat "the file was written" or "the process exited 0" as evidence of
  anything. That assumption is the entire defect.
- Do not make verification advisory. An unverified capture does not reach a
  model, full stop.
- Do not add continuous screen capture. Screen is on-demand only, exactly once
  per routed question — this is a privacy property of the product, not an
  optimisation.

## Report back

The A8 result both ways, the verification signals you actually implemented and
which fired, capture latency per platform, and whether the microphone
permission blocker (open since Day 9, blocking the wake→first-word measurement)
is resolved by `wellsy doctor`.
