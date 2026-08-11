import { useEffect, useRef } from 'react';
import type { Frame } from '../vision/types';
import { drawHud } from './drawHud';
import { EMPTY_HUD_STATE, updateHudState } from './hudState';

interface Props {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  frameRef: React.RefObject<Frame>;
  active: boolean;
  reducedMotion: boolean;
  /** Rolling HUD draw-time in ms, mirrored into state at ~4Hz for the panel. */
  onDrawMs?: (ms: number) => void;
}

/** Guards against a huge dt after a backgrounded tab regains focus — without
 * this a lock-on animation would visibly teleport through its whole arc in
 * one tick instead of just resuming. */
const MAX_DT_MS = 100;

/**
 * The overlay canvas. Runs its own rAF loop so it can animate smoothly
 * (scanline, chrome, lock-on) even when detection is running slower than
 * display refresh. Owns the HUD's own render-state (`hudState.ts`) — memory
 * the stateless `drawHud` painter and the tracker deliberately don't keep.
 */
export function HudCanvas({ videoRef, frameRef, active, reducedMotion, onDrawMs }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const hudStateRef = useRef(EMPTY_HUD_STATE);

  useEffect(() => {
    if (!active) {
      hudStateRef.current = EMPTY_HUD_STATE;
      return;
    }
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;

    let raf = 0;
    let lastT = performance.now();
    let drawTick = 0;
    let smoothedDrawMs = 0;

    const render = (t: number) => {
      const video = videoRef.current;
      const dtMs = Math.min(MAX_DT_MS, Math.max(0, t - lastT));
      lastT = t;

      if (video && video.videoWidth > 0) {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const cssW = video.clientWidth;
        const cssH = video.clientHeight;

        if (canvas.width !== cssW * dpr || canvas.height !== cssH * dpr) {
          canvas.width = cssW * dpr;
          canvas.height = cssH * dpr;
          canvas.style.width = `${cssW}px`;
          canvas.style.height = `${cssH}px`;
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        hudStateRef.current = updateHudState(
          hudStateRef.current,
          frameRef.current,
          dtMs,
          video.videoWidth,
          video.videoHeight,
        );

        const drawStart = performance.now();
        drawHud({
          ctx,
          hudState: hudStateRef.current,
          canvasW: cssW,
          canvasH: cssH,
          scaleX: cssW / video.videoWidth,
          scaleY: cssH / video.videoHeight,
          frameW: video.videoWidth,
          frameH: video.videoHeight,
          t,
          mirrored: true,
          reducedMotion,
        });
        const drawMs = performance.now() - drawStart;
        smoothedDrawMs = smoothedDrawMs === 0 ? drawMs : smoothedDrawMs + (drawMs - smoothedDrawMs) * 0.1;

        // Report to the panel at ~4Hz, not every frame — same pattern useDetector uses for stats.
        if (onDrawMs && ++drawTick % 15 === 0) onDrawMs(smoothedDrawMs);
      }

      raf = requestAnimationFrame(render);
    };

    raf = requestAnimationFrame(render);
    return () => cancelAnimationFrame(raf);
  }, [active, videoRef, frameRef, reducedMotion, onDrawMs]);

  return <canvas ref={canvasRef} className="hud-canvas" />;
}
