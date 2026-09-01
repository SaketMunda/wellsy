"""WELLSY agent runtime — the part that *acts*.

Step 5 (`.claude/rebuild/step5-agent-runtime.md`). Five pieces, none of which
existed before this step:

  * `backends/`  — a platform-neutral PIM interface + a portable JSON store
                   (the default, used on Linux/CI) + a macOS `osascript` backend.
  * `servers/`   — our own FastMCP stdio servers (PIM + scoped filesystem). MCP
                   is the standard and we speak it; we author the servers because
                   no community macOS Apple-app server clears INVARIANTS #8.
  * `policy.py`  — `PolicyGate.check(...) -> Allow | Confirm | Deny`, driven by a
                   YAML sidecar keyed by `server.tool_name`. Unannotated tools
                   are risk 3 and fail closed (#9).
  * `autonomy.py`— the autonomy *level*: it rises against the audit log, not a
                   switch. Risk-2 stays gated until the log shows a clean run.
  * `audit.py`   — one JSONL line per consequential action, written *before* the
                   action returns (#12). Extends `honesty/provenance.py`.
  * `graph.py`   — the LangGraph state machine: plan -> policy -> act -> verify
                   by read-back -> checkpoint. `interrupt()` is the approval gate.
  * `models.py`  — two model roles (fast path / planner), never one model.
"""
