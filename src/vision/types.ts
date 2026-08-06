/** A single detected thing in the current frame. */
export interface Detection {
  /** COCO class label, e.g. "person", "laptop". */
  label: string;
  /** Model confidence, 0..1. */
  score: number;
  /** [x, y, width, height] in *video pixel* space, not CSS space. */
  bbox: [number, number, number, number];
}

/** Everything the HUD needs to render one frame. */
export interface Frame {
  detections: Detection[];
  /** Milliseconds spent inside the model for this frame. */
  inferenceMs: number;
  /** Rolling frames-per-second of the detect loop. */
  fps: number;
}

/** What the narrator believes is currently true about the scene. */
export interface SceneState {
  /** Label -> how many of it are visible. */
  counts: Record<string, number>;
  /** Labels that appeared since the last stable scene. */
  entered: string[];
  /** Labels that disappeared since the last stable scene. */
  exited: string[];
}
