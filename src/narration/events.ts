/**
 * The event layer.
 *
 * This sits between detection and personality and is the *truthful* half of the
 * system: it says what happened, in structured form, with no opinions. The
 * personality layer downstream may only restyle these facts, never invent them.
 *
 * As of Day 3 this reads track enter/exit directly off the tracker's output
 * (`src/vision/tracker.ts`) rather than diffing label counts. A second person
 * walking in is `appear` for that track, never `count_change` — `count_change`
 * stays defined (and in the template bank) but a track-identity-based tracker
 * has no case that produces it: every count delta already rides an appear or
 * disappear for the track that caused it.
 */
import type { Track } from '../vision/types';

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
   * Feed one *settled* set of tracks. Returns the events it implies.
   *
   * `still_present` is only raised when nothing else happened — an idle remark
   * on top of real news is just noise.
   */
  update(tracks: Track[], now: number, idleEscalationMs: number): NarrationEvent[];
  reset(): void;
}

function countByLabel(tracks: Track[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const t of tracks) counts[t.label] = (counts[t.label] ?? 0) + 1;
  return counts;
}

export function createEventTracker(): EventTracker {
  let prevTracks: Track[] = [];
  /** When this label last did anything — a track of it appeared or left. */
  let lastChange: Record<string, number> = {};
  let lastIdleEmit: Record<string, number> = {};

  return {
    update(tracks, now, idleEscalationMs) {
      const prevIds = new Set(prevTracks.map((t) => t.id));
      const currentIds = new Set(tracks.map((t) => t.id));
      const prevCounts = countByLabel(prevTracks);
      const counts = countByLabel(tracks);

      const events: NarrationEvent[] = [];

      const newByLabel = new Map<string, Track[]>();
      for (const t of tracks) {
        if (prevIds.has(t.id)) continue;
        const arr = newByLabel.get(t.label);
        if (arr) arr.push(t);
        else newByLabel.set(t.label, [t]);
      }
      for (const [label, arrived] of newByLabel) {
        lastChange[label] = now;
        lastIdleEmit[label] = now;
        events.push({
          type: 'appear',
          object: label,
          count: counts[label],
          previous_count: prevCounts[label] ?? 0,
          confidence: Math.max(...arrived.map((t) => t.score)),
          timestamp: now,
          duration_in_frame: Math.max(...arrived.map((t) => t.ageMs)),
        });
      }

      const goneByLabel = new Map<string, Track[]>();
      for (const t of prevTracks) {
        if (currentIds.has(t.id)) continue;
        const arr = goneByLabel.get(t.label);
        if (arr) arr.push(t);
        else goneByLabel.set(t.label, [t]);
      }
      for (const [label, left] of goneByLabel) {
        lastChange[label] = now;
        delete lastIdleEmit[label];
        events.push({
          type: 'disappear',
          object: label,
          count: counts[label] ?? 0,
          previous_count: prevCounts[label],
          confidence: Math.max(...left.map((t) => t.score)),
          timestamp: now,
          duration_in_frame: Math.max(...left.map((t) => t.ageMs)),
        });
      }

      if (events.length === 0) {
        for (const label of Object.keys(counts)) {
          const since = lastIdleEmit[label] ?? lastChange[label] ?? now;
          if (now - since >= idleEscalationMs) {
            lastIdleEmit[label] = now;
            const ofLabel = tracks.filter((t) => t.label === label);
            events.push({
              type: 'still_present',
              object: label,
              count: counts[label],
              previous_count: counts[label],
              confidence: Math.max(...ofLabel.map((t) => t.score)),
              timestamp: now,
              duration_in_frame: Math.max(...ofLabel.map((t) => t.ageMs)),
              idle_ms: now - (lastChange[label] ?? now),
            });
          }
        }
      }

      prevTracks = tracks;
      return events;
    },

    reset() {
      prevTracks = [];
      lastChange = {};
      lastIdleEmit = {};
    },
  };
}
