import { describe, expect, it } from 'vitest';
import { describeScene, queryObject } from './describeScene';
import type { Track } from '../vision/types';

function track(label: string, over: Partial<Track> = {}): Track {
  return {
    id: over.id ?? Math.random(),
    label,
    score: 0.9,
    bbox: [0, 0, 10, 10],
    ageMs: 0,
    missedFrames: 0,
    labelConfidence: 1,
    runnerUpLabel: null,
    labelVotes: { [label]: 0.9 },
    ...over,
  };
}

describe('describeScene', () => {
  it('reports an empty scene honestly', () => {
    expect(describeScene([])).toBe('nothing in view right now.');
  });

  it('describes a single object with an indefinite article', () => {
    expect(describeScene([track('laptop')])).toBe('one thing: a laptop.');
  });

  it('lists several distinct objects with an Oxford comma', () => {
    const scene = [track('person'), track('laptop'), track('bottle')];
    expect(describeScene(scene)).toBe('three things: a person, a laptop, and a bottle.');
  });

  it('joins exactly two objects with "and", no comma', () => {
    expect(describeScene([track('person'), track('laptop')])).toBe('two things: a person and a laptop.');
  });

  it('pluralizes and counts multiple of the same label', () => {
    expect(describeScene([track('person'), track('person')])).toBe('two things: two people.');
  });

  it('reports an uncertain track as unidentified, never guessing the winning label', () => {
    const scene = [
      track('person'),
      track('laptop'),
      track('bed', { labelConfidence: 0.5, runnerUpLabel: 'dining table' }),
    ];
    expect(describeScene(scene)).toBe('three things: a person, a laptop, and something unidentified.');
  });

  it('groups multiple unidentified tracks together', () => {
    const scene = [
      track('bed', { id: 1, labelConfidence: 0.5, runnerUpLabel: 'dining table' }),
      track('couch', { id: 2, labelConfidence: 0.5, runnerUpLabel: 'bed' }),
    ];
    expect(describeScene(scene)).toBe('two things: two unidentified things.');
  });
});

describe('queryObject', () => {
  it('answers yes with a count when the object is confidently present', () => {
    expect(queryObject([track('laptop')], 'laptop')).toBe('yes. one laptop in view.');
    expect(queryObject([track('person'), track('person')], 'person')).toBe('yes. two people in view.');
  });

  it('answers no when the object is not present at all', () => {
    expect(queryObject([track('laptop')], 'bottle')).toBe('no. no bottle in view.');
  });

  it('hedges rather than confirming when the only candidate is uncertain', () => {
    const scene = [track('bed', { labelConfidence: 0.5, runnerUpLabel: 'dining table' })];
    expect(queryObject(scene, 'dining table')).toBe('maybe. something that could be a dining table, unconfirmed.');
    expect(queryObject(scene, 'bed')).toBe('maybe. something that could be a bed, unconfirmed.');
  });
});
