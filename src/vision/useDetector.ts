import { useEffect, useRef, useState } from 'react';
import * as tf from '@tensorflow/tfjs';
import * as cocoSsd from '@tensorflow-models/coco-ssd';
import type { Detection, Frame } from './types';
import { updateTracks } from './tracker';

const MIN_SCORE = 0.5;
const MAX_DETECTIONS = 12;
/** Smoothing factor for the FPS readout — low = calmer number. */
const FPS_SMOOTHING = 0.1;

export type ModelStatus = 'idle' | 'loading' | 'ready' | 'error';

/**
 * Runs COCO-SSD over the video element in a requestAnimationFrame loop.
 *
 * Detections land in a ref (`frameRef`) rather than React state: the HUD reads
 * them from its own draw loop, so re-rendering React 30x/second would be pure
 * waste. Only the low-frequency stats are mirrored into state for the panel.
 */
export function useDetector(
  videoRef: React.RefObject<HTMLVideoElement | null>,
  active: boolean,
) {
  const [status, setStatus] = useState<ModelStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState({ fps: 0, inferenceMs: 0, trackMs: 0, count: 0 });
  const frameRef = useRef<Frame>({ detections: [], tracks: [], inferenceMs: 0, fps: 0 });
  const modelRef = useRef<cocoSsd.ObjectDetection | null>(null);
  const tracksRef = useRef<Frame['tracks']>([]);
  const nextTrackIdRef = useRef(1);

  // Load the model once, as soon as the app is switched on.
  useEffect(() => {
    if (!active || modelRef.current) return;
    let cancelled = false;

    (async () => {
      setStatus('loading');
      try {
        await tf.setBackend('webgl');
        await tf.ready();
        // lite_mobilenet_v2 is the smallest/fastest COCO-SSD variant — the
        // right trade for a live HUD where latency beats a few accuracy points.
        // Day 6 A/B'd `mobilenet_v2` against this — measured ~50% higher
        // inference (11ms -> 16-17ms) for accuracy this environment couldn't
        // verify (no real webcam scene to test bed/table confusion against).
        // Reverted; see decisions.md.
        const model = await cocoSsd.load({ base: 'lite_mobilenet_v2' });
        if (cancelled) return;
        modelRef.current = model;
        setStatus('ready');
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setStatus('error');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [active]);

  // The detect loop.
  useEffect(() => {
    if (!active || status !== 'ready') return;

    let raf = 0;
    let running = true;
    let lastTs = performance.now();
    let smoothedFps = 0;
    let statsTick = 0;

    const tick = async () => {
      if (!running) return;
      const video = videoRef.current;
      const model = modelRef.current;

      if (video && model && video.readyState >= 2) {
        const t0 = performance.now();
        let raw: cocoSsd.DetectedObject[] = [];
        try {
          raw = await model.detect(video, MAX_DETECTIONS, MIN_SCORE);
        } catch {
          // A dropped frame is not worth killing the loop over.
        }
        const t1 = performance.now();

        const detections: Detection[] = raw.map((d) => ({
          label: d.class,
          score: d.score,
          bbox: d.bbox as [number, number, number, number],
        }));

        const dt = t1 - lastTs;
        lastTs = t1;
        const instantFps = dt > 0 ? 1000 / dt : 0;
        smoothedFps = smoothedFps === 0
          ? instantFps
          : smoothedFps + (instantFps - smoothedFps) * FPS_SMOOTHING;

        const t2 = performance.now();
        tracksRef.current = updateTracks(tracksRef.current, detections, dt, () => nextTrackIdRef.current++);
        const trackMs = performance.now() - t2;

        frameRef.current = {
          detections,
          tracks: tracksRef.current,
          inferenceMs: t1 - t0,
          fps: smoothedFps,
        };

        // Push to React ~4x/second, not every frame.
        if (++statsTick % 8 === 0) {
          setStats({
            fps: smoothedFps,
            inferenceMs: t1 - t0,
            trackMs,
            count: detections.length,
          });
        }
      }

      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => {
      running = false;
      cancelAnimationFrame(raf);
      tracksRef.current = [];
      frameRef.current = { detections: [], tracks: [], inferenceMs: 0, fps: 0 };
    };
  }, [active, status, videoRef]);

  return { frameRef, status, error, stats };
}
