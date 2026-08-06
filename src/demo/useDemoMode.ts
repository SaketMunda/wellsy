import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { createDemoController, type DemoController } from './controller';
import { isDemoArmed, isDemoHudVisible, readDemoConfig, type FailureMode } from './config';

/** `1`-`4` toggle a failure, `0` redeems, `9` resets. Nothing else is bound. */
const KEY_TO_MODE: Record<string, FailureMode> = {
  '1': 'mislabel',
  '2': 'lag',
  '3': 'ghost',
  '4': 'denial',
};

/**
 * Builds the controller once, at module-evaluation time for this hook, and only
 * if the URL says so. No `?demo=broken`, no controller, no key listener, no
 * behaviour change of any kind.
 */
function build(): DemoController | null {
  if (typeof window === 'undefined') return null;
  const params = new URLSearchParams(window.location.search);
  if (!isDemoArmed(params)) return null;
  return createDemoController(readDemoConfig(params), isDemoHudVisible(params));
}

export function useDemoMode(): DemoController | null {
  const ref = useRef<DemoController | null | undefined>(undefined);
  if (ref.current === undefined) ref.current = build();
  const demo = ref.current;

  useEffect(() => {
    if (!demo) return;

    const onKey = (e: KeyboardEvent) => {
      // Never steal a keystroke from a real input, and leave browser shortcuts
      // alone — a stray cmd+1 mid-take should switch tabs, not mislabel a mug.
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;

      const mode = KEY_TO_MODE[e.key];
      if (mode) demo.toggle(mode);
      else if (e.key === '0') demo.redeem();
      else if (e.key === '9') demo.reset();
      else return;
      e.preventDefault();
    };

    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [demo]);

  return demo;
}

/** Re-renders the indicator when modes change, without touching the draw loop. */
export function useDemoModes(demo: DemoController | null): FailureMode[] {
  const empty = useRef<FailureMode[]>([]).current;
  const snapshot = useRef<FailureMode[]>(empty);

  return useSyncExternalStore(
    (fn) => demo?.subscribe(fn) ?? (() => {}),
    () => {
      if (!demo) return empty;
      const next = demo.activeModes();
      // useSyncExternalStore demands a referentially stable snapshot.
      const prev = snapshot.current;
      if (prev.length === next.length && prev.every((m, i) => m === next[i])) return prev;
      snapshot.current = next;
      return next;
    },
    () => empty,
  );
}

/** Same store, for the redemption pill. */
export function useRedemptionState(demo: DemoController | null) {
  const [state, setState] = useState(() => demo?.redemptionState() ?? 'idle');
  useEffect(() => {
    if (!demo) return;
    return demo.subscribe(() => setState(demo.redemptionState()));
  }, [demo]);
  return state;
}
