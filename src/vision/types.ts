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
