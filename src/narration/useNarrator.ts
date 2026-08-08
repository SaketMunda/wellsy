import { useCallback, useEffect, useRef, useState } from 'react';
import type { Frame } from '../vision/types';
import { DEFAULT_CONFIG, loadConfig, saveConfig, type NarratorConfig } from './config';
import {
  byInterest,
  createEventTracker,
  debugLine,
  literalLine,
  type NarrationEvent,
} from './events';
import { createLineGenerator } from './generateLine';
import { nextLogId } from './ids';
import { primeSpeech, speak, stopSpeaking } from './speech';

/** How often we sample the frame for scene changes. */
const SAMPLE_MS = 250;
/** A scene must hold this long before we'll talk about it — kills flicker. */
const STABLE_MS = 900;

export interface LogEntry {
  /** Unique row key. Wall-clock ms alone collides when lag mode replays. */
  id: number;
  /** The styled, in-character line. */
  text: string;
  /** How the old narrator would have said it — shown in "boring mode". */
  boring: string;
  /** Structured event dump, for the debug tooltip. */
  debug: string;
  at: number;
}

/**
 * Watches the detection stream and narrates when the scene *changes and settles*.
 *
 * The pipeline is: settled scene -> structured events (truth) -> styled line
 * (voice). The two stages are deliberately separate, so "boring mode" can show
 * the raw event for the same log row and prove the detection is real.
 */
export function useNarrator(frameRef: React.RefObject<Frame>, enabled: boolean) {
  const [log, setLog] = useState<LogEntry[]>([]);
  const [config, setConfigState] = useState<NarratorConfig>(DEFAULT_CONFIG);

  const configRef = useRef(config);
  configRef.current = config;

  const trackerRef = useRef(createEventTracker());
  const generatorRef = useRef(createLineGenerator(() => configRef.current));
  /** `key` is the sorted track-id set, joined — cheap way to detect "same cast". */
  const candidateRef = useRef<{ key: string; since: number } | null>(null);
  const queueRef = useRef<NarrationEvent[]>([]);
  const lastSpokeAtRef = useRef(0);

  // Load persisted settings once on mount.
  useEffect(() => setConfigState(loadConfig()), []);

  const setConfig = useCallback((patch: Partial<NarratorConfig>) => {
    // Must run synchronously inside the click that enabled voice — browsers
    // only unlock speech from a real user gesture.
    if (patch.voice_enabled) primeSpeech();
    if (patch.voice_enabled === false) stopSpeaking();
    setConfigState((prev) => {
      const next = { ...prev, ...patch };
      saveConfig(next);
      return next;
    });
  }, []);

  useEffect(() => {
    if (!enabled) return;

    const id = setInterval(() => {
      const now = performance.now();
      const cfg = configRef.current;

      const tracks = frameRef.current.tracks;
      const key = tracks.map((t) => t.id).sort((a, b) => a - b).join(',');

      // Track how long the current cast of track ids has held.
      const candidate = candidateRef.current;
      if (!candidate || candidate.key !== key) {
        candidateRef.current = { key, since: now };
        return;
      }
      if (now - candidate.since >= STABLE_MS) {
        const events = trackerRef.current.update(
          tracks,
          now,
          cfg.idle_escalation_minutes * 60_000,
        );
        if (events.length > 0) queueRef.current.push(...events);
      }

      // Rate limit: at most one line per min_seconds_between_lines.
      if (queueRef.current.length === 0) return;
      if (now - lastSpokeAtRef.current < cfg.min_seconds_between_lines * 1000) return;

      const queued = [...queueRef.current].sort(byInterest);
      queueRef.current = [];
      const [primary, secondary] = queued;

      let text = generatorRef.current.generateLine(primary);
      if (secondary) {
        text += ` ${generatorRef.current.foldLine(secondary)}`;
      }

      lastSpokeAtRef.current = now;

      const entry: LogEntry = {
        id: nextLogId(),
        text,
        boring: queued.map(literalLine).join(' '),
        debug: queued.map(debugLine).join('\n'),
        at: Date.now(),
      };

      if (cfg.voice_enabled) speak(text);
      setLog((prev) => [entry, ...prev].slice(0, 8));
    }, SAMPLE_MS);

    return () => clearInterval(id);
  }, [enabled, frameRef]);

  // Reset the narrator's memory when it's switched off, so re-enabling it
  // reintroduces the scene instead of silently assuming you heard it already.
  useEffect(() => {
    if (enabled) return;
    stopSpeaking();
    trackerRef.current.reset();
    generatorRef.current.reset();
    candidateRef.current = null;
    queueRef.current = [];
  }, [enabled]);

  return { log, config, setConfig };
}
