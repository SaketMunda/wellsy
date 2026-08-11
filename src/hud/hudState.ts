/**
 * The HUD's own memory. `drawHud` is a pure painter and the tracker
 * (`src/vision/tracker.ts`) has no idea a screen exists — neither can hold
 * the state a cinematic HUD needs: how long a target has been converging on
 * lock, a fade-out for a target the tracker has already dropped, a stable
 * per-target phase so pulses don't all beat in unison, and a box that's
 * interpolated at render rate instead of holding its last position and
 * jumping. This is that memory, kept deliberately separate from the
 * tracker's — detection-side track lifetime is a vision concern with tuned
 * constants (see decisions.md D11), how long a bracket lingers on screen is
 * a rendering concern.
 *
 * Pure and testable, same shape as `tracker.ts`'s `updateTracks`:
 * `updateHudState(prev, frame, dtMs, frameW, frameH) -> next`.
 */
import type { Frame } from '../vision/types';

/** Brackets converge inward over this long on acquire. */
export const ACQUIRE_MS = 300;
/** Brackets release outward and fade over this long on loss. */
export const EXIT_MS = 300;
/** How long focus takes to transfer from one primary target to another. */
export const PRIMARY_TRANSFER_MS = 250;
/**
 * Exponential time constant for render-time box interpolation: the drawn box
 * closes ~63% of the gap to the latest tracked box every this many ms.
 * Detection delivers a new box every ~12-80ms; the display refreshes every
 * ~16ms, so without this the box holds still and then jumps. 70ms was picked
 * by feel against the tracker's own α=0.4 detection-rate smoothing — tight
 * enough to still read as "locked on", loose enough to visibly remove the
 * jump. Tradeoff, stated plainly: this adds a few frames of visual lag
 * between a real move and the box following it. See decisions.md.
 */
export const BOX_LERP_TAU_MS = 70;

export interface TargetState {
  id: number;
  label: string;
  score: number;
  /** Winning label's vote share, 0..1 (`Track.labelConfidence` — see tracker.ts). */
  labelConfidence: number;
  /** Second-place label by vote share, if the track has one. */
  runnerUpLabel: string | null;
  /** Interpolated display box, video-pixel space. */
  bbox: [number, number, number, number];
  ageMs: number;
  /** 0..ACQUIRE_MS since this id was first seen by the HUD (not the tracker). */
  acquireMs: number;
  /** True once the tracker has dropped this id; it's fading out, not gone yet. */
  exiting: boolean;
  /** 0..EXIT_MS since the tracker dropped this id. */
  exitMs: number;
  /** Stable per-target phase offset (radians), so pulses/rotation desync. */
  phase: number;
  /** 0..1, eased toward 1 while primary and 0 while not — drives focus transfer. */
  primaryProgress: number;
}

export interface HudState {
  targets: Map<number, TargetState>;
  primaryId: number | null;
}

export const EMPTY_HUD_STATE: HudState = { targets: new Map(), primaryId: null };

function lerpBox(
  prev: [number, number, number, number],
  next: [number, number, number, number],
  factor: number,
): [number, number, number, number] {
  return [
    prev[0] + (next[0] - prev[0]) * factor,
    prev[1] + (next[1] - prev[1]) * factor,
    prev[2] + (next[2] - prev[2]) * factor,
    prev[3] + (next[3] - prev[3]) * factor,
  ];
}

/** Linear ease toward `target`, `durationMs` to cross the full 0..1 range. */
function ease(current: number, target: number, dtMs: number, durationMs: number): number {
  const step = dtMs / durationMs;
  return target > current ? Math.min(target, current + step) : Math.max(target, current - step);
}

/**
 * Golden-angle spacing gives every track id a stable, well-distributed phase
 * without per-target randomness or a shared clock — the thing that would
 * make every pulse/rotation beat in unison and read as a screensaver.
 */
function phaseFor(id: number): number {
  return (id * 2.399963) % (Math.PI * 2);
}

/** 1 at frame center, falling off to 0 at the frame's corners. */
function centrality(bbox: [number, number, number, number], frameW: number, frameH: number): number {
  if (frameW <= 0 || frameH <= 0) return 1;
  const cx = bbox[0] + bbox[2] / 2;
  const cy = bbox[1] + bbox[3] / 2;
  const halfDiag = Math.hypot(frameW, frameH) / 2;
  if (halfDiag <= 0) return 1;
  const dist = Math.hypot(cx - frameW / 2, cy - frameH / 2);
  return Math.max(0, 1 - dist / halfDiag);
}

export function updateHudState(
  prev: HudState,
  frame: Frame,
  dtMs: number,
  frameW: number,
  frameH: number,
): HudState {
  const targets = new Map<number, TargetState>();
  const seen = new Set(frame.tracks.map((t) => t.id));

  for (const track of frame.tracks) {
    const existing = prev.targets.get(track.id);
    const lerpFactor = 1 - Math.exp(-dtMs / BOX_LERP_TAU_MS);
    targets.set(track.id, {
      id: track.id,
      label: track.label,
      score: track.score,
      labelConfidence: track.labelConfidence,
      runnerUpLabel: track.runnerUpLabel,
      bbox: existing ? lerpBox(existing.bbox, track.bbox, lerpFactor) : track.bbox,
      ageMs: track.ageMs,
      acquireMs: Math.min(ACQUIRE_MS, (existing?.acquireMs ?? 0) + dtMs),
      exiting: false,
      exitMs: 0,
      phase: existing?.phase ?? phaseFor(track.id),
      primaryProgress: existing?.primaryProgress ?? 0,
    });
  }

  // Targets the tracker has already dropped: keep fading them for EXIT_MS,
  // then release. This is memory the tracker itself deliberately doesn't keep.
  for (const [id, existing] of prev.targets) {
    if (seen.has(id)) continue;
    const exitMs = existing.exitMs + dtMs;
    if (exitMs >= EXIT_MS) continue;
    targets.set(id, { ...existing, exiting: true, exitMs });
  }

  let primaryId: number | null = null;
  let bestScore = -Infinity;
  for (const t of targets.values()) {
    if (t.exiting) continue;
    const area = t.bbox[2] * t.bbox[3];
    const score = area * centrality(t.bbox, frameW, frameH);
    if (score > bestScore) {
      bestScore = score;
      primaryId = t.id;
    }
  }

  for (const [id, t] of targets) {
    const goal = id === primaryId ? 1 : 0;
    targets.set(id, { ...t, primaryProgress: ease(t.primaryProgress, goal, dtMs, PRIMARY_TRANSFER_MS) });
  }

  return { targets, primaryId };
}
