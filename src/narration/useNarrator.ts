import { useEffect, useRef, useState } from 'react';
import type { Frame } from '../vision/types';
import { describeScene, diffScene, sameScene, toSceneState } from './describeScene';

/** How often we sample the frame for scene changes. */
const SAMPLE_MS = 250;
/** A scene must hold this long before we'll talk about it — kills flicker. */
const STABLE_MS = 900;
/** Hard floor between two utterances, however interesting the world gets. */
const COOLDOWN_MS = 3500;

export interface LogEntry {
  text: string;
  at: number;
}

/**
 * Watches the detection stream and speaks when the scene *changes and settles*.
 *
 * The three timers above are the whole trick: without STABLE_MS the narrator
 * stutters on every flickering low-confidence box, and without COOLDOWN_MS it
 * talks over itself in a busy room.
 */
export function useNarrator(frameRef: React.RefObject<Frame>, enabled: boolean) {
  const [log, setLog] = useState<LogEntry[]>([]);
  const spokenRef = useRef<Record<string, number>>({});
  const candidateRef = useRef<{ counts: Record<string, number>; since: number } | null>(null);
  const lastSpokeAtRef = useRef(0);
  const isFirstRef = useRef(true);

  useEffect(() => {
    if (!enabled) return;

    const id = setInterval(() => {
      const now = performance.now();
      const counts = toSceneState(frameRef.current.detections);

      // Track how long the current arrangement has held.
      const candidate = candidateRef.current;
      if (!candidate || !sameScene(candidate.counts, counts)) {
        candidateRef.current = { counts, since: now };
        return;
      }
      if (now - candidate.since < STABLE_MS) return;
      if (sameScene(spokenRef.current, counts)) return;
      if (now - lastSpokeAtRef.current < COOLDOWN_MS) return;

      const scene = diffScene(spokenRef.current, counts);
      const text = describeScene(scene, isFirstRef.current);
      if (!text) return;

      spokenRef.current = counts;
      lastSpokeAtRef.current = now;
      isFirstRef.current = false;

      speak(text);
      setLog((prev) => [{ text, at: Date.now() }, ...prev].slice(0, 8));
    }, SAMPLE_MS);

    return () => clearInterval(id);
  }, [enabled, frameRef]);

  // Reset the narrator's memory when it's switched off, so re-enabling it
  // reintroduces the scene instead of silently assuming you heard it already.
  useEffect(() => {
    if (enabled) return;
    window.speechSynthesis?.cancel();
    spokenRef.current = {};
    candidateRef.current = null;
    isFirstRef.current = true;
  }, [enabled]);

  return { log };
}

function speak(text: string) {
  const synth = window.speechSynthesis;
  if (!synth) return;
  synth.cancel();
  const utter = new SpeechSynthesisUtterance(text);
  utter.rate = 1.05;
  utter.pitch = 0.9;
  synth.speak(utter);
}
