# Step 3 — Capture layer: results

**Machine:** M4 Pro, 24 GB, macOS 15.5 (Darwin 24.5.0). Commit base `30453ab`.
**Measurement rule:** p50/p95 over ≥ 20 trials, cold vs warm separate.

## What shipped

```
engine/capture/
  base.py            CaptureSource protocol, CaptureResult, CaptureError, WindowInfo, Permission
  camera.py          on-demand single-frame OpenCV grab (blank-frame guard)
  verify.py          the degenerate-capture gate — 4 combined signals
  doctor.py          wellsy doctor: camera / mic / screen for THIS process tree
  screen/
    __init__.py      backend selection by platform + WELLSY_SCREEN_BACKEND override
    macos.py         ScreenCaptureKit (SCScreenshotManager) + Quartz probes  [only place platform pkgs are imported]
    linux.py         PipeWire-portal scaffold — UNEXECUTED, no Linux box
    windows.py       Windows.Graphics.Capture scaffold — UNEXECUTED, no Windows box
    portable.py      mss fallback (Core Graphics on macOS → same TCC failure, hence verify)
bench/capture_bench.py
tests/test_capture_verify.py       11 tests (regression fixture written first)
tests/test_capture_portability.py  invariant #14 guard scoped to engine/capture
tests/fixtures/wallpaper_only_capture.png   live stripped capture, used as the regression fixture
```

`screencapture` is not shelled out to anywhere. `capture_screen()` raises
`CaptureError` rather than ever returning an unverified frame.

## A8 — both halves

| Half | Result | Evidence |
|---|---|---|
| **Revoked** | **PASS** | `capture_screen()` raises `CaptureError`, spoken line *"I can't see your screen — screen recording permission isn't granted for this process"*, remedy names System Settings > Screen Recording and the per-process-tree caveat. ScreenCaptureKit backend refuses via `SCStreamError -3801`; forced mss fallback refuses via `CGPreflight = DENIED` **and independently** via window-cross-check + wallpaper NCC 0.93. No wallpaper/desktop/menu-bar description is produced. |
| **Granted** | **NOT RUN** | This process tree (`Code → claude → zsh → python`) has no Screen Recording grant and TCC cannot be granted non-interactively from here. The granted path is implemented and unit-tested against a stubbed backend (`test_verified_when_granted_and_real_content`), but the live "read text off a real window" check needs a granted process tree. This is the one acceptance item outstanding. |
| **Regression fixture** | **PASS** | `tests/fixtures/wallpaper_only_capture.png` — a real stripped capture taken live through the CG path (menu bar + redwood wallpaper, zero windows, with Arc + VS Code open). `verify_screen()` rejects it. Test written before the gate existed. |

## Verification signals — implemented, and which fired

Combined in `verify.py`, never one alone:

1. **Permission probe** — `CGPreflightScreenCaptureAccess()` (macOS). Cheapest,
   most direct, checked first. **Fired:** returns `DENIED` here → refuse.
2. **Window-list cross-check** — `CGWindowListCopyWindowInfo`, count layer-0
   windows owned by other PIDs. **Fired two ways:** (a) macOS withholds window
   *titles* without the grant — 2 windows present, 0 titles → stripped; (b)
   windows present + every frame matches wallpaper / has no chrome → stripped.
   This is the signal that works with no permission API, i.e. on Linux/Windows.
3. **Wallpaper correlation** — decode `NSWorkspace.desktopImageURLForScreen_`,
   aspect-fill-crop, 48×48 luma NCC. **Fired:** fixture scores **0.934** vs the
   live desktop picture (threshold 0.85); a real screenshot scores 0.0. Decoded
   wallpaper is cached by path+mtime (a 4K HEIC decode is ~150 ms).
4. **Content heuristic** — count long axis-aligned Hough edges (window chrome).
   **Weak, corroboration only, never sole basis:** fixture 1–4 lines vs a real
   grab's 18–20, but noisy across downscales. `verify_screen` only ever uses it
   inside `windows_open AND all(wallpaper_match OR low_chrome)`.

