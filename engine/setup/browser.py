"""Playwright MCP on the WELLSY Chrome profile, through the MCP Python client."""

from __future__ import annotations

import shutil
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from engine.settings import profile_dir


def server_params(settings: dict, *, headless: bool) -> StdioServerParameters:
    web = settings["web"]
    profile = profile_dir(settings)
    # No page snapshots: account pages hold the owner's personal data.
    args = ["-y", f"@playwright/mcp@{web['playwright_mcp']}",
            "--browser", web["browser"], "--user-data-dir", str(profile),
            "--output-dir", str(profile.parent / "playwright-mcp"), "--snapshot-mode", "none"]
    if headless:
        args.append("--headless")
    return StdioServerParameters(command=shutil.which("npx") or "npx", args=args)


@asynccontextmanager
async def session_for(params: StdioServerParameters):
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            yield session


def playwright_mcp(settings: dict, *, headless: bool):
    return session_for(server_params(settings, headless=headless))


async def call(session: ClientSession, tool: str, **args) -> str:
    """Call a Playwright MCP tool; return its text, raise on a tool error."""
    res = await session.call_tool(tool, args)
    text = "\n".join(c.text for c in res.content if getattr(c, "type", "") == "text")
    if res.isError:
        msg = "\n".join(l for l in text.splitlines() if not l.startswith("### ")).strip()
        raise RuntimeError(msg.removeprefix("Error: ") or f"{tool} failed")
    return text


def result_value(text: str) -> str:
    """The value under `### Result` in a Playwright MCP reply."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "### Result":
            body = []
            for nxt in lines[i + 1:]:
                if nxt.startswith("### "):
                    break
                body.append(nxt)
            return "\n".join(body).strip().strip('"')
    return text.strip().strip('"')
