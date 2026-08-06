import type { Detection } from '../vision/types';

/**
 * A detection as the *display* sees it. Superset of the real thing: the extra
 * flags exist only inside the demo layer, and the renderer treats them as
 * optional so a real `Detection` passes through unchanged.
 */
export interface DemoDetection extends Detection {
  /** [3] This box is frozen in place. The object left; the box did not. */
  ghost?: boolean;
  /** [5] The one clean box of the redemption shot. */
  redeemed?: boolean;
}
