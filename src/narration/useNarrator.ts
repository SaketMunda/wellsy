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

/** How often we sample the frame for scene changes. */
const SAMPLE_MS = 250;
/** A scene must hold this long before we'll talk about it — kills flicker. */
const STABLE_MS = 900;

export interface LogEntry {
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
  const candidateRef = useRef<{ counts: Record<string, number>; since: number } | null>(null);
  const queueRef = useRef<NarrationEvent[]>([]);
  const lastSpokeAtRef = useRef(0);

  // Load persisted settings once on mount.
  useEffect(() => setConfigState(loadConfig()), []);

  const setConfig = useCallback((patch: Partial<NarratorConfig>) => {
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
      const detections = frameRef.current.detections;
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

      let text = generatorRef.current.generateLine(primary);
      if (secondary) text += ` ${generatorRef.current.foldLine(secondary)}`;

      lastSpokeAtRef.current = now;
      if (cfg.voice_enabled) speak(text);

      const entry: LogEntry = {
        text,
        boring: queued.map(literalLine).join(' '),
        debug: queued.map(debugLine).join('\n'),
        at: Date.now(),
      };
      setLog((prev) => [entry, ...prev].slice(0, 8));
    }, SAMPLE_MS);

    return () => clearInterval(id);
  }, [enabled, frameRef]);

  // Reset the narrator's memory when it's switched off, so re-enabling it
  // reintroduces the scene instead of silently assuming you heard it already.
  useEffect(() => {
    if (enabled) return;
    window.speechSynthesis?.cancel();
    trackerRef.current.reset();
    generatorRef.current.reset();
    candidateRef.current = null;
    queueRef.current = [];
  }, [enabled]);

  return { log, config, setConfig };
}

/** Picks the least theatrical English voice available. Deadpan needs a flat read. */
function pickVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis?.getVoices?.() ?? [];
  const english = voices.filter((v) => v.lang?.toLowerCase().startsWith('en'));
  if (english.length === 0) return null;
  const novelty = /bubbles|jester|zarvox|bells|boing|trinoids|whisper|good news|bad news|wobble|superstar/i;
  const plain = english.filter((v) => !novelty.test(v.name));
  return plain.find((v) => v.default) ?? plain[0] ?? english[0];
}

function speak(text: string) {
  const synth = window.speechSynthesis;
  if (!synth) return;
  // Never let speech lag more than one line behind the log.
  synth.cancel();
  const utter = new SpeechSynthesisUtterance(text);
  const voice = pickVoice();
  if (voice) utter.voice = voice;
  utter.rate = 0.9;
  utter.pitch = 1.0;
  synth.speak(utter);
}
