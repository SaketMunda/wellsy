"""Deliberate-failure injection for acceptance scenario A11.

`WELLSY_AGENT_BREAK_TOOLS` is a comma-separated list of bare MCP tool names.
Any listed tool raises `BrokenToolError` *before* touching a backend, so a
4-step plan with a broken step 2 exercises the real retry / checkpoint / honest
-report path without corrupting the store. This is the only sanctioned way to
make a tool fail on purpose — there is no hidden failure mode elsewhere.
"""

from __future__ import annotations

import functools
import os


class BrokenToolError(RuntimeError):
    pass


def _broken() -> set[str]:
    raw = os.environ.get("WELLSY_AGENT_BREAK_TOOLS", "")
    return {t.strip() for t in raw.split(",") if t.strip()}


def breakable(name: str):
    """Decorator: raise if `name` is in `WELLSY_AGENT_BREAK_TOOLS`. Read from
    the environment on every call so a test can toggle it per-scenario."""

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if name in _broken():
                raise BrokenToolError(
                    f"tool {name!r} is in WELLSY_AGENT_BREAK_TOOLS — injected failure (A11)"
                )
            return fn(*args, **kwargs)

        return wrapper

    return deco
