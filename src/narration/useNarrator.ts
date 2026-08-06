import { useCallback, useEffect, useRef, useState } from 'react';
import type { Frame } from '../vision/types';
import { toSceneState, sameScene } from './describeScene';
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
import type { DemoController } from '../demo/controller';

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
  /** Demo layer only: released late by lag mode, styled as past tense. */
  lagged?: boolean;
  /** Demo layer only: a line the failure modes authored rather than the scene. */
  kind?: 'ghost' | 'denial' | 'redemption';
}

/**
 * Watches the detection stream and narrates when the scene *changes and settles*.
 *
 * The pipeline is: settled scene -> structured events (truth) -> styled line
 * (voice). The two stages are deliberately separate, so "boring mode" can show
 * the raw event for the same log row and prove the detection is real.
 */
export function useNarrator(
  frameRef: React.RefObject<Frame>,
  enabled: boolean,
  /** Present only under `?demo=broken`. Null in every normal session. */
  demo: DemoController | null = null,
) {
  const [log, setLog] = useState<LogEntry[]>([]);
  const [config, setConfigState] = useState<NarratorConfig>(DEFAULT_CONFIG);

  const configRef = useRef(config);
  configRef.current = config;

  const trackerRef = useRef(createEventTracker());
  const generatorRef = useRef(createLineGenerator(() => configRef.current));
  const candidateRef = useRef<{ counts: Record<string, number>; since: number } | null>(null);
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

      // Lines the demo layer owes us: lag releases, ghosts, denial, redemption.
      // Drained first so they land in order even if the narrator says nothing.
      if (demo) {
        const owed = demo.takePending(now);
        if (owed.length > 0) {
          setLog((prev) => [...owed.reverse(), ...prev].slice(0, 8));
          if (cfg.voice_enabled) for (const e of owed) speak(e.text);
        }
        // The redemption shot owns the screen. One line, nothing else.
        if (demo.isSuppressed()) return;
      }

      // In broken mode the narrator reads the *corrupted* frame, so a mug
      // mislabelled as a toilet is a toilet in the boxes and in the log.
      const detections = (demo?.current() ?? frameRef.current).detections;
      const counts = toSceneState(detections);

      // Track how long the current arrangement has held.
      const candidate = candidateRef.current;
      if (!candidate || !sameScene(candidate.counts, counts)) {
        candidateRef.current = { counts, since: now };
        return;
      }
      if (now - candidate.since >= STABLE_MS) {
        const events = trackerRef.current.update(
          counts,
          detections,
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

      // The broken banks get first refusal; anything they have no line for
      // falls through to the real voice, unchanged.
      let text = demo?.brokenLine(primary) ?? generatorRef.current.generateLine(primary);
      if (secondary) {
        const fold = demo?.brokenLine(secondary);
        text += ` ${fold ? `also, ${fold}` : generatorRef.current.foldLine(secondary)}`;
      }

      lastSpokeAtRef.current = now;

      const entry: LogEntry = {
        id: nextLogId(),
        text,
        boring: queued.map(literalLine).join(' '),
        debug: queued.map(debugLine).join('\n'),
        at: Date.now(),
      };

      // Lag mode holds the row back and releases it with its original
      // timestamp intact. The boxes stay live; only the story is late.
      if (demo?.bufferLog(entry, now)) return;

      if (cfg.voice_enabled) speak(text);
      setLog((prev) => [entry, ...prev].slice(0, 8));
    }, SAMPLE_MS);

    return () => clearInterval(id);
  }, [enabled, frameRef, demo]);

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
