/**
 * Episode 3: the failure episode.
 *
 * Everything in `src/demo/` corrupts the *presentation* only. Detection runs
 * exactly as it always has — `useDetector` writes a truthful `Frame`, and this
 * layer produces a corrupted *copy* of it at render and narration time. Delete
 * this directory and the app is byte-identical to today.
 *
 * Two hard rules this file exists to enforce:
 *
 * 1. Nothing here runs unless the URL carries `?demo=broken`. No param, no
 *    import side effects, no corruption, no hotkey listener.
 * 2. Nothing here is random. Every choice is a cursor or a clock, so take 4
 *    looks like take 1.
 */

/** The five things a keypress can do. `1`-`4` toggle, `0` redeems, `9` resets. */
export type FailureMode = 'mislabel' | 'lag' | 'ghost' | 'denial';

export interface Mislabel {
  /** What the HUD and the log will call it instead. */
  as: string;
  /** What the HUD and the log will claim the confidence is. The joke is that
   * the wrong answer is more confident than the right one ever was. */
  confidence: number;
}

/**
 * The corruption map, applied at display time by exact COCO label.
 *
 * Note on `mug`: COCO-SSD has no `mug` class — a mug detects as `cup`. The
 * `mug` key is kept as a harmless alias so the map reads the way you wrote it,
 * and so it still works if the model is ever swapped for one that has it.
 */
export const MISLABEL_MAP: Record<string, Mislabel> = {
  person: { as: 'furniture', confidence: 0.51 },
  cup: { as: 'toilet', confidence: 0.91 },
  mug: { as: 'toilet', confidence: 0.91 },
  'cell phone': { as: 'remote control', confidence: 0.88 },
  chair: { as: 'dog', confidence: 0.64 },
  keyboard: { as: 'piano', confidence: 0.97 },
  bottle: { as: 'fire hydrant', confidence: 0.73 },
};

export interface DemoConfig {
  /** [2] How far behind real time the narration log runs, in seconds. */
  lagSeconds: number;
  /** [3] How long a departed object's box hangs around, in seconds. */
  ghostSeconds: number;
  /** [3] Confidence lost per second while a ghost is decaying. 0.97 -> 0.96 -> … */
  ghostDecayPerSecond: number;
  /** [3] A ghost never decays below this — it loses conviction, not the plot. */
  ghostFloor: number;
  /** [4] How often the denial line fires, in seconds, while any mode is on. */
  denialIntervalSeconds: number;
  /** [5] Seconds the redemption shot holds the single clean box before the app
   * returns to plain normal rendering. Sized for a hard cut, not a fade. */
  redemptionHoldSeconds: number;
  /** [5] The confidence the redemption box claims. The one honest number. */
  redemptionConfidence: number;
}

export const DEFAULT_DEMO_CONFIG: DemoConfig = {
  lagSeconds: 7,
  ghostSeconds: 12,
  ghostDecayPerSecond: 0.01,
  ghostFloor: 0.6,
  denialIntervalSeconds: 10,
  redemptionHoldSeconds: 4,
  redemptionConfidence: 0.99,
};

/**
 * Live tuning between takes without a rebuild: `?demo=broken&lag=8&ghost=15`.
 * Unknown or unparseable values fall back to the defaults rather than throwing
 * mid-shoot.
 */
export function readDemoConfig(params: URLSearchParams): DemoConfig {
  const num = (key: string, fallback: number) => {
    const v = Number(params.get(key));
    return Number.isFinite(v) && v > 0 ? v : fallback;
  };
  return {
    ...DEFAULT_DEMO_CONFIG,
    lagSeconds: num('lag', DEFAULT_DEMO_CONFIG.lagSeconds),
    ghostSeconds: num('ghost', DEFAULT_DEMO_CONFIG.ghostSeconds),
    denialIntervalSeconds: num('denial', DEFAULT_DEMO_CONFIG.denialIntervalSeconds),
  };
}

/** `?demo=broken` arms the layer. Anything else and none of this exists. */
export function isDemoArmed(params: URLSearchParams): boolean {
  return params.get('demo') === 'broken';
}

/** `?hud=1` shows the mode indicator. Rehearsing on, filming off. */
export function isDemoHudVisible(params: URLSearchParams): boolean {
  return params.get('hud') === '1';
}
