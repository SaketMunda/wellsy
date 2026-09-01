"""Platform-neutral PIM (personal-information-management) backend.

The tool-facing interface here is deliberately platform-neutral (INVARIANTS
#14): `servers/pim.py` calls only `PimBackend`, so the Linux/robot backend
drops in without touching the MCP server or the agent. Two implementations:

  * `portable.PortablePimBackend` — a JSON store under `runs/agent/`. The
    default everywhere unless `WELLSY_PIM_BACKEND=macos`. Deterministic, seeded,
    and the only backend the acceptance tests touch — so A4/A5/A6/A11 do not
    depend on a real calendar or a real mail account.
  * `macos.MacPimBackend` — `osascript` (AppleScript/JXA) against Calendar,
    Reminders, Mail, Notes and Contacts. Real, darwin-only, selected explicitly.
"""

from __future__ import annotations

import os

from engine.agent.backends.base import (
    Contact,
    Draft,
    Event,
    MailMessage,
    Note,
    PimBackend,
    Reminder,
    ToolError,
)

__all__ = [
    "Contact",
    "Draft",
    "Event",
    "MailMessage",
    "Note",
    "PimBackend",
    "Reminder",
    "ToolError",
    "get_pim_backend",
]

_INSTANCE: PimBackend | None = None


def get_pim_backend() -> PimBackend:
    """Process-wide singleton. `WELLSY_PIM_BACKEND` selects: `portable`
    (default) or `macos`. An unknown value fails loudly rather than silently
    falling back — a misconfigured backend must not look like an empty
    calendar."""

    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE

    name = os.environ.get("WELLSY_PIM_BACKEND", "portable").strip().lower()
    if name == "portable":
        from engine.agent.backends.portable import PortablePimBackend

        _INSTANCE = PortablePimBackend()
    elif name == "macos":
        from engine.agent.backends.macos import MacPimBackend

        _INSTANCE = MacPimBackend()
    else:
        raise ValueError(
            f"WELLSY_PIM_BACKEND={name!r} is not a known backend (portable | macos)"
        )
    return _INSTANCE


def reset_pim_backend() -> None:
    """Test hook — drop the singleton so the next `get_pim_backend()` rereads
    the environment and (for portable) reseeds from a clean store."""

    global _INSTANCE
    _INSTANCE = None
