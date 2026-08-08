import { describe, expect, it } from 'vitest';
import { DEFAULT_CONFIG, type NarratorConfig } from './config';
import { createEventTracker, type NarrationEvent } from './events';
import { createLineGenerator } from './generateLine';
import { BANNED_WORDS, MAX_WORDS, TEMPLATES } from './templates';
import type { Track } from '../vision/types';

const COCO_SAMPLE = [
  'person', 'chair', 'bottle', 'cell phone', 'cup', 'laptop', 'book',
  'keyboard', 'potted plant', 'tv', 'dining table', 'teddy bear',
];

const PLURALS: Record<string, string> = { person: 'people', scissors: 'scissors' };

function event(over: Partial<NarrationEvent> = {}): NarrationEvent {
  return {
    type: 'appear',
    object: 'chair',
    confidence: 0.8,
    timestamp: 0,
    duration_in_frame: 0,
    count: 1,
    previous_count: 0,
    ...over,
  };
}

function gen(config: Partial<NarratorConfig> = {}, random = Math.random) {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  return createLineGenerator(() => cfg, random);
}

const words = (line: string) => line.split(/\s+/).filter(Boolean).length;

describe('template bank', () => {
  it('has no duplicate template text within a bank', () => {
    for (const [type, bank] of Object.entries(TEMPLATES)) {
      const texts = bank.map((t) => t.text);
      expect(new Set(texts).size, `duplicates in ${type}`).toBe(texts.length);
    }
  });

  it('uses no exclamation marks', () => {
    for (const bank of Object.values(TEMPLATES)) {
      for (const t of bank) expect(t.text).not.toMatch(/!/);
    }
  });

  it('has a generic pool large enough for the no-repeat window at default spice', () => {
    // still_present is tiered by idle minutes, so it is exercised separately.
    for (const type of ['appear', 'disappear', 'count_change'] as const) {
      const pool = TEMPLATES[type].filter((t) => !t.only && t.spice <= DEFAULT_CONFIG.spice_level);
      expect(pool.length, `${type} pool`).toBeGreaterThan(10);
    }
  });
});

