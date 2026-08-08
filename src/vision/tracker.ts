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
/** How much a matched box moves toward its new position each update. Lower = smoother, laggier. */
const SMOOTHING_ALPHA = 0.4;
/** Frames a track survives with no matching detection before it's dropped. */
const MAX_MISSED_FRAMES = 20;

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

  // Greedy best-match-first pairing, restricted to same-label pairs. A pair is
  // eligible via IoU *or* center closeness — see the two constants above for why.
  const candidates: { track: Track; detection: Detection; score: number }[] = [];
  for (const track of previousTracks) {
    for (const detection of detections) {
      if (track.label !== detection.label) continue;
      const overlap = iou(track.bbox, detection.bbox);
      const centered = centerDistanceRatio(track.bbox, detection.bbox) <= CENTER_MATCH_RATIO;
      if (overlap >= IOU_MATCH_THRESHOLD || centered) {
        candidates.push({ track, detection, score: matchScore(track.bbox, detection.bbox) });
      }
    }
  }
  candidates.sort((a, b) => b.score - a.score);

  const matched: Track[] = [];
  for (const { track, detection } of candidates) {
    if (!unmatchedTracks.has(track) || !unmatchedDetections.has(detection)) continue;
    unmatchedTracks.delete(track);
    unmatchedDetections.delete(detection);
    matched.push({
      id: track.id,
      label: detection.label,
      score: detection.score,
      bbox: smooth(track.bbox, detection.bbox),
      ageMs: track.ageMs + dtMs,
      missedFrames: 0,
    });
  }

  const missed: Track[] = [];
  for (const track of unmatchedTracks) {
    if (track.missedFrames + 1 > MAX_MISSED_FRAMES) continue;
    missed.push({ ...track, ageMs: track.ageMs + dtMs, missedFrames: track.missedFrames + 1 });
  }

  const created: Track[] = [];
  for (const detection of unmatchedDetections) {
    created.push({ ...detection, id: nextId(), ageMs: 0, missedFrames: 0 });
  }

  return [...matched, ...missed, ...created];
}
