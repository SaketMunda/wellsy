"""Track ids via ByteTrack (supervision) — replaces the hand-rolled IoU
tracker's job (decisions.md D11/D21/D27; see D31 for why each of those was
right for the *old* detector and is superseded now, not just deleted).

Emits dicts shaped close to src/vision/types.ts's `Track` so Day 9's bridge
is plumbing, not translation: id, label, score, bbox, ageMs, missedFrames,
labelConfidence, runnerUpLabel, labelVotes.

`supervision`'s public `sv.ByteTrack` is soft-deprecated in 0.30 in favor of
a name not yet published (deprecation warning names no replacement) — the
underlying implementation this imports directly is the same code either
name points at. Revisit when supervision ships the replacement class.
"""

from __future__ import annotations

import time
import warnings

import numpy as np

from supervision.tracker.byte_tracker.core import ByteTrack

import supervision as sv

# How many recent label observations a track remembers for its vote —
# small on purpose: an open-vocab model flickering between two prompts
# should resolve fast, not drag stale votes for minutes (D21's old window
# was tuned for a weaker, noisier 80-class model).
LABEL_VOTE_WINDOW = 15


class Tracker:
    def __init__(self, frame_rate: int = 8) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            self._bytetrack = ByteTrack(frame_rate=frame_rate)
        # id -> {"labels": deque[str], "first_seen": float}
        self._track_meta: dict[int, dict] = {}

    def update(self, detections: list[dict], now: float | None = None) -> list[dict]:
        """`detections`: list of {label, score, bbox} (detector.predict's
        output). Returns Track dicts with stable ids."""
        now = now if now is not None else time.time()
        if not detections:
            sv_dets = sv.Detections.empty()
        else:
            xyxy = np.array(
                [[b[0], b[1], b[0] + b[2], b[1] + b[3]] for b in (d["bbox"] for d in detections)],
                dtype=float,
            )
            confidence = np.array([d["score"] for d in detections], dtype=float)
            # ByteTrack needs numeric class ids for its internal matching;
            # labels ride along out-of-band since our vocabulary is
            # open-ended text, not a fixed class table.
            class_id = np.zeros(len(detections), dtype=int)
            sv_dets = sv.Detections(xyxy=xyxy, confidence=confidence, class_id=class_id)
            sv_dets.data["label"] = np.array([d["label"] for d in detections], dtype=object)

        tracked = self._bytetrack.update_with_detections(sv_dets)

        live_ids = set()
        tracks = []
        for i in range(len(tracked)):
            tid = int(tracked.tracker_id[i])
            live_ids.add(tid)
            x1, y1, x2, y2 = tracked.xyxy[i]
            label = str(tracked.data["label"][i])
            score = float(tracked.confidence[i])

            meta = self._track_meta.setdefault(tid, {"labels": [], "first_seen": now})
            meta["labels"].append(label)
            if len(meta["labels"]) > LABEL_VOTE_WINDOW:
                meta["labels"].pop(0)

            votes: dict[str, int] = {}
            for lbl in meta["labels"]:
                votes[lbl] = votes.get(lbl, 0) + 1
            ranked = sorted(votes.items(), key=lambda kv: kv[1], reverse=True)
            winning_label, winning_votes = ranked[0]
            total_votes = sum(votes.values())
            runner_up = ranked[1][0] if len(ranked) > 1 else None

            tracks.append({
                "id": tid,
                "label": winning_label,
                "score": round(score, 4),
                "bbox": [round(float(x1), 1), round(float(y1), 1), round(float(x2 - x1), 1), round(float(y2 - y1), 1)],
                "ageMs": round((now - meta["first_seen"]) * 1000, 1),
                # ByteTrack coasts lost tracks internally (up to its own
                # max-age) and only returns currently-matched ones here, so
                # a track appearing in this list has 0 frames missed by
                # definition — the old tracker's hand-rolled grace counter
                # (D11) is now the library's job, not ours.
                "missedFrames": 0,
                "labelConfidence": round(winning_votes / total_votes, 4),
                "runnerUpLabel": runner_up,
                "labelVotes": votes,
            })

        # Drop bookkeeping for ids ByteTrack has stopped returning (it
        # already decided they're gone; we just stop remembering their
        # label history so this dict doesn't grow unbounded over a long run).
        for tid in list(self._track_meta.keys()):
            if tid not in live_ids:
                del self._track_meta[tid]

        return tracks
