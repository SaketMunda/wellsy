"""The inference seam — four small protocols, one per modality, plus the
capability descriptor every backend must publish.

Why this exists (`.claude/rebuild/step2-backend-abstraction.md`): the Day 11
build was slow because the runtime layer was a generation behind and hard-wired
— `llm.py` spoke straight to `localhost:11434`, nothing consumed a token
stream, and there was no seam at which to swap an accelerated backend in per
platform. The project is now OS-independent by requirement (endgame: an agent
on a Linux/ARM64/Jetson humanoid), so platform acceleration may only ever live
*behind* an interface like the ones here, selected at runtime, with a portable
fallback (INVARIANTS #14).

Design rules baked in:

* **Streaming is the only shape.** There is no non-streaming `generate()`. A
  backend that genuinely cannot stream wraps its single result as a one-element
  iterator and sets ``BackendCapabilities.streams = False`` so callers and the
  bench harness can see it. The 508 ms/turn that Day 11 discarded came from
  having a non-streaming path at all.
* **VLM is folded into `LlmBackend`** via ``images=``, not a fifth protocol.
  The agent roadmap needs exactly one text bottleneck where tools, memory, the
  policy gate and the audit log sit; a separate VLM path would be a second seam
  with none of that. Qwen3-VL is a single model anyway.
* **Every backend carries its pinned version and the date it was verified**
  (INVARIANTS #8). ``verified`` is an ISO date string, checked in the
  conformance test to be a real past date.

Nothing here imports a platform-exclusive package, and nothing heavy is
imported at module scope — ``detect_accelerator()`` does its probing lazily.
"""

from __future__ import annotations

import datetime as _dt
import os as _os
import platform as _platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Protocol, Sequence, runtime_checkable

# The sole path outside the repo that INVARIANTS #1 permits: model weights.
# Overridable for CI / the eventual Jetson image via WELLSY_WEIGHTS_DIR.
WEIGHTS_DIR = Path(
    _os.environ.get("WELLSY_WEIGHTS_DIR", Path.home() / ".cache" / "wellsy" / "weights")
).expanduser()

# --------------------------------------------------------------------------- #
# Errors                                                                       #
# --------------------------------------------------------------------------- #


class BackendUnavailable(RuntimeError):
    """Raised when a backend cannot run here — a missing optional import, an
    absent model file, an unreachable server, or a capability it does not have
    (e.g. asking the MLX backend for a VLM turn). The registry and the bench
    harness catch this and record the reason rather than crashing."""


# --------------------------------------------------------------------------- #
# Capability descriptor                                                        #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BackendCapabilities:
    """What a backend is and what it can do. Populated on the instance (after
    load, so ``resident_mb`` can be real) and printed verbatim by ``wellsy
    bench``."""

    modality: str          # "llm" | "asr" | "tts" | "vad"
    name: str              # backend id, matches the registry key, e.g. "openai_http"
    platform: str          # "<os>/<arch>", e.g. "darwin/arm64"
    accelerator: str       # "cuda" | "metal" | "coreml" | "cpu" | "remote"
    streams: bool          # does stream() genuinely yield incrementally?
    version: str           # pinned version of the runtime / server / model
    verified: str          # ISO date (YYYY-MM-DD) this pin was checked — INVARIANTS #8
    max_context: int | None = None    # tokens; None = not applicable
    resident_mb: float | None = None  # measured RSS delta across load; None = unknown
    detail: dict[str, Any] = field(default_factory=dict)  # free-form, e.g. model id

    def as_row(self) -> dict[str, Any]:
        return {
            "modality": self.modality,
            "backend": self.name,
            "platform": self.platform,
            "accelerator": self.accelerator,
            "streams": self.streams,
            "version": self.version,
            "verified": self.verified,
            "maxContext": self.max_context,
            "residentMb": round(self.resident_mb, 1) if self.resident_mb is not None else None,
            **({"detail": self.detail} if self.detail else {}),
        }


# --------------------------------------------------------------------------- #
# Stream payloads                                                              #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Delta:
    """One increment of an LLM/VLM response stream."""

    text: str = ""
    tool_call: dict[str, Any] | None = None
    done: bool = False


