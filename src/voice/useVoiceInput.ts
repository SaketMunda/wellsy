import { useCallback, useEffect, useRef, useState } from 'react';
import { getAsrEngine, resampleTo16kMono, type AsrStatus } from './speechToText';

export type MicStatus = 'idle' | 'starting' | 'ready' | 'denied' | 'error';
export type RecordingState = 'idle' | 'recording' | 'transcribing';

/**
 * Hard ceiling on one push-to-talk press. A held key that never gets a
 * matching keyup (alt-tab, focus loss, a stuck key event) must not record
 * forever — this guarantees the mic releases itself even if nothing else does.
 */
const MAX_RECORDING_MS = 12_000;

/**
 * Push-to-talk: hold to record, release to transcribe. Owns its own audio
 * `MediaStream` — a second `getUserMedia` prompt, separate from
 * `useCamera`'s video-only one (D6). Mic permission denial is handled the
 * same way `useCamera` handles camera denial: a stated reason, never a
 * crash, and everything else keeps working with the mic refused.
 *
 * Recording -> transcription is a request-response the user is actively
 * waiting on, so unlike narration's generate-ahead model this is fine to
 * await plainly (see decisions.md Day 6) — there is no 250ms sampler to
 * protect here.
 */
export function useVoiceInput(onResult: (transcript: string) => void) {
  const [micStatus, setMicStatus] = useState<MicStatus>('idle');
  const [micError, setMicError] = useState<string | null>(null);
  const [recording, setRecording] = useState<RecordingState>('idle');
  const [asrStatus, setAsrStatus] = useState<AsrStatus>({ state: 'idle', progress: 0, lastTranscribeMs: null });

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;
  /**
   * Set the instant `stop()` is called. `start()` is async (it awaits mic
   * permission), so a fast press-release can call `stop()` before the
   * `MediaRecorder` even exists — without this flag, `stop()` would find
   * nothing to stop, and the recorder that starts moments later would keep
   * recording with no keyup left to end it. Checked at both points `start()`
   * could otherwise win the race: right after `ensureStream()` resolves, and
   * right after the recorder starts.
   */
  const stopRequestedRef = useRef(false);
  const maxDurationTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const ensureStream = useCallback(async (): Promise<MediaStream | null> => {
    if (streamRef.current) return streamRef.current;
    setMicStatus('starting');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      setMicStatus('ready');
      return stream;
    } catch (err) {
      const e = err as DOMException;
      setMicError(e.message ?? String(err));
      setMicStatus(e.name === 'NotAllowedError' ? 'denied' : 'error');
      return null;
    }
  }, []);

  const handleStop = useCallback(async () => {
    clearTimeout(maxDurationTimerRef.current);
    setRecording('transcribing');
    try {
      const mimeType = recorderRef.current?.mimeType;
      const blob = new Blob(chunksRef.current, mimeType ? { type: mimeType } : undefined);
      chunksRef.current = [];
      if (blob.size === 0) return;

      const AudioCtor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioCtor) return;
      const ctx = new AudioCtor();
      const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
      await ctx.close();
      const audio = await resampleTo16kMono(decoded);

      const engine = getAsrEngine(setAsrStatus);
      const text = (await engine.transcribe(audio)).trim();
      if (text) onResultRef.current(text);
    } catch (err) {
      console.warn('local ASR failed:', err);
    } finally {
      setRecording('idle');
    }
  }, []);

  /** Shared by `stop()` and the max-duration safety timer — defined once so neither can drift out of sync with the other. */
  const stopRecorder = useCallback(() => {
    stopRequestedRef.current = true;
    clearTimeout(maxDurationTimerRef.current);
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === 'inactive') return;
    recorder.stop();
  }, []);

  const start = useCallback(async () => {
    if (recording !== 'idle') return;
    stopRequestedRef.current = false;
    const stream = await ensureStream();
    if (!stream) return;
    // The user already released the key while we were waiting on mic
    // permission/the stream — don't start recording at all.
    if (stopRequestedRef.current) return;
    try {
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        void handleStop();
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording('recording');
      // The user released between the check above and here — stop immediately.
      if (stopRequestedRef.current) {
        recorder.stop();
      } else {
        maxDurationTimerRef.current = setTimeout(() => {
          console.warn('push-to-talk exceeded the max recording duration — auto-stopping.');
          stopRecorder();
        }, MAX_RECORDING_MS);
      }
    } catch (err) {
      setMicError(err instanceof Error ? err.message : String(err));
      setMicStatus('error');
    }
  }, [recording, ensureStream, handleStop, stopRecorder]);

  const stop = useCallback(() => {
    stopRecorder();
  }, [stopRecorder]);

  // Release the mic stream on unmount only — held across pushes so a second
  // press doesn't re-prompt for permission.
  useEffect(
    () => () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    },
    [],
  );

  return { start, stop, micStatus, micError, recording, asrStatus };
}
