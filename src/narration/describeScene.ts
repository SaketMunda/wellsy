import type { Detection, SceneState } from '../vision/types';

/** Irregular plurals we actually hit in the COCO label set. */
const PLURALS: Record<string, string> = {
  person: 'people',
  mouse: 'mice',
  knife: 'knives',
  sandwich: 'sandwiches',
  couch: 'couches',
  bench: 'benches',
  scissors: 'scissors',
  skis: 'skis',
  broccoli: 'broccoli',
};

function plural(label: string, n: number): string {
  if (n === 1) return label;
  return PLURALS[label] ?? `${label}s`;
}

/** Collapse a detection list into a label -> count map. */
export function toSceneState(detections: Detection[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const d of detections) counts[d.label] = (counts[d.label] ?? 0) + 1;
  return counts;
}

/** True when two scenes are meaningfully the same (same labels, same counts). */
export function sameScene(a: Record<string, number>, b: Record<string, number>): boolean {
  const ka = Object.keys(a);
  const kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  return ka.every((k) => a[k] === b[k]);
}

export function diffScene(
  prev: Record<string, number>,
  next: Record<string, number>,
): SceneState {
  const entered = Object.keys(next).filter((k) => !prev[k]);
  const exited = Object.keys(prev).filter((k) => !next[k]);
  return { counts: next, entered, exited };
}

function list(items: string[]): string {
  if (items.length === 0) return '';
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(', ')}, and ${items[items.length - 1]}`;
}

/**
 * Turns a scene diff into one short spoken line.
 *
 * Prefers the *change* ("a laptop just entered view") over a full re-read of
 * the scene, because re-reading the whole list every few seconds is what makes
 * narration feel robotic. Falls back to a full description on first sight.
 */
export function describeScene(scene: SceneState, isFirst: boolean): string | null {
  const labels = Object.keys(scene.counts);

  if (labels.length === 0) {
    return scene.exited.length > 0 ? 'View is clear.' : null;
  }

  const phrase = (k: string) => `${scene.counts[k]} ${plural(k, scene.counts[k])}`;

  if (isFirst) {
    return `I can see ${list(labels.map(phrase))}.`;
  }

  const parts: string[] = [];
  if (scene.entered.length > 0) {
    parts.push(`${list(scene.entered.map(phrase))} in view`);
  }
  if (scene.exited.length > 0) {
    parts.push(`${list(scene.exited)} gone`);
  }

  if (parts.length === 0) {
    // Counts shifted but the cast is the same — e.g. one more person walked in.
    return `Now ${list(labels.map(phrase))}.`;
  }
  return `${parts.join('. ')}.`;
}
