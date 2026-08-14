import type { Detection, Track } from './types';

/**
 * Below this IoU, boxes are treated as different objects — *unless* the
 * center-distance fallback below says otherwise. `lite_mobilenet_v2` (chosen
 * for speed, see decisions.md D2) is noisy: the box for one static, unmoving
 * object can shift several percent of its own size between two real frames
 * purely from model jitter, worse for small objects (a phone) where that
 * jitter is a bigger fraction of the box. A strict IoU-only match drops the
 * threshold below 0.3 on a large fraction of ticks even when nothing moved,
 * which mints a brand-new track/id immediately (see the `created` loop below)
 * instead of just waiting out the grace window — that's what produced ids
 * counting into the hundreds for a motionless phone.
 */
const IOU_MATCH_THRESHOLD = 0.15;
/**
 * Fallback match when IoU is low: same label, and box centers within this
 * fraction of the boxes' average diagonal. Center distance is far less
 * sensitive to small-object jitter than IoU, where a few pixels of noise on
 * a small box can swing the ratio wildly.
 */
const CENTER_MATCH_RATIO = 0.5;
/**
 * A *different*-label pair may still match if geometric overlap is at least
 * this strong — this is what fixes the `bed` <-> `dining table` id-churn
 * (see decisions.md Day 6): the model flips its word for the same object,
 * but the box barely moves. Deliberately much stricter than the same-label
 * threshold above: a chair must never inherit a person's id off an
 * ambiguous overlap, and this high bar is what buys that.
 */
const CROSS_LABEL_IOU_THRESHOLD = 0.5;
/** How much a matched box moves toward its new position each update. Lower = smoother, laggier. */
const SMOOTHING_ALPHA = 0.4;
/** Frames a track survives with no matching detection before it's dropped. */
const MAX_MISSED_FRAMES = 20;
/**
 * Per matched frame, existing label votes decay by this factor before the new
 * detection's score is added — so a track that genuinely changes object (or a
 * reused id) can have its label overtaken instead of the first label winning
 * forever. Chosen so a confidently-flipping model (bed/dining table, roughly
 * 50/50) settles on a single winner within a couple of seconds of frames
 * rather than within a single frame (too twitchy) or never (too sticky).
 */
const VOTE_DECAY = 0.9;
/** Votes below this are pruned each update so the record doesn't grow forever. */
const VOTE_PRUNE_THRESHOLD = 0.02;

function iou(a: [number, number, number, number], b: [number, number, number, number]): number {
  const [ax, ay, aw, ah] = a;
  const [bx, by, bw, bh] = b;
  const ix = Math.max(ax, bx);
  const iy = Math.max(ay, by);
  const iw = Math.min(ax + aw, bx + bw) - ix;
  const ih = Math.min(ay + ah, by + bh) - iy;
  if (iw <= 0 || ih <= 0) return 0;
  const intersection = iw * ih;
  const union = aw * ah + bw * bh - intersection;
  return union > 0 ? intersection / union : 0;
}

/** Center distance as a fraction of the boxes' average diagonal — scale-invariant. */
function centerDistanceRatio(a: [number, number, number, number], b: [number, number, number, number]): number {
  const [ax, ay, aw, ah] = a;
  const [bx, by, bw, bh] = b;
  const dist = Math.hypot(ax + aw / 2 - (bx + bw / 2), ay + ah / 2 - (by + bh / 2));
  const avgDiag = (Math.hypot(aw, ah) + Math.hypot(bw, bh)) / 2;
  return avgDiag > 0 ? dist / avgDiag : Infinity;
}

/** Combined match quality: best of IoU and center-closeness, so either signal can carry a match. */
function matchScore(a: [number, number, number, number], b: [number, number, number, number]): number {
  return Math.max(iou(a, b), 1 - centerDistanceRatio(a, b) / CENTER_MATCH_RATIO);
}

function smooth(prev: [number, number, number, number], next: [number, number, number, number]): [number, number, number, number] {
  return [
    prev[0] + (next[0] - prev[0]) * SMOOTHING_ALPHA,
    prev[1] + (next[1] - prev[1]) * SMOOTHING_ALPHA,
    prev[2] + (next[2] - prev[2]) * SMOOTHING_ALPHA,
    prev[3] + (next[3] - prev[3]) * SMOOTHING_ALPHA,
  ];
}

/**
 * Decays every existing vote, then adds this frame's detection score to its
 * label's bucket — a rolling, recency-weighted histogram rather than a
 * simple "latest label wins" or "first label wins forever".
 */
function castVote(votes: Record<string, number>, label: string, score: number): Record<string, number> {
  const next: Record<string, number> = {};
  for (const [l, v] of Object.entries(votes)) {
    const decayed = v * VOTE_DECAY;
    if (decayed >= VOTE_PRUNE_THRESHOLD) next[l] = decayed;
  }
  next[label] = (next[label] ?? 0) + score;
  return next;
}

interface VoteResult {
  label: string;
  labelConfidence: number;
  runnerUpLabel: string | null;
}

