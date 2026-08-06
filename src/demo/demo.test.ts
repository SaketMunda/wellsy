import { describe, expect, it } from 'vitest';
import type { Detection, Frame } from '../vision/types';
import type { NarrationEvent } from '../narration/events';
import { BANNED_WORDS, MAX_WORDS } from '../narration/templates';
import {
  DEFAULT_DEMO_CONFIG,
  MISLABEL_MAP,
  isDemoArmed,
  isDemoHudVisible,
  readDemoConfig,
} from './config';
import {
  DENIAL_LINES,
  GHOST_TEMPLATES,
  LAG_TEMPLATES,
  MISLABEL_TEMPLATES,
  REDEMPTION_LINE,
} from './brokenTemplates';
import { createBrokenLineGenerator } from './brokenLine';
import { createDemoController } from './controller';
import type { DemoDetection } from './types';

const words = (line: string) => line.split(/\s+/).filter(Boolean).length;

function det(label: string, score = 0.8, bbox: [number, number, number, number] = [0, 0, 10, 10]): Detection {
  return { label, score, bbox };
}

function frame(...detections: Detection[]): Frame {
  return { detections, inferenceMs: 10, fps: 30 };
}

function event(over: Partial<NarrationEvent> = {}): NarrationEvent {
  return {
    type: 'appear',
    object: 'toilet',
    confidence: 0.91,
    timestamp: 0,
    duration_in_frame: 0,
    count: 1,
    previous_count: 0,
    ...over,
  };
}

function controller(hud = false) {
  return createDemoController({ ...DEFAULT_DEMO_CONFIG }, hud);
}

const labels = (f: Frame) => f.detections.map((d) => d.label);

// ---------------------------------------------------------------------------

describe('arming', () => {
  it('only arms on ?demo=broken', () => {
    expect(isDemoArmed(new URLSearchParams(''))).toBe(false);
    expect(isDemoArmed(new URLSearchParams('demo=1'))).toBe(false);
    expect(isDemoArmed(new URLSearchParams('demo=broken'))).toBe(true);
  });

  it('hides the indicator unless ?hud=1', () => {
    expect(isDemoHudVisible(new URLSearchParams('demo=broken'))).toBe(false);
    expect(isDemoHudVisible(new URLSearchParams('demo=broken&hud=1'))).toBe(true);
  });

  it('reads tunables from the URL and ignores junk', () => {
    const cfg = readDemoConfig(new URLSearchParams('lag=8&ghost=nonsense'));
    expect(cfg.lagSeconds).toBe(8);
    expect(cfg.ghostSeconds).toBe(DEFAULT_DEMO_CONFIG.ghostSeconds);
  });
});

describe('broken template banks', () => {
  const banks = {
    ...Object.fromEntries(Object.entries(MISLABEL_TEMPLATES).map(([k, v]) => [`mislabel:${k}`, v])),
    ...Object.fromEntries(Object.entries(LAG_TEMPLATES).map(([k, v]) => [`lag:${k}`, v])),
    ghost: GHOST_TEMPLATES,
  };

  it('keeps the voice: 4-14 words, lowercase, no exclamation', () => {
    for (const [name, pool] of Object.entries(banks)) {
      for (const t of pool) {
        const filled = t.text
          .replace(/\{objects\}/g, 'toilets')
          .replace(/\{object\}/g, 'toilet')
          .replace(/\{count\}/g, '2')
          .replace(/\{confidence\}/g, '0.91');
        expect(words(filled), `${name}: "${filled}"`).toBeLessThanOrEqual(MAX_WORDS);
        expect(words(filled), `${name}: "${filled}"`).toBeGreaterThanOrEqual(4);
        expect(filled, `${name}: "${filled}"`).not.toContain('!');
        expect(filled[0], `${name}: "${filled}"`).toBe(filled[0].toLowerCase());
        for (const banned of BANNED_WORDS) expect(filled).not.toContain(banned);
      }
    }
  });

  it('never lets the narrator suspect itself', () => {
    // The whole bit is zero self-doubt. A hedge here kills the joke.
    const tells = ['error', 'sorry', 'maybe wrong', 'not sure', 'glitch', 'malfunction'];
    for (const pool of Object.values(banks)) {
      for (const t of pool) {
        for (const tell of tells) expect(t.text).not.toContain(tell);
      }
    }
  });

  it('has a usable pool for every event type', () => {
    for (const [name, pool] of Object.entries(banks)) {
      expect(pool.length, name).toBeGreaterThanOrEqual(4);
      const texts = pool.map((t) => t.text);
      expect(new Set(texts).size, `duplicates in ${name}`).toBe(texts.length);
    }
  });

  it('denial lines are short status lines, never observations', () => {
    for (const line of DENIAL_LINES) {
      expect(words(line)).toBeGreaterThanOrEqual(3);
      expect(words(line)).toBeLessThanOrEqual(6);
    }
    expect(new Set(DENIAL_LINES).size).toBe(DENIAL_LINES.length);
  });
});

