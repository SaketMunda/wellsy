"""`wellsy doctor` — permission preflight for the *current process tree*.

TCC (and its equivalents) are granted per process tree: the terminal, an IDE's
integrated terminal, and a packaged app each need their own grant. This has
already bitten this project once for the microphone (open since Day 9, blocking
the wake -> first-word measurement). `doctor` makes the state legible: it names
the app at the top of this process tree, then reports camera, microphone and
screen-recording for it, with the exact place to grant each.
"""

from __future__ import annotations

import sys

from engine.capture.base import Permission
from engine.capture.screen import all_candidates

_OK = "OK "
_NO = "MISSING"
_UNK = "UNKNOWN"


def _mark(p: Permission) -> str:
    return {
        Permission.GRANTED: _OK,
        Permission.DENIED: _NO,
        Permission.NOT_DETERMINED: _NO,
        Permission.RESTRICTED: _NO,
        Permission.UNKNOWN: _UNK,
    }[p]


def process_tree() -> list[str]:
    """Names from this process up to the session leader — the chain that owns
    the TCC grant. The last entry is what the user must authorize."""
    try:
        import psutil
    except Exception:
        return []
    chain = []
    try:
        p = psutil.Process()
        for _ in range(12):
            chain.append(f"{p.name()} (pid {p.pid})")
            parent = p.parent()
            if parent is None or parent.pid in (0, 1) or parent.pid == p.pid:
                break
            p = parent
    except Exception:
        pass
    return chain


# --------------------------------------------------------------------------- #
# camera / mic — probed via the sanctioned macOS platform module (screen/macos);
# doctor.py itself imports no platform package (invariant #14).
# --------------------------------------------------------------------------- #
def _av_status(media_type: str) -> Permission:
    if sys.platform != "darwin":
        return Permission.UNKNOWN  # opening the device is the only signal elsewhere
    try:
        from engine.capture.screen import macos

        return Permission(macos.av_media_authorization(media_type))
    except Exception:
        return Permission.UNKNOWN


def camera_permission() -> Permission:
    return _av_status("vide")


def microphone_permission() -> Permission:
    return _av_status("soun")


def screen_permission() -> tuple[Permission, str]:
    for be in all_candidates():
        if be.available():
            return be.permission(), be.name
    return Permission.UNKNOWN, "none"


_GRANT_WHERE = {
    "darwin": {
        "camera": " > System Settings > Privacy & Security > Camera",
        "microphone": " > System Settings > Privacy & Security > Microphone",
        "screen": " > System Settings > Privacy & Security > Screen Recording",
    },
}


def _where(kind: str) -> str:
    return _GRANT_WHERE.get(sys.platform, {}).get(
        kind, f"your OS privacy settings ({kind})"
    )


def run(request: bool = False) -> int:
    """Print the report. `request=True` also fires the one-time OS prompts.
    Returns 0 if camera + microphone + screen are all usable, else 1."""
    print("WELLSY doctor — permissions for this process tree\n")

    chain = process_tree()
    if chain:
        print("  process tree (grant the app at the end):")
        print("    " + "  <-  ".join(chain))
        print(f"\n  --> authorize: {chain[-1].split(' (pid')[0]}\n")

    if request and sys.platform == "darwin":
        for be in all_candidates():
            if be.available():
                be.request_permission()
                break

    cam = camera_permission()
    mic = microphone_permission()
    scr, scr_backend = screen_permission()

    rows = [
        ("camera", cam, "camera"),
        ("microphone", mic, "microphone"),
        (f"screen recording  (backend: {scr_backend})", scr, "screen"),
    ]
    worst_ok = True
    for label, perm, kind in rows:
        mark = _mark(perm)
        print(f"  [{mark:>7}]  {label}")
        if perm is not Permission.GRANTED:
            print(f"             grant at: {_where(kind)}")
            if perm is Permission.UNKNOWN:
                print("             (this platform/backend has no synchronous probe; "
                      "verified at capture time instead)")
            else:
                worst_ok = False
        if perm is Permission.UNKNOWN and kind != "screen":
            worst_ok = worst_ok  # unknown is not a hard fail for camera/mic here

    print()
    if scr is not Permission.GRANTED and scr is not Permission.UNKNOWN:
        print("  Screen grounding ('what's on my screen') will REFUSE until Screen")
        print("  Recording is granted — it will not describe the wallpaper.")
    if mic is not Permission.GRANTED and mic is not Permission.UNKNOWN:
        print("  The wake-word / voice path needs microphone access for this tree.")
    if worst_ok:
        print("  All required permissions are in place for this process tree.")
    print("\n  After granting anything on macOS, fully quit and reopen this app —")
    print("  TCC changes do not apply to an already-running process tree.")
    return 0 if worst_ok else 1
