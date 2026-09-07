"""LLM/VLM backend — a streaming client for the OpenAI-compatible
``/v1/chat/completions`` API.

This is the **portable default** for the LLM modality. The same code talks,
unchanged, to:

* Ollama (``http://localhost:11434/v1``) — what this dev machine runs,
* llama.cpp's own ``llama-server``,
* vLLM / SGLang — the correct server for a Linux/CUDA production box
  (`stack-teardown.md` §4).

It is the opposite of the Day 11 mistake. Day 11 failed because `llm.py` was
hard-wired to one endpoint *and never consumed a token stream* (508 ms/turn
discarded). Here the endpoint is configurable, the transport is portable, and
``stream()`` yields every SSE delta the moment it arrives — proven by
`tests/test_llm_streaming.py`.

INVARIANTS #2 explicitly permits "a private server the owner controls"; this
client never leaves localhost unless pointed elsewhere on purpose.

Config (env var > constructor arg > default):
    WELLSY_LLM_BASE_URL   default http://localhost:11434/v1
    WELLSY_LLM_MODEL      default qwen3-vl:2b-instruct-q4_K_M
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Iterator, Sequence

import httpx

from engine.inference.base import (
    BackendCapabilities,
    BackendUnavailable,
    Delta,
    platform_tag,
)

DEFAULT_BASE_URL = "http://localhost:11434/v1"
# Step 5b: the non-reasoning `-instruct` VLM build. `qwen3-vl:4b` (hybrid)
# reasoned uncontrollably (~4 s to first audio, step 4b); `2b-instruct` is
# non-reasoning by construction, 2.0 GB resident, matched the 3B incumbent on a
# legibility spot-check (`.claude/rebuild/step5b-results.md` §4). The full
# real-vision-path resolution sweep is owed (debt D3).
DEFAULT_MODEL = "qwen3-vl:2b-instruct-q4_K_M"
VERIFIED = "2026-09-03"  # Ollama 0.33.2 /v1 streaming re-verified, step 5b


def _base_url(explicit: str | None = None) -> str:
    return (explicit or os.environ.get("WELLSY_LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _model(explicit: str | None = None) -> str:
    return explicit or os.environ.get("WELLSY_LLM_MODEL") or DEFAULT_MODEL


def _server_banner(base_url: str) -> str:
    """Best-effort '<server>/<version>' for the capability row. Never raises."""

    root = base_url.rsplit("/v1", 1)[0]
    try:
        r = httpx.get(root + "/api/version", timeout=2.0)
        if r.status_code == 200:
            return f"ollama/{r.json().get('version', '?')}"
    except Exception:
        pass
    return "openai-compatible/unknown"


def _to_data_uri(image: Any) -> str:
    if isinstance(image, (str, Path)) and Path(image).exists():
        raw = Path(image).read_bytes()
        mime = "image/png" if str(image).lower().endswith(".png") else "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(raw).decode()}"
    if isinstance(image, (bytes, bytearray)):
        return f"data:image/png;base64,{base64.b64encode(bytes(image)).decode()}"
    if isinstance(image, str) and image.startswith("data:"):
        return image
    raise BackendUnavailable(f"unsupported image type for openai_http backend: {type(image)!r}")


def _with_images(
    messages: Sequence[dict[str, Any]], images: Sequence[Any] | None
) -> list[dict[str, Any]]:
    """Attach images to the last user message as OpenAI multi-part content."""

    msgs = [dict(m) for m in messages]
    if not images:
        return msgs
    for m in reversed(msgs):
        if m.get("role") == "user":
            text = m.get("content", "")
            parts: list[dict[str, Any]] = []
            if text:
                parts.append({"type": "text", "text": text})
            for img in images:
                parts.append({"type": "image_url", "image_url": {"url": _to_data_uri(img)}})
            m["content"] = parts
            return msgs
    raise BackendUnavailable("images= supplied but no user message to attach them to")


class OpenAiHttpLlm:
    NAME = "openai_http"
    MODALITY = "llm"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = _base_url(base_url)
        self.model = _model(model)
        self._client = httpx.Client(timeout=timeout)
        self.capabilities = BackendCapabilities(
            modality="llm",
            name=self.NAME,
            platform=platform_tag(),
            accelerator="remote",  # the server picks Metal/CUDA/… — not ours to know
            streams=True,
            version=_server_banner(self.base_url),
            verified=VERIFIED,
            max_context=None,
            resident_mb=None,  # lives in the server process, not measurable from here
            detail={"base_url": self.base_url, "model": self.model},
        )

    @classmethod
    def is_available(cls, base_url: str | None = None) -> bool:
        try:
            r = httpx.get(_base_url(base_url) + "/models", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    def stream(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        tools: Sequence[dict[str, Any]] | None = None,
        images: Sequence[Any] | None = None,
    ) -> Iterator[Delta]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": _with_images(messages, images),
            "stream": True,
        }
        if tools:
            payload["tools"] = list(tools)
        try:
            with self._client.stream(
                "POST", self.base_url + "/chat/completions", json=payload
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    obj = json.loads(data)
                    choice = (obj.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    text = delta.get("content") or ""
                    tcs = delta.get("tool_calls") or []
                    if text or tcs:
                        yield Delta(text=text, tool_call=tcs[0] if tcs else None)
                    if choice.get("finish_reason"):
                        break
        except httpx.HTTPError as e:
            raise BackendUnavailable(f"{self.base_url} unreachable or errored: {e}") from e
        yield Delta(done=True)

    def close(self) -> None:
        self._client.close()
