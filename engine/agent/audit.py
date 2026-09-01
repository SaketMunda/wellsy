"""The agent audit log — one JSONL line per consequential action, written
*before* the action returns (INVARIANTS #12), not after and not on success
only.

This extends `engine/honesty/provenance.py`'s discipline into agency: same
append-only JSONL, same lock, same "a claim is not evidence" stance. The
perception layer logs what it *saw*; this logs what it *did*, and why it was
allowed to.

The write ordering the runtime must honour (enforced by `graph.py`, checked by
the acceptance suite):

    1. policy decision reached
    2. audit line written with outcome="pending"    <-- before the tool runs
    3. tool runs
    4. read-back verification
    5. audit line finalised (outcome, read_back) via `finalize()`

If the process dies at step 3, the pending line is still on disk — that is the
point. A denial writes a single terminal line (no tool runs).
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

RUNS_DIR = Path(__file__).resolve().parents[2] / "runs" / "agent"
AUDIT_PATH = RUNS_DIR / "audit.jsonl"

_SECRET_HINTS = ("password", "passwd", "token", "secret", "api_key", "apikey",
                 "authorization", "auth", "cookie", "credential")

_lock = threading.Lock()


def _audit_path() -> Path:
    # Indirection so tests can point the log at a tmp dir via env.
    override = os.environ.get("WELLSY_AUDIT_PATH")
    return Path(override) if override else AUDIT_PATH


def redact(obj: Any) -> Any:
    """Recursively blank anything whose key looks like a secret. Values are
    replaced with '***' — the key stays so the shape of the call is auditable."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and any(h in k.lower() for h in _SECRET_HINTS):
                out[k] = "***"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    return obj


def _write(record: dict) -> None:
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, default=str)
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())


class AuditEntry:
    """A single consequential action's audit record. Constructed and written
    (outcome='pending') by `begin()`; completed by `finalize()`."""

    def __init__(self, record: dict) -> None:
        self.id: str = record["auditId"]
        self._record = record
        self._final = False

    def finalize(
        self, *, outcome: str, read_back: Any = None, error: str | None = None,
    ) -> None:
        """Append the terminal line for this action. `outcome`: 'ok' | 'error' |
        'denied' | 'unverified'. `read_back` is the independent verification
        result (INVARIANTS #15) or None if the action class has no read-back."""
        if self._final:
            return
        self._final = True
        rec = dict(self._record)
        rec.update({
            "t": round(time.time(), 3),
            "phase": "final",
            "outcome": outcome,
            "readBack": redact(read_back) if read_back is not None else None,
            "error": error,
            "durationMs": round((time.time() - self._record["t"]) * 1000, 1),
        })
        _write(rec)


def begin(
    *,
    actor: str,
    tool: str,
    arguments: dict,
    risk: int,
    policy_decision: str,
    approval_source: str | None,
    plan_id: str,
    step_id: str,
    capability: str | None = None,
) -> AuditEntry:
    """Write the pending line and return a handle to finalise it. Call this
    *before* the tool executes. `policy_decision`: 'allow' | 'confirm' | 'deny'.
    `approval_source`: who approved a confirm ('user:cli', 'autonomy:promoted',
    None for allow/deny)."""
    rec = {
        "auditId": uuid.uuid4().hex[:12],
        "t": round(time.time(), 3),
        "phase": "pending",
        "actor": actor,
        "tool": tool,
        "capability": capability,
        "arguments": redact(arguments),
        "risk": risk,
        "policyDecision": policy_decision,
        "approvalSource": approval_source,
        "outcome": "pending",
        "readBack": None,
        "planId": plan_id,
        "stepId": step_id,
    }
    _write(rec)
    return AuditEntry(rec)


def record_denial(
    *, actor: str, tool: str, arguments: dict, risk: int, reason: str,
    plan_id: str, step_id: str, approval_source: str | None = None,
    capability: str | None = None,
) -> None:
    """A denial (policy deny, or a user declining a confirm). One terminal line,
    no pending line, no tool run. A6 requires this line exist for a declined
    send."""
    entry = begin(
        actor=actor, tool=tool, arguments=arguments, risk=risk,
        policy_decision="deny", approval_source=approval_source,
        plan_id=plan_id, step_id=step_id, capability=capability,
    )
    entry.finalize(outcome="denied", error=reason)


def read_all(path: Path | None = None) -> list[dict]:
    p = path or _audit_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def summarize(plan_id: str | None = None, path: Path | None = None) -> list[dict]:
    """Collapse pending+final pairs into one row per action, for `wellsy audit`
    and scenario A12. Derived from the log on disk, never from conversation
    memory."""
    rows = read_all(path)
    by_id: dict[str, dict] = {}
    for r in rows:
        aid = r["auditId"]
        cur = by_id.setdefault(aid, {})
        cur.update({k: v for k, v in r.items() if v is not None or k not in cur})
        cur["auditId"] = aid
    actions = list(by_id.values())
    if plan_id is not None:
        actions = [a for a in actions if a.get("planId") == plan_id]
    return sorted(actions, key=lambda a: a.get("t", 0))
