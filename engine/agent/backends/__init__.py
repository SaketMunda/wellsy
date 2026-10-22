"""Platform-neutral PIM (personal-information-management) backend.

The tool-facing interface here is deliberately platform-neutral (INVARIANTS
#14): `servers/pim.py` calls only `PimBackend`, so the Linux/robot backend
drops in without touching the MCP server or the agent. Two implementations:

  * `standard.AccountsPimBackend` — the user's real accounts over standard
    protocols (IMAP/SMTP mail, CalDAV calendar, CardDAV contacts), the same on
    every OS. Used when an account is connected (`wellsy accounts add`).
  * `portable.PortablePimBackend` — a seeded JSON demo store under
    `runs/agent/`. Used when no account is connected, and the only backend the
    acceptance tests touch, so A4/A5/A6/A11 do not depend on a real account.
"""

from __future__ import annotations

import os
import sys

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
    """Process-wide singleton. `WELLSY_PIM_BACKEND` selects: `auto` (default:
    accounts when one is connected, else portable), `accounts` or `portable`.
    An unknown value fails loudly rather than silently falling back — a misconfigured backend must not look like an empty
    calendar."""

    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE

    name = os.environ.get("WELLSY_PIM_BACKEND", "auto").strip().lower()
    if name == "auto":
        from engine.agent.backends.accounts import load_accounts

        name = "accounts" if load_accounts().mail else "portable"
        if name == "portable":
            print("PIM: demo store (no account connected; run `wellsy accounts add`)", file=sys.stderr)
    if name == "portable":
        from engine.agent.backends.portable import PortablePimBackend

        _INSTANCE = PortablePimBackend()
    elif name == "accounts":
        from engine.agent.backends.standard import AccountsPimBackend

        _INSTANCE = AccountsPimBackend()
    else:
        raise ValueError(
            f"WELLSY_PIM_BACKEND={name!r} is not a known backend (auto | accounts | portable)"
        )
    return _INSTANCE


def reset_pim_backend() -> None:
    """Test hook — drop the singleton so the next `get_pim_backend()` rereads
    the environment and (for portable) reseeds from a clean store."""

    global _INSTANCE
    _INSTANCE = None
