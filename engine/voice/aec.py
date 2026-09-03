"""Acoustic echo cancellation — the real fix that buys back true full-duplex
barge-in (step 4c Deliverable 4).

We have the reference signal: what was sent to the speaker. An adaptive filter
estimates the room's echo path and subtracts the predicted echo from the mic
capture, with residual-echo suppression and double-talk detection on top (the
filter must freeze adaptation during double-talk or it diverges).

This module is the **portable interface**. The engine ships on macOS, Linux and
Windows from one codebase (INVARIANTS #14), and the robot is Linux/ARM64
(D51) — so the portable WebRTC path is the one that must exist; a platform AEC
(macOS `AUVoiceProcessingIO`) is legitimate only as a swappable backend behind
this interface.

Status (2026-09-02): **not wired into the live transport yet.** Integrating it
means routing `transport.output()`'s render stream into the canceller as the
far-end reference, sample-aligned with the mic capture, ahead of the VAD. That
needs a live session to measure ERLE and to confirm no self-transcript is
produced (INVARIANTS #15 — a library's own "it's cancelling" is not evidence).
Until then `engine/voice/duplex.py` carries open-air on the half-duplex gate.

--------------------------------------------------------------------------- #
Library survey (INVARIANTS #8 — verified 2026-09-02, record what was rejected)
--------------------------------------------------------------------------- #

* ``webrtc-audio-processing`` (xiongyihui) — **REJECTED.** Last PyPI release
  0.1.3, 2018-07-17. Dead since 2018, exactly as INVARIANTS #8 flags. No
  wheels for current Python / aarch64.
* ``aec-audio-processing`` (1.0.1, 2025-09-01) — **REJECTED for the core.**
  Wheels are Windows-x86_64 only; no Linux, no macOS, no aarch64. Cannot run
  on the robot or the dev box.
* ``pywebrtc-audio`` (strands-labs, 0.1.0, 2026-05-19, Apache-2.0) —
  **candidate.** Wraps the same WebRTC APM (AEC3 + NS + AGC + VAD) that ships
  in Chrome. Pre-built wheels for cp310-cp314 across manylinux/musllinux
  x86_64 + aarch64, macOS x86_64 + arm64, win_amd64 — covers the M-series dev
  box and a Jetson Orin. `EchoCanceller`/`AudioProcessor` take a near (mic) and
  far (speaker reference) stream. Caveats: v0.1.0, a young 2-commit repo — pin
  the exact version, keep `NullEchoCanceller` as the tested fallback, and do
  not add it to `pyproject.toml` until the live ERLE run proves it earns its
  place.
* macOS ``AUVoiceProcessingIO`` / `AVAudioEngine.voiceProcessingEnabled` — the
  system AEC, and a legitimate *backend* (`CoreAudioEchoCanceller`, TODO) so
  long as it stays behind this interface and the portable WebRTC path remains
  the default. Banned as an *interface* by INVARIANTS #14, same as
  ScreenCaptureKit.

--------------------------------------------------------------------------- #
"""

from __future__ import annotations

import math
from typing import Protocol, runtime_checkable

import numpy as np

FRAME_MS = 10  # WebRTC APM processes fixed 10 ms frames


@runtime_checkable
class EchoCanceller(Protocol):
    """Portable AEC seam. All PCM is int16 mono at `sample_rate`."""

    sample_rate: int

    def analyze_render(self, far_pcm: np.ndarray) -> None:
        """Feed the far-end reference (what was sent to the speaker)."""

    def process_capture(self, near_pcm: np.ndarray) -> np.ndarray:
        """Return the mic capture with the estimated echo removed."""

    def close(self) -> None:  # pragma: no cover - trivial
        ...


class NullEchoCanceller:
    """Portable fallback: passes the capture through untouched. Tested on every
    platform so a component with no AEC still has a defined behaviour
    (INVARIANTS #14). Open-air correctness in this mode rests entirely on the
    half-duplex gate + self-echo reject in `engine/voice/duplex.py`."""

    def __init__(self, *, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate

    def analyze_render(self, far_pcm: np.ndarray) -> None:  # noqa: D401
        return None

    def process_capture(self, near_pcm: np.ndarray) -> np.ndarray:
        return near_pcm

    def close(self) -> None:
        return None


class WebRtcEchoCanceller:
    """WebRTC APM (AEC3) backend via ``pywebrtc-audio``. Import is lazy and
    guarded — the dependency is intentionally *not* in `pyproject.toml` until a
    live ERLE measurement justifies it (see module docstring)."""

    def __init__(self, *, sample_rate: int = 16000) -> None:
        try:
            import pywebrtc_audio  # type: ignore
        except ImportError as e:  # pragma: no cover - depends on optional dep
            raise RuntimeError(
                "pywebrtc-audio is not installed. It is a deliberately optional "
                "dependency (INVARIANTS #8 / #15): pin and install it only once "
                "the live ERLE run in step 4c proves it. Until then use "
                "NullEchoCanceller + the half-duplex gate."
            ) from e

        self.sample_rate = sample_rate
        self._apm = pywebrtc_audio.AudioProcessor(
            sample_rate=sample_rate,
            channels=1,
            echo_cancellation=True,
            noise_suppression=True,
            auto_gain_control=False,   # a small speaker driven loud clips; keep gain linear
        )

    def analyze_render(self, far_pcm: np.ndarray) -> None:
        self._apm.process_reverse_stream(_as_i16(far_pcm).tobytes())

    def process_capture(self, near_pcm: np.ndarray) -> np.ndarray:
        out = self._apm.process_stream(_as_i16(near_pcm).tobytes())
        return np.frombuffer(out, dtype=np.int16)

    def close(self) -> None:  # pragma: no cover - trivial
        closer = getattr(self._apm, "close", None)
        if closer:
            closer()


def get_echo_canceller(*, sample_rate: int = 16000, backend: str | None = None) -> EchoCanceller:
    """Select an AEC backend. ``backend="webrtc"`` forces the WebRTC APM;
    ``"null"`` (the default until integration is proven) forces passthrough;
    ``None`` today resolves to ``"null"``."""
    backend = (backend or "null").lower()
    if backend in ("null", "none", "off"):
        return NullEchoCanceller(sample_rate=sample_rate)
    if backend in ("webrtc", "aec3", "pywebrtc"):
        return WebRtcEchoCanceller(sample_rate=sample_rate)
    raise ValueError(f"unknown AEC backend {backend!r}")


# --------------------------------------------------------------------------- #
# measurement                                                                  #
# --------------------------------------------------------------------------- #


def _as_i16(pcm: np.ndarray) -> np.ndarray:
    if pcm.dtype == np.int16:
        return pcm
    return (np.clip(pcm, -1.0, 1.0) * 32767.0).astype(np.int16)


def erle_db(echo_before: np.ndarray, echo_after: np.ndarray) -> float:
    """Echo Return Loss Enhancement, in dB: 10·log10(E[before²] / E[after²]).

    Measured on echo-only segments (bot speaking, user silent). Higher is
    better; WebRTC AEC3 on aligned hardware clears ~25-40 dB. This is the
    number step 4c Deliverable 4 must report from a live run, alongside a
    session where a long answer produces no transcript of the bot's own words.
    """
    before = np.asarray(echo_before, dtype=np.float64)
    after = np.asarray(echo_after, dtype=np.float64)
    p_before = float(np.mean(before**2)) + 1e-12
    p_after = float(np.mean(after**2)) + 1e-12
    return 10.0 * math.log10(p_before / p_after)
