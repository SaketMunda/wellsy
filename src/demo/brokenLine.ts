/**
 * The broken-mode line picker.
 *
 * Deliberately *not* the normal generator. That one is random with no-repeat
 * memory, which is right for a live toy and wrong for a shoot: take 4 must look
 * like take 1. This one walks each bank with a cursor, so the first line you
 * see after pressing a key is always the same line.
 *
 * Ordering is authored-first: `only`-matched lines come before generics, so the
 * moment `[1]` goes on and a cup becomes a toilet, the first thing the log says
 * is "a toilet appears. on the desk. bold." Every time.
 */
import type { NarrationEvent } from '../narration/events';
import {
  GHOST_TEMPLATES,
  LAG_TEMPLATES,
  MISLABEL_TEMPLATES,
  type BrokenTemplate,
} from './brokenTemplates';

export type BrokenBank = 'mislabel' | 'lag' | 'ghost';

/** Plurals for the corrupted nouns. `furniture` is the one that doesn't take an s. */
const PLURALS: Record<string, string> = {
  furniture: 'furniture',
  person: 'people',
  mouse: 'mice',
};

function plural(label: string, n: number): string {
  if (n === 1) return label;
  return PLURALS[label] ?? `${label}s`;
}

export interface BrokenLineGenerator {
  /** A styled line from the given bank, or null if the bank has nothing valid. */
  line(bank: BrokenBank, event: NarrationEvent): string | null;
  /** Rewind every cursor. Called on mode-on, `9` and `0` so takes are identical. */
  reset(): void;
}

export function createBrokenLineGenerator(): BrokenLineGenerator {
  const cursors = new Map<string, number>();

  function bankFor(bank: BrokenBank, event: NarrationEvent): BrokenTemplate[] {
    if (bank === 'ghost') return GHOST_TEMPLATES;
    return (bank === 'lag' ? LAG_TEMPLATES : MISLABEL_TEMPLATES)[event.type];
  }

  function fill(text: string, event: NarrationEvent): string {
    return text
      .replace(/\{objects\}/g, plural(event.object, event.count))
      .replace(/\{object\}/g, event.object)
      .replace(/\{count\}/g, String(event.count))
      .replace(/\{confidence\}/g, event.confidence.toFixed(2));
  }

  return {
    line(bank, event) {
      const all = bankFor(bank, event);
      const valid = all.filter(
        (t) => (!t.only || t.only.includes(event.object)) && (t.minCount ?? 0) <= event.count,
      );
      if (valid.length === 0) return null;

      // Authored lines first, generics after — same relative order every run.
      const pool = [...valid.filter((t) => t.only), ...valid.filter((t) => !t.only)];

      const key = `${bank}:${event.type}:${event.object}`;
      const i = cursors.get(key) ?? 0;
      cursors.set(key, i + 1);
      return fill(pool[i % pool.length].text, event);
    },

    reset() {
      cursors.clear();
    },
  };
}
