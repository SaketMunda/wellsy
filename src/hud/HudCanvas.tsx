import { useEffect, useRef } from 'react';
import type { Frame } from '../vision/types';
import type { DemoController } from '../demo/controller';
import { drawHud } from './drawHud';

interface Props {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  frameRef: React.RefObject<Frame>;
  active: boolean;
  /** Present only under `?demo=broken`. Null in every normal session. */
  demo?: DemoController | null;
}

/**
 * The overlay canvas. Runs its own rAF loop so it can animate smoothly
 * (scanline, chrome) even when detection is running slower than display
 * refresh — the boxes just hold their last known position between inferences.
 */
export function HudCanvas({ videoRef, frameRef, active, demo = null }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!active) return;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;

    let raf = 0;
    const render = (t: number) => {
      const video = videoRef.current;
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

        // Sole caller of `tick`: it advances ghost timers and the denial clock,
        // and two callers advancing them independently would drift.
        drawHud(
          ctx,
          demo ? demo.tick(frameRef.current, t) : frameRef.current,
          cssW,
          cssH,
          cssW / video.videoWidth,
          cssH / video.videoHeight,
          t,
          true,
        );
      }
      raf = requestAnimationFrame(render);
    };

    raf = requestAnimationFrame(render);
    return () => cancelAnimationFrame(raf);
  }, [active, videoRef, frameRef, demo]);

  return <canvas ref={canvasRef} className="hud-canvas" />;
}
