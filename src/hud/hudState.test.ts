import { describe, expect, it } from 'vitest';
import { ACQUIRE_MS, EMPTY_HUD_STATE, EXIT_MS, updateHudState } from './hudState';
import type { Frame, Track } from '../vision/types';

function track(id: number, bbox: [number, number, number, number], overrides: Partial<Track> = {}): Track {
  return {
    id,
    label: 'person',
    score: 0.9,
    bbox,
    ageMs: 0,
    missedFrames: 0,
    labelConfidence: 1,
    runnerUpLabel: null,
    labelVotes: { person: 0.9 },
    ...overrides,
  };
}

function frame(tracks: Track[]): Frame {
  return { detections: [], tracks, inferenceMs: 0, fps: 60 };
}

describe('updateHudState', () => {
  it('advances acquire progress with dt and caps it at ACQUIRE_MS', () => {
    let state = EMPTY_HUD_STATE;
    const f = frame([track(1, [0, 0, 100, 100])]);
    state = updateHudState(state, f, 100, 1280, 720);
    expect(state.targets.get(1)?.acquireMs).toBe(100);
    state = updateHudState(state, f, 100, 1280, 720);
    expect(state.targets.get(1)?.acquireMs).toBe(200);
    state = updateHudState(state, f, 1000, 1280, 720);
    expect(state.targets.get(1)?.acquireMs).toBe(ACQUIRE_MS);
  });

  it('sends a track that disappears into exit, then releases it after EXIT_MS', () => {
    let state = EMPTY_HUD_STATE;
    state = updateHudState(state, frame([track(1, [0, 0, 100, 100])]), 16, 1280, 720);
    expect(state.targets.has(1)).toBe(true);

    state = updateHudState(state, frame([]), 100, 1280, 720);
    expect(state.targets.get(1)?.exiting).toBe(true);
    expect(state.targets.get(1)?.exitMs).toBe(100);

    state = updateHudState(state, frame([]), EXIT_MS, 1280, 720);
    expect(state.targets.has(1)).toBe(false);
  });

  it('a re-appearing track (same tracker id) is not treated as still exiting', () => {
    let state = EMPTY_HUD_STATE;
    state = updateHudState(state, frame([track(1, [0, 0, 100, 100])]), 16, 1280, 720);
    state = updateHudState(state, frame([track(1, [0, 0, 100, 100])]), 16, 1280, 720);
    expect(state.targets.get(1)?.exiting).toBe(false);
    expect(state.targets.get(1)?.exitMs).toBe(0);
  });

  it('interpolates the drawn box toward the latest tracked box over successive ticks', () => {
    let state = EMPTY_HUD_STATE;
    state = updateHudState(state, frame([track(1, [0, 0, 100, 100])]), 16, 1280, 720);
    const start = state.targets.get(1)!.bbox[0];
    expect(start).toBe(0);

    state = updateHudState(state, frame([track(1, [200, 0, 100, 100])]), 16, 1280, 720);
    const mid = state.targets.get(1)!.bbox[0];
    expect(mid).toBeGreaterThan(0);
    expect(mid).toBeLessThan(200);

    // Many more ticks toward the same target box should keep closing the gap.
    for (let i = 0; i < 50; i++) {
      state = updateHudState(state, frame([track(1, [200, 0, 100, 100])]), 16, 1280, 720);
    }
    expect(state.targets.get(1)!.bbox[0]).toBeGreaterThan(199);
  });

  it('picks the larger, more central box as primary', () => {
    let state = EMPTY_HUD_STATE;
    // A big box dead-center, and a small box in a corner.
    const f = frame([
      track(1, [590, 310, 100, 100], { label: 'chair' }),
      track(2, [0, 0, 20, 20], { label: 'cup' }),
    ]);
    state = updateHudState(state, f, 16, 1280, 720);
    expect(state.primaryId).toBe(1);
  });

  it('eases primaryProgress toward 1 for the primary and 0 for everyone else', () => {
    let state = EMPTY_HUD_STATE;
    const f = frame([
      track(1, [590, 310, 200, 200]),
      track(2, [0, 0, 20, 20], { label: 'cup' }),
    ]);
    state = updateHudState(state, f, 300, 1280, 720);
    expect(state.targets.get(1)!.primaryProgress).toBeGreaterThan(0);
    expect(state.targets.get(2)!.primaryProgress).toBe(0);
  });

  it('gives each track id a stable phase across ticks', () => {
    let state = EMPTY_HUD_STATE;
    const f = frame([track(7, [0, 0, 100, 100])]);
    state = updateHudState(state, f, 16, 1280, 720);
    const phase1 = state.targets.get(7)!.phase;
    state = updateHudState(state, f, 16, 1280, 720);
    expect(state.targets.get(7)!.phase).toBe(phase1);
  });
});
