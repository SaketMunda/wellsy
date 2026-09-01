"""WELLSY streaming voice path (step 4).

Pipecat is the streaming frame pipeline, semantic turn detection (Smart Turn v3,
ONNX, bundled) and barge-in. Nothing here waits for a complete buffer: audio
streams into ASR, ASR results into the LLM, LLM tokens are sentence-chunked into
TTS, TTS PCM streams to the device — every stage overlapping. This replaces the
777-line hand-rolled `query_loop.py` the rebuild exists to delete.

Layout:

    config.py      wake phrases + tunable thresholds, hot-reloaded
    intent_gate.py IntentGate — parse_intent BEFORE any model (INVARIANTS #3)
    wake.py        WakeGate — asleep/awake gate, fuzzy wake-phrase match
    adapters.py    Pipecat services wrapping the step-2 inference seam
    pipeline.py    build + run the Pipecat pipeline
    metrics.py     first-PCM-sample timing, turn timing, barge-in latency
    run.py         `wellsy voice`, `wellsy record-wake`, `wellsy tune-wake`
"""

import os as _os
from pathlib import Path as _Path


def _bootstrap_env() -> None:
    """Point NLTK at the pre-fetched punkt_tab and fix macOS SSL cert lookup so
    Pipecat's sentence tokenizer and any first-run model fetch work offline /
    behind a corporate cert store. Both live under the sanctioned cache dir
    (~/.cache/wellsy), never in the repo (INVARIANTS #1)."""
    cache = _Path(_os.environ.get("WELLSY_WEIGHTS_DIR", _Path.home() / ".cache" / "wellsy" / "weights"))
    nltk_dir = cache.parent / "nltk_data"
    if nltk_dir.exists():
        existing = _os.environ.get("NLTK_DATA", "")
        parts = [p for p in existing.split(_os.pathsep) if p]
        if str(nltk_dir) not in parts:
            _os.environ["NLTK_DATA"] = _os.pathsep.join([str(nltk_dir), *parts])
    if "SSL_CERT_FILE" not in _os.environ:
        try:
            import certifi

            _os.environ["SSL_CERT_FILE"] = certifi.where()
        except Exception:
            pass


_bootstrap_env()

from engine.voice.config import VoiceConfig, load_voice_config

__all__ = ["VoiceConfig", "load_voice_config"]
