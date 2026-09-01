"""Voice-path configuration: wake phrases and the tunable fuzzy-match threshold.

Both are hot-reloadable (mtime-checked) so a running session picks up an edit —
the perception loop already works this way for `prompts.txt` (INVARIANTS #10:
hand-editing config changes behaviour).

`wake_phrases.txt` is the existing human-edited list. `voice.json` holds the
numeric knobs; `wellsy tune-wake` rewrites `wake_threshold` there from the
measured false-accept / false-reject curve — never a guessed value
(step 4 Deliverable 5, resolves the `TODO(step4)` left on 0.72).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
WAKE_PHRASES_PATH = _CONFIG_DIR / "wake_phrases.txt"
VOICE_JSON_PATH = _CONFIG_DIR / "voice.json"

# The old single-syllable wake word transcribed as "app"; 0.72 was tuned for it
# and is only a bootstrap default now. tune-wake replaces it against recordings.
_DEFAULT_WAKE_THRESHOLD = 0.72
_DEFAULT_WAKE_WINDOW_SECONDS = 1.6


def _read_phrases(path: Path) -> list[str]:
    if not path.exists():
        return ["wellsy", "hey wellsy"]
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s.lower())
    return out or ["wellsy", "hey wellsy"]


@dataclass
class VoiceConfig:
    wake_phrases: list[str] = field(default_factory=list)
    wake_threshold: float = _DEFAULT_WAKE_THRESHOLD
    wake_window_seconds: float = _DEFAULT_WAKE_WINDOW_SECONDS
    # mtimes captured at load, so a caller can cheaply check for a change
    _phrases_mtime: float | None = None
    _json_mtime: float | None = None

    def stale(self) -> bool:
        pm = WAKE_PHRASES_PATH.stat().st_mtime if WAKE_PHRASES_PATH.exists() else None
        jm = VOICE_JSON_PATH.stat().st_mtime if VOICE_JSON_PATH.exists() else None
        return pm != self._phrases_mtime or jm != self._json_mtime


def load_voice_config() -> VoiceConfig:
    cfg = VoiceConfig()
    cfg.wake_phrases = _read_phrases(WAKE_PHRASES_PATH)

    data: dict = {}
    if VOICE_JSON_PATH.exists():
        try:
            data = json.loads(VOICE_JSON_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    cfg.wake_threshold = float(
        os.environ.get("WELLSY_WAKE_THRESHOLD", data.get("wake_threshold", _DEFAULT_WAKE_THRESHOLD))
    )
    cfg.wake_window_seconds = float(
        data.get("wake_window_seconds", _DEFAULT_WAKE_WINDOW_SECONDS)
    )

    cfg._phrases_mtime = WAKE_PHRASES_PATH.stat().st_mtime if WAKE_PHRASES_PATH.exists() else None
    cfg._json_mtime = VOICE_JSON_PATH.stat().st_mtime if VOICE_JSON_PATH.exists() else None
    return cfg


def save_wake_threshold(value: float, *, provenance: dict | None = None) -> None:
    """Persist a tuned threshold to voice.json, preserving other keys."""
    data: dict = {}
    if VOICE_JSON_PATH.exists():
        try:
            data = json.loads(VOICE_JSON_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data["wake_threshold"] = round(float(value), 4)
    if provenance:
        data["wake_threshold_provenance"] = provenance
    VOICE_JSON_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