describe('deterministic line picking', () => {
  it('produces the identical sequence on every take', () => {
    const runs = [0, 1].map(() => {
      const g = createBrokenLineGenerator();
      return [0, 1, 2, 3, 4].map(() => g.line('mislabel', event()));
    });
    expect(runs[0]).toEqual(runs[1]);
  });

  it('leads with the authored line for a corrupted label', () => {
    const g = createBrokenLineGenerator();
    expect(g.line('mislabel', event())).toBe('a toilet appears. on the desk. bold.');
  });

  it('fills confidence from the corrupted number', () => {
    const g = createBrokenLineGenerator();
    g.line('mislabel', event()); // consume the authored first line
    expect(g.line('mislabel', event())).toBe('a toilet. 0.91. i have no notes.');
  });

  it('reset rewinds to the first line', () => {
    const g = createBrokenLineGenerator();
    const first = g.line('mislabel', event());
    g.line('mislabel', event());
    g.reset();
    expect(g.line('mislabel', event())).toBe(first);
  });
});

describe('[1] mislabel', () => {
  it('is off until toggled', () => {
    const c = controller();
    expect(labels(c.tick(frame(det('cup')), 0))).toEqual(['cup']);
  });

  it('swaps label and confidence from the map, not the model', () => {
    const c = controller();
    c.toggle('mislabel', 0);
    const out = c.tick(frame(det('cup', 0.52)), 0);
    expect(out.detections[0].label).toBe('toilet');
    expect(out.detections[0].score).toBe(0.91);
  });

  it('leaves unmapped labels completely alone', () => {
    const c = controller();
    c.toggle('mislabel', 0);
    expect(labels(c.tick(frame(det('laptop')), 0))).toEqual(['laptop']);
  });

  it('routes the corrupted noun to the corrupted bank', () => {
    const c = controller();
    c.toggle('mislabel', 0);
    expect(c.brokenLine(event({ object: 'toilet' }))).toContain('toilet');
    // A real, uncorrupted label falls through to the normal voice.
    expect(c.brokenLine(event({ object: 'laptop' }))).toBeNull();
  });

  it('toggles back off without a reload', () => {
    const c = controller();
    c.toggle('mislabel', 0);
    c.toggle('mislabel', 100);
    expect(labels(c.tick(frame(det('cup')), 200))).toEqual(['cup']);
  });
});

describe('[2] lag', () => {
  const entry = () => ({ id: 1, text: 'a toilet appears.', boring: 'cup in view.', debug: '', at: 5000 });

  it('holds entries back and releases them lagSeconds later', () => {
    const c = controller();
    c.toggle('lag', 0);
    expect(c.bufferLog(entry(), 0)).toBe(true);
    expect(c.takePending(6000)).toHaveLength(0);
    const released = c.takePending(7001);
    expect(released).toHaveLength(1);
    expect(released[0].lagged).toBe(true);
  });

  it('keeps the ORIGINAL timestamp so the log narrates the past', () => {
    const c = controller();
    c.toggle('lag', 0);
    c.bufferLog(entry(), 0);
    expect(c.takePending(7001)[0].at).toBe(5000);
  });

  it('does not buffer when off', () => {
    const c = controller();
    expect(c.bufferLog(entry(), 0)).toBe(false);
  });

  it('lets the backlog catch up when toggled off by hand', () => {
    const c = controller();
    c.toggle('lag', 0);
    c.bufferLog(entry(), 0);
    c.toggle('lag', 100);
    expect(c.takePending(200)).toHaveLength(1);
  });
});