Plus a **"cannot verify" refusal**: portable backend, no permission API, and the
window server reports nothing → a genuinely empty desktop and a stripped capture
are indistinguishable → refuse (an unverified capture never reaches a model).

`CaptureResult` carries `verified`, `verified_by` (e.g. `preflight+window-crosscheck`),
`verified_at`; `.provenance()` returns the dict `honesty/provenance.py` folds in.

## Multi-monitor — PARTIAL

Two displays enumerated, ordered primary-first, labelled
`primary (1512x982)` / `display 1 (1920x1080)`. Verified through the mss path
(which returns frames). The ScreenCaptureKit multi-display path is the same code
(`for d in content.displays()`, sorted by `CGMainDisplayID`) but is unrun
without the grant. The real multi-monitor fix from §1 (capture every display,
label by index, single display → exactly one frame) is carried.

## Latency (≥ 30 trials)

| Path | Cold | Warm p50 | Warm p95 | vs prior baseline |
|---|---|---|---|---|
| Screen capture, mss, 2 displays (raw) | 118.5 ms | **32.8 ms** | 35.8 ms | prior 203.9 ms (one 1080p frame) |
| Screen capture **+ verify**, mss, 2 displays, e2e | — | **74.0 ms** | 77.9 ms | — |
| verify only, 2 displays | — | 41.9 ms | 44.8 ms | — |
| Screen capture, ScreenCaptureKit | — | — | — | **not measurable — backend refuses without grant** |
| Camera one-shot (open+grab), index 0 | 2434 ms | 482.6 ms | 613.1 ms | reopen-per-call; see note |
| Perception fast path (T0+T1) no-regression | 454 ms | **13.56 ms** | 22.64 ms | step-1 baseline 13.2 ms → **PASS** |

Camera note: the ~0.5 s is dominated by `VideoCapture` open/close each call
(Continuity Camera). The routed-query path should read the already-open handle
from `engine/perception/capture.py`, not reopen — `capture_camera()` is for
standalone use.

## `wellsy doctor` — PASS

```
process tree (grant the app at the end):
  Python  <-  zsh  <-  claude  <-  Code Helper (Plugin)  <-  Code
  --> authorize: Code
  [    OK ]  camera
  [    OK ]  microphone
  [MISSING]  screen recording  (backend: screencapturekit)
```

Reports for the *current* process tree, names the app to authorize, points at the
exact System Settings pane, and warns that TCC changes need a full quit+reopen.

## Microphone blocker (open since Day 9)

**Resolved as an observability problem, which is what it was.** `wellsy doctor`
reports **microphone = GRANTED for this process tree** (`Code → … → python`).
The Day 9 blocker was per-process-tree TCC — the mic was granted to one tree and
the wake→first-word run happened in another. Run that measurement from a tree
`wellsy doctor` shows green (all three permissions) and it is unblocked. The
screen grant for this same tree is still missing and is the A8-granted blocker.

## Invariant #14

`tests/test_capture_portability.py` AST-walks `engine/capture/` and fails if any
platform package (`Quartz`, `ScreenCaptureKit`, `AppKit`, `AVFoundation`, `mlx`,
`dxcam`, `win32`, …) is imported outside `engine/capture/screen/`. `mss` is
allowed anywhere (cross-platform). `doctor.py` reaches camera/mic status through
`screen/macos.av_media_authorization()` so it imports no platform package
itself. Full step-2 tree-wide checker still pending in step 2.

## Not done / carried forward

- **A8 granted half** — needs a process tree with the Screen Recording grant.
- **ScreenCaptureKit latency** — unmeasurable here for the same reason.
- **Linux / Windows backends** — scaffolds only, explicitly unexecuted.
- **Provenance wiring** — `CaptureResult.provenance()` exists; folding it into
  `honesty/provenance.log_answer()` happens when the voice path calls capture
  (step 4).