@dataclass(frozen=True)
class Partial:
    """A revisable ASR hypothesis — the text so far, may change on the next one."""

    text: str
    t0: float | None = None   # seconds from stream start
    t1: float | None = None


@dataclass(frozen=True)
class Final:
    """A committed ASR segment — will not change."""

    text: str
    t0: float | None = None
    t1: float | None = None


@dataclass(frozen=True)
class PcmChunk:
    """A slice of synthesised audio. ``pcm`` is mono float32 in [-1, 1]."""

    pcm: Any            # numpy.ndarray, kept as Any so base.py has no numpy import cost
    sample_rate: int


@dataclass(frozen=True)
class SpeechProb:
    """Per-frame VAD output."""

    prob: float         # 0..1 probability the frame contains speech
    t: float            # seconds from stream start
    is_speech: bool      # prob >= the backend's threshold


# --------------------------------------------------------------------------- #
# Protocols                                                                    #
# --------------------------------------------------------------------------- #

# Every backend class also carries two class attributes the registry keys on:
#     NAME: str      — registry id, equal to BackendCapabilities.name
#     MODALITY: str  — "llm" | "asr" | "tts" | "vad"
# and a classmethod is_available() -> bool that must be cheap (no model load).


@runtime_checkable
class LlmBackend(Protocol):
    capabilities: BackendCapabilities

    @classmethod
    def is_available(cls) -> bool: ...

    def stream(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        tools: Sequence[dict[str, Any]] | None = None,
        images: Sequence[Any] | None = None,
    ) -> Iterator[Delta]: ...


@runtime_checkable
class AsrBackend(Protocol):
    capabilities: BackendCapabilities

    @classmethod
    def is_available(cls) -> bool: ...

    def stream(self, audio_chunks: Iterator[Any]) -> Iterator[Partial | Final]: ...


@runtime_checkable
class TtsBackend(Protocol):
    capabilities: BackendCapabilities

    @classmethod
    def is_available(cls) -> bool: ...

    def stream(self, text_chunks: Iterator[str]) -> Iterator[PcmChunk]: ...


@runtime_checkable
class VadBackend(Protocol):
    capabilities: BackendCapabilities

    @classmethod
    def is_available(cls) -> bool: ...

    def stream(self, frames: Iterator[Any]) -> Iterator[SpeechProb]: ...


PROTOCOLS: dict[str, type] = {
    "llm": LlmBackend,
    "asr": AsrBackend,
    "tts": TtsBackend,
    "vad": VadBackend,
}


# --------------------------------------------------------------------------- #
# Platform probes — lazy, portable                                             #
# --------------------------------------------------------------------------- #


def platform_tag() -> str:
    """``"<os>/<arch>"`` — ``darwin/arm64``, ``linux/x86_64``, ``windows/amd64``."""

    return f"{_platform.system().lower()}/{_platform.machine().lower()}"


def detect_accelerator() -> str:
    """Best-effort local accelerator: ``cuda`` > ``metal`` / ``coreml`` > ``cpu``.

    All imports are inside the function so this module stays cheap and portable
    — importing it never drags in onnxruntime or torch.
    """

    # NVIDIA, via whatever is installed.
    try:  # pragma: no cover - depends on host
        import torch  # type: ignore

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    try:  # pragma: no cover - depends on host
        import onnxruntime as ort  # type: ignore

        providers = set(ort.get_available_providers())
        if "CUDAExecutionProvider" in providers or "TensorrtExecutionProvider" in providers:
            return "cuda"
        if "ROCMExecutionProvider" in providers:
            return "rocm"
        if "CoreMLExecutionProvider" in providers:
            return "coreml"
        if "DmlExecutionProvider" in providers:
            return "directml"
    except Exception:
        pass
    if _platform.system() == "Darwin" and _platform.machine().lower() in {"arm64", "aarch64"}:
        return "metal"
    return "cpu"


def is_past_iso_date(value: str) -> bool:
    """True if ``value`` is a YYYY-MM-DD date that is today or earlier. Used by
    the conformance test to hold backends to INVARIANTS #8."""

    try:
        d = _dt.date.fromisoformat(value)
    except ValueError:
        return False
    return d <= _dt.date.today()
