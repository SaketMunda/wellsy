"""`fs` MCP server — a filesystem scoped to explicit allowed roots. Not `/`.

Allowed roots come from `WELLSY_FS_ROOTS` (os.pathsep-separated). Default: one
root, `runs/agent/scratch/` inside the repo (INVARIANTS #1 — project files stay
in the repo). Every path argument is resolved and checked against the roots
*before* any I/O; a path that escapes every root is refused here **and** is
risk 3 in `policy.yaml` (`fs.write_file` / `fs.delete_file` outside roots). The
server refusing is defence in depth, not a substitute for the policy gate.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from engine.agent.servers._break import breakable

mcp = FastMCP("fs")

_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_ROOT = _REPO / "runs" / "agent" / "scratch"


def _roots() -> list[Path]:
    raw = os.environ.get("WELLSY_FS_ROOTS", "").strip()
    if not raw:
        _DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)
        return [_DEFAULT_ROOT.resolve()]
    out = []
    for part in raw.split(os.pathsep):
        if part.strip():
            p = Path(part).expanduser().resolve()
            p.mkdir(parents=True, exist_ok=True)
            out.append(p)
    return out


def _resolve(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = _roots()[0] / p
    p = p.resolve()
    for root in _roots():
        if p == root or root in p.parents:
            return p
    raise RuntimeError(
        f"path_outside_roots: {p} is not inside any allowed root ({[str(r) for r in _roots()]})"
    )


@mcp.tool()
def fs_allowed_roots() -> list[str]:
    """The roots this server will read or write under. Risk 0."""
    return [str(r) for r in _roots()]


@mcp.tool()
@breakable("fs_list_dir")
def fs_list_dir(path: str = ".") -> list[dict]:
    """List a directory inside the allowed roots. Risk 0 — read."""
    d = _resolve(path)
    if not d.is_dir():
        raise RuntimeError(f"not_a_directory: {d}")
    return sorted(
        ({"name": c.name, "is_dir": c.is_dir(), "size": c.stat().st_size} for c in d.iterdir()),
        key=lambda r: (not r["is_dir"], r["name"]),
    )


@mcp.tool()
@breakable("fs_read_file")
def fs_read_file(path: str) -> str:
    """Read a UTF-8 text file inside the allowed roots. Risk 0 — read."""
    f = _resolve(path)
    if not f.is_file():
        raise RuntimeError(f"not_found: {f}")
    return f.read_text(encoding="utf-8", errors="replace")


@mcp.tool()
@breakable("fs_write_file")
def fs_write_file(path: str, content: str) -> dict:
    """Write a UTF-8 text file. Risk 1 inside a root (write to scratch); risk 3
    outside (the policy gate blocks that — this server also refuses)."""
    f = _resolve(path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return {"path": str(f), "bytes": len(content.encode("utf-8"))}


@mcp.tool()
@breakable("fs_delete_file")
def fs_delete_file(path: str) -> dict:
    """Delete a file. Risk 3 — irreversible. Gated by default (policy.yaml)."""
    f = _resolve(path)
    if not f.is_file():
        raise RuntimeError(f"not_found: {f}")
    f.unlink()
    return {"deleted": str(f)}


if __name__ == "__main__":  # pragma: no cover
    mcp.run("stdio")
