/**
 * The personality layer.
 *
 * Takes a truthful `NarrationEvent` and returns a styled line. That is the
 * entire public contract: `generateLine(event) => string`. Today it is a
 * template bank with no-repeat memory — offline, sub-millisecond, testable.
 * If a future phase wants an LLM behind this, it swaps in here and no caller
 * changes.
 */
import type { NarratorConfig } from './config';
import type { NarrationEvent } from './events';
import { ALSO_PREFIXES, TEMPLATES, type Template } from './templates';

/** A (type, object) pair may not reuse a template within this many utterances. */
const NO_REPEAT_WINDOW = 10;

/**
 * Templates are also blocked across *all* objects for this many lines. Without
 * it the per-pair memory happily says "laptop appears. the room accepts it
 * without question." and then the same line about a bottle four seconds later,
 * which reads like a lottery rather than a character.
 */
const GLOBAL_WINDOW = 6;

/**
 * How much more often an object-specific line is picked over a generic one.
 * The authored jokes ("phone detected. focus not detected.") are the whole
 * personality, but there are only a couple per object against ~20 generics, so
 * unweighted they would almost never surface.
 */
const SPECIFIC_WEIGHT = 6;

/**
 * Irregular plurals, duplicated from `describeScene` on purpose: that module is
 * the untouched detection-side code and this one is the personality layer. The
 * few bytes of duplication buy a clean seam between them.
 */
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

/**
 * How long the scene has been *boring*, which is what the idle jokes claim.
 * Distinct from `duration_in_frame` (how long the object has been visible): a
 * cup that was joined by a second cup a moment ago is not an hour-old tableau.
 */
function idleMs(event: NarrationEvent): number {
  return event.idle_ms ?? event.duration_in_frame;
}

export interface LineGenerator {
  generateLine(event: NarrationEvent): string;
  /** Styles a secondary event as a trailing clause: "also, the bottle left." */
  foldLine(event: NarrationEvent): string;
  reset(): void;
}

export function createLineGenerator(
  getConfig: () => NarratorConfig,
  /** Injectable so tests are deterministic. */
  random: () => number = Math.random,
): LineGenerator {
  const history = new Map<string, string[]>();
  let globalRecent: string[] = [];

  function eligible(event: NarrationEvent, config: NarratorConfig): Template[] {
    const minutesIdle = idleMs(event) / 60000;
    return TEMPLATES[event.type].filter(
      (t) =>
        t.spice <= config.spice_level &&
        (!t.only || t.only.includes(event.object)) &&
        (t.minMinutes ?? 0) <= minutesIdle &&
        (t.minCount ?? 0) <= event.count &&
        (!t.direction || t.direction === (event.count > event.previous_count ? 'up' : 'down')),
    );
  }

  function pick(event: NarrationEvent, config: NarratorConfig): Template {
    const pool = eligible(event, config);
    if (pool.length === 0) {
      // Only reachable if a bank is misconfigured; never leave the UI silent.
      return { text: `{object} detected.`, spice: 0 };
    }

    const key = `${event.type}:${event.object}`;
    const recent = history.get(key) ?? [];
    // Small pools (early `still_present` tiers) can't honour a full window, so
    // remember as much as the pool can actually support.
    const window = Math.min(NO_REPEAT_WINDOW, pool.length - 1);
    const blocked = new Set([
      ...recent.slice(0, window),
      ...globalRecent.slice(0, Math.min(GLOBAL_WINDOW, pool.length - 1)),
    ]);

    const fresh = pool.filter((t) => !blocked.has(t.text));
    const from = fresh.length > 0 ? fresh : pool;

    // Weighted pick: object-specific lines carry more weight than generics.
    const weight = (t: Template) => (t.only ? SPECIFIC_WEIGHT : 1);
    const total = from.reduce((sum, t) => sum + weight(t), 0);
    let roll = random() * total;
    let chosen = from[from.length - 1];
    for (const t of from) {
      roll -= weight(t);
      if (roll < 0) {
        chosen = t;
        break;
      }
    }

    history.set(key, [chosen.text, ...recent].slice(0, NO_REPEAT_WINDOW));
    globalRecent = [chosen.text, ...globalRecent].slice(0, GLOBAL_WINDOW);
    return chosen;
  }

  function fill(template: Template, event: NarrationEvent): string {
    return template.text
      .replace(/\{objects\}/g, plural(event.object, event.count))
      .replace(/\{object\}/g, event.object)
      .replace(/\{count\}/g, String(event.count))
      .replace(/\{minutes_idle\}/g, String(Math.max(1, Math.round(idleMs(event) / 60000))));
  }

  return {
    generateLine(event) {
      const config = getConfig();
      return fill(pick(event, config), event);
    },

    foldLine(event) {
      const config = getConfig();
      const prefix = ALSO_PREFIXES[Math.floor(random() * ALSO_PREFIXES.length) % ALSO_PREFIXES.length];
      return prefix + fill(pick(event, config), event);
    },

    reset() {
      history.clear();
      globalRecent = [];
    },
  };
}
