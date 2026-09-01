"""Regression + unit tests for the capture-verification gate
(`.claude/rebuild/step3-capture-layer.md`, acceptance 3).

The load-bearing test is `test_wallpaper_only_fixture_is_rejected`: the stored
wallpaper-only capture (menu bar + desktop picture, zero windows, taken live on
2026-09-01 through the exact Core-Graphics path that has the TCC defect) must be
*rejected* by `verify_screen`. It was written before the gate existed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from engine.capture.base import CaptureError, DisplayFrame, Permission, WindowInfo
from engine.capture.verify import (
    CHROME_LINES_MIN,
    chrome_line_count,
    looks_like_wallpaper_only,
    verify_screen,
)

FIXTURES = Path(__file__).parent / "fixtures"
WALLPAPER_ONLY = FIXTURES / "wallpaper_only_capture.png"
# A real screen grab that genuinely contains window chrome (the Day 11 HUD).
REAL_SCREEN = Path(__file__).parents[1] / ".claude" / "day11-images" / "hud-engine-mode-live.png"


def _frame(path: Path, index: int = 0) -> DisplayFrame:
    img = cv2.imread(str(path))
    assert img is not None, f"missing fixture {path}"
    return DisplayFrame(index=index, image=img, width=img.shape[1], height=img.shape[0], is_primary=True)


class StubBackend:
    """A `ScreenBackend` whose probes return whatever the test dictates."""

    name = "stub"

    def __init__(self, permission: Permission, windows: list[WindowInfo] | None = None):
        self._perm = permission
        self._windows = windows or []

    def available(self) -> bool:
        return True

    def permission(self) -> Permission:
        return self._perm

    def request_permission(self) -> Permission:
        return self._perm

    def list_windows(self) -> list[WindowInfo]:
        return self._windows

    def capture(self) -> list[DisplayFrame]:  # pragma: no cover - not used
        raise NotImplementedError


def _windows(*, titled: bool) -> list[WindowInfo]:
    # Matches what the window server actually reported when the fixture was
    # captured: Arc and VS Code open, layer 0, other PIDs.
    return [
        WindowInfo("Arc", 4321, "Inbox — arc.net" if titled else None, (1512, 25, 1920, 1055), 0),
        WindowInfo("Code", 4322, "verify.py — wellsy" if titled else None, (86, 38, 1426, 944), 0),
    ]


# --------------------------------------------------------------------------- #
# The regression test — written first.
# --------------------------------------------------------------------------- #
def test_wallpaper_only_fixture_is_rejected():
    """Windows are open, the backend cannot probe permission (portable path),
    and the frame is only wallpaper. verify_screen MUST raise, not return."""
    backend = StubBackend(Permission.UNKNOWN, _windows(titled=False))
    with pytest.raises(CaptureError) as ei:
        verify_screen([_frame(WALLPAPER_ONLY)], backend, me_pid=999999)
    assert ei.value.permission == "screen-recording"
    assert "screen recording permission isn't granted" in ei.value.spoken.lower()
    assert "wallpaper" not in ei.value.spoken.lower() or "not describe" not in ei.value.spoken.lower()


def test_wallpaper_only_fixture_rejected_on_denied_preflight():
    backend = StubBackend(Permission.DENIED, _windows(titled=False))
    with pytest.raises(CaptureError):
        verify_screen([_frame(WALLPAPER_ONLY)], backend, me_pid=999999)


def test_wallpaper_only_fixture_rejected_when_titles_withheld():
    """macOS tell: windows exist but every title is None -> stripped."""
    if sys.platform != "darwin":
        pytest.skip("title-withholding signal is macOS-specific")
    backend = StubBackend(Permission.NOT_DETERMINED, _windows(titled=False))
    with pytest.raises(CaptureError):
        verify_screen([_frame(WALLPAPER_ONLY)], backend, me_pid=999999)


# --------------------------------------------------------------------------- #
# Signal primitives
# --------------------------------------------------------------------------- #
def test_looks_like_wallpaper_only_true_on_fixture_via_ncc():
    """The strong content signal: the fixture correlates >0.85 with the
    actual current desktop picture."""
    if sys.platform != "darwin":
        pytest.skip("wallpaper lookup is macOS-specific here")
    from engine.capture.screen import macos

    if not macos.available():
        pytest.skip("pyobjc unavailable")
    wallpapers = macos.desktop_pictures()
    if not wallpapers:
        pytest.skip("no desktop picture resolvable in this environment")
    img = cv2.imread(str(WALLPAPER_ONLY))
    assert looks_like_wallpaper_only(img, wallpapers) is True


def test_real_screenshot_has_far_more_chrome_than_wallpaper():
    """Weakest signal, corroboration only — but a real screen grab still
    shows markedly more window-chrome structure than a wallpaper photo."""
    real = cv2.imread(str(REAL_SCREEN))
    fixture = cv2.imread(str(WALLPAPER_ONLY))
    assert real is not None
    assert chrome_line_count(real) >= 3 * max(1, chrome_line_count(fixture))


def test_solid_frame_has_no_chrome():
    blank = np.full((900, 1440, 3), 30, dtype=np.uint8)
    assert chrome_line_count(blank) < CHROME_LINES_MIN


# --------------------------------------------------------------------------- #
# The pass paths
# --------------------------------------------------------------------------- #
def test_verified_when_granted_and_real_content():
    backend = StubBackend(Permission.GRANTED, _windows(titled=True))
    result = verify_screen([_frame(REAL_SCREEN)], backend, me_pid=999999)
    assert result.verified is True
    assert "preflight" in result.verified_by


def test_verified_when_unknown_but_windows_and_real_content():
    """Portable backend on X11: no probe, but the window server lists real
    titled windows and the frame has chrome -> best-effort verified."""
    backend = StubBackend(Permission.UNKNOWN, _windows(titled=True))
    result = verify_screen([_frame(REAL_SCREEN)], backend, me_pid=999999)
    assert result.verified is True
    assert "window-crosscheck" in result.verified_by


def test_cannot_verify_when_unknown_and_no_windows():
    """A genuinely empty desktop and a stripped capture are indistinguishable
    when the backend can't probe and reports no windows -> refuse."""
    backend = StubBackend(Permission.UNKNOWN, [])
    with pytest.raises(CaptureError):
        verify_screen([_frame(REAL_SCREEN)], backend, me_pid=999999)


def test_no_frames_is_rejected():
    with pytest.raises(CaptureError):
        verify_screen([], StubBackend(Permission.GRANTED, []), me_pid=999999)


# --------------------------------------------------------------------------- #
# macOS CGImage conversion
# --------------------------------------------------------------------------- #
def test_cgimage_to_bgr_roundtrip():
    if sys.platform != "darwin":
        pytest.skip("macOS only")
    from engine.capture.screen import macos

    if not macos.available():
        pytest.skip(f"pyobjc unavailable: {macos.import_error()}")
    import Quartz

    src = np.zeros((16, 24, 3), dtype=np.uint8)
    src[:, :, 2] = 255  # pure red in BGR
    ok, png = cv2.imencode(".png", src)
    assert ok
    provider = Quartz.CGDataProviderCreateWithData(None, png.tobytes(), len(png.tobytes()), None)
    cgimg = Quartz.CGImageCreateWithPNGDataProvider(provider, None, True, Quartz.kCGRenderingIntentDefault)
    out = macos._cgimage_to_bgr(cgimg)
    assert out.shape == (16, 24, 3)
    assert out[:, :, 2].mean() > 240 and out[:, :, 0].mean() < 15
