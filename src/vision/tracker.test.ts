import { describe, expect, it } from 'vitest';
import { updateTracks } from './tracker';
import type { Detection, Track } from './types';

function det(label: string, bbox: [number, number, number, number], score = 0.9): Detection {
  return { label, bbox, score };
}

function ids(tracks: Track[]): number[] {
  return tracks.filter((t) => t.missedFrames === 0).map((t) => t.id);
}

describe('updateTracks', () => {
  it('assigns a new id to a genuinely new object', () => {
    let counter = 1;
    const nextId = () => counter++;
    const tracks = updateTracks([], [det('person', [100, 100, 200, 400])], 16, nextId);
    expect(tracks).toHaveLength(1);
    expect(tracks[0].id).toBe(1);
    expect(tracks[0].ageMs).toBe(0);
  });

  it('keeps the same id across small frame-to-frame jitter — a static object should not mint new ids', () => {
    let counter = 1;
    const nextId = () => counter++;
    let tracks: Track[] = [];
    // A small (phone-sized) box, jittering aggressively frame to frame the
    // way a real lite_mobilenet_v2 detection does for a static object —
    // enough to push plain IoU against the *previous* frame below 0.3 on
    // several of these steps. This is exactly the case that used to
    // runaway-mint ids (see decisions.md D11): each consecutive pair below
    // was chosen so IoU([i], [i+1]) < 0.3 while the boxes still plainly
    // describe "the same phone, roughly where it was."
    const jitteredBoxes: [number, number, number, number][] = [
      [400, 300, 60, 90],
      [425, 280, 60, 90],
      [400, 300, 60, 90],
      [420, 315, 60, 90],
      [398, 298, 60, 90],
      [418, 282, 60, 90],
    ];
    for (const bbox of jitteredBoxes) {
      tracks = updateTracks(tracks, [det('cell phone', bbox)], 16, nextId);
    }
    expect(ids(tracks)).toEqual([1]);
    expect(counter).toBe(2); // only one id was ever minted
  });

  it('keeps the same id while a person moves a moderate amount frame to frame', () => {
    let counter = 1;
    const nextId = () => counter++;
    let tracks: Track[] = [];
    let x = 100;
    for (let i = 0; i < 10; i++) {
      x += 15; // steady walking motion
      tracks = updateTracks(tracks, [det('person', [x, 100, 200, 400])], 16, nextId);
    }
    expect(ids(tracks)).toEqual([1]);
  });

  it('drops a track and mints a fresh id once it has been gone well past the grace window', () => {
    let counter = 1;
    const nextId = () => counter++;
    let tracks = updateTracks([], [det('person', [100, 100, 200, 400])], 16, nextId);
    expect(ids(tracks)).toEqual([1]);

    for (let i = 0; i < 25; i++) {
      tracks = updateTracks(tracks, [], 16, nextId);
    }
    expect(tracks.find((t) => t.id === 1)).toBeUndefined();

    tracks = updateTracks(tracks, [det('person', [900, 100, 200, 400])], 16, nextId);
    expect(tracks.some((t) => t.id === 2)).toBe(true);
  });

  it('recovers the same id after a brief gap within the grace window', () => {
    let counter = 1;
    const nextId = () => counter++;
    let tracks = updateTracks([], [det('person', [100, 100, 200, 400])], 16, nextId);
    expect(ids(tracks)).toEqual([1]);

    // Two missed frames — well inside MAX_MISSED_FRAMES.
    tracks = updateTracks(tracks, [], 16, nextId);
    tracks = updateTracks(tracks, [], 16, nextId);

    tracks = updateTracks(tracks, [det('person', [105, 102, 200, 400])], 16, nextId);
    expect(ids(tracks)).toEqual([1]);
  });

  it('never matches across different labels even when boxes coincide exactly', () => {
    let counter = 1;
    const nextId = () => counter++;
    let tracks = updateTracks([], [det('chair', [100, 100, 200, 400])], 16, nextId);
    tracks = updateTracks(tracks, [det('person', [100, 100, 200, 400])], 16, nextId);
    expect(tracks.map((t) => t.label).sort()).toEqual(['chair', 'person']);
    expect(tracks.map((t) => t.id).sort()).toEqual([1, 2]);
  });

  it('smooths matched box position toward the new detection rather than snapping', () => {
    let counter = 1;
    const nextId = () => counter++;
    let tracks = updateTracks([], [det('person', [100, 100, 200, 400])], 16, nextId);
    tracks = updateTracks(tracks, [det('person', [300, 100, 200, 400])], 16, nextId);
    const [t] = tracks;
    expect(t.bbox[0]).toBeGreaterThan(100);
    expect(t.bbox[0]).toBeLessThan(300);
  });
});
