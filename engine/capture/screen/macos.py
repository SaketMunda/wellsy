"""macOS screen backend — ScreenCaptureKit for pixels, Quartz for the probes.

This is a *backend behind the portable `ScreenBackend` interface*, permitted by
invariant #14 as the macOS acceleration path. It is never imported outside
`engine/capture/screen/`. Every platform import is guarded so the module loads
(reporting `available() == False`) on Linux and Windows too.

Why not `screencapture`: the CLI silently strips the window layer when Screen
Recording (TCC) is not granted and still exits 0 with a full-resolution PNG —
that is `stack-teardown.md` §1, the defect this whole step exists to kill.
ScreenCaptureKit instead *fails loudly* (`SCStreamErrorDomain` code -3801,
"The user declined TCCs...") which we turn into a `CaptureError` with a remedy.
"""

from __future__ import annotations

import os
import threading

import cv2
import numpy as np

from engine.capture.base import (
    CaptureError,
    DisplayFrame,
    Permission,
    WindowInfo,
)

try:  # platform guard — invariant #14, backend may load on any OS
    import Quartz  # pyobjc-framework-Quartz
    import ScreenCaptureKit as SCK  # pyobjc-framework-ScreenCaptureKit
    from AppKit import NSScreen, NSWorkspace  # pyobjc-framework-Cocoa
    from Foundation import NSURL

    _IMPORT_ERROR: str | None = None
except Exception as exc:  # pragma: no cover - only on non-macOS
    Quartz = SCK = NSScreen = NSWorkspace = NSURL = None  # type: ignore
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

try:  # AVFoundation is only needed for `wellsy doctor`'s camera/mic readout.
    import AVFoundation as _AV  # pyobjc-framework-AVFoundation

    _AV_ERROR: str | None = None
except Exception as exc:  # pragma: no cover - only on non-macOS
    _AV = None  # type: ignore
    _AV_ERROR = f"{type(exc).__name__}: {exc}"

_SCK_TCC_DECLINED = -3801  # SCStreamErrorUserDeclined

_SETTINGS_REMEDY = (
    "Grant it in  > System Settings > Privacy & Security > Screen Recording, "
    "enable the entry for THIS app (the terminal, your IDE, or the packaged "
    "WELLSY — TCC is per process tree), then fully quit and reopen it. Run "
    "`wellsy doctor` to confirm."
)


def available() -> bool:
    return _IMPORT_ERROR is None


def import_error() -> str | None:
    return _IMPORT_ERROR


# --------------------------------------------------------------------------- #
# Probes — the cheap, direct signals verify.py leans on first.
# --------------------------------------------------------------------------- #
def preflight() -> Permission:
    """`CGPreflightScreenCaptureAccess()` — does not prompt, does not log.
    The most direct signal there is: it answers the exact question TCC asks."""
    if not available():
        return Permission.UNKNOWN
    try:
        return Permission.GRANTED if Quartz.CGPreflightScreenCaptureAccess() else Permission.DENIED
    except Exception:
        return Permission.UNKNOWN


def request_access() -> Permission:
    """`CGRequestScreenCaptureAccess()` — fires the one-time OS prompt (only
    ever prompts once per process tree; after that it is a no-op that returns
    the current state). Used by `wellsy doctor`, never silently at runtime."""
    if not available():
        return Permission.UNKNOWN
    try:
        Quartz.CGRequestScreenCaptureAccess()
    except Exception:
        pass
    return preflight()


def av_media_authorization(media_type: str) -> str:
    """`AVCaptureDevice.authorizationStatusForMediaType_` for 'vide' (camera)
    or 'soun' (microphone), as a plain string: 'granted' | 'denied' |
    'not_determined' | 'restricted' | 'unknown'. Lives here because this is
    the sanctioned home for macOS platform imports (invariant #14); `doctor.py`
    stays platform-package-free and calls through this."""
    if _AV is None:
        return "unknown"
    try:
        s = int(_AV.AVCaptureDevice.authorizationStatusForMediaType_(media_type))
    except Exception:
        return "unknown"
    return {0: "not_determined", 1: "restricted", 2: "denied", 3: "granted"}.get(s, "unknown")


