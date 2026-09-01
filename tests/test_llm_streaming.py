"""Streaming proof — `.claude/rebuild/step2-backend-abstraction.md` acceptance
criterion 3: "`LlmBackend.stream` demonstrably yields a first delta *before* the
full answer completes — prove it with a timestamped test, and report the gap."

The Day 11 build measured Ollama first-token at 1,693 ms against a full answer
at 2,201 ms and threw the 508 ms away because nothing consumed the stream. This
test fails if that regresses — i.e. if `stream()` only yields once everything is
ready.
"""

from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import pytest

from engine.inference import base, registry

RESULTS_DIR = Path(__file__).resolve().parents[1] / "spec" / "results"

_LLM_BACKENDS = registry.available_backends("llm")
if not _LLM_BACKENDS:
    pytest.skip(
        "no LLM backend available (start Ollama, or `uv sync --extra inference-mlx` "
        "and cache the MLX model) — streaming proof needs a live backend",
        allow_module_level=True,
    )

# `/no_think` keeps Qwen3 from spending 15-20 s on reasoning tokens before the
# first answer token — it is ignored as plain text by any non-Qwen server, so
# the test stays model-agnostic while running in a couple of seconds.
PROMPT = [
    {
        "role": "user",
        "content": "/no_think Write two sentences about the sea. Plain prose, no preamble.",
    }
]


@pytest.mark.parametrize("name", _LLM_BACKENDS)
def test_first_delta_arrives_before_completion(name, record_property):
    try:
        backend = registry.get_backend("llm", name)
    except base.BackendUnavailable as e:
        pytest.skip(f"llm/{name} unavailable: {e}")

    assert backend.capabilities.streams is True, f"{name} does not advertise streaming"

    t0 = time.monotonic()
    t_first_text: float | None = None   # first delta carrying answer text
    t_last_text: float | None = None    # last delta carrying answer text
    t_stream_end: float | None = None   # iterator exhausted
    text_deltas = 0
    chars = 0
    for d in backend.stream(PROMPT):
        now = time.monotonic()
        if d.text:
            if t_first_text is None:
                t_first_text = now
            t_last_text = now
            text_deltas += 1
            chars += len(d.text)
        t_stream_end = now

    assert t_first_text is not None, f"{name} produced no text deltas"

    # The proof: the answer was delivered in pieces over time, and the first
    # piece was in hand while the model was still producing later ones — i.e.
    # nothing waited for the whole answer before yielding. A non-streaming path
    # wrapped as a one-element iterator fails both clauses.
    assert text_deltas >= 2, (
        f"{name} yielded the whole answer in one delta — not streaming"
    )
    assert t_last_text > t_first_text, (
        f"{name} first and last text delta share a timestamp — arrived as one clump"
    )
    assert t_stream_end >= t_last_text

    ttft_ms = (t_first_text - t0) * 1000
    span_ms = (t_last_text - t_first_text) * 1000  # first answer token -> last
    line = (
        f"[streaming] {name}: first answer delta @ {ttft_ms:.0f} ms; remaining "
        f"{text_deltas - 1} of {text_deltas} deltas ({chars} chars) streamed over "
        f"the next {span_ms:.0f} ms — a non-streaming path would have withheld all "
        f"{text_deltas} until +{span_ms:.0f} ms"
    )
    print(line, file=sys.stderr)
    record_property("streaming_report", line)

    (RESULTS_DIR / f"streaming-{date.today().isoformat()}.txt").open("a").write(line + "\n")
