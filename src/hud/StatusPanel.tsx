import type { LogEntry } from '../narration/useNarrator';

interface Props {
  fps: number;
  inferenceMs: number;
  count: number;
  modelStatus: string;
  cameraStatus: string;
  log: LogEntry[];
}

function Stat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value" data-warn={warn ? 'true' : undefined}>{value}</span>
    </div>
  );
}

export function StatusPanel({ fps, inferenceMs, count, modelStatus, cameraStatus, log }: Props) {
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

      <div className="panel-block panel-log">
        <h2>Narration log</h2>
        {log.length === 0 ? (
          <p className="log-empty">Awaiting first observation…</p>
        ) : (
          <ul>
            {log.map((entry) => (
              <li key={entry.at}>
                <time>{new Date(entry.at).toLocaleTimeString([], { hour12: false })}</time>
                <span>{entry.text}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
