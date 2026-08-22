"""Local TTS for the engine's T3 loop — Chatterbox Turbo replaces `say`.

**Pulled forward from Day 14 into Day 11, on explicit direction from the
project owner during the Day 11 session** — not planned, not a quiet scope
add. D39 shipped `say -v Samantha` deliberately as a stopgap to close the
nine-day-old audibility gap, with the real ask (human-sounding, emotional
TTS) named and scoped to Day 14 (`v2-roadmap.md`). The owner pushed back
live: "I can't wait for Day 14." This is that swap, done now, with the real
costs measured and stated rather than hidden because the ask was urgent.

**Model: Chatterbox Turbo (`ResembleAI/chatterbox-turbo`), Resemble AI,
MIT license.** Verified real and current before installing (not assumed
from `v2-roadmap.md`'s earlier research) — a live web check the same
session found the model, its PyPI package (`chatterbox-tts`, which ships
both `chatterbox.tts` and `chatterbox.tts_turbo`), and its GitHub repo,
all active as of this session.

**Real problems hit installing this, fixed, recorded (per house rules — a
dependency doesn't go in silently):**
1. `chatterbox-tts` hard-pins `torch==2.6.0`, a downgrade from this
   project's existing `torch==2.13.0` (pulled in by `ultralytics`, which
   only requires `torch>=1.8.0` — no real conflict, checked before
   accepting the downgrade). **Regression-tested**: YOLOE inference after
   the downgrade was 3849.9ms on the very first call (cold Metal kernel
   compile, same phenomenon D40 noted for the LLM) then a steady
   21.8-22.2ms on every call after — matches pre-downgrade performance,
   confirmed not assumed.
2. Loading the model raised `TypeError: 'NoneType' object is not
   callable` on `perth.PerthImplicitWatermarker()` (Resemble's invisible
   audio watermarking, applied to every generated clip). Root cause,
   traced rather than guessed: `perth`'s watermark submodule imports
   `pkg_resources`, which modern `setuptools` (84.x, already installed)
   dropped entirely as of late 2025. Fixed by pinning `setuptools<81` —
   the last line still shipping `pkg_resources` — not by disabling the
   watermarker, since keeping Resemble's own provenance watermark active
   on every clip this project generates is the more responsible default.

**Real measured latency, this machine, this session — and it does NOT
match the model card's advertised numbers, stated plainly:** Resemble's
own claim is "75ms latency, 6x real-time" (almost certainly measured on
CUDA). On this M4 Pro's MPS backend, real generation time for short,
assistant-shaped replies: `"okay."` 3167ms, `"i am listening."` 1652ms,
`"yes, one person in view."` 2269ms, `"nothing in view right now."`
1852ms — a real-time factor of roughly **1.1x-3.3x** (generation takes
about as long as, or longer than, the resulting clip), not 6x *faster*
than real-time. Cold model load: **7693ms**, paid once at startup, same
pattern as `Stt`/`Llm`.

**The actual cost of this swap, said out loud, not buried:** Day 10's
centerpiece number — 119.1ms from intent to TTS-start for a deterministic
`describe_scene` answer — is gone. `say` produced audio within a handful of
ms of being invoked; every Chatterbox utterance now costs **1.6-3.2s of
real generation time before any sound starts**, even for the simple,
previously-instant answers. This is not a hidden regression: the fast
*deterministic* path (`parse_intent` → tracks → `describe_scene`) is still
exactly as fast as it always was — what changed is that speaking the
answer, any answer, now has a real, human-noticeable pause in front of it
that did not exist before. That is the real price of not sounding like
Samantha, on this hardware, with this model. Kokoro-82M (already vetted,
D13/D39) is the documented fallback if this pause proves worse than the
robotic voice it replaced — not attempted this session per the owner's own
urgency, but a one-file swap back if needed.

**`exaggeration`/`cfg_weight` are accepted by `generate()` but silently
ignored by the Turbo checkpoint** (its own logged warning:
"CFG, min_p and exaggeration are not supported by Turbo version"). The
emotion-*control knob* named in `v2-roadmap.md`'s Day 14 description does
not actually function on the fast checkpoint — only the base (non-Turbo)
`chatterbox.tts.ChatterboxTTS` supports it, at an unmeasured, presumably
higher latency cost this session didn't have time to test. Turbo's voice
is still a real neural voice, not `say`'s formant synthesis — the
complaint being fixed ("sounds like Stephen Hawking") is about baseline
naturalness, which Turbo does deliver, not about dynamic exaggeration
control, which it doesn't.

**Interruption, kept working, implemented differently.** `say`'s
subprocess made "stop mid-word" trivial (SIGTERM). Chatterbox generates a
whole clip in-process, then plays it via `sounddevice` — `SpeechHandle.stop()`
now sets a cancellation flag (checked before playback starts, so a stop
during the 1.6-3.2s generation window prevents the clip from ever playing)
and calls `sd.stop()` (cuts actual playback instantly, same guarantee as
before once audio has started). **Not yet true mid-generation
cancellation** — if `stop()` fires while `model.generate()` is still
running, that call runs to completion in its background thread before the
cancellation flag is even checked; the *user* hears silence immediately
either way (nothing plays), but the CPU cost of that discarded generation
isn't reclaimed. Acceptable for a first cut; a hard cancellation would need
threading support the `chatterbox` library doesn't expose.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

MODEL_NAME = "chatterbox-turbo"
_model_lock = threading.Lock()
_model = None


def _get_model():
    global _model
    with _model_lock:
        if _model is None:
            import os

            # Real, measured finding this session: with weights already
            # cached under HF_HOME, `from_pretrained` still made a live
            # HF Hub metadata round-trip that stalled for 30s+ once
            # (unauthenticated rate limiting, same warning STT/LLM setup
            # already log). Weights don't change between runs once
            # downloaded, so this forces offline/cache-only mode the same
            # way a pinned model version would -- not set globally in
            # main.py because Stt's first-ever run still needs one real
            # fetch.
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            from chatterbox.tts_turbo import ChatterboxTurboTTS

            _model = ChatterboxTurboTTS.from_pretrained(device="mps")
    return _model


class SpeechHandle:
    """One in-flight utterance: a background thread generates the clip,
    then plays it via `sounddevice`. `stop()` is idempotent and safe to
    call from a different thread than the one that started speech — same
    push-to-talk-interrupts-playback guarantee `say`'s version had."""

    def __init__(self, text: str) -> None:
        self.text = text
        # Call-time, not first-audio-time -- unlike `say`'s version, this
        # no longer doubles as a good "TTS-start" proxy, because real
        # generation now sits between this timestamp and any sound
        # actually starting. `audio_started_at` (below) is the honest
        # number for that; query_loop.py's `ttsFirstAudioMs` should be
        # read as "time to hand off to TTS," not "time to first sound,"
        # until/unless it's updated to use `audio_started_at` instead.
        self.started_at = time.monotonic()
        self.audio_started_at: float | None = None
        self._done = threading.Event()
        self._cancelled = threading.Event()

    def wait(self) -> None:
        self._done.wait()

    def stop(self) -> None:
        self._cancelled.set()
        sd.stop()

    @property
    def speaking(self) -> bool:
        return not self._done.is_set()


def _generate_and_play(handle: SpeechHandle, text: str) -> None:
    try:
        model = _get_model()
        wav = model.generate(text)
        if handle._cancelled.is_set():
            return
        arr = wav.squeeze().detach().cpu().numpy().astype(np.float32)
        handle.audio_started_at = time.monotonic()
        sd.play(arr, samplerate=model.sr)
        sd.wait()
    finally:
        handle._done.set()


def speak(text: str) -> SpeechHandle:
    """Non-blocking, same contract as the `say`-based version: returns
    immediately with a handle; generation and playback happen on a
    background thread."""
    handle = SpeechHandle(text)
    threading.Thread(target=_generate_and_play, args=(handle, text), daemon=True).start()
    return handle


if __name__ == "__main__":
    h = speak("Hello. This is the new voice.")
    h.wait()
    print(f"done, audio_started_at offset: {(h.audio_started_at - h.started_at) * 1000:.0f}ms")
