/**
 * The sabotage engine.
 *
 * Owns every bit of broken-mode state and is the *only* thing that knows the
 * failures exist. It never sees the model and never writes to the detection
 * pipeline: `tick()` takes the real `Frame` and returns a corrupted copy for
 * display. Stop calling `tick()` and the app is exactly what it was.
 *
 * Single writer by design: the HUD's rAF loop is the one caller of `tick()`,
 * and the narrator reads `current()`. Two callers advancing ghost timers and
 * denial clocks independently would drift, and drift is how a take dies.
 */
import type { Frame } from '../vision/types';
import type { NarrationEvent } from '../narration/events';
import type { LogEntry } from '../narration/useNarrator';
import { literalLine } from '../narration/events';
import { nextLogId } from '../narration/ids';
import { MISLABEL_MAP, type DemoConfig, type FailureMode } from './config';
import { DENIAL_LINES, REDEMPTION_LINE } from './brokenTemplates';
import { createBrokenLineGenerator, type BrokenBank } from './brokenLine';
import type { DemoDetection } from './types';

export type RedemptionState = 'idle' | 'armed' | 'holding';

/** Frozen box left behind by an object that has left the frame. */
interface Ghost {
  /** The COCO label it really was — stable across mislabel toggles. */
  realLabel: string;
  /** The boxes as they were displayed at the moment of departure. */
  boxes: DemoDetection[];
  /** Confidence at freeze time; decay counts down from here. */
  startScore: number;
  bornAt: number;
}

export interface DemoController {
  config: DemoConfig;
  readonly hudVisible: boolean;

  /** Advance all demo state and return the frame to display. rAF only. */
  tick(real: Frame, now: number): Frame;
  /** The last frame `tick` produced. What the narrator reads. */
  current(): Frame;

  isActive(mode: FailureMode): boolean;
  activeModes(): FailureMode[];
  redemptionState(): RedemptionState;

  toggle(mode: FailureMode, now?: number): void;
  /** `9` — everything off, buffers dropped, cursors rewound. */
  reset(): void;
  /** `0` — the cliffhanger. */
  redeem(now?: number): void;

  /** True while the redemption shot owns the screen: no other line may emit. */
  isSuppressed(): boolean;
  /** A broken-bank line for this event, or null to let the normal voice speak. */
  brokenLine(event: NarrationEvent): string | null;
  /** True if the entry was held back by lag mode and must not be logged yet. */
  bufferLog(entry: LogEntry, now: number): boolean;
  /** Lines the demo layer owes the log: released lag, ghosts, denial, redemption. */
  takePending(now: number): LogEntry[];

  subscribe(fn: () => void): () => void;
}

const EMPTY_FRAME: Frame = { detections: [], inferenceMs: 0, fps: 0 };

