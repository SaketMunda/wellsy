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

  it('never matches across different labels when geometric overlap is weak', () => {
    let counter = 1;
    const nextId = () => counter++;
    // Two genuinely different, non-overlapping objects — a chair must never
    // inherit a person's id off a coincidence, and there is none here to lean on.
    let tracks = updateTracks([], [det('chair', [100, 100, 200, 400])], 16, nextId);
    tracks = updateTracks(tracks, [det('person', [900, 100, 200, 400])], 16, nextId);
    expect(tracks.map((t) => t.label).sort()).toEqual(['chair', 'person']);
    expect(tracks.map((t) => t.id).sort()).toEqual([1, 2]);
  });

  it('cross-label match: a track survives the model flipping its label when the box barely moves (bed -> dining table)', () => {
    let counter = 1;
    const nextId = () => counter++;
    let tracks = updateTracks([], [det('bed', [100, 100, 400, 250])], 16, nextId);
    expect(tracks.map((t) => t.id)).toEqual([1]);
    tracks = updateTracks(tracks, [det('dining table', [102, 98, 400, 250])], 16, nextId);
    expect(tracks).toHaveLength(1);
    expect(tracks[0].id).toBe(1); // same id survived the label flip
    expect(counter).toBe(2); // no second id was minted
  });

  it('cross-label match: works in the other direction too (dining table -> bed)', () => {
    let counter = 1;
    const nextId = () => counter++;
    let tracks = updateTracks([], [det('dining table', [100, 100, 400, 250])], 16, nextId);
    tracks = updateTracks(tracks, [det('bed', [102, 98, 400, 250])], 16, nextId);
    expect(tracks).toHaveLength(1);
    expect(tracks[0].id).toBe(1);
    expect(counter).toBe(2);
  });

  it('label voting: a track flip-flopping between two labels settles on a winner rather than showing the latest frame', () => {
    let counter = 1;
    const nextId = () => counter++;
    let tracks: Track[] = [];
    const bbox: [number, number, number, number] = [100, 100, 400, 250];
    // Mostly "bed", occasionally "dining table" — a noisy but bed-leaning model.
    const sequence = ['bed', 'bed', 'dining table', 'bed', 'bed', 'dining table', 'bed', 'bed'];
    for (const label of sequence) {
      tracks = updateTracks(tracks, [det(label, bbox, 0.8)], 16, nextId);
    }
    expect(tracks).toHaveLength(1);
    expect(tracks[0].id).toBe(1);
    expect(tracks[0].label).toBe('bed');
    expect(tracks[0].runnerUpLabel).toBe('dining table');
    expect(tracks[0].labelConfidence).toBeGreaterThan(0.5);
    expect(tracks[0].labelConfidence).toBeLessThan(1);
  });

  it('a dominant track never steals a neighbor\'s detection on the frame its own label briefly drops out', () => {
    // Regression test for a real reported bug ("it always talks about the
    // bed, never the chair or the mic"). The trigger isn't a chair sitting
    // near a bed every frame — same-label matching always wins a track its
    // own unchanged detection first (score 1.0 beats any cross-label
    // score), so that alone can't cause a steal. The real trigger is more
    // realistic and much easier to hit on real footage: `lite_mobilenet_v2`
    // (D2) doesn't detect every object on every single frame, even a big
    // stationary one — a `bed` detection can simply be *absent* for one
    // tick. On exactly that tick, the bed track has no same-label candidate
    // at all, so its only candidate is the cross-label one against whatever
    // nearby object *is* detected. If that neighbor's own same-label score
    // (against its own last known box, possibly a little jittered) happens
    // to be lower than the bed's cross-label overlap — verified by direct
    // computation for the geometry below (same-label chair score 0.333,
    // cross-label bed-vs-chair overlap 0.75, both clearing their gates) —
    // the original single-ranked-candidate-list code let the bed steal the
    // chair's detection outright, even relabeling itself `chair` for a
    // tick, while the real chair track was starved and marked missed. The
    // two-phase fix (same-label pass fully first, cross-label only on what
    // that pass left over) makes this structurally impossible: the chair's
    // own same-label candidate is matched in phase 1 regardless of how it
    // compares to any cross-label score, before phase 2 ever runs.
    let counter = 1;
    const nextId = () => counter++;
    const bedBox: [number, number, number, number] = [0, 0, 400, 300];
    const chairPrev: [number, number, number, number] = [100, 100, 300, 300];
    const chairNow: [number, number, number, number] = [0, 0, 300, 300];

    let tracks = updateTracks([], [det('bed', bedBox), det('chair', chairPrev)], 16, nextId);
    expect(tracks).toHaveLength(2);
    const bedId = tracks.find((t) => t.label === 'bed')!.id;
    const chairId = tracks.find((t) => t.label === 'chair')!.id;

    // The bed goes undetected for one tick; the chair is still there, jittered.
    tracks = updateTracks(tracks, [det('chair', chairNow)], 16, nextId);

    const bed = tracks.find((t) => t.id === bedId)!;
    const chair = tracks.find((t) => t.id === chairId)!;
    expect(chair.label).toBe('chair'); // not stolen, not relabeled
    expect(chair.missedFrames).toBe(0); // matched this tick, not starved
    expect(bed.label).toBe('bed'); // did not repaint itself as "chair"
    expect(bed.missedFrames).toBe(1); // correctly just missed, not falsely matched
    expect(counter).toBe(3); // no id churn from any of this
  });

  it('a track with a single consistent label carries full label confidence and no runner-up', () => {
    let counter = 1;
    const nextId = () => counter++;
    let tracks: Track[] = [];
    for (let i = 0; i < 5; i++) {
      tracks = updateTracks(tracks, [det('laptop', [100, 100, 200, 150])], 16, nextId);
    }
    expect(tracks[0].labelConfidence).toBe(1);
    expect(tracks[0].runnerUpLabel).toBeNull();
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
