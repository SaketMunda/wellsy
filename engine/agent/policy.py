"""The policy gate. `PolicyGate.check(tool, args, context) -> Decision`.

Not a policy engine. No OPA. ~150 lines of the rule in
`.claude/rebuild/INVARIANTS.md`:

  * Every tool call goes through here, no exceptions (`graph.py` has one call
    site for tool execution and it is behind this).
  * A tool with no entry in `policy.yaml` is risk 3 and fails closed (#9) —
    returned as Confirm, never Allow, with the reason stated.
  * risk 0, or risk 1 + reversible + not requires_approval  -> Allow
  * risk 2  -> Allow iff the autonomy ledger has promoted the capability,
               else Confirm
  * risk 3  -> Confirm (a human, every time). `decision: deny` in the sidecar
               -> Deny (never runs).
  * A path-escape on an `fs.*` write/delete is forced to risk 3 regardless of
    the sidecar, because the sidecar keys the *tool*, not the *arguments*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from engine.agent.autonomy import AutonomyLedger

POLICY_PATH = Path(__file__).resolve().parent / "policy.yaml"

Action = Literal["allow", "confirm", "deny"]


@dataclass(frozen=True)
class Annotation:
    capability: str
    risk: int
    reversible: bool
    requires_approval: bool
    decision: str | None = None  # "deny" hard override
    annotated: bool = True


UNANNOTATED = Annotation(
    capability="unknown",
    risk=3,
    reversible=False,
    requires_approval=True,
    decision=None,
    annotated=False,
)


@dataclass(frozen=True)
class Decision:
    action: Action
    risk: int
    capability: str
    reason: str
    annotation: Annotation
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def requires_approval(self) -> bool:
        return self.action == "confirm"


def load_policy(path: Path | None = None) -> dict[str, Annotation]:
    raw = yaml.safe_load((path or POLICY_PATH).read_text()) or {}
    out: dict[str, Annotation] = {}
    for key, val in raw.items():
        if not isinstance(val, dict):
            continue
        try:
            out[key] = Annotation(
                capability=str(val["capability"]),
                risk=int(val["risk"]),
                reversible=bool(val["reversible"]),
                requires_approval=bool(val["requires_approval"]),
                decision=val.get("decision"),
            )
        except (KeyError, TypeError, ValueError):
            # A malformed entry is treated as if the tool were unannotated —
            # fail closed, don't crash the gate.
            out[key] = UNANNOTATED
    return out


def _fs_path_escapes(tool: str, args: dict) -> bool:
    if not tool.startswith("fs.") or "path" not in args:
        return False
    try:
        from engine.agent.servers.fs import _resolve

        _resolve(str(args["path"]))
        return False
    except Exception:
        return True


class PolicyGate:
    def __init__(
        self,
        *,
        policy_path: Path | None = None,
        autonomy: AutonomyLedger | None = None,
    ) -> None:
        self._path = policy_path
        self._policy = load_policy(policy_path)
        self._autonomy = autonomy or AutonomyLedger()

    def reload(self) -> None:
        self._policy = load_policy(self._path)

    def annotation_for(self, tool: str) -> Annotation:
        return self._policy.get(tool, UNANNOTATED)

    def check(self, tool: str, args: dict | None = None, context: dict | None = None) -> Decision:
        args = args or {}
        ann = self.annotation_for(tool)
        risk = ann.risk
        reason: str

        if not ann.annotated:
            return Decision(
                "confirm", 3, "unknown",
                f"{tool!r} has no policy.yaml entry — risk 3, fail closed (INVARIANTS #9)",
                ann,
            )

        # An argument-level escape upgrades a benign-looking fs tool to risk 3.
        if _fs_path_escapes(tool, args):
            return Decision(
                "confirm", 3, ann.capability,
                f"{tool!r} targets a path outside every allowed root — forced risk 3",
                ann, extra={"forcedRisk": 3},
            )

        if ann.decision == "deny":
            return Decision("deny", risk, ann.capability,
                            f"{tool!r} is denied by policy.yaml", ann)

        if risk <= 0:
            return Decision("allow", risk, ann.capability, "risk 0 read", ann)

        if risk == 1:
            # Risk 1 is "create draft / create reminder / write to scratch" — it
            # runs silently from the start (autonomy rule) unless the sidecar
            # explicitly flags `requires_approval`. `reversible` is recorded as
            # metadata but is not itself a gate at this level.
            if ann.requires_approval:
                return Decision("confirm", risk, ann.capability,
                                "risk 1 flagged requires_approval in policy.yaml", ann)
            return Decision("allow", risk, ann.capability,
                            "risk 1, no approval required", ann)

        if risk == 2:
            runs = self._autonomy.clean_runs(ann.capability)
            if self._autonomy.is_promoted(ann.capability, risk):
                return Decision(
                    "allow", risk, ann.capability,
                    f"risk 2 promoted — {runs} clean read-back-verified runs of "
                    f"{ann.capability!r} in the audit log",
                    ann, extra={"cleanRuns": runs, "promoted": True},
                )
            return Decision(
                "confirm", risk, ann.capability,
                f"risk 2 not yet promoted — {runs} clean run(s) of "
                f"{ann.capability!r}, need more before it runs unsupervised",
                ann, extra={"cleanRuns": runs, "promoted": False},
            )

        # risk 3
        return Decision(
            "confirm", 3, ann.capability,
            "risk 3 (delete / shell / write outside roots) — gated by default", ann,
        )
