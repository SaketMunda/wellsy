"""Local STT for the engine's T3 loop and the wake-phrase matcher —
`useful-moonshine-onnx`, the `moonshine/tiny` checkpoint. Same reasoning as
decisions.md D24's Whisper choice for the browser build: push-to-talk/wake
commands are short, English, few-word — the smallest model that clears the
bar, per the house rule. Moved to Python because T3 lives in the engine
(decisions.md D37) and audio has to be native.

Model weights cache is redirected to the single recorded cache exception
(`~/.cache/yap-engine/weights`, D30) via `HF_HOME`, set in main.py before
this module is imported — do not add a second cache location.
"""

from __future__ import annotations

import numpy as np
from moonshine_onnx import MoonshineOnnxModel, load_tokenizer

MODEL_NAME = "moonshine/base"
# Switched from moonshine/tiny after real-usage feedback: tiny mis-heard
# "hey yap" as "app" consistently and garbled full questions badly enough
# to misroute intent (decisions.md D39 amendment). base costs more compute
# per call (still ~15-20ms on a silent 3s clip, warm) but is the smallest
# step up in accuracy Moonshine ships, per the same house rule that picked
# tiny in the first place — smallest model that clears the bar, re-checked
# once tiny turned out not to.


# Real bug, found from a live report: "what do you see" transcribed as "or
# do you see", "hello, yap" transcribed as "yeah, yeah" -- whole syllables
# dropped or replaced, not just a wake-phrase-matching miss. Cross-checked
# against real wake_debug/*.wav evidence from the same session (vad.py's
# MIN_ABSOLUTE_SPEECH_RMS comment): even near-silent noise blips had
# non-trivial RMS relative to what real speech was apparently producing --
# consistent with this user's actual mic input running quiet overall, not
# just occasional silence. A small STT model fed a low-amplitude signal has
# less headroom above quantization/self-noise and guesses at whatever
# "sounds close," which is exactly this failure shape (dropped words,
# plausible-sounding wrong words) rather than empty output. Gain-normalize
# every clip up toward full scale before transcribing, capped so it can't
# amplify true silence/noise into full-scale garbage.
TARGET_PEAK = 0.9
MAX_GAIN = 20.0


def _normalize_gain(audio: np.ndarray) -> np.ndarray:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak < 1e-4:
        return audio  # near-silence -- nothing real to boost, avoid amplifying noise floor into noise
    gain = min(TARGET_PEAK / peak, MAX_GAIN)
    return audio * gain


class Stt:
    """Loads once, reused across calls — `moonshine_onnx.transcribe()`
    reloads the model from disk every call (measured ~1.35-1.4s per call
    even warm, see day10-results.md), which is not acceptable inside a
    latency-critical query loop. This class holds the loaded
    `MoonshineOnnxModel` + tokenizer in memory instead.

    `model_name`: `moonshine/tiny` (fast, used for wake-phrase spotting,
    where a rough match is enough) or `moonshine/base` (slower, more
    accurate — used for the actual command transcription after Day 10's
    real-usage feedback found `tiny` mis-hearing full questions badly
    enough to misroute intent, e.g. "do you see a cellphone" garbling into
    something that matched `describe_scene` instead of `query_object` —
    see decisions.md D39's amendment)."""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self._model = MoonshineOnnxModel(model_name=model_name)
        self._tokenizer = load_tokenizer()

    def transcribe(self, audio: np.ndarray) -> str:
        """`audio`: float32 mono, 16kHz, arbitrary length."""
        audio = _normalize_gain(audio)
        if audio.ndim == 1:
            audio = audio[None, ...]
        tokens = self._model.generate(audio)
        text = self._tokenizer.decode(tokens[0], skip_special_tokens=True)
        return text.strip()
