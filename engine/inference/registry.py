"""Runtime backend detection and selection.

`.claude/rebuild/step2-backend-abstraction.md` Deliverable 2: detect the
platform and accelerator at runtime, pick a backend per modality, and let an
env var or a config dict override the pick.

Selection order (highest wins):

    1. WELLSY_<MODALITY>_BACKEND env var   e.g. WELLSY_LLM_BACKEND=mlx
    2. config dict passed to select()/get_backend()
    3. auto — platform + availability

Auto-selection table (`stack-teardown.md` §4, step 2 Deliverable 2):

    | platform                | llm          | asr            | tts    | vad    |
    |-------------------------|--------------|----------------|--------|--------|
    | linux + nvidia / jetson | openai_http* | faster_whisper | kokoro | silero |
    | windows + nvidia        | openai_http* | faster_whisper | kokoro | silero |
    | macos apple silicon     | openai_http* | faster_whisper | kokoro | silero |
    | anything, no accel      | openai_http* | faster_whisper | kokoro | silero |

    `faster_whisper` / `kokoro` fall back to `reference` when their package or
    weights are absent. `onnx` stays registered as the generic ONNX-session
    scaffold (env-var driven) but is no longer auto-selected.

    * openai_http is the portable LLM path — it points at whatever local server
      is running (Ollama here; llama-server / vLLM / SGLang on Linux/CUDA).
      llama.cpp *is* reachable this way; an in-process llama-cpp-python backend
      can be added later without touching this table.

**MLX is never returned by auto-selection on any platform** (INVARIANTS #14 /
step 2 "Do not"). It is reachable only by explicitly asking for it. The backend
modules for accelerated paths import their platform-only packages lazily, so
importing this registry is safe everywhere.
"""

from __future__ import annotations

import os
import platform as _platform
from dataclasses import dataclass
from typing import Any

from engine.inference.base import BackendUnavailable, detect_accelerator, platform_tag
from engine.inference.backends.energy import EnergyVad
from engine.inference.backends.kokoro import KokoroTts
from engine.inference.backends.mlx import MlxLlm
from engine.inference.backends.onnx import OnnxAsr, OnnxTts
from engine.inference.backends.openai_http import OpenAiHttpLlm
from engine.inference.backends.reference import ReferenceAsr, ReferenceTts
from engine.inference.backends.silero import SileroVad
from engine.inference.backends.whisper_faster import FasterWhisperAsr

MODALITIES = ("llm", "asr", "tts", "vad")

# registry key -> backend class
_BACKENDS: dict[str, dict[str, type]] = {
    "llm": {"openai_http": OpenAiHttpLlm, "mlx": MlxLlm},
    "asr": {"faster_whisper": FasterWhisperAsr, "onnx": OnnxAsr, "reference": ReferenceAsr},
    "tts": {"kokoro": KokoroTts, "onnx": OnnxTts, "reference": ReferenceTts},
    "vad": {"silero": SileroVad, "energy": EnergyVad},
}

# Ordered auto-selection preference per modality. The first entry whose
# is_available() is true wins. MLX is intentionally absent.
_AUTO_ORDER: dict[str, tuple[str, ...]] = {
    "llm": ("openai_http",),
    "asr": ("faster_whisper", "onnx", "reference"),
    "tts": ("kokoro", "onnx", "reference"),
    "vad": ("silero", "energy"),
}


@dataclass(frozen=True)
class Platform:
    os: str            # "darwin" | "linux" | "windows"
    arch: str          # "arm64" | "x86_64" | ...
    accelerator: str   # "cuda" | "rocm" | "metal" | "coreml" | "directml" | "cpu"

    @property
    def tag(self) -> str:
        return f"{self.os}/{self.arch}"

    @property
    def is_jetson(self) -> bool:
        # ARM64 Linux with an NVIDIA accelerator == a Jetson-class board
        # (production target #1). Kept as a property so callers can branch
        # without re-deriving it.
        return self.os == "linux" and self.arch in {"aarch64", "arm64"} and self.accelerator in {"cuda", "rocm"}


def detect_platform() -> Platform:
    return Platform(
        os=_platform.system().lower(),
        arch=_platform.machine().lower(),
        accelerator=detect_accelerator(),
    )


def _env_override(modality: str) -> str | None:
    return os.environ.get(f"WELLSY_{modality.upper()}_BACKEND") or None


def backends_for(modality: str) -> dict[str, type]:
    if modality not in _BACKENDS:
        raise KeyError(f"unknown modality {modality!r}; expected one of {MODALITIES}")
    return dict(_BACKENDS[modality])


def available_backends(modality: str) -> list[str]:
    """Registry keys whose ``is_available()`` is true right now. This is what
    the bench harness and the conformance test parametrise over."""

    out = []
    for name, cls in _BACKENDS[modality].items():
        try:
            if cls.is_available():
                out.append(name)
        except Exception:
            pass
    return out


def select(modality: str, config: dict[str, str] | None = None) -> str:
    """Resolve a backend *name* for ``modality`` without instantiating it."""

    if modality not in _BACKENDS:
        raise KeyError(f"unknown modality {modality!r}")

    forced = _env_override(modality) or (config or {}).get(modality)
    if forced:
        if forced not in _BACKENDS[modality]:
            raise KeyError(
                f"{modality} backend {forced!r} not registered; "
                f"have {sorted(_BACKENDS[modality])}"
            )
        return forced

    for name in _AUTO_ORDER[modality]:
        cls = _BACKENDS[modality].get(name)
        if cls is None:
            continue
        try:
            if cls.is_available():
                return name
        except Exception:
            continue

    # Nothing reported available (e.g. no server running for llm). Fall back to
    # the last entry in the auto order so callers get a real object whose
    # stream() will raise BackendUnavailable with a useful message.
    return _AUTO_ORDER[modality][-1]


def get_backend(
    modality: str,
    name: str | None = None,
    *,
    config: dict[str, str] | None = None,
    **kwargs: Any,
) -> Any:
    """Instantiate a backend. ``name`` overrides everything; otherwise
    ``select()`` decides. Raises ``BackendUnavailable`` (not a bare exception)
    when the chosen backend cannot start here."""

    chosen = name or select(modality, config)
    cls = _BACKENDS[modality].get(chosen)
    if cls is None:
        raise KeyError(f"{modality} backend {chosen!r} not registered")
    try:
        return cls(**kwargs)
    except BackendUnavailable:
        raise
    except Exception as e:  # normalise construction failures
        raise BackendUnavailable(f"{modality}/{chosen} failed to start: {e}") from e


def describe() -> dict[str, Any]:
    """Snapshot for `wellsy bench` headers and debugging."""

    plat = detect_platform()
    return {
        "platform": plat.tag,
        "accelerator": plat.accelerator,
        "isJetson": plat.is_jetson,
        "selected": {m: select(m) for m in MODALITIES},
        "available": {m: available_backends(m) for m in MODALITIES},
        "registered": {m: sorted(_BACKENDS[m]) for m in MODALITIES},
    }
