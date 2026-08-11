import type { LogEntry } from '../narration/useNarrator';
import type { NarratorConfig } from '../narration/config';
import type { LlmStatus } from '../narration/llmLineGenerator';
import type { TtsStatus } from '../narration/speech';

interface Props {
  fps: number;
  inferenceMs: number;
  hudDrawMs: number;
  count: number;
  modelStatus: string;
  cameraStatus: string;
  log: LogEntry[];
  boring: boolean;
  onToggleBoring: () => void;
  config: NarratorConfig;
  onConfigChange: (patch: Partial<NarratorConfig>) => void;
  llmStatus: LlmStatus;
  ttsStatus: TtsStatus;
}

/** `loading` engines get a live percentage; everything else is a fixed word. */
function engineLabel(state: string, progress: number): string {
  return state === 'loading' ? `loading ${Math.round(progress * 100)}%` : state;
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
  hudDrawMs,
  count,
  modelStatus,
  cameraStatus,
  log,
  boring,
  onToggleBoring,
  config,
  onConfigChange,
  llmStatus,
  ttsStatus,
}: Props) {
  return (
    <aside className="panel">
      <div className="panel-block">
        <h2>Telemetry</h2>
        <Stat label="FPS" value={fps.toFixed(1)} warn={fps > 0 && fps < 10} />
        <Stat label="Inference" value={`${inferenceMs.toFixed(0)} ms`} warn={inferenceMs > 100} />
        <Stat label="HUD draw" value={`${hudDrawMs.toFixed(1)} ms`} warn={hudDrawMs > 8} />
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
            Boring mode: {boring ? 'on' : 'off'}
          </button>
          <button
            className="chip"
            onClick={() => onConfigChange({ voice_enabled: !config.voice_enabled })}
            aria-pressed={config.voice_enabled}
            title="Speaks each line out loud, via whichever voice engine is selected below"
          >
            Voice: {config.voice_enabled ? 'on' : 'off'}
          </button>
          <button
            className="chip"
            onClick={() =>
              onConfigChange({ spice_level: (((config.spice_level + 1) % 3) as 0 | 1 | 2) })
            }
          >
            Spice: {config.spice_level}
          </button>
        </div>
      </div>

      <div className="panel-block">
        <h2>Engines</h2>
        <div className="narrator-controls">
          <button
            className="chip"
            onClick={() =>
              onConfigChange({
                line_generator_engine:
                  config.line_generator_engine === 'template' ? 'local-llm' : 'template',
              })
            }
            aria-pressed={config.line_generator_engine === 'local-llm'}
            title="template: authored line bank, sub-millisecond. local-llm: on-device model, generated ahead of its slot"
          >
            Lines: {config.line_generator_engine}
          </button>
          <button
            className="chip"
            onClick={() =>
              onConfigChange({
                voice_engine: config.voice_engine === 'system' ? 'local-tts' : 'system',
              })
            }
            aria-pressed={config.voice_engine === 'local-tts'}
            title="system: browser speechSynthesis. local-tts: on-device neural voice (Kokoro)"
          >
            Voice engine: {config.voice_engine}
          </button>
        </div>
        {config.line_generator_engine === 'local-llm' && (
          <>
            <Stat label="LLM" value={engineLabel(llmStatus.state, llmStatus.progress)} warn={llmStatus.state === 'error'} />
            <Stat
              label="LLM latency"
              value={llmStatus.lastInferenceMs === null ? '—' : `${llmStatus.lastInferenceMs.toFixed(0)} ms`}
            />
          </>
        )}
        {config.voice_engine === 'local-tts' && (
          <>
            <Stat label="TTS" value={engineLabel(ttsStatus.state, ttsStatus.progress)} warn={ttsStatus.state === 'error'} />
            <Stat
              label="TTS latency"
              value={ttsStatus.lastSynthMs === null ? '—' : `${ttsStatus.lastSynthMs.toFixed(0)} ms`}
            />
          </>
        )}
      </div>

      <div className="panel-block panel-log">
        <h2>{boring ? 'Detection log' : 'Narration log'}</h2>
        {log.length === 0 ? (
          <p className="log-empty">Awaiting first observation…</p>
        ) : (
          <ul>
            {log.map((entry) => (
              <li key={entry.id} title={entry.debug}>
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
