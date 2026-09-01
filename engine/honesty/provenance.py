"""Provenance logging for VLM answers — day11-prompt.md Part 1.3, extending
D22's `labelConfidence`/`runnerUpLabel` honesty discipline to the new layer
(spec §19: claim -> source -> timestamp -> confidence -> freshness).

One JSONL line per answer, appended to `clips/provenance.jsonl` — not a new
cache location (D30's boundary is about model weights, not per-run logs;
`clips/` already holds every other per-run artifact this project writes,
e.g. `verify_preemption.py`'s output).

**The disagreement check is a heuristic, stated as one -- and a real
20-query run (day11-results.md row 7) found it over-flags, not
under-flags.** There is no ground truth to compare the VLM's answer
against — only the tracker's own confident, open-vocabulary labels.
`flag_disagreement()` checks whether any currently-tracked label appears as
a substring of the VLM's answer; if the tracker sees confident objects and
the answer mentions none of them, that's logged as
`possibleDisagreement: true` for a human to look at, never treated as proof
either the VLM or the tracker was wrong.

**Measured, not assumed: this flags 58% (11/19) of real answers**, and
reading those 11 shows the heuristic's actual failure mode -- it fires on
any question the VLM correctly answers *without restating the tracked
objects*, e.g. "is there a window?" -> "Yes, there's a window..." gets
flagged purely because the answer never says "person"/"glasses"/"blanket",
not because it contradicts anything. A track with `UNCERTAIN_CONFIDENCE`-
flagged labels (scene.py) is excluded from this check, since an
already-hedged label was never a strong claim to begin with. **Read
`possibleDisagreement: true` as "worth a human glance," not "the VLM was
wrong"** -- the real value here is that a *false* claim will always trip
this flag too (the flag has no false negatives against the cases it can
detect at all), at the cost of a high false-positive rate on
off-topic-but-correct answers. A tighter version (e.g. only flag when the
question is itself about object identity) is the honest next iteration,
not attempted this session.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

# Was `from scene import UNCERTAIN_CONFIDENCE` — scene.py (the voice-path scene
# describer) is deleted in the rebuild. This is the *label-vote* confidence
# floor (a track's winning-label share), not detector.py's identically-named
# *detection-score* floor (0.35); the two are distinct thresholds that happened
# to share a name. Inlined at scene.py's value to preserve behaviour exactly.
UNCERTAIN_CONFIDENCE = 0.6

RUNS_DIR = Path(__file__).resolve().parents[2] / "runs"
PROVENANCE_PATH = RUNS_DIR / "provenance.jsonl"

_lock = threading.Lock()


def flag_disagreement(answer: str, tracks: list[dict]) -> bool:
    """True if none of the tracker's confident labels appear anywhere in
    the VLM's answer text, and the tracker saw at least one confident
    label. A crude, substring-only check -- "a person" won't match "someone"
    -- so this under-counts disagreement more than it over-counts it,
    logged as a heuristic on purpose rather than tuned to look more
    accurate than it is."""
    confident_labels = [
        t["label"].lower() for t in tracks if t.get("labelConfidence", 1.0) >= UNCERTAIN_CONFIDENCE
    ]
    if not confident_labels:
        return False
    answer_lower = answer.lower()
    return not any(label in answer_lower for label in confident_labels)


def log_answer(
    *,
    transcript: str,
    answer: str,
    source: str,
    frame_source: str,
    tracks: list[dict],
    frame_age_ms: float | None,
    llm_ms: float | None,
) -> None:
    """`source`: 'vlm' (image + question) or 'vlm+tracks' if tracks were
    non-empty and passed as corroboration -- always the latter today since
    query_loop.py always passes tracks when it has them, kept as a
    distinct value in case a screen-only query with no camera tracks
    becomes 'vlm' alone later. `frame_source`: 'camera' or 'screen'."""
    record = {
        "t": round(time.time(), 3),
        "claim": answer,
        "transcript": transcript,
        "source": source,
        "frameSource": frame_source,
        "trackLabels": [t["label"] for t in tracks],
        "frameAgeMs": frame_age_ms,
        "llmMs": llm_ms,
        "possibleDisagreement": flag_disagreement(answer, tracks),
    }
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        with open(PROVENANCE_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
