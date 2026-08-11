import { describe, expect, it, vi } from 'vitest';
import { DEFAULT_CONFIG, type NarratorConfig } from './config';
import type { NarrationEvent } from './events';
import { createLlmLineGenerator, sanitizeLlmLine, type LlmStatus } from './llmLineGenerator';

function event(over: Partial<NarrationEvent> = {}): NarrationEvent {
  return {
    type: 'appear',
    object: 'chair',
    confidence: 0.8,
    timestamp: 0,
    duration_in_frame: 0,
    count: 1,
    previous_count: 0,
    uncertain: false,
    alternativeObject: null,
    ...over,
  };
}

function cfg(over: Partial<NarratorConfig> = {}): NarratorConfig {
  return { ...DEFAULT_CONFIG, ...over };
}

/** Waits for microtasks queued by the fake engine's promise chain to settle. */
async function flush() {
  await new Promise((r) => setTimeout(r, 0));
}

describe('sanitizeLlmLine', () => {
  it('lowercases, trims, and terminates the line', () => {
    expect(sanitizeLlmLine('  A Bottle Left  ', cfg())).toBe('a bottle left.');
  });

  it('rejects banned words', () => {
    expect(sanitizeLlmLine('what an amazing journey for this chair', cfg())).toBeNull();
  });

  it('rejects swears below spice 2', () => {
    expect(sanitizeLlmLine('the damn chair again', cfg({ spice_level: 1 }))).toBeNull();
    expect(sanitizeLlmLine('the damn chair again', cfg({ spice_level: 2 }))).not.toBeNull();
  });

  it('rejects lines too short to be a real sentence', () => {
    expect(sanitizeLlmLine('chair.', cfg())).toBeNull();
  });

  it('truncates rather than passing a line over the word ceiling', () => {
    const long = Array.from({ length: 30 }, (_, i) => `word${i}`).join(' ');
    const line = sanitizeLlmLine(long, cfg({ line_max_words: 14 }));
    expect(line).not.toBeNull();
    expect(line!.split(/\s+/).length).toBeLessThanOrEqual(14);
  });

  it('converts exclamation marks to periods (deadpan, never excited)', () => {
    expect(sanitizeLlmLine('a chair appears!!', cfg())).toBe('a chair appears.');
  });

  it('rejects a confident single-label line for an uncertain event, even if otherwise in-character', () => {
    const hedge = { alternativeObject: 'dining table' };
    expect(sanitizeLlmLine('the bed remains. as expected.', cfg(), hedge)).toBeNull();
  });

  it('accepts a line that hedges by naming the alternative', () => {
    const hedge = { alternativeObject: 'dining table' };
    expect(sanitizeLlmLine('a bed, or a dining table. unclear which.', cfg(), hedge)).not.toBeNull();
  });

  it('accepts a line that hedges with a cue word even without naming the alternative', () => {
    const hedge = { alternativeObject: 'dining table' };
    expect(sanitizeLlmLine('something bed-shaped. hard to say what.', cfg(), hedge)).not.toBeNull();
  });
});

describe('createLlmLineGenerator', () => {
  function fakeEngine(reply: string, opts: { delayMs?: number; calls?: number[] } = {}) {
    let inFlight = 0;
    const loadEngine = vi.fn(async (onProgress: (p: number) => void) => {
      onProgress(0.5);
      onProgress(1);
      return {
        chat: {
          completions: {
            create: vi.fn(async () => {
              inFlight++;
              opts.calls?.push(inFlight);
              if (opts.delayMs) await new Promise((r) => setTimeout(r, opts.delayMs));
              inFlight--;
              return { choices: [{ message: { content: reply } }] };
            }),
          },
        },
      };
    });
    return loadEngine;
  }

  it('falls back to the template line before the async line is ready', () => {
    const statuses: LlmStatus[] = [];
    const gen = createLlmLineGenerator(() => cfg(), (s) => statuses.push(s), fakeEngine('a chair appears. bold.'));
    const e = event();
    gen.prefetch?.(e);
    // Nothing has resolved yet — must not block, must return a template line.
    const line = gen.generateLine(e);
    expect(line).toMatch(/chair/);
    expect(statuses[0].state).toBe('loading');
  });

  it('uses the LLM line once prefetch resolves, without the caller awaiting anything', async () => {
    const gen = createLlmLineGenerator(() => cfg(), () => {}, fakeEngine('a chair appears. bold interior choices.'));
    const e = event();
    gen.prefetch?.(e);
    await flush();
    expect(gen.generateLine(e)).toBe('a chair appears. bold interior choices.');
  });

  it('does not re-issue inference for the same event object', async () => {
    const loadEngine = fakeEngine('a chair appears. bold.');
    const gen = createLlmLineGenerator(() => cfg(), () => {}, loadEngine);
    const e = event();
    gen.prefetch?.(e);
    gen.prefetch?.(e);
    gen.prefetch?.(e);
    await flush();
    expect(loadEngine).toHaveBeenCalledTimes(1);
  });

  it('serializes concurrent prefetches — never two inferences in flight at once', async () => {
    const calls: number[] = [];
    const loadEngine = fakeEngine('a chair appears. bold.', { delayMs: 5, calls });
    const gen = createLlmLineGenerator(() => cfg(), () => {}, loadEngine);
    gen.prefetch?.(event({ object: 'chair' }));
    gen.prefetch?.(event({ object: 'cup' }));
    gen.prefetch?.(event({ object: 'bottle' }));
    await flush();
    await new Promise((r) => setTimeout(r, 30));
    expect(Math.max(...calls)).toBe(1);
  });

  it('rejects an out-of-character reply and falls back to the template instead', async () => {
    const gen = createLlmLineGenerator(() => cfg(), () => {}, fakeEngine('WOW an amazing journey for this chair!!!'));
    const e = event();
    gen.prefetch?.(e);
    await flush();
    const line = gen.generateLine(e);
    expect(line).not.toMatch(/amazing|journey/);
    expect(line).toMatch(/chair/);
  });

  it('falls back to the template forever when the engine is unavailable', async () => {
    const loadEngine = vi.fn(async () => {
      throw Object.assign(new Error('no webgpu'), { yapUnavailable: true });
    });
    const statuses: LlmStatus[] = [];
    const gen = createLlmLineGenerator(() => cfg(), (s) => statuses.push(s), loadEngine);
    const e = event();
    gen.prefetch?.(e);
    await flush();
    expect(gen.generateLine(e)).toMatch(/chair/);
    expect(statuses.some((s) => s.state === 'unavailable')).toBe(true);
  });

  it('reset() clears the template fallback history without throwing', () => {
    const gen = createLlmLineGenerator(() => cfg(), () => {}, fakeEngine('a chair appears. bold.'));
    expect(() => gen.reset()).not.toThrow();
  });
});