describe('[3] ghost', () => {
  it('freezes the last box when the object leaves', () => {
    const c = controller();
    c.toggle('ghost', 0);
    c.tick(frame(det('keyboard', 0.97)), 0);
    const out = c.tick(frame(), 1000);
    expect(labels(out)).toEqual(['keyboard']);
    expect((out.detections[0] as DemoDetection).ghost).toBe(true);
  });

  it('ticks confidence down one hundredth a second from the moment it left', () => {
    const c = controller();
    c.toggle('ghost', 0);
    c.tick(frame(det('keyboard', 0.97)), 0);
    const at = (t: number) => c.tick(frame(), t).detections[0]?.score;
    expect(at(1000)).toBeCloseTo(0.97, 5); // the instant it froze
    expect(at(2000)).toBeCloseTo(0.96, 5);
    expect(at(3000)).toBeCloseTo(0.95, 5);
    expect(at(4000)).toBeCloseTo(0.94, 5);
  });

  it('floors the decay instead of running to zero', () => {
    const c = createDemoController(
      { ...DEFAULT_DEMO_CONFIG, ghostSeconds: 100, ghostDecayPerSecond: 0.1 },
      false,
    );
    c.toggle('ghost', 0);
    c.tick(frame(det('keyboard', 0.97)), 0);
    c.tick(frame(), 1000);
    expect(c.tick(frame(), 60_000).detections[0].score).toBe(DEFAULT_DEMO_CONFIG.ghostFloor);
  });

  it('expires after ghostSeconds', () => {
    const c = controller();
    c.toggle('ghost', 0);
    c.tick(frame(det('keyboard')), 0);
    c.tick(frame(), 1000);
    expect(c.tick(frame(), 13_001).detections).toHaveLength(0);
  });

  it('drops the ghost the moment the real thing comes back', () => {
    const c = controller();
    c.toggle('ghost', 0);
    c.tick(frame(det('keyboard')), 0);
    c.tick(frame(), 1000);
    expect(labels(c.tick(frame(det('keyboard')), 2000))).toEqual(['keyboard']);
  });

  it('emits a ghost line when the box freezes', () => {
    const c = controller();
    c.toggle('ghost', 0);
    c.tick(frame(det('keyboard')), 0);
    c.tick(frame(), 1000);
    const [line] = c.takePending(1000);
    expect(line.kind).toBe('ghost');
    expect(line.text).toContain('keyboard');
  });

  it('ghosts the CORRUPTED label when mislabel is also on', () => {
    const c = controller();
    c.toggle('mislabel', 0);
    c.toggle('ghost', 0);
    c.tick(frame(det('keyboard', 0.4)), 0);
    const out = c.tick(frame(), 1000);
    expect(out.detections[0].label).toBe('piano');
    // Decay starts from the corrupted confidence, not the model's 0.4.
    expect(out.detections[0].score).toBeCloseTo(0.97, 5);
    expect(c.tick(frame(), 3000).detections[0].score).toBeCloseTo(0.95, 5);
  });

  it('does not spawn a ghost just because mislabel was toggled', () => {
    const c = controller();
    c.toggle('ghost', 0);
    c.tick(frame(det('cup')), 0);
    c.toggle('mislabel', 100);
    // The real label never left, so nothing froze — only the noun changed.
    expect(labels(c.tick(frame(det('cup')), 200))).toEqual(['toilet']);
  });
});

