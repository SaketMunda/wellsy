"""Degenerate-capture verification — this is the step.

The defect (`stack-teardown.md` §1): with Screen Recording denied, Core Graphics
returns the desktop composite — menu bar + wallpaper, **zero application
windows** — and no error. The old guard checked only "did the process exit 0"
and "was a file written". Both pass on a stripped capture. A garbage frame
reached the vision model with full confidence: an accidental violation of
invariant #6.

The fix: **before any capture reaches a model it is verified non-degenerate.**
A capture that cannot be verified raises `CaptureError` with an actionable
permission message — it never returns. Verification is not advisory.

Signals, combined — never one alone:

1. Permission probe (`macos.preflight` / `CGPreflightScreenCaptureAccess`).
   Cheapest and most direct. Checked first. DENIED -> refuse.
2. Window-list cross-check. Ask the window server how many normal windows
   belong to *other* apps. Highest signal: if it reports windows and the
   capture is only wallpaper, the capture is stripped. On macOS the window
   server also withholds *titles* without the grant — all-untitled windows
   that plainly exist is itself the tell.
3. Wallpaper correlation. Compare each frame to the current desktop picture.
   A near-exact match with windows reportedly open is a stripped capture.
4. Content heuristic (last, weakest). Almost no window-chrome structure
   (long axis-aligned edges) across the whole frame is suspicious —
   **never the sole basis for a refusal**, because a legitimately empty
   desktop looks identical.
"""

from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np

from engine.capture.base import (
    CaptureError,
    CaptureResult,
    DisplayFrame,
    Permission,
    ScreenBackend,
    WindowInfo,
)

# Wallpaper NCC at/above this on a 48x48 luma downscale == "this frame is the
# desktop picture". Calibrated on the live stripped capture in
# tests/fixtures/wallpaper_only_capture.png (0.95 against the system default).
WALLPAPER_NCC = 0.85

# Long axis-aligned edges (title bars, sidebars, window borders) at/below this
# count == "no window chrome anywhere in frame". Calibrated: a real full-screen
# grab with windows shows 14-84; the stripped fixture shows 1. Corroboration
# only — a bare desktop with the same wallpaper would also score low.
CHROME_LINES_MIN = 4

_IS_MAC = sys.platform == "darwin"

_REMEDY_MAC = (
    "Grant Screen Recording in  > System Settings > Privacy & Security > "
    "Screen Recording for THIS app (terminal / IDE / packaged WELLSY — TCC is "
    "per process tree), then quit and reopen it. `wellsy doctor` confirms."
)
_REMEDY_GENERIC = (
    "Grant screen-capture permission for this process, or run with a native "
    "backend (WELLSY_SCREEN_BACKEND=screencapturekit on macOS)."
)
_SPOKEN = "I can't see your screen — screen recording permission isn't granted for this process."


# --------------------------------------------------------------------------- #
# Per-frame signal primitives (pure, unit-testable on a bare image)
# --------------------------------------------------------------------------- #
def _aspect_fill_crop(img: np.ndarray, aspect: float) -> np.ndarray:
    h, w = img.shape[:2]
    cur = w / h
    if cur > aspect:
        nw = max(1, int(round(h * aspect)))
        x = (w - nw) // 2
        return img[:, x : x + nw]
    nh = max(1, int(round(w / aspect)))
    y = (h - nh) // 2
    return img[y : y + nh, :]


def _ncc(a: np.ndarray, b: np.ndarray, n: int = 48) -> float:
    ga = cv2.resize(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), (n, n)).astype(np.float32)
    gb = cv2.resize(cv2.cvtColor(b, cv2.COLOR_BGR2GRAY), (n, n)).astype(np.float32)
    ga -= ga.mean()
    gb -= gb.mean()
    denom = float(np.linalg.norm(ga) * np.linalg.norm(gb))
    if denom < 1e-6:
        return 0.0
    return float((ga * gb).sum() / denom)


def wallpaper_ncc(frame: np.ndarray, wallpapers: list[np.ndarray]) -> float:
    """Best normalized cross-correlation of `frame` against any current
    desktop picture, each aspect-fill-cropped to the frame. 0.0 if no
    wallpaper is available to compare against."""
    best = 0.0
    for wp in wallpapers:
        if wp is None or wp.size == 0:
            continue
        cropped = _aspect_fill_crop(wp, frame.shape[1] / frame.shape[0])
        best = max(best, _ncc(frame, cropped))
    return best


