"""LLM backend — Apple MLX, via ``mlx-lm``.

**This backend is opt-in and never a default (INVARIANTS #14 / step 2 "Do
not").** The registry's auto-selection will not return it on any platform; it
runs only when asked for explicitly (``WELLSY_LLM_BACKEND=mlx`` or config).
MLX is measurably faster than llama.cpp on sub-14B models on this dev machine
(20–87%), which is exactly why it must not be allowed to become load-bearing —
it does not exist on Linux, Windows, or the Jetson target.

``mlx_lm`` is imported **lazily inside methods**, never at module scope, so that
importing the registry on a non-Apple box is fine.

Config:
    WELLSY_MLX_MODEL   default mlx-community/Qwen3-4B-4bit
"""

from __future__ import annotations

import importlib.util
import os
import platform
import time
from typing import Any, Iterator, Sequence

from engine.inference.base import (
    BackendCapabilities,
    BackendUnavailable,
    Delta,
    platform_tag,
)

DEFAULT_MODEL = "mlx-community/Qwen3-4B-4bit"
VERIFIED = "2026-09-01"  # mlx-lm 0.31.3 / mlx 0.32.2


def _model_id(explicit: str | None = None) -> str:
    return explicit or os.environ.get("WELLSY_MLX_MODEL") or DEFAULT_MODEL


def _is_cached(model_id: str) -> bool:
    """True if the HF snapshot for ``model_id`` is already on disk — keeps
    ``is_available()`` cheap and honest (no silent multi-GB download)."""

    try:
        from huggingface_hub import try_to_load_from_cache  # type: ignore
    except Exception:
        return False
    # A repo is cached if its config.json resolved to a real path.
    hit = try_to_load_from_cache(repo_id=model_id, filename="config.json")
    return isinstance(hit, str) and os.path.exists(hit)


class MlxLlm:
    NAME = "mlx"
    MODALITY = "llm"

    def __init__(self, *, model_id: str | None = None, max_tokens: int = 512) -> None:
        if platform.system() != "Darwin":
            raise BackendUnavailable("MLX runs on Apple Silicon only")
        if importlib.util.find_spec("mlx_lm") is None:
            raise BackendUnavailable(
                "mlx-lm not installed — `uv sync --extra inference-mlx` (macOS only)"
            )
        import mlx_lm  # lazy — never at module scope

        self.model_id = _model_id(model_id)
        self.max_tokens = max_tokens
        t0 = time.monotonic()
        try:
            self._model, self._tok = mlx_lm.load(self.model_id)
        except Exception as e:  # network off + not cached, bad id, …
            raise BackendUnavailable(f"could not load MLX model {self.model_id!r}: {e}") from e
        self._load_s = time.monotonic() - t0

        try:
            from importlib.metadata import version as _v

            ver = f"mlx-lm {_v('mlx-lm')}"
        except Exception:
            ver = "mlx-lm ?"
        max_ctx = getattr(self._tok, "model_max_length", None)
        if not isinstance(max_ctx, int) or max_ctx > 10_000_000:
            max_ctx = None
        self.capabilities = BackendCapabilities(
            modality="llm",
            name=self.NAME,
            platform=platform_tag(),
            accelerator="metal",
            streams=True,
            version=ver,
            verified=VERIFIED,
            max_context=max_ctx,
            resident_mb=None,
            detail={"model": self.model_id, "load_s": round(self._load_s, 2)},
        )

    @classmethod
    def is_available(cls) -> bool:
        return (
            platform.system() == "Darwin"
            and importlib.util.find_spec("mlx_lm") is not None
            and _is_cached(_model_id())
        )

    def stream(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        tools: Sequence[dict[str, Any]] | None = None,
        images: Sequence[Any] | None = None,
    ) -> Iterator[Delta]:
        if images:
            raise BackendUnavailable(
                "MLX backend has no VLM path — use the openai_http backend for image turns"
            )
        import mlx_lm  # lazy

        prompt = self._tok.apply_chat_template(
            list(messages), add_generation_prompt=True, tokenize=False
        )
        for resp in mlx_lm.stream_generate(
            self._model, self._tok, prompt, max_tokens=self.max_tokens
        ):
            if resp.text:
                yield Delta(text=resp.text)
        yield Delta(done=True)
