"""Step 4c Deliverable 4 — the portable AEC seam.

The real acoustic cancellation is not wired into the live transport yet (it
needs a live ERLE run to justify adopting `pywebrtc-audio` — INVARIANTS #15).
What is testable now: the seam's contract, the null fallback, backend
selection, and the ERLE metric.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.voice.aec import (
    EchoCanceller,
    NullEchoCanceller,
    erle_db,
    get_echo_canceller,
)


def test_null_canceller_is_passthrough_and_satisfies_the_protocol():
    aec = NullEchoCanceller(sample_rate=16000)
    assert isinstance(aec, EchoCanceller)
    near = (np.random.rand(320) * 2 - 1).astype(np.float32)
    aec.analyze_render(near)
    out = aec.process_capture(near)
    assert np.array_equal(out, near)
    aec.close()


def test_get_echo_canceller_defaults_to_null():
    assert isinstance(get_echo_canceller(), NullEchoCanceller)
    assert isinstance(get_echo_canceller(backend="off"), NullEchoCanceller)
    with pytest.raises(ValueError):
        get_echo_canceller(backend="bogus")


def test_webrtc_backend_fails_clean_when_dep_absent():
    pytest.importorskip  # noqa: B018 - just documenting intent
    try:
        import pywebrtc_audio  # type: ignore  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="pywebrtc-audio is not installed"):
            get_echo_canceller(backend="webrtc")


def test_erle_db_matches_the_definition():
    rng = np.random.default_rng(0)
    echo = rng.standard_normal(8000).astype(np.float32)
    # a filter that removes 90% of the echo energy -> 10 dB ERLE
    residual = echo * np.sqrt(0.1)
    assert erle_db(echo, residual) == pytest.approx(10.0, abs=0.2)
    # no change -> ~0 dB
    assert erle_db(echo, echo) == pytest.approx(0.0, abs=1e-6)