describe('generateLine', () => {
  it('preserves the fact: the object name always survives the joke', () => {
    const g = gen({ spice_level: 2 });
    for (const object of COCO_SAMPLE) {
      for (const type of ['appear', 'disappear', 'count_change', 'still_present'] as const) {
        for (let i = 0; i < 40; i++) {
          const line = g.generateLine(
            event({ type, object, count: 2, duration_in_frame: 60 * 60_000 }),
          );
          const plural = PLURALS[object] ?? `${object}s`;
          const stem = object.split(' ').pop()!;
          expect(
            line.includes(object) || line.includes(plural) || line.includes(stem),
            `"${line}" lost the object "${object}"`,
          ).toBe(true);
        }
      }
    }
  });

  it('never leaves an unfilled slot placeholder', () => {
    const g = gen({ spice_level: 2 });
    for (const object of COCO_SAMPLE) {
      for (const type of ['appear', 'disappear', 'count_change', 'still_present'] as const) {
        for (let i = 0; i < 40; i++) {
          const line = g.generateLine(
            event({ type, object, count: 3, duration_in_frame: 90 * 60_000 }),
          );
          expect(line, 'unfilled slot').not.toMatch(/\{[a-z_]+\}/);
        }
      }
    }
  });

  it('stays within the word ceiling', () => {
    const g = gen({ spice_level: 2 });
    for (const object of COCO_SAMPLE) {
      for (const type of ['appear', 'disappear', 'count_change', 'still_present'] as const) {
        for (let i = 0; i < 40; i++) {
          const line = g.generateLine(
            event({ type, object, count: 12, duration_in_frame: 120 * 60_000 }),
          );
          expect(words(line), `too long: "${line}"`).toBeLessThanOrEqual(MAX_WORDS);
          expect(words(line), `too short: "${line}"`).toBeGreaterThanOrEqual(4);
        }
      }
    }
  });

  it('uses no banned words and no exclamation marks', () => {
    const g = gen({ spice_level: 2 });
    for (const object of COCO_SAMPLE) {
      for (const type of ['appear', 'disappear', 'count_change', 'still_present'] as const) {
        for (let i = 0; i < 40; i++) {
          const line = g.generateLine(
            event({ type, object, duration_in_frame: 120 * 60_000 }),
          );
          for (const banned of BANNED_WORDS) expect(line).not.toContain(banned);
          expect(line).not.toMatch(/!/);
        }
      }
    }
  });

  it('does not repeat a template for a (type, object) pair within the window', () => {
    const g = gen({ spice_level: 1 });
    for (const type of ['appear', 'disappear', 'count_change'] as const) {
      const seen: string[] = [];
      for (let i = 0; i < 11; i++) {
        seen.push(g.generateLine(event({ type, object: 'tv', count: 2 })));
      }
      expect(new Set(seen).size, `${type} repeated inside 11 lines`).toBe(seen.length);
    }
  });

  it('keeps spice 2 lines out of lower spice levels', () => {
    const g = gen({ spice_level: 1 });
    const swears = /damn|hell/;
    for (let i = 0; i < 300; i++) {
      const line = g.generateLine(event({ type: 'appear', object: 'tv' }));
      expect(line, `swear leaked at spice 1: "${line}"`).not.toMatch(swears);
    }
  });

  it('escalates still_present with idle time', () => {
    const g = gen({ spice_level: 1 });
    // A freshly-idle scene must not claim an hour has passed.
    const fresh = g.generateLine(event({ type: 'still_present', object: 'tv', duration_in_frame: 0 }));
    expect(fresh).not.toMatch(/furniture|permanent/);

    const long = new Set<string>();
    for (let i = 0; i < 60; i++) {
      long.add(g.generateLine(event({ type: 'still_present', object: 'tv', duration_in_frame: 60 * 60_000 })));
    }
    // The late tiers only unlock once enough idle time has accrued.
    expect([...long].some((l) => /furniture|permanent|check on the room|blinked/.test(l))).toBe(true);
  });

  it('agrees with itself about singular and plural counts', () => {
    const g = gen({ spice_level: 2 });
    for (let i = 0; i < 200; i++) {
      const one = g.generateLine(event({ type: 'count_change', object: 'cup', count: 1 }));
      expect(one, `bad grammar: "${one}"`).not.toMatch(/\b1 cups\b/);
      const many = g.generateLine(event({ type: 'count_change', object: 'person', count: 3 }));
      expect(many, `bad grammar: "${many}"`).not.toMatch(/\b3 person\b/);
    }
  });

  it('does not reuse a template across different objects back to back', () => {
    const g = gen({ spice_level: 1 });
    const objects = ['laptop', 'bottle', 'tv', 'book', 'cup', 'chair'];
    const lines: string[] = [];
    for (let i = 0; i < 40; i++) {
      // Strip the object out so we compare the joke, not the noun.
      const object = objects[i % objects.length];
      const line = g.generateLine(event({ type: 'appear', object }));
      lines.push(line.replace(object, '{}'));
    }
    for (let i = 1; i < lines.length; i++) {
      expect(lines[i], `template repeated back to back: "${lines[i]}"`).not.toBe(lines[i - 1]);
    }
  });

  it('surfaces object-specific lines often enough to read as authored', () => {
    const g = gen({ spice_level: 1 });
    let specific = 0;
    for (let i = 0; i < 400; i++) {
      const line = g.generateLine(event({ type: 'appear', object: 'cell phone' }));
      if (line.includes('focus not detected')) specific++;
    }
    expect(specific, 'authored line never surfaced').toBeGreaterThan(20);
  });

  it('measures idle time from the last change, not from first sighting', () => {
    const g = gen({ spice_level: 1 });
    // Visible an hour, but something changed a minute ago: no hour-old claims.
    const line = g.generateLine(
      event({ type: 'still_present', object: 'tv', duration_in_frame: 60 * 60_000, idle_ms: 60_000 }),
    );
    expect(line).not.toMatch(/furniture|permanent|60 minutes/);
  });

  it('never asserts a direction the count did not move in', () => {
    const g = gen({ spice_level: 2 });
    for (let i = 0; i < 300; i++) {
      const down = g.generateLine(
        event({ type: 'count_change', object: 'cup', count: 1, previous_count: 3 }),
      );
      expect(down, `claimed an increase on a decrease: "${down}"`).not.toMatch(
        /more than before|up to|escalation|collecting/,
      );
      const up = g.generateLine(
        event({ type: 'count_change', object: 'cup', count: 3, previous_count: 1 }),
      );
      expect(up, `claimed a decrease on an increase: "${up}"`).not.toMatch(
        /down to|thins out|attrition/,
      );
    }
  });

  it('is deterministic when given a deterministic random source', () => {
    const seeded = () => {
      let n = 0;
      return () => ((n = (n * 1103515245 + 12345) % 2147483648) / 2147483648);
    };
    const a = gen({}, seeded());
    const b = gen({}, seeded());
    for (let i = 0; i < 20; i++) {
      expect(a.generateLine(event({ object: 'cup' }))).toBe(b.generateLine(event({ object: 'cup' })));
    }
  });

  it('generates a line in well under 10ms', () => {
    const g = gen();
    const start = performance.now();
    for (let i = 0; i < 1000; i++) g.generateLine(event({ object: 'cup' }));
    expect((performance.now() - start) / 1000).toBeLessThan(10);
  });
});

