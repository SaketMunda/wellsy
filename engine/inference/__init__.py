"""WELLSY inference seam — one small streaming protocol per modality, a
runtime backend registry, an AST portability check, and the `wellsy bench`
harness. Built before any model work so "OS independent" cannot quietly become
"slow everywhere" (`.claude/rebuild/step2-backend-abstraction.md`).
"""

from engine.inference.base import (
    AsrBackend,
    BackendCapabilities,
    BackendUnavailable,
    Delta,
    Final,
    LlmBackend,
    Partial,
    PcmChunk,
    SpeechProb,
    TtsBackend,
    VadBackend,
    WEIGHTS_DIR,
    detect_accelerator,
    platform_tag,
)
from engine.inference.registry import (
    MODALITIES,
    Platform,
    available_backends,
    backends_for,
    describe,
    detect_platform,
    get_backend,
    select,
)

__all__ = [
    "AsrBackend",
    "BackendCapabilities",
    "BackendUnavailable",
    "Delta",
    "Final",
    "LlmBackend",
    "Partial",
    "PcmChunk",
    "SpeechProb",
    "TtsBackend",
    "VadBackend",
    "WEIGHTS_DIR",
    "detect_accelerator",
    "platform_tag",
    "MODALITIES",
    "Platform",
    "available_backends",
    "backends_for",
    "describe",
    "detect_platform",
    "get_backend",
    "select",
]
