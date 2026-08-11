/** A single detected thing in the current frame. */
export interface Detection {
  /** COCO class label, e.g. "person", "laptop". */
  label: string;
  /** Model confidence, 0..1. */
  score: number;
  /** [x, y, width, height] in *video pixel* space, not CSS space. */
  bbox: [number, number, number, number];
}

/**
 * A `Detection` given persistent identity across frames by the IoU tracker
 * (`src/vision/tracker.ts`). Position/size are exponentially smoothed, so a
 * `Track`'s `bbox` deliberately lags a raw `Detection`'s by design — that lag
 * is what kills jitter.
 */
export interface Track extends Detection {
  /** Stable identity, assigned once when the track is created. */
  id: number;
  /** How long this id has continuously existed, in ms (survives brief misses). */
  ageMs: number;
  /** Consecutive frames this track had no matching detection. */
  missedFrames: number;
  /**
   * `label` above is the winning label's *vote share* across this track's
   * recent frames (see tracker.ts), not the raw per-frame model output —
   * `Detection.score` (also inherited) stays this frame's raw model
   * confidence for whichever label matched. `labelConfidence` is a
   * different number: the winning label's share of total accumulated
   * votes, 0..1. A track flickering between two plausible labels (e.g.
   * `bed` / `dining table`) has a low `labelConfidence` even when each
   * individual detection was confident.
   */
  labelConfidence: number;
  /** Second-place label by vote share, if the track has ever seen one. */
  runnerUpLabel: string | null;
  /** Internal vote history driving `label`/`labelConfidence`/`runnerUpLabel` above. Not for display. */
  labelVotes: Record<string, number>;
}

/** Everything the HUD needs to render one frame. */
export interface Frame {
  detections: Detection[];
  /** `detections`, given persistent identity and smoothed position/size. */
  tracks: Track[];
  /** Milliseconds spent inside the model for this frame. */
  inferenceMs: number;
  /** Rolling frames-per-second of the detect loop. */
  fps: number;
}
