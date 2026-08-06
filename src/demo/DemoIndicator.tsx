import type { DemoController } from './controller';
import { useDemoModes, useRedemptionState } from './useDemoMode';
import type { FailureMode } from './config';

const LABELS: Record<FailureMode, string> = {
  mislabel: '1 mislabel',
  lag: '2 lag',
  ghost: '3 ghost',
  denial: '4 denial',
};

/**
 * Rehearsal-only readout of what is currently sabotaged.
 *
 * Hidden unless `?hud=1`. While filming the sabotage must be invisible in the
 * recording — the audience finds out the same moment the narrator doesn't.
 */
export function DemoIndicator({ demo }: { demo: DemoController | null }) {
  const modes = useDemoModes(demo);
  const redemption = useRedemptionState(demo);

  if (!demo || !demo.hudVisible) return null;

  return (
    <div className="demo-indicator" aria-hidden="true">
      <span className="demo-indicator-title">DEMO</span>
      {modes.length === 0 && redemption === 'idle' && <span className="demo-chip-off">clean</span>}
      {(['mislabel', 'lag', 'ghost', 'denial'] as FailureMode[])
        .filter((m) => modes.includes(m))
        .map((m) => (
          <span key={m} className="demo-chip">{LABELS[m]}</span>
        ))}
      {redemption !== 'idle' && (
        <span className="demo-chip demo-chip-redeem">
          0 redemption · {redemption}
        </span>
      )}
    </div>
  );
}
