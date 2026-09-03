"""The portable Presence/HUD backend interface.

INVARIANTS #14: the core selects a backend at runtime and every backend honours
this contract. Platform code (NSPanel semantics, wlr-layer-shell) lives *inside*
a backend, behind this seam — never in the core, exactly like the step-3 screen
backends.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from engine.interface.state import StateSnapshot


@runtime_checkable
class PresenceBackend(Protocol):
    name: str

    def start(self) -> None:
        """Create the surface (or not, for headless). Non-blocking."""

    def render(self, snap: StateSnapshot) -> None:
        """Push the latest measured snapshot at the render cadence. Must be
        cheap; must throttle its own frame rate when `snap` is not changing
        (performance budget: orb asleep < 1% of the machine)."""

    def show_hud(self, view: dict) -> None:
        """Unfold the HUD with real content: plan, approval prompt, captured
        frame, audit trail. `view` is already-shaped data — the backend does no
        fetching."""

    def hide_hud(self) -> None: ...

    def stop(self) -> None: ...
