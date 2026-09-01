"""FastMCP stdio servers WELLSY owns and ships.

`pim` — Calendar, Reminders, Mail, Notes, Contacts (via `backends/`).
`fs`  — a filesystem server scoped to explicit allowed roots. Not `/`.

Run standalone for debugging:  `python -m engine.agent.servers.pim`
They are normally spawned over stdio by `engine.agent.mcp_client`.

Why our own instead of a community server: verified 2026-09-01, the macOS
Apple-app MCP servers on GitHub are 2-commit repos with no tagged release, a
Node/bun runtime dependency, no Mail tools, and no read-only / safety-mode
flag. None clears INVARIANTS #8, and MCP SDK v2 (protocol 2026-07-28) is not
yet supported by `langchain-mcp-adapters`. Authoring the servers *is* using the
standard — MCP — not building a bespoke tool registry.
"""
