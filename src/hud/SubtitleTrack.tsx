import { useEffect, useRef, useState } from 'react';
import type { LogEntry } from '../narration/useNarrator';

interface Props {
  log: LogEntry[];
  boring: boolean;
  visible: boolean;
}

/** How long a line stays on screen if nothing replaces it — matched to the
 * narrator's own default rate limit (min_seconds_between_lines) plus a little
 * air, so a caption doesn't outlive the line it belongs to nor vanish early. */
const DISPLAY_MS = 4500;

/**
 * The narration line, rendered large and legible over the video frame.
 * Anchored to the *frame*, not to a moving box — DOM + CSS, not canvas, per
 * the project's canvas/DOM split. This is the only place most viewers will
 * ever actually read the narration, since audio has never been confirmed
 * audible from any machine this project has run on (see decisions.md D13)
 * and social video is watched muted by default anyway.
 */
export function SubtitleTrack({ log, boring, visible }: Props) {
  const [shown, setShown] = useState<LogEntry | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    const latest = log[0];
    if (!latest) return;
    setShown(latest);
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setShown(null), DISPLAY_MS);
    return () => clearTimeout(timerRef.current);
  }, [log]);

  if (!visible || !shown) return null;

  return (
    <div className="subtitle-track" key={shown.id}>
      <span className="subtitle-text">{boring ? shown.boring : shown.text}</span>
    </div>
  );
}
