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

# Open-air audio (step 4c). Half-duplex gate default ON — it is what the
# pre-rebuild build did and it makes laptop speakers usable without AEC. The
# self-transcript reject layer is cheap and always on.
_DEFAULT_HALF_DUPLEX = True
_DEFAULT_HALF_DUPLEX_TAIL_MS = 400
_DEFAULT_BARGE_IN_MODE = "mute"          # "mute" | "wake_gated" | "full"
_DEFAULT_SELF_ECHO_REJECT = True
_DEFAULT_SELF_ECHO_THRESHOLD = 0.8
_DEFAULT_SELF_ECHO_TTL_S = 12.0


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


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
    # step 4c — open-air audio
    half_duplex: bool = _DEFAULT_HALF_DUPLEX
    half_duplex_tail_ms: int = _DEFAULT_HALF_DUPLEX_TAIL_MS
    barge_in_mode: str = _DEFAULT_BARGE_IN_MODE
    self_echo_reject: bool = _DEFAULT_SELF_ECHO_REJECT
    self_echo_threshold: float = _DEFAULT_SELF_ECHO_THRESHOLD
    self_echo_ttl_s: float = _DEFAULT_SELF_ECHO_TTL_S
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

    cfg.half_duplex = _env_bool(
        "WELLSY_HALF_DUPLEX", bool(data.get("half_duplex", _DEFAULT_HALF_DUPLEX))
    )
    cfg.half_duplex_tail_ms = int(
        os.environ.get(
            "WELLSY_HALF_DUPLEX_TAIL_MS",
            data.get("half_duplex_tail_ms", _DEFAULT_HALF_DUPLEX_TAIL_MS),
        )
    )
    cfg.barge_in_mode = os.environ.get(
        "WELLSY_BARGE_IN_MODE", data.get("barge_in_mode", _DEFAULT_BARGE_IN_MODE)
    )
    cfg.self_echo_reject = _env_bool(
        "WELLSY_SELF_ECHO_REJECT",
        bool(data.get("self_echo_reject", _DEFAULT_SELF_ECHO_REJECT)),
    )
    cfg.self_echo_threshold = float(
        os.environ.get(
            "WELLSY_SELF_ECHO_THRESHOLD",
            data.get("self_echo_threshold", _DEFAULT_SELF_ECHO_THRESHOLD),
        )
    )
    cfg.self_echo_ttl_s = float(
        data.get("self_echo_ttl_s", _DEFAULT_SELF_ECHO_TTL_S)
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
