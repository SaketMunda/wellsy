/** Day 7 measurement instrumentation, gated behind ?bench=1 (see App.tsx). Not
 * a feature — this exists to produce the numbers in day7-baseline.md and
 * should stay invisible on the normal path. */

export interface BenchDump {
  /** ms between consecutive rAF callbacks on the main thread — the same
   * signal a dropped frame or a visible freeze would show up in. */
  frameDeltas: number[];
  /** PerformanceObserver('longtask') entries — anything the browser itself
   * considers a main-thread block ≥50ms. */
  longTasks: { start: number; duration: number }[];
  startedAt: number;
  dumpedAt: number;
}

const RING_SIZE = 20_000; // generous headroom for a 60s+ run at 60fps

export function createBenchRecorder() {
  const frameDeltas: number[] = [];
  const longTasks: { start: number; duration: number }[] = [];
  let last = performance.now();
  let rafId = 0;
  let observer: PerformanceObserver | null = null;
  const startedAt = performance.now();

  function tick(now: number) {
    const delta = now - last;
    last = now;
    if (frameDeltas.length < RING_SIZE) frameDeltas.push(delta);
    rafId = requestAnimationFrame(tick);
  }

  function start() {
    last = performance.now();
    rafId = requestAnimationFrame(tick);
    if ('PerformanceObserver' in window) {
      try {
        observer = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (longTasks.length < RING_SIZE) {
              longTasks.push({ start: entry.startTime, duration: entry.duration });
            }
          }
        });
        observer.observe({ type: 'longtask', buffered: true });
      } catch {
        // 'longtask' unsupported in this browser — frameDeltas alone still answers the question.
      }
    }
  }

  function stop() {
    cancelAnimationFrame(rafId);
    observer?.disconnect();
    observer = null;
  }

  function reset() {
    frameDeltas.length = 0;
    longTasks.length = 0;
  }

  function dump(): BenchDump {
    return { frameDeltas: [...frameDeltas], longTasks: [...longTasks], startedAt, dumpedAt: performance.now() };
  }

  return { start, stop, reset, dump };
}

export type BenchRecorder = ReturnType<typeof createBenchRecorder>;
