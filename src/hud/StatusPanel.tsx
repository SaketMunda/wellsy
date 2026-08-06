import type { LogEntry } from '../narration/useNarrator';
import type { NarratorConfig } from '../narration/config';

interface Props {
  fps: number;
  inferenceMs: number;
  count: number;
  modelStatus: string;
  cameraStatus: string;
  log: LogEntry[];
  boring: boolean;
  onToggleBoring: () => void;
  config: NarratorConfig;
  onConfigChange: (patch: Partial<NarratorConfig>) => void;
}

function Stat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value" data-warn={warn ? 'true' : undefined}>{value}</span>
    </div>
  );
}

export function StatusPanel({
  fps,
  inferenceMs,
  count,
  modelStatus,
  cameraStatus,
  log,
  boring,
  onToggleBoring,
  config,
  onConfigChange,
}: Props) {
  return (
    <aside className="panel">
      <div className="panel-block">
        <h2>Telemetry</h2>
        <Stat label="FPS" value={fps.toFixed(1)} warn={fps > 0 && fps < 10} />
        <Stat label="Inference" value={`${inferenceMs.toFixed(0)} ms`} warn={inferenceMs > 100} />
        <Stat label="Targets" value={String(count)} />
      </div>

      <div className="panel-block">
        <h2>Systems</h2>
        <Stat label="Camera" value={cameraStatus} />
        <Stat label="Model" value={modelStatus} />
      </div>

      <div className="panel-block">
        <h2>Narrator</h2>
        <div className="narrator-controls">
          <button className="chip" onClick={onToggleBoring} aria-pressed={boring}>
            {boring ? 'Boring mode' : 'Boring mode off'}
          </button>
          <button
            className="chip"
            onClick={() => onConfigChange({ voice_enabled: !config.voice_enabled })}
            aria-pressed={config.voice_enabled}
          >
            {config.voice_enabled ? 'Voice on' : 'Voice off'}
          </button>
          <button
            className="chip"
            onClick={() =>
              onConfigChange({ spice_level: (((config.spice_level + 1) % 3) as 0 | 1 | 2) })
            }
          >
            Spice {config.spice_level}
          </button>
        </div>
      </div>

      <div className="panel-block panel-log">
        <h2>{boring ? 'Detection log' : 'Narration log'}</h2>
        {log.length === 0 ? (
          <p className="log-empty">Awaiting first observation…</p>
        ) : (
          <ul>
            {log.map((entry) => (
              <li key={entry.at} title={entry.debug}>
                <time>{new Date(entry.at).toLocaleTimeString([], { hour12: false })}</time>
                <span>{boring ? entry.boring : entry.text}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