describe('event tracker', () => {
  const track = (id: number, label: string, ageMs = 0, score = 0.9): Track => ({
    id,
    label,
    score,
    bbox: [0, 0, 1, 1],
    ageMs,
    missedFrames: 0,
  });
  const IDLE = 2 * 60_000;

  it('raises appear per track and disappear truthfully — a second same-label track is its own appear, not a count_change', () => {
    const t = createEventTracker();
    expect(t.update([track(1, 'chair')], 0, IDLE)).toMatchObject([
      { type: 'appear', object: 'chair', count: 1 },
    ]);
    expect(t.update([track(1, 'chair', 100), track(2, 'chair', 0)], 100, IDLE)).toMatchObject([
      { type: 'appear', object: 'chair', count: 2 },
    ]);
    expect(t.update([], 200, IDLE)).toMatchObject([
      { type: 'disappear', object: 'chair', count: 0 },
    ]);
  });

  it('emits nothing while the track id set is unchanged and not yet idle', () => {
    const t = createEventTracker();
    t.update([track(1, 'chair')], 0, IDLE);
    expect(t.update([track(1, 'chair', 1000)], 1000, IDLE)).toEqual([]);
  });

  it('emits still_present once the idle threshold passes', () => {
    const t = createEventTracker();
    t.update([track(1, 'chair')], 0, IDLE);
    const events = t.update([track(1, 'chair', IDLE + 1)], IDLE + 1, IDLE);
    expect(events).toMatchObject([{ type: 'still_present', object: 'chair' }]);
    expect(events[0].duration_in_frame).toBeGreaterThanOrEqual(IDLE);
  });

  it('suppresses still_present when real news happened in the same tick', () => {
    const t = createEventTracker();
    t.update([track(1, 'chair')], 0, IDLE);
    const events = t.update(
      [track(1, 'chair', IDLE + 1), track(2, 'cup', 0)],
      IDLE + 1,
      IDLE,
    );
    expect(events.map((e) => e.type)).toEqual(['appear']);
  });

  it('resets the idle clock when a new track of the same label appears', () => {
    const t = createEventTracker();
    t.update([track(1, 'cup')], 0, IDLE);
    t.update([track(1, 'cup', 50 * 60_000), track(2, 'cup', 0)], 50 * 60_000, IDLE);
    const [e] = t.update(
      [track(1, 'cup', 52 * 60_000), track(2, 'cup', 2 * 60_000)],
      52 * 60_000,
      IDLE,
    );
    expect(e.type).toBe('still_present');
    // Visible for 52 minutes, but only boring for 2 of them.
    expect(e.duration_in_frame).toBe(52 * 60_000);
    expect(e.idle_ms).toBe(2 * 60_000);
  });

  it('reports the observed confidence, not an invented one', () => {
    const t = createEventTracker();
    const [e] = t.update([track(1, 'chair', 0, 0.42)], 0, IDLE);
    expect(e.confidence).toBeCloseTo(0.42);
  });
});