def chrome_line_count(frame: np.ndarray) -> int:
    """Long near-horizontal / near-vertical straight edges — the geometric
    signature of window chrome. A wallpaper photograph has almost none.
    Downscaled to <=1280px wide first: Hough on full 4K costs ~150 ms and the
    long structural lines survive the resize (below ~1000px, wallpaper texture
    starts registering as spurious lines — this heuristic is weak either way,
    which is why it is never the sole basis for a refusal)."""
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if g.shape[1] > 1280:
        s = 1280 / g.shape[1]
        g = cv2.resize(g, (1280, max(1, int(g.shape[0] * s))), interpolation=cv2.INTER_AREA)
    h, w = g.shape
    edges = cv2.Canny(g, 50, 150)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180,
        threshold=80,
        minLineLength=int(0.25 * min(h, w)),
        maxLineGap=8,
    )
    if lines is None:
        return 0
    count = 0
    for ln in lines:
        x1, y1, x2, y2 = (int(v) for v in np.asarray(ln).ravel()[:4])
        ang = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
        if ang < 3 or ang > 177 or abs(ang - 90) < 3:
            count += 1
    return count


def looks_like_wallpaper_only(
    frame: np.ndarray, wallpapers: list[np.ndarray] | None = None
) -> bool:
    """Content-only verdict for one frame, callable on a bare image (the
    regression fixture uses this). True == 'only a desktop picture, no
    windows'. Weak by construction: an empty desktop trips it too, which is
    why `verify_screen` never refuses on this alone."""
    wallpapers = wallpapers or []
    ncc = wallpaper_ncc(frame, wallpapers)
    if ncc >= WALLPAPER_NCC:
        return True
    return chrome_line_count(frame) < CHROME_LINES_MIN


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #
def _real_other_windows(windows: list[WindowInfo], me_pid: int) -> list[WindowInfo]:
    out = []
    for wnd in windows:
        if wnd.layer != 0 or wnd.pid in (0, me_pid) or not wnd.owner:
            continue
        if wnd.bounds[2] < 40 or wnd.bounds[3] < 40:
            continue
        out.append(wnd)
    return out


def _refuse(reason: str) -> CaptureError:
    return CaptureError(
        reason,
        permission="screen-recording",
        remedy=_REMEDY_MAC if _IS_MAC else _REMEDY_GENERIC,
        spoken=_SPOKEN,
    )


def verify_screen(
    frames: list[DisplayFrame],
    backend: ScreenBackend,
    *,
    me_pid: int | None = None,
) -> CaptureResult:
    """Raise `CaptureError` unless every frame is confirmed non-degenerate.
    On success returns the `CaptureResult` a model is allowed to receive,
    stamped with which signal confirmed it."""
    me_pid = os.getpid() if me_pid is None else me_pid
    if not frames:
        raise _refuse("The capture produced no frames.")

    perm = backend.permission()
    windows = backend.list_windows()
    others = _real_other_windows(windows, me_pid)
    titled = [w for w in others if w.title]

    wallpapers: list[np.ndarray] = []
    if _IS_MAC:
        try:
            from engine.capture.screen import macos

            wallpapers = macos.desktop_pictures() if macos.available() else []
        except Exception:
            wallpapers = []

    per_frame_wallpaper = [wallpaper_ncc(f.image, wallpapers) for f in frames]
    per_frame_chrome = [chrome_line_count(f.image) for f in frames]
    all_stripped = all(
        per_frame_wallpaper[i] >= WALLPAPER_NCC or per_frame_chrome[i] < CHROME_LINES_MIN
        for i in range(len(frames))
    )

    # 1. Permission probe — most direct.
    if perm is Permission.DENIED:
        raise _refuse("Screen Recording permission is denied for this process (CGPreflight).")
    if perm in (Permission.RESTRICTED,):
        raise _refuse("Screen Recording is blocked by device policy for this process.")

    # 2. Window-list cross-check — highest signal.
    if _IS_MAC and others and not titled:
        raise _refuse(
            f"The window server lists {len(others)} open window(s) from other apps "
            f"but reveals no titles — Screen Recording is not granted, the capture "
            f"is the desktop composite."
        )
    if others and all_stripped:
        raise _refuse(
            f"{len(others)} window(s) are open but the capture shows only wallpaper "
            f"/ no window chrome — this is a stripped capture, not your screen."
        )

    # 3 / 4 fold into `all_stripped` above (wallpaper NCC + chrome heuristic).

    # Cannot verify -> must not return (doc: an unverified capture never reaches a model).
    if perm is Permission.UNKNOWN and not others:
        raise _refuse(
            "Could not verify the screen capture is real: this backend cannot probe "
            "the permission and the window server reported no windows, so a genuinely "
            "empty desktop and a permission-stripped capture are indistinguishable here."
        )

    if perm is Permission.GRANTED:
        method = "preflight+window-crosscheck" if others else "preflight"
    else:
        method = "window-crosscheck"
        if titled:
            method = "window-crosscheck+titles"

    return CaptureResult(
        frames=frames,
        backend=getattr(backend, "name", backend.__class__.__name__),
        verified=True,
        verified_by=method,
        verified_at=time.time(),
        source="screen",
    )