_SYSTEM_OWNERS = {
    "Window Server",
    "Dock",
    "WindowManager",
    "Control Center",
    "Notification Center",
    "Spotlight",
    "SystemUIServer",
    "coreautha",
}


def list_windows() -> list[WindowInfo]:
    """Every on-screen window from `CGWindowListCopyWindowInfo`. Titles come
    back only when Screen Recording is granted — `verify.py` uses the absence
    of *all* titles as a stripped-capture tell."""
    if not available():
        return []
    try:
        raw = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
    except Exception:
        return []
    out: list[WindowInfo] = []
    for w in raw or []:
        b = w.get("kCGWindowBounds", {}) or {}
        out.append(
            WindowInfo(
                owner=str(w.get("kCGWindowOwnerName") or "").strip(),
                pid=int(w.get("kCGWindowOwnerPID") or 0),
                title=(str(w["kCGWindowName"]) if w.get("kCGWindowName") else None),
                bounds=(
                    int(b.get("X", 0)),
                    int(b.get("Y", 0)),
                    int(b.get("Width", 0)),
                    int(b.get("Height", 0)),
                ),
                layer=int(w.get("kCGWindowLayer") or 0),
            )
        )
    return out


def other_app_windows(frames_wh: list[tuple[int, int]] | None = None) -> list[WindowInfo]:
    """Normal windows (layer 0) owned by some *other* process — i.e. the
    windows a correct capture must contain pixels of."""
    me = os.getpid()
    out = []
    for w in list_windows():
        if w.layer != 0 or w.pid in (0, me):
            continue
        if w.owner in _SYSTEM_OWNERS or not w.owner:
            continue
        if w.bounds[2] < 40 or w.bounds[3] < 40:  # sliver / off-screen helper
            continue
        out.append(w)
    return out


_WP_CACHE: dict[str, np.ndarray | None] = {}


def desktop_pictures() -> list[np.ndarray]:
    """The wallpaper image(s) currently set, decoded to BGR and downscaled,
    one per screen. `verify.py` correlates the capture against these — a
    near-exact match with windows reportedly open is a stripped capture.

    Decoding a 4K HEIC costs ~150 ms, so results are cached by path+mtime;
    the wallpaper changes rarely and a stale entry only weakens one of four
    signals."""
    if not available():
        return []
    out: list[np.ndarray] = []
    try:
        ws = NSWorkspace.sharedWorkspace()
        for screen in NSScreen.screens():
            url = ws.desktopImageURLForScreen_(screen)
            if url is None:
                continue
            path = str(url.path()) if hasattr(url, "path") else str(url)
            key = path
            try:
                import os as _os

                key = f"{path}:{_os.path.getmtime(path)}"
            except Exception:
                pass
            if key not in _WP_CACHE:
                img = _decode_image_url(url)
                if img is not None:
                    # 640px wide is plenty for a 48x48-downscale NCC.
                    h, w = img.shape[:2]
                    if w > 640:
                        img = cv2.resize(img, (640, max(1, int(h * 640 / w))), interpolation=cv2.INTER_AREA)
                _WP_CACHE[key] = img
            if _WP_CACHE.get(key) is not None:
                out.append(_WP_CACHE[key])
    except Exception:
        return out
    return out


def _decode_image_url(url) -> np.ndarray | None:
    try:
        from AppKit import NSImage

        ns = NSImage.alloc().initWithContentsOfURL_(url)
        if ns is None:
            return None
        tiff = ns.TIFFRepresentation()
        if tiff is None:
            return None
        buf = np.frombuffer(tiff.bytes(), dtype=np.uint8)
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Capture — ScreenCaptureKit one-shot per display.
# --------------------------------------------------------------------------- #
def _shareable_content(timeout: float = 5.0):
    box: dict = {}
    done = threading.Event()

    def handler(content, err):
        box["content"], box["err"] = content, err
        done.set()

    SCK.SCShareableContent.getShareableContentWithCompletionHandler_(handler)
    if not done.wait(timeout):
        raise CaptureError("ScreenCaptureKit did not return the display list in time")
    if box.get("err") is not None:
        _raise_for_sck_error(box["err"])
    return box["content"]


