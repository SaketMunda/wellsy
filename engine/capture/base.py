"""Portable capture interface — shared types for camera and screen.

Nothing in this module imports a platform package (invariant #14). The
platform backends live under `engine/capture/screen/` and are the *only*
place a macOS / Linux / Windows API may be touched.

The contract that matters: a capture that has not been *verified* non-degenerate
never reaches a model. `verify.py` enforces it; `CaptureResult.verified` records
the outcome honestly (invariant #6 — no fabricated observation presented as
fact, and invariant #15 — a tool's own success is a claim, not evidence).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

import numpy as np


class Permission(str, Enum):
    """Authorization state for a capture device, for the *current process tree*.
    TCC on macOS is granted per process tree, so the terminal, an IDE's
    integrated terminal and a packaged app each need their own grant."""

    GRANTED = "granted"
    DENIED = "denied"
    NOT_DETERMINED = "not_determined"  # never prompted yet
    RESTRICTED = "restricted"  # blocked by policy (MDM / parental controls)
    UNKNOWN = "unknown"  # backend cannot probe (e.g. portable mss on macOS pre-14)

    @property
    def usable(self) -> bool:
        return self is Permission.GRANTED


@dataclass(frozen=True)
class WindowInfo:
    """One on-screen window as the window server reports it. `title is None`
    is meaningful on macOS: the window server withholds titles from processes
    that lack Screen Recording authorization, so `title is None` on a window
    that plainly exists is itself a signal the capture will be stripped."""

    owner: str
    pid: int
    title: str | None
    bounds: tuple[int, int, int, int]  # x, y, w, h in global display coords
    layer: int  # 0 == normal app window; menu bar / dock / wallpaper are non-zero


@dataclass
class DisplayFrame:
    """One captured display. `image` is BGR uint8 (H, W, 3), matching the
    convention the perception core already uses (`engine/perception`)."""

    index: int  # 0-based display index, stable ordering (primary first)
    image: np.ndarray
    width: int
    height: int
    is_primary: bool = False
    label: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            tag = "primary" if self.is_primary else f"display {self.index}"
            self.label = f"{tag} ({self.width}x{self.height})"


@dataclass
class CaptureResult:
    """What a model is allowed to receive. Only ever constructed by
    `verify.verify_screen()` after the capture cleared verification, or by the
    camera path (which has no degenerate-capture failure mode of this kind)."""

    frames: list[DisplayFrame]
    backend: str
    verified: bool
    verified_by: str  # which signal confirmed it: "preflight+window-crosscheck", ...
    verified_at: float = field(default_factory=time.time)
    source: str = "screen"  # "screen" | "camera"

    @property
    def primary(self) -> DisplayFrame:
        for f in self.frames:
            if f.is_primary:
                return f
        return self.frames[0]

    def provenance(self) -> dict:
        """The record `honesty/provenance.py` folds into its per-answer line."""
        return {
            "captureSource": self.source,
            "captureBackend": self.backend,
            "captureVerified": self.verified,
            "captureVerifiedBy": self.verified_by,
            "captureVerifiedAt": round(self.verified_at, 3),
            "displayCount": len(self.frames),
        }


class CaptureError(RuntimeError):
    """Raised instead of returning an unverified or failed capture. Carries an
    actionable, human-legible remedy — never a bare stack trace, and never a
    description of whatever degenerate pixels came back."""

    def __init__(
        self,
        reason: str,
        *,
        permission: str | None = None,
        remedy: str | None = None,
        spoken: str | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.permission = permission
        self.remedy = remedy
        # What WELLSY says out loud / logs. Never a wallpaper description.
        self.spoken = spoken or (
            "I can't see your screen — screen recording permission isn't granted "
            "for this process."
        )

    def report(self) -> str:
        lines = [self.reason]
        if self.remedy:
            lines.append(self.remedy)
        return "\n".join(lines)


@runtime_checkable
class ScreenBackend(Protocol):
    """One implementation per platform, selected at runtime by
    `screen/__init__.py`. Callers outside `screen/` use this shape only."""

    name: str

    def available(self) -> bool:
        """True if this backend's platform APIs imported and are callable here."""

    def permission(self) -> Permission:
        """Screen-recording authorization for the current process tree."""

    def request_permission(self) -> Permission:
        """Trigger the OS grant flow if one exists; return the state after."""

    def list_windows(self) -> list[WindowInfo]:
        """On-screen windows the window server knows about. Empty list is a
        valid answer (nothing open) and also what a backend that cannot ask
        returns — `verify` distinguishes the two using `permission()`."""

    def capture(self) -> list[DisplayFrame]:
        """Every attached display, primary first. Raises `CaptureError` with a
        permission remedy if the platform API refuses (ScreenCaptureKit does;
        `screencapture` did not, which was the entire bug)."""
