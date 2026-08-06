/**
 * The event layer.
 *
 * This sits between detection and personality and is the *truthful* half of the
 * system: it says what happened, in structured form, with no opinions. The
 * personality layer downstream may only restyle these facts, never invent them.
 *
 * Nothing here touches the perception pipeline — it consumes the same settled
 * scene counts the old narrator did (via `toSceneState`), so the detections
 * themselves are byte-for-byte what they always were.
 */
import type { Detection } from '../vision/types';

export type NarrationEventType = 'appear' | 'disappear' | 'count_change' | 'still_present';

export interface NarrationEvent {
  type: NarrationEventType;
  /** COCO label this event is about. */
  object: string;
  /** Best confidence seen for this label, 0..1. Last known value on disappear. */
  confidence: number;
  /** Wall-clock ms when the event was raised. */
  timestamp: number;
  /** How long the object had been continuously visible, in ms. */
  duration_in_frame: number;
  /** How many of it are visible now (0 on disappear). */
  count: number;
  /** How many were visible before this event. Lets the voice avoid claiming
   * "more than before" about a decrease. */
  previous_count: number;
  /**
   * How long this object has gone without changing, in ms. Set on
   * `still_present`, where the jokes make claims about elapsed boredom — a cup
   * that has been visible an hour but gained a neighbour a minute ago is not
   * an hour-old tableau, so this is not the same as `duration_in_frame`.
   */
  idle_ms?: number;
}

/** Which event wins when several land inside one rate-limit window. */
const PRIORITY: Record<NarrationEventType, number> = {
  appear: 3,
  disappear: 2,
  count_change: 1,
  still_present: 0,
};

export function byInterest(a: NarrationEvent, b: NarrationEvent): number {
  return PRIORITY[b.type] - PRIORITY[a.type];
}

/**
 * Renders an event the way the old narrator would have said it — flat, literal,
 * faintly robotic. This is what "boring mode" shows, and it is the on-camera
 * proof that the detection under the jokes is real.
 */
export function literalLine(event: NarrationEvent): string {
  switch (event.type) {
    case 'appear':
      return `${event.count} ${event.object} in view.`;
    case 'disappear':
      return `${event.object} gone.`;
    case 'count_change':
      return `Now ${event.count} ${event.object}.`;
    case 'still_present':
      return `${event.object} still in frame (${Math.round(event.duration_in_frame / 60000)}m).`;
  }
}

/** Compact structured dump for the debug tooltip. */
export function debugLine(event: NarrationEvent): string {
  return [
    event.type,
    event.object,
    `x${event.count}`,
    `conf ${event.confidence.toFixed(2)}`,
    `${(event.duration_in_frame / 1000).toFixed(1)}s`,
  ].join(' · ');
}

export interface EventTracker {
  /**
   * Feed one *settled* scene. Returns the events it implies.
   *
   * `still_present` is only raised when nothing else happened — an idle remark
   * on top of real news is just noise.
   */
  update(
    counts: Record<string, number>,
    detections: Detection[],
    now: number,
    idleEscalationMs: number,
  ): NarrationEvent[];
  reset(): void;
}

export function createEventTracker(): EventTracker {
  let prev: Record<string, number> = {};
  let firstSeen: Record<string, number> = {};
  let lastConf: Record<string, number> = {};
  let lastIdleEmit: Record<string, number> = {};
  /** When this object last did anything — appeared or changed count. */
  let lastChange: Record<string, number> = {};

  return {
    update(counts, detections, now, idleEscalationMs) {
      // Best confidence per label in this frame.
      for (const d of detections) {
        lastConf[d.label] = Math.max(lastConf[d.label] ?? 0, d.score);
      }

      const events: NarrationEvent[] = [];
      const make = (
        type: NarrationEventType,
        object: string,
        count: number,
      ): NarrationEvent => ({
        type,
        object,
        count,
        previous_count: prev[object] ?? 0,
        confidence: lastConf[object] ?? 0,
        timestamp: now,
        duration_in_frame: now - (firstSeen[object] ?? now),
      });

      for (const label of Object.keys(counts)) {
        if (prev[label] === undefined) {
          firstSeen[label] = now;
          lastIdleEmit[label] = now;
          lastChange[label] = now;
          events.push(make('appear', label, counts[label]));
        } else if (prev[label] !== counts[label]) {
          lastIdleEmit[label] = now;
          lastChange[label] = now;
          events.push(make('count_change', label, counts[label]));
        }
      }

      for (const label of Object.keys(prev)) {
        if (counts[label] === undefined) {
          events.push(make('disappear', label, 0));
          delete firstSeen[label];
          delete lastIdleEmit[label];
          delete lastChange[label];
        }
      }

      if (events.length === 0) {
        for (const label of Object.keys(counts)) {
          const since = lastIdleEmit[label] ?? firstSeen[label] ?? now;
          if (now - since >= idleEscalationMs) {
            lastIdleEmit[label] = now;
            events.push({
              ...make('still_present', label, counts[label]),
              idle_ms: now - (lastChange[label] ?? firstSeen[label] ?? now),
            });
          }
        }
      }

      prev = counts;
      return events;
    },

    reset() {
      prev = {};
      firstSeen = {};
      lastConf = {};
      lastIdleEmit = {};
      lastChange = {};
    },
  };
}
