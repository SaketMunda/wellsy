"""macOS panel semantics for the orb — the platform backend permitted by
INVARIANTS #14 (portable interface in the core, per-platform backend here;
same rule as ScreenCaptureKit in step 3). This file lives in a sanctioned
backend dir, so `pyobjc` imports are allowed; nothing outside `backends/`
imports it.

A plain always-on-top Qt window drops when the user enters a fullscreen app or
switches Spaces, because window levels only order *within* a Space. The orb
needs `NSPanel`-style behaviour: a floating non-activating panel, `.floating`
level or above, collection behaviour including `canJoinAllSpaces` and
`fullScreenAuxiliary`.
"""

from __future__ import annotations


def apply(win_id: int) -> bool:
    """Promote the NSView-backed Qt window `win_id` to floating-panel
    behaviour. Returns True on success, False if AppKit is unavailable (caller
    then reports degraded Presence rather than pretending)."""
    try:
        import objc  # noqa: F401
        from AppKit import (
            NSFloatingWindowLevel,
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowCollectionBehaviorStationary,
        )
    except Exception:
        return False

    ns_view = objc.objc_object(c_void_p=win_id) if False else _view_from_winid(win_id)
    if ns_view is None:
        return False
    ns_window = ns_view.window()
    if ns_window is None:
        return False

    ns_window.setLevel_(NSFloatingWindowLevel + 1)
    ns_window.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces
        | NSWindowCollectionBehaviorFullScreenAuxiliary
        | NSWindowCollectionBehaviorStationary
    )
    ns_window.setHidesOnDeactivate_(False)
    # non-activating: showing the orb must never steal key focus from the app
    try:
        ns_window.setStyleMask_(ns_window.styleMask() | (1 << 7))  # NSWindowStyleMaskNonactivatingPanel
    except Exception:
        pass
    return True


def _view_from_winid(win_id: int):
    try:
        import objc

        return objc.objc_object(c_void_p=win_id)
    except Exception:
        return None