export function createDemoController(config: DemoConfig, hudVisible: boolean): DemoController {
  const modes = new Set<FailureMode>();
  const generator = createBrokenLineGenerator();
  const subscribers = new Set<() => void>();

  let displayed: Frame = EMPTY_FRAME;
  /** Last displayed boxes, grouped by their REAL label. Source for ghosts. */
  let lastByRealLabel = new Map<string, DemoDetection[]>();
  let ghosts: Ghost[] = [];
  let lagBuffer: { entry: LogEntry; releaseAt: number }[] = [];
  let pending: LogEntry[] = [];
  let denialCursor = 0;
  let lastDenialAt = 0;
  let redemption: RedemptionState = 'idle';
  let redemptionHoldUntil = 0;
  let redeemedBox: DemoDetection | null = null;

  const notify = () => subscribers.forEach((fn) => fn());

  function logEntry(text: string, boring: string, extra: Partial<LogEntry> = {}): LogEntry {
    return { id: nextLogId(), text, boring, debug: boring, at: Date.now(), ...extra };
  }

  /** A synthetic event so demo-authored lines reuse the same slot filling. */
  function syntheticEvent(object: string, confidence: number, count: number): NarrationEvent {
    return {
      type: 'still_present',
      object,
      confidence,
      count,
      previous_count: count,
      timestamp: Date.now(),
      duration_in_frame: 0,
    };
  }

  // -------------------------------------------------------------------------
  // [1] mislabel
  // -------------------------------------------------------------------------

  function corrupt(d: DemoDetection): DemoDetection {
    const swap = modes.has('mislabel') ? MISLABEL_MAP[d.label] : undefined;
    if (!swap) return { ...d };
    // Confidence comes from the map, not the model. The certainty is the joke.
    return { ...d, label: swap.as, score: swap.confidence };
  }

  // -------------------------------------------------------------------------
  // [3] ghost
  // -------------------------------------------------------------------------

  function updateGhosts(real: Frame, now: number) {
    if (!modes.has('ghost')) {
      ghosts = [];
      return;
    }

    const presentNow = new Set(real.detections.map((d) => d.label));

    // An object that left frame leaves its last box behind.
    for (const [realLabel, boxes] of lastByRealLabel) {
      if (presentNow.has(realLabel)) continue;
      if (ghosts.some((g) => g.realLabel === realLabel)) continue;
      if (boxes.length === 0) continue;

      const startScore = Math.max(...boxes.map((b) => b.score));
      ghosts.push({ realLabel, boxes, startScore, bornAt: now });

      const event = syntheticEvent(boxes[0].label, startScore, boxes.length);
      const text = generator.line('ghost', event);
      if (text) pending.push(logEntry(text, literalLine(event), { kind: 'ghost' }));
    }

    // Came back, or outstayed its welcome.
    ghosts = ghosts.filter(
      (g) => !presentNow.has(g.realLabel) && now - g.bornAt < config.ghostSeconds * 1000,
    );
  }

  /** Confidence loses conviction on a clock, not a coin flip. */
  function ghostBoxes(now: number): DemoDetection[] {
    return ghosts.flatMap((g) => {
      const elapsed = (now - g.bornAt) / 1000;
      const score = Math.max(config.ghostFloor, g.startScore - config.ghostDecayPerSecond * elapsed);
      return g.boxes.map((b) => ({ ...b, score, ghost: true }));
    });
  }

  // -------------------------------------------------------------------------
  // [4] denial
  // -------------------------------------------------------------------------

  function updateDenial(now: number) {
    if (!modes.has('denial') || modes.size < 2) return;
    if (now - lastDenialAt < config.denialIntervalSeconds * 1000) return;
    lastDenialAt = now;
    const text = DENIAL_LINES[denialCursor % DENIAL_LINES.length];
    denialCursor++;
    pending.push(logEntry(text, text, { kind: 'denial' }));
  }

  // -------------------------------------------------------------------------
  // [5] redemption
  // -------------------------------------------------------------------------

  function largestPerson(real: Frame): DemoDetection | null {
    const people = real.detections.filter((d) => d.label === 'person');
    if (people.length === 0) return null;
    const best = [...people].sort((a, b) => b.bbox[2] * b.bbox[3] - a.bbox[2] * a.bbox[3])[0];
    return {
      label: 'person',
      score: config.redemptionConfidence,
      bbox: best.bbox,
      redeemed: true,
    };
  }

  /** Returns the frame to show while redemption owns the screen, or null. */
  function redemptionFrame(real: Frame, now: number): Frame | null {
    if (redemption === 'idle') return null;

    if (redemption === 'armed') {
      const person = largestPerson(real);
      if (!person) return null; // Corruption is already off; wait for a person.
      redeemedBox = person;
      redemption = 'holding';
      redemptionHoldUntil = now + config.redemptionHoldSeconds * 1000;
      pending.push(logEntry(REDEMPTION_LINE, REDEMPTION_LINE, { kind: 'redemption' }));
      notify();
      return { ...real, detections: [person] };
    }

    if (now >= redemptionHoldUntil) {
      redemption = 'idle';
      redeemedBox = null;
      notify();
      return null;
    }

    // Hold the box even if they step out mid-shot — the frame must not blink.
    const person = largestPerson(real) ?? redeemedBox;
    if (person) redeemedBox = person;
    return { ...real, detections: person ? [person] : [] };
  }

  // -------------------------------------------------------------------------

  return {
    config,
    hudVisible,

    tick(real, now) {
      const redeemed = redemptionFrame(real, now);
      if (redeemed) {
        displayed = redeemed;
        lastByRealLabel = new Map();
        return displayed;
      }

      const pairs = real.detections.map((d) => [d.label, corrupt(d)] as const);
      const display = pairs.map(([, d]) => d);

      updateGhosts(real, now);
      updateDenial(now);

      const grouped = new Map<string, DemoDetection[]>();
      for (const [realLabel, d] of pairs) {
        const list = grouped.get(realLabel) ?? [];
        list.push(d);
        grouped.set(realLabel, list);
      }
      lastByRealLabel = grouped;

      displayed = { ...real, detections: [...display, ...ghostBoxes(now)] };
      return displayed;
    },

    current: () => displayed,

    isActive: (mode) => modes.has(mode),
    activeModes: () => [...modes],
    redemptionState: () => redemption,

    toggle(mode, now = performance.now()) {
      if (modes.has(mode)) {
        modes.delete(mode);
        if (mode === 'ghost') ghosts = [];
        // Turning lag off lets the backlog catch up rather than vanish.
        if (mode === 'lag') {
          pending.push(...lagBuffer.map((b) => b.entry));
          lagBuffer = [];
        }
      } else {
        if (modes.size === 0) lastDenialAt = now;
        modes.add(mode);
        // Rewind the banks so the first line after a keypress is always the
        // same line. This is what makes take 4 look like take 1.
        generator.reset();
        if (mode === 'denial') lastDenialAt = now;
      }
      notify();
    },

    reset() {
      modes.clear();
      ghosts = [];
      lagBuffer = [];
      pending = [];
      denialCursor = 0;
      redemption = 'idle';
      redeemedBox = null;
      generator.reset();
      notify();
    },

    redeem(now = performance.now()) {
      modes.clear();
      ghosts = [];
      // Discarded, not flushed: dumping seven seconds of backlog over the hard
      // cut is the one thing that would ruin this shot.
      lagBuffer = [];
      pending = [];
      denialCursor = 0;
      generator.reset();
      redemption = 'armed';
      redemptionHoldUntil = now;
      notify();
    },

    isSuppressed: () => redemption !== 'idle',

    brokenLine(event) {
      // Lag outranks mislabel for *which bank speaks*; the label is already
      // corrupted underneath either way, so [1]+[2] gives
      // "a toilet appeared. previously. historically."
      const bank: BrokenBank | null = modes.has('lag')
        ? 'lag'
        : modes.has('mislabel') && isCorrupted(event.object)
          ? 'mislabel'
          : null;
      return bank ? generator.line(bank, event) : null;
    },

    bufferLog(entry, now) {
      if (!modes.has('lag')) return false;
      // The timestamp stays the ORIGINAL event time, so the log visibly
      // narrates the past while the boxes stay live.
      lagBuffer.push({ entry: { ...entry, lagged: true }, releaseAt: now + config.lagSeconds * 1000 });
      return true;
    },

    takePending(now) {
      const due = lagBuffer.filter((b) => now >= b.releaseAt);
      if (due.length > 0) lagBuffer = lagBuffer.filter((b) => now < b.releaseAt);
      const out = [...due.map((b) => b.entry), ...pending];
      pending = [];
      return out;
    },

    subscribe(fn) {
      subscribers.add(fn);
      return () => subscribers.delete(fn);
    },
  };
}

/** Is this a label the map invented? Corrupted nouns get the corrupted bank. */
function isCorrupted(label: string): boolean {
  for (const key of Object.keys(MISLABEL_MAP)) {
    if (MISLABEL_MAP[key].as === label) return true;
  }
  return false;
}