def _raise_for_sck_error(err) -> None:
    code = None
    try:
        code = int(err.code())
    except Exception:
        pass
    text = str(err.localizedDescription()) if hasattr(err, "localizedDescription") else str(err)
    if code == _SCK_TCC_DECLINED or "declined TCC" in text:
        raise CaptureError(
            "Screen Recording permission is not granted for this process — "
            "ScreenCaptureKit refused the capture.",
            permission="screen-recording",
            remedy=_SETTINGS_REMEDY,
        )
    raise CaptureError(f"ScreenCaptureKit capture failed: {text}")


def _capture_one(display, exclude_pid: int, timeout: float = 5.0):
    cfg = SCK.SCStreamConfiguration.alloc().init()
    cfg.setWidth_(int(display.width()))
    cfg.setHeight_(int(display.height()))
    cfg.setShowsCursor_(False)

    excl = []
    try:  # keep WELLSY's own windows out of the shot
        content = _shareable_content(timeout)
        excl = [w for w in content.windows() if int(w.owningApplication().processID()) == exclude_pid]
    except Exception:
        excl = []
    filt = SCK.SCContentFilter.alloc().initWithDisplay_excludingWindows_(display, excl)

    box: dict = {}
    done = threading.Event()

    def handler(img, err):
        box["img"], box["err"] = img, err
        done.set()

    SCK.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_(
        filt, cfg, handler
    )
    if not done.wait(timeout):
        raise CaptureError("ScreenCaptureKit screenshot timed out")
    if box.get("err") is not None:
        _raise_for_sck_error(box["err"])
    return box["img"]


def _cgimage_to_bgr(cgimg) -> np.ndarray:
    w = int(Quartz.CGImageGetWidth(cgimg))
    h = int(Quartz.CGImageGetHeight(cgimg))
    cs = Quartz.CGColorSpaceCreateDeviceRGB()
    bpr = w * 4
    buf = bytearray(h * bpr)
    ctx = Quartz.CGBitmapContextCreate(
        buf, w, h, 8, bpr, cs,
        Quartz.kCGImageAlphaPremultipliedLast | Quartz.kCGBitmapByteOrder32Big,
    )
    Quartz.CGContextDrawImage(ctx, Quartz.CGRectMake(0, 0, w, h), cgimg)
    rgba = np.frombuffer(bytes(buf), dtype=np.uint8).reshape(h, w, 4)
    return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)


def capture() -> list[DisplayFrame]:
    if not available():
        raise CaptureError(f"macOS screen backend unavailable: {_IMPORT_ERROR}")

    # Fail fast and loud rather than hand back a stripped composite.
    if preflight() is Permission.DENIED:
        raise CaptureError(
            "Screen Recording permission is not granted for this process.",
            permission="screen-recording",
            remedy=_SETTINGS_REMEDY,
        )

    content = _shareable_content()
    displays = list(content.displays())
    if not displays:
        raise CaptureError("ScreenCaptureKit reported zero displays")

    main_id = None
    try:
        main_id = int(Quartz.CGMainDisplayID())
    except Exception:
        pass

    me = os.getpid()
    frames: list[DisplayFrame] = []
    for d in displays:
        did = int(d.displayID())
        cgimg = _capture_one(d, exclude_pid=me)
        bgr = _cgimage_to_bgr(cgimg)
        frames.append(
            DisplayFrame(
                index=0,  # fixed up after sort
                image=bgr,
                width=bgr.shape[1],
                height=bgr.shape[0],
                is_primary=(did == main_id),
            )
        )

    frames.sort(key=lambda f: (not f.is_primary))
    for i, f in enumerate(frames):
        f.index = i
        f.label = ""
        f.__post_init__()
    return frames


class MacOSScreenBackend:
    name = "screencapturekit"

    def available(self) -> bool:
        return available()

    def permission(self) -> Permission:
        return preflight()

    def request_permission(self) -> Permission:
        return request_access()

    def list_windows(self) -> list[WindowInfo]:
        return list_windows()

    def capture(self) -> list[DisplayFrame]:
        return capture()
