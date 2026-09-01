"""The MCP tool layer — an MCP *client*, not a tool registry.

`langchain_mcp_adapters.MultiServerMCPClient` connects to WELLSY's own stdio
servers (`engine.agent.servers.pim`, `engine.agent.servers.fs`) and any extra
servers declared in `WELLSY_MCP_SERVERS` (a JSON object of
`name -> {command, args, env}`). Tools come back as LangChain `BaseTool`s the
LangGraph loop can call directly.

`AgentTools` keeps one persistent session per server for the life of the
runtime, indexes tools by their policy key `<server>.<tool_name>`, and exposes
`list_tools()` with full JSON schemas (acceptance item 1: >= 15).
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

_REPO = Path(__file__).resolve().parents[2]


def _builtin_connections() -> dict[str, dict]:
    py = sys.executable
    common = {"transport": "stdio", "command": py, "cwd": str(_REPO)}
    return {
        "pim": {**common, "args": ["-m", "engine.agent.servers.pim"]},
        "fs": {**common, "args": ["-m", "engine.agent.servers.fs"]},
    }


def _extra_connections() -> dict[str, dict]:
    raw = os.environ.get("WELLSY_MCP_SERVERS", "").strip()
    if not raw:
        return {}
    obj = json.loads(raw)
    out = {}
    for name, cfg in obj.items():
        out[name] = {"transport": "stdio", **cfg}
    return out


def connections() -> dict[str, dict]:
    conns = _builtin_connections()
    conns.update(_extra_connections())
    return conns


@dataclass
class LoadedTool:
    key: str          # "<server>.<tool_name>" — the policy.yaml key
    server: str
    name: str
    tool: Any         # langchain_core.tools.BaseTool

    def schema(self) -> dict:
        return {
            "key": self.key,
            "server": self.server,
            "name": self.name,
            "description": (self.tool.description or "").strip(),
            "inputSchema": getattr(self.tool, "args_schema", None) and _json_schema(self.tool),
        }


def _json_schema(tool: Any) -> dict | None:
    sch = getattr(tool, "args_schema", None)
    if sch is None:
        return None
    if isinstance(sch, dict):
        return sch
    try:
        return sch.model_json_schema()
    except Exception:
        return None


class AgentTools:
    """Async context manager. `async with AgentTools() as tools: ...`."""

    def __init__(self, extra_env: dict[str, str] | None = None) -> None:
        self._client: MultiServerMCPClient | None = None
        self._stack = AsyncExitStack()
        self._by_key: dict[str, LoadedTool] = {}
        self._extra_env = extra_env or {}

    async def __aenter__(self) -> "AgentTools":
        conns = connections()
        for cfg in conns.values():
            env = dict(cfg.get("env") or {})
            env.setdefault("PATH", os.environ.get("PATH", ""))
            # propagate the backend / break-tool / audit-path selection into the
            # child servers so tests and the CLI stay in one world
            # NB: WELLSY_PIM_RESET is deliberately NOT propagated — a reseed is a
            # parent-side concern (do it once), never something every spawned
            # server should re-do and wipe mid-run.
            for k in ("WELLSY_PIM_BACKEND", "WELLSY_PIM_STORE",
                      "WELLSY_FS_ROOTS", "WELLSY_AGENT_BREAK_TOOLS", "PYTHONPATH"):
                if k in os.environ:
                    env.setdefault(k, os.environ[k])
            env.update(self._extra_env)
            cfg["env"] = env

        self._client = MultiServerMCPClient(conns)
        for server in conns:
            session = await self._stack.enter_async_context(self._client.session(server))
            # handle_tool_errors=False: a tool that raises must reach the agent
            # loop AS an exception, so `graph.act_node` can retry it (A11) and
            # the audit line records outcome="error". The default (True) turns a
            # failure into a benign-looking string result — exactly the "a claim
            # is not evidence" trap INVARIANTS #15 warns about.
            tools = await load_mcp_tools(session, handle_tool_errors=False)
            for t in tools:
                key = f"{server}.{t.name}"
                self._by_key[key] = LoadedTool(key=key, server=server, name=t.name, tool=t)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._stack.aclose()
        self._client = None

    # --- accessors --------------------------------------------------------
    def keys(self) -> list[str]:
        return sorted(self._by_key)

    def get(self, key: str) -> LoadedTool:
        if key not in self._by_key:
            raise KeyError(f"no MCP tool {key!r}; have {self.keys()}")
        return self._by_key[key]

    def list_tools(self) -> list[dict]:
        return [self._by_key[k].schema() for k in self.keys()]

    async def call(self, key: str, args: dict[str, Any]) -> Any:
        """Raw tool call — NO policy check. Only `graph.py` calls this, and only
        after `PolicyGate` returned Allow or an approved Confirm. The MCP
        adapter hands back a list of `{"type": "text", "text": "<json>"}`
        content blocks; this parses them into Python values so the verify step
        gets structured data, not a string."""
        lt = self.get(key)
        raw = await lt.tool.ainvoke(args or {})
        return _normalize(raw)


def _normalize(raw: Any) -> Any:
    if isinstance(raw, tuple) and len(raw) == 2:  # (content, artifact)
        raw = raw[1] if raw[1] is not None else raw[0]
    if isinstance(raw, list) and raw and all(
        isinstance(b, dict) and b.get("type") == "text" for b in raw
    ):
        parsed = []
        for b in raw:
            txt = b.get("text", "")
            try:
                parsed.append(json.loads(txt))
            except (json.JSONDecodeError, TypeError):
                parsed.append(txt)
        return parsed[0] if len(parsed) == 1 else parsed
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw
    return raw