describe('[4] denial', () => {
  it('stays quiet unless another failure is active', () => {
    const c = controller();
    c.toggle('denial', 0);
    c.tick(frame(), 20_000);
    expect(c.takePending(20_000)).toHaveLength(0);
  });

  it('fires on the interval while chaos is visible', () => {
    const c = controller();
    c.toggle('mislabel', 0);
    c.toggle('denial', 0);
    c.tick(frame(), 9_000);
    expect(c.takePending(9_000)).toHaveLength(0);
    c.tick(frame(), 10_001);
    const [line] = c.takePending(10_001);
    expect(line.kind).toBe('denial');
    expect(line.text).toBe(DENIAL_LINES[0]);
  });

  it('cycles the lines in a fixed order', () => {
    const c = controller();
    c.toggle('mislabel', 0);
    c.toggle('denial', 0);
    const seen: string[] = [];
    for (let t = 10_001; t < 40_000; t += 10_001) {
      c.tick(frame(), t);
      seen.push(...c.takePending(t).map((e) => e.text));
    }
    expect(seen).toEqual(DENIAL_LINES.slice(0, seen.length));
  });
});

describe('[5] redemption', () => {
  it('kills every active corruption instantly', () => {
    const c = controller();
    (['mislabel', 'lag', 'ghost', 'denial'] as const).forEach((m) => c.toggle(m, 0));
    c.redeem(1000);
    expect(c.activeModes()).toEqual([]);
  });

  it('renders one clean person box at 0.99 and nothing else', () => {
    const c = controller();
    c.toggle('mislabel', 0);
    c.redeem(1000);
    const out = c.tick(frame(det('cup'), det('person', 0.62), det('chair')), 1100);
    expect(out.detections).toHaveLength(1);
    expect(out.detections[0].label).toBe('person');
    expect(out.detections[0].score).toBe(0.99);
  });

  it('emits exactly one line, the true one', () => {
    const c = controller();
    c.redeem(1000);
    c.tick(frame(det('person')), 1100);
    const pending = c.takePending(1100);
    expect(pending).toHaveLength(1);
    expect(pending[0].text).toBe(REDEMPTION_LINE);
  });

  it('discards the lag backlog rather than dumping it over the cut', () => {
    const c = controller();
    c.toggle('lag', 0);
    c.bufferLog({ id: 1, text: 'old news', boring: '', debug: '', at: 0 }, 0);
    c.redeem(1000);
    c.tick(frame(det('person')), 1100);
    expect(c.takePending(60_000).map((e) => e.text)).toEqual([REDEMPTION_LINE]);
  });

  it('waits, armed, until a person actually appears', () => {
    const c = controller();
    c.redeem(1000);
    expect(c.tick(frame(det('cup')), 1100).detections).toHaveLength(1); // untouched
    expect(c.takePending(1100)).toHaveLength(0);
    c.tick(frame(det('person')), 2000);
    expect(c.takePending(2000)).toHaveLength(1);
  });

  it('suppresses all other narration while it holds, then releases', () => {
    const c = controller();
    c.redeem(1000);
    c.tick(frame(det('person')), 1100);
    expect(c.isSuppressed()).toBe(true);
    c.tick(frame(det('person')), 5200); // hold is 4s
    expect(c.isSuppressed()).toBe(false);
  });

  it('holds the box even if they step out mid-shot', () => {
    const c = controller();
    c.redeem(1000);
    c.tick(frame(det('person')), 1100);
    const out = c.tick(frame(), 2000);
    expect(out.detections).toHaveLength(1);
    expect(out.detections[0].score).toBe(0.99);
  });

  it('works from any state, ten times running', () => {
    for (let i = 0; i < 10; i++) {
      const c = controller();
      (['mislabel', 'lag', 'ghost', 'denial'] as const).slice(0, (i % 4) + 1).forEach((m) => c.toggle(m, 0));
      c.tick(frame(det('cup'), det('person')), 100);
      c.tick(frame(det('cup')), 200); // leave a ghost behind
      c.redeem(1000);
      const out = c.tick(frame(det('cup'), det('person', 0.55)), 1100);
      expect(out.detections).toHaveLength(1);
      expect(out.detections[0].label).toBe('person');
      expect(out.detections[0].score).toBe(0.99);
      expect(c.takePending(1100).map((e) => e.text)).toEqual([REDEMPTION_LINE]);
    }
  });
});

