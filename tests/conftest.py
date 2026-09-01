"""Shared fixtures for the step-5 agent-runtime tests.

`agent_env` isolates the audit log and the portable PIM store into a tmp dir so
tests never touch `runs/agent/*` and never see each other's state. It also
resets the backend singleton and clears the break-tool switch.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def agent_env(tmp_path, monkeypatch):
    audit_path = tmp_path / "audit.jsonl"
    store_path = tmp_path / "pim_store.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    monkeypatch.setenv("WELLSY_AUDIT_PATH", str(audit_path))
    monkeypatch.setenv("WELLSY_PIM_STORE", str(store_path))
    monkeypatch.setenv("WELLSY_PIM_BACKEND", "portable")
    monkeypatch.setenv("WELLSY_FS_ROOTS", str(scratch))
    monkeypatch.delenv("WELLSY_PIM_RESET", raising=False)
    monkeypatch.delenv("WELLSY_AGENT_BREAK_TOOLS", raising=False)
    monkeypatch.setenv("WELLSY_AUTONOMY_CLEAN_RUNS", "2")

    # seed the portable store ONCE, here, in the parent — children only read it
    # (a reseed mid-run would wipe drafts/events created earlier in the test).
    backends = importlib.import_module("engine.agent.backends")
    backends.reset_pim_backend()
    from engine.agent.backends.portable import PortablePimBackend

    PortablePimBackend(reset=True)
    backends.reset_pim_backend()

    yield {
        "audit_path": audit_path,
        "store_path": store_path,
        "scratch": scratch,
        "tmp": tmp_path,
    }

    backends.reset_pim_backend()
