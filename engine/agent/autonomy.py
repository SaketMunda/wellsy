"""Autonomy as a level that rises against the audit log — not a switch.

The rule (INVARIANTS "Autonomy rule", stack-teardown §12.5):

  * risk 0 / 1, reversible  -> run silently from the start
  * risk 2                  -> Confirm required *until the audit log shows a
                              clean run of that action class*, then silent
  * risk 3                  -> gated by default, indefinitely

"Clean run of that action class" is read straight off `audit.jsonl`:
`WELLSY_AUTONOMY_CLEAN_RUNS` (default 3) finalised entries for the same
`capability`, each with `outcome == "ok"`, a non-null `readBack` that verified,
an explicit human approval (`approvalSource` starting `user:`), and zero
denials or errors for that capability anywhere in the log.

A single denial or error for a capability resets it: the count must be rebuilt
from entries *after* the last bad one. Promotion is earned continuously, not
banked.

This class only *reads* the log and reports a verdict. It never writes, never
flips a persisted flag — there is no persisted autonomy state to tamper with,
which is the point.
"""

from __future__ import annotations

import os
from pathlib import Path

from engine.agent import audit


def _threshold() -> int:
    try:
        return max(1, int(os.environ.get("WELLSY_AUTONOMY_CLEAN_RUNS", "3")))
    except ValueError:
        return 3


def _read_back_ok(entry: dict) -> bool:
    rb = entry.get("readBack")
    if rb is None:
        return False
    if isinstance(rb, dict):
        # graph.py's verify step stores {"verified": bool, ...}
        return bool(rb.get("verified", False))
    return True


class AutonomyLedger:
    """Verdict source for `PolicyGate`. Construct per check (cheap — the log is
    small) or reuse; `clean_runs()` always re-reads."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    def _entries(self) -> list[dict]:
        return audit.summarize(path=self._path)

    def clean_runs(self, capability: str) -> int:
        """How many consecutive clean, human-approved, read-back-verified runs
        of `capability` sit at the tail of the log (after the last error or
        denial for that capability)."""
        count = 0
        for e in self._entries():
            if e.get("capability") != capability:
                continue
            outcome = e.get("outcome")
            if outcome in ("error", "denied", "unverified"):
                count = 0
                continue
            if outcome != "ok":
                continue
            approved_by_human = str(e.get("approvalSource") or "").startswith("user:")
            if approved_by_human and _read_back_ok(e):
                count += 1
            else:
                # an "ok" that was auto-run or unverified doesn't build trust,
                # but doesn't reset it either
                continue
        return count

    def is_promoted(self, capability: str, risk: int) -> bool:
        """True if `capability` may run silently now. Risk 3 is never promoted.
        Risk <= 1 doesn't need promotion (handled in PolicyGate) but returns
        True here for completeness."""
        if risk >= 3:
            return False
        if risk <= 1:
            return True
        return self.clean_runs(capability) >= _threshold()

    def status(self) -> list[dict]:
        """For `wellsy autonomy` — every capability seen in the log, its clean
        streak, and whether it is promoted."""
        caps: dict[str, int] = {}
        for e in self._entries():
            cap = e.get("capability")
            risk = e.get("risk", 3)
            if cap and risk == 2:
                caps.setdefault(cap, 0)
        out = []
        for cap in sorted(caps):
            runs = self.clean_runs(cap)
            out.append({
                "capability": cap,
                "cleanRuns": runs,
                "threshold": _threshold(),
                "promoted": runs >= _threshold(),
            })
        return out
