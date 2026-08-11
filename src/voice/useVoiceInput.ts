import { useCallback, useEffect, useRef, useState } from 'react';
import { getAsrEngine, resampleTo16kMono, type AsrStatus } from './speechToText';

export type MicStatus = 'idle' | 'starting' | 'ready' | 'denied' | 'error';
export type RecordingState = 'idle' | 'recording' | 'transcribing';

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

  const start = useCallback(async () => {
    if (recording !== 'idle') return;
    const stream = await ensureStream();
    if (!stream) return;
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
    } catch (err) {
      setMicError(err instanceof Error ? err.message : String(err));
      setMicStatus('error');
    }
  }, [recording, ensureStream, handleStop]);

  const stop = useCallback(() => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === 'inactive') return;
    recorder.stop();
  }, []);

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
