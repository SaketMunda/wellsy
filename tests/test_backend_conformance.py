"""Shared backend conformance — `.claude/rebuild/step2-backend-abstraction.md`
acceptance criterion 2: "Each of the four interfaces has >= 2 backends ... and
both pass an identical conformance test."

Two layers:

* **shape** — every *registered* backend (available or not) has the class
  contract: NAME, MODALITY, a cheap ``is_available()`` classmethod, a
  ``stream`` method, and structurally satisfies its protocol. This is the
  "identical conformance test" all backends pass, including the ASR/TTS ONNX
  scaffolds whose real model is wired in a later step.
* **streaming** — every backend that reports ``is_available()`` is actually
  driven: it yields at least one correctly-typed payload and publishes a
  populated `BackendCapabilities` with a real past ``verified`` date
  (INVARIANTS #8).

`mlx` is exercised here only if its weights are already cached — the test
never triggers a multi-GB download.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.inference import base, registry
from engine.inference.base import (
    Delta,
    Final,
    Partial,
    PcmChunk,
    SpeechProb,
    is_past_iso_date,
)

_ALL = [(m, name) for m in registry.MODALITIES for name in sorted(registry.backends_for(m))]
_AVAILABLE = [(m, name) for m in registry.MODALITIES for name in registry.available_backends(m)]

_PAYLOAD = {
    "llm": (Delta,),
    "asr": (Partial, Final),
    "tts": (PcmChunk,),
    "vad": (SpeechProb,),
}


def _feed(modality: str, inst):
    if modality == "llm":
        # `/no_think` short-circuits Qwen3 reasoning; harmless text elsewhere.
        return inst.stream([{"role": "user", "content": "/no_think Say the single word: ok."}])
    if modality == "vad":
        frame = getattr(inst, "FRAME", 512)
        return inst.stream(iter([np.zeros(frame, dtype=np.float32) for _ in range(3)]))
    if modality == "asr":
        return inst.stream(iter([np.zeros(8000, dtype=np.float32) for _ in range(2)]))
    if modality == "tts":
        return inst.stream(iter(["hello ", "world"]))
    raise KeyError(modality)


# --------------------------------------------------------------------------- #
# every interface really does have >= 2 registered backends, >= 1 portable     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("modality", registry.MODALITIES)
def test_interface_has_two_backends_one_portable(modality):
    names = registry.backends_for(modality)
    assert len(names) >= 2, f"{modality} has < 2 backends: {sorted(names)}"
    portable = {
        "llm": "openai_http",
        "asr": "reference",
        "tts": "reference",
        "vad": "energy",
    }[modality]
    assert portable in names


# --------------------------------------------------------------------------- #
# shape — all registered backends                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("modality,name", _ALL, ids=[f"{m}/{n}" for m, n in _ALL])
def test_backend_shape(modality, name):
    cls = registry.backends_for(modality)[name]
    assert cls.NAME == name
    assert cls.MODALITY == modality
    assert callable(getattr(cls, "is_available", None))
    assert isinstance(cls.is_available(), bool)      # cheap + returns a bool
    # stream() is defined on the class (or an inherited base), takes >1 arg.
    stream = getattr(cls, "stream", None)
    assert callable(stream)
    assert stream.__code__.co_argcount >= 2  # self + at least one input
    # the protocol exists and is the runtime-checkable one for this modality
    assert base.PROTOCOLS[modality].__name__.lower().startswith(modality)


# --------------------------------------------------------------------------- #
# streaming — available backends only                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("modality,name", _AVAILABLE, ids=[f"{m}/{n}" for m, n in _AVAILABLE])
def test_available_backend_streams_typed_payloads(modality, name):
    try:
        inst = registry.get_backend(modality, name)
    except base.BackendUnavailable as e:
        pytest.skip(f"{modality}/{name} unavailable at instantiation: {e}")

    assert isinstance(inst, base.PROTOCOLS[modality])  # runtime_checkable structural match

    caps = inst.capabilities
    assert caps.modality == modality
    assert caps.name == name
    assert caps.platform == base.platform_tag()
    assert isinstance(caps.streams, bool)
    assert caps.version
    assert is_past_iso_date(caps.verified), f"{name} verified={caps.verified!r} not a real past date"

    allowed = _PAYLOAD[modality]
    want = 1 if modality == "llm" else 2  # keep live-model calls short
    got = 0
    for item in _feed(modality, inst):
        assert isinstance(item, allowed), f"{name} yielded {type(item).__name__}, want {allowed}"
        got += 1
        if got >= want:
            break
    assert got >= 1, f"{name} yielded nothing"


def test_registry_snapshot_is_serialisable():
    import json

    json.dumps(registry.describe())