/** Argmax over the vote histogram, plus the winner's vote share and runner-up. */
function tally(votes: Record<string, number>): VoteResult {
  const entries = Object.entries(votes).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  const [topLabel, topVotes] = entries[0];
  return {
    label: topLabel,
    labelConfidence: total > 0 ? topVotes / total : 1,
    runnerUpLabel: entries[1]?.[0] ?? null,
  };
}

/**
 * Matches this frame's detections against last frame's tracks by IoU-or-
 * center-closeness (same label required — a chair should never inherit a
 * person's id), applies exponential position smoothing to matches, ages
 * every surviving track by `dtMs`, and keeps a track alive for
 * `MAX_MISSED_FRAMES` misses before dropping it so a brief occlusion — or a
 * single noisy frame that fails to match — doesn't reset identity.
 *
 * Pure and side-effect free except for id assignment, which is deliberately
 * pushed to the caller via `nextId` (same injection pattern as
 * `generateLine.ts`'s `random`) so this stays a plain function of its inputs.
 */
export function updateTracks(
  previousTracks: Track[],
  detections: Detection[],
  dtMs: number,
  nextId: () => number,
): Track[] {
  const unmatchedDetections = new Set(detections);
  const unmatchedTracks = new Set(previousTracks);

  // Two SEPARATE passes, deliberately not one shared ranked list. Same-label
  // matching (permissive: IoU *or* center closeness, per D11) always runs
  // and consumes first — a track's own real detection, if present this
  // frame, must always win it. Cross-label matching (D21) only ever gets a
  // shot at whatever's left over *after* that: a track with no same-label
  // detection this frame, geometrically explained by a different-label
  // detection with no same-label track of its own. Putting both kinds of
  // candidate in one score-sorted list (the original D21 cut) let a big
  // track's high *raw IoU* against a nearby, genuinely different, smaller
  // object outscore and steal that object's own lower-scoring same-label
  // match — observed live as a bed track absorbing every nearby chair/mic
  // detection and everything else going silent. Two passes make that
  // structurally impossible: a detection can only be stolen cross-label if
  // its own track already failed to claim it on same-label terms alone.
  const sameLabelCandidates: { track: Track; detection: Detection; score: number }[] = [];
  for (const track of previousTracks) {
    for (const detection of detections) {
      if (track.label !== detection.label) continue;
      const overlap = iou(track.bbox, detection.bbox);
      const centered = centerDistanceRatio(track.bbox, detection.bbox) <= CENTER_MATCH_RATIO;
      if (overlap >= IOU_MATCH_THRESHOLD || centered) {
        sameLabelCandidates.push({ track, detection, score: matchScore(track.bbox, detection.bbox) });
      }
    }
  }
  sameLabelCandidates.sort((a, b) => b.score - a.score);

  const matched: Track[] = [];
  const applyMatch = (track: Track, detection: Detection) => {
    unmatchedTracks.delete(track);
    unmatchedDetections.delete(detection);
    const labelVotes = castVote(track.labelVotes, detection.label, detection.score);
    const { label, labelConfidence, runnerUpLabel } = tally(labelVotes);
    matched.push({
      id: track.id,
      label,
      score: detection.score,
      bbox: smooth(track.bbox, detection.bbox),
      ageMs: track.ageMs + dtMs,
      missedFrames: 0,
      labelVotes,
      labelConfidence,
      runnerUpLabel,
    });
  };

  for (const { track, detection } of sameLabelCandidates) {
    if (!unmatchedTracks.has(track) || !unmatchedDetections.has(detection)) continue;
    applyMatch(track, detection);
  }

  // Cross-label pass: only tracks and detections same-label matching left
  // unclaimed, only above the much stricter `CROSS_LABEL_IOU_THRESHOLD`.
  const crossLabelCandidates: { track: Track; detection: Detection; score: number }[] = [];
  for (const track of unmatchedTracks) {
    for (const detection of unmatchedDetections) {
      if (track.label === detection.label) continue;
      const overlap = iou(track.bbox, detection.bbox);
      if (overlap >= CROSS_LABEL_IOU_THRESHOLD) {
        crossLabelCandidates.push({ track, detection, score: overlap });
      }
    }
  }
  crossLabelCandidates.sort((a, b) => b.score - a.score);

  for (const { track, detection } of crossLabelCandidates) {
    if (!unmatchedTracks.has(track) || !unmatchedDetections.has(detection)) continue;
    applyMatch(track, detection);
  }

  const missed: Track[] = [];
  for (const track of unmatchedTracks) {
    if (track.missedFrames + 1 > MAX_MISSED_FRAMES) continue;
    missed.push({ ...track, ageMs: track.ageMs + dtMs, missedFrames: track.missedFrames + 1 });
  }

  const created: Track[] = [];
  for (const detection of unmatchedDetections) {
    created.push({
      ...detection,
      id: nextId(),
      ageMs: 0,
      missedFrames: 0,
      labelVotes: { [detection.label]: detection.score },
      labelConfidence: 1,
      runnerUpLabel: null,
    });
  }

  return [...matched, ...missed, ...created];
}
