import { useEffect, useRef, useState } from 'react';
import type { LogEntry } from '../narration/useNarrator';

export interface Transcript {
  text: string;
  at: number;
}

interface Props {
  log: LogEntry[];
  boring: boolean;
  visible: boolean;
  /** The user's own last push-to-talk transcript, shown separately from YAP's line. */
  transcript?: Transcript | null;
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
 *
 * Day 6 adds the user's own transcript (push-to-talk) as a second, visually
 * distinct row — right-aligned, dimmer, `>` prefixed — so a silent screen
 * recording reads as an actual back-and-forth, not just YAP talking.
 */
export function SubtitleTrack({ log, boring, visible, transcript }: Props) {
  const [shown, setShown] = useState<LogEntry | null>(null);
  const [shownTranscript, setShownTranscript] = useState<Transcript | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const transcriptTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    const latest = log[0];
    if (!latest) return;
    setShown(latest);
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setShown(null), DISPLAY_MS);
    return () => clearTimeout(timerRef.current);
  }, [log]);

  useEffect(() => {
    if (!transcript) return;
    setShownTranscript(transcript);
    clearTimeout(transcriptTimerRef.current);
    transcriptTimerRef.current = setTimeout(() => setShownTranscript(null), DISPLAY_MS);
    return () => clearTimeout(transcriptTimerRef.current);
  }, [transcript]);

  if (!visible || (!shown && !shownTranscript)) return null;

  return (
    <div className="subtitle-track">
      {shownTranscript && (
        <div className="subtitle-transcript" key={shownTranscript.at}>
          <span className="subtitle-transcript-text">&gt; {shownTranscript.text}</span>
        </div>
      )}
      {shown && (
        <div className="subtitle-line" key={shown.id}>
          <span className="subtitle-text">{boring ? shown.boring : shown.text}</span>
        </div>
      )}
    </div>
  );
}