describe('[9] reset', () => {
  it('drops modes, ghosts and buffers', () => {
    const c = controller();
    (['mislabel', 'ghost', 'lag'] as const).forEach((m) => c.toggle(m, 0));
    c.tick(frame(det('cup')), 0);
    c.tick(frame(), 1000);
    c.bufferLog({ id: 1, text: 'x', boring: '', debug: '', at: 0 }, 1000);
    c.reset();
    expect(c.activeModes()).toEqual([]);
    expect(c.tick(frame(det('cup')), 2000).detections.map((d) => d.label)).toEqual(['cup']);
    expect(c.takePending(60_000)).toHaveLength(0);
  });
});

describe('the cue sheet', () => {
  it('runs the 60-second rehearsal without a wrong frame', () => {
    const c = controller();
    const mug = det('cup', 0.55, [10, 10, 40, 40]);
    const me = det('person', 0.71, [100, 20, 120, 200]);

    // start clean
    expect(labels(c.tick(frame(mug, me), 0))).toEqual(['cup', 'person']);

    // [1] on — mug is a toilet everywhere, and confidently so
    c.toggle('mislabel', 1000);
    const mis = c.tick(frame(mug, me), 1100);
    expect(labels(mis)).toEqual(['toilet', 'furniture']);
    expect(mis.detections[0].score).toBe(0.91);
    expect(c.brokenLine(event({ object: 'toilet' }))).toBe('a toilet appears. on the desk. bold.');

    // [3] on — mug leaves, the toilet stays behind, losing its nerve
    c.toggle('ghost', 12_000);
    c.tick(frame(mug, me), 12_100);
    const ghosted = c.tick(frame(me), 13_100);
    expect(labels(ghosted)).toEqual(['furniture', 'toilet']);
    expect(ghosted.detections[1].score).toBeCloseTo(0.91, 5);
    // …and it starts losing its nerve on camera.
    expect(c.tick(frame(me), 16_100).detections[1].score).toBeCloseTo(0.88, 5);

    // [2] on — narration falls behind, boxes do not
    c.toggle('lag', 24_000);
    expect(c.bufferLog({ id: 9, text: 'a toilet appears.', boring: '', debug: '', at: 24_000 }, 24_000)).toBe(true);
    expect(labels(c.tick(frame(me), 24_100))).toContain('furniture');

    // [4] fires
    c.toggle('denial', 30_000);
    c.tick(frame(me), 40_100);
    expect(c.takePending(40_100).some((e) => e.kind === 'denial')).toBe(true);

    // 0 — redemption
    c.redeem(55_000);
    const clean = c.tick(frame(me, mug), 55_100);
    expect(clean.detections).toHaveLength(1);
    expect(clean.detections[0].label).toBe('person');
    expect(clean.detections[0].score).toBe(0.99);
    expect(c.takePending(55_100).map((e) => e.text)).toEqual(['person. 0.99. confirmed.']);
  });
});

describe('normal mode is untouched', () => {
  it('passes the frame through byte-for-byte with no modes on', () => {
    const c = controller();
    const f = frame(det('cup'), det('person'), det('keyboard'));
    const out = c.tick(f, 0);
    expect(out.detections).toEqual(f.detections);
    expect(out.fps).toBe(f.fps);
    expect(out.inferenceMs).toBe(f.inferenceMs);
    expect(c.takePending(0)).toHaveLength(0);
    expect(c.brokenLine(event())).toBeNull();
    expect(c.isSuppressed()).toBe(false);
  });

  it('maps only the labels named in the map', () => {
    expect(Object.keys(MISLABEL_MAP).sort()).toEqual(
      ['bottle', 'cell phone', 'chair', 'cup', 'keyboard', 'mug', 'person'],
    );
  });
});
