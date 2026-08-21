import { useEffect, useRef, useState } from 'react';
import type { Detection, Frame, Track } from './types';

export type EngineStatus = 'idle' | 'loading' | 'ready' | 'stale' | 'error';

/** engine/bridge.py's payload — a superset of the stdout JSONL record
 * (decisions.md D35), plus the coordinate-contract fields
 * (day9-prompt.md Part 1) the client needs to rescale boxes into the
 * browser's own video element's pixel space. */
interface EngineVoiceExchange {
  transcript: string;
  answer: string;
  /** Python `time.time()` epoch seconds, not ms — converted on read. */
  at: number;
}

interface EngineMessage {
  t: number;
  motion: number;
  gated: boolean;
  captureMs: number;
  gateMs: number;
  detections: Detection[];
  tracks: Track[];
  inferenceMs: number | null;
  sourceWidth: number;
  sourceHeight: number;
  voice?: EngineVoiceExchange | null;
}

/** localhost only (decisions.md D10/D35) — never configurable to a LAN/host
 * address from this app. */
const ENGINE_URL = 'ws://127.0.0.1:8765';

/** No message for this long means the engine is dead or stuck — the HUD must
 * say so rather than holding a beautiful stale frame forever (day9-prompt.md,
 * same discipline as UNIDENTIFIED, D22). */
const STALE_AFTER_MS = 1000;
const STALE_CHECK_INTERVAL_MS = 250;

const EMPTY_FRAME: Frame = { detections: [], tracks: [], inferenceMs: 0, fps: 0 };

/**
 * Alternative to `useDetector` (`?engine=1`) — same `Frame`-shaped output,
 * sourced from the Python engine over a local WebSocket instead of an
 * in-browser TF.js model. `HudCanvas`/`drawHud`/`hudState.ts` don't know or
 * care which hook produced `frameRef`; that's the seam day9-prompt.md is
 * testing.
 *
 * Camera architecture (A): this hook does not open the camera — `useCamera`
 * still owns the browser's own video element for display. This hook only
 * supplies boxes, rescaled from the engine's own capture resolution
 * (`sourceWidth`/`sourceHeight`) into the *displayed* video's pixel space,
 * so a resolution mismatch between the two independent camera readers is a
 * non-event rather than a coordinate bug.
 */
export function useEngineSocket(videoRef: React.RefObject<HTMLVideoElement | null>, active: boolean) {
  const [status, setStatus] = useState<EngineStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState({ fps: 0, inferenceMs: 0, trackMs: 0, count: 0 });
  const [voice, setVoice] = useState<EngineVoiceExchange | null>(null);
  const frameRef = useRef<Frame>(EMPTY_FRAME);
  const lastMessageAtRef = useRef(0);
  const lastInferenceMsRef = useRef(0);
  const lastVoiceAtRef = useRef(0);
  const msgTimesRef = useRef<number[]>([]);

  useEffect(() => {
    if (!active) {
      frameRef.current = EMPTY_FRAME;
      setStatus('idle');
      return;
    }

    let cancelled = false;
    let ws: WebSocket | null = null;
    let everReady = false;
    setStatus('loading');

    try {
      ws = new WebSocket(ENGINE_URL);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus('error');
      return;
    }

    ws.onopen = () => {
      if (cancelled) return;
      everReady = true;
      setStatus('ready');
    };

    // A hard socket close (the engine process killed, network dropped) fires
    // immediately — much faster than the ~1s staleness timer below would
    // ever notice on its own. If the engine was never ready in the first
    // place, this is a real connection failure ('error', the curtain-error
    // UI). If it *was* ready, this is the "engine died on camera" case
    // day9-prompt.md names explicitly: the HUD should degrade to 'stale'
    // (last-known frame, visibly marked old), not jump to a scary error
    // screen — the frame data in frameRef is still real, just aging.
    ws.onerror = () => {
      if (cancelled) return;
      if (!everReady) {
        setError('engine socket error — is `uv run main.py` running?');
        setStatus('error');
      }
    };

    ws.onclose = () => {
      if (cancelled) return;
      setStatus(everReady ? 'stale' : 'error');
    };

    // Latest-wins by construction (D29's rule, crossing the socket): this
    // handler just overwrites frameRef.current every time it fires. There is
    // no queue to grow — the browser's own event loop can only deliver one
    // onmessage at a time, and each one fully replaces the last, never
    // appends. A message that arrives while the previous one is still
    // "unprocessed" (i.e. before the next render tick reads frameRef) is
    // exactly the case this discipline exists for: the older one is dropped
    // by simply being overwritten, never buffered or drawn.
    ws.onmessage = (ev) => {
      if (cancelled) return;
      let msg: EngineMessage;
      try {
        msg = JSON.parse(ev.data as string);
      } catch {
        return;
      }

      const now = performance.now();
      lastMessageAtRef.current = now;
      msgTimesRef.current.push(now);
      while (msgTimesRef.current.length && now - msgTimesRef.current[0] > 1000) {
        msgTimesRef.current.shift();
      }

      const video = videoRef.current;
      const scaleX = video && video.videoWidth > 0 ? video.videoWidth / msg.sourceWidth : 1;
      const scaleY = video && video.videoHeight > 0 ? video.videoHeight / msg.sourceHeight : 1;
      const rescale = (bbox: [number, number, number, number]): [number, number, number, number] => [
        bbox[0] * scaleX,
        bbox[1] * scaleY,
        bbox[2] * scaleX,
        bbox[3] * scaleY,
      ];

      const detections = msg.detections.map((d) => ({ ...d, bbox: rescale(d.bbox) }));
      const tracks = msg.tracks.map((t) => ({ ...t, bbox: rescale(t.bbox) }));

      if (msg.inferenceMs !== null) lastInferenceMsRef.current = msg.inferenceMs;

      // `voice` only changes when T3 actually speaks (roughly once per
      // exchange, not once per ~125ms broadcast) -- dedupe on `at` so this
      // doesn't re-trigger SubtitleTrack's display timer on every frame.
      if (msg.voice && msg.voice.at !== lastVoiceAtRef.current) {
        lastVoiceAtRef.current = msg.voice.at;
        setVoice(msg.voice);
      }

      frameRef.current = {
        detections,
        tracks,
        inferenceMs: lastInferenceMsRef.current,
        fps: msgTimesRef.current.length,
      };

      setStatus((s) => (s === 'ready' || s === 'stale' ? 'ready' : s));
      setStats({
        fps: msgTimesRef.current.length,
        inferenceMs: lastInferenceMsRef.current,
        trackMs: 0, // tracking already happens inside the engine's own inferenceMs — no separate number to show
        count: tracks.length,
      });
    };

    const staleCheck = window.setInterval(() => {
      if (cancelled || lastMessageAtRef.current === 0) return;
      const idleMs = performance.now() - lastMessageAtRef.current;
      setStatus((s) => {
        if (s === 'error' || s === 'idle' || s === 'loading') return s;
        return idleMs > STALE_AFTER_MS ? 'stale' : 'ready';
      });
    }, STALE_CHECK_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(staleCheck);
      ws?.close();
      frameRef.current = EMPTY_FRAME;
      lastMessageAtRef.current = 0;
      lastVoiceAtRef.current = 0;
      msgTimesRef.current = [];
    };
  }, [active, videoRef]);

  return { frameRef, status, error, stats, voice };
}
