import { useState } from 'react';
import { useCamera } from './vision/useCamera';
import { useDetector } from './vision/useDetector';
import { useNarrator } from './narration/useNarrator';
import { HudCanvas } from './hud/HudCanvas';
import { StatusPanel } from './hud/StatusPanel';
import './App.css';

export default function App() {
  const [active, setActive] = useState(false);
  const [narrating, setNarrating] = useState(true);
  const [boring, setBoring] = useState(false);

  const { videoRef, status: cameraStatus, error: cameraError } = useCamera(active);
  const { frameRef, status: modelStatus, error: modelError, stats } = useDetector(videoRef, active);
  const { log, config, setConfig, llmStatus, ttsStatus } = useNarrator(
    frameRef,
    active && narrating && modelStatus === 'ready',
  );

  const live = cameraStatus === 'live' && modelStatus === 'ready';
  const error = cameraError ?? modelError;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">YAP</span>
          <span className="brand-sub">Yet Another Perception · live vision overlay</span>
        </div>
        <div className="controls">
          <button
            className="btn"
            onClick={() => setNarrating((n) => !n)}
            disabled={!active}
            aria-pressed={narrating}
          >
            {narrating ? 'Narration on' : 'Narration off'}
          </button>
          <button className="btn btn-primary" onClick={() => setActive((a) => !a)}>
            {active ? 'Stop' : 'Start camera'}
          </button>
        </div>
      </header>

      <main className="stage">
        <div className="viewport">
          <video ref={videoRef} className="video" playsInline muted />
          <HudCanvas videoRef={videoRef} frameRef={frameRef} active={active} />

          {!active && (
            <div className="curtain">
              <p className="curtain-title">Perception offline</p>
              <p className="curtain-sub">
                Start the camera to begin real-time detection. Video never leaves this device.
              </p>
            </div>
          )}

          {active && !live && !error && (
            <div className="curtain">
              <p className="curtain-title">
                {modelStatus === 'loading' ? 'Loading vision model…' : 'Acquiring camera…'}
              </p>
              <p className="curtain-sub">First load pulls the model weights, then it&apos;s cached.</p>
            </div>
          )}

          {error && (
            <div className="curtain curtain-error">
              <p className="curtain-title">Signal lost</p>
              <p className="curtain-sub">{error}</p>
            </div>
          )}
        </div>

        <StatusPanel
          fps={stats.fps}
          inferenceMs={stats.inferenceMs}
          count={stats.count}
          modelStatus={modelStatus}
          cameraStatus={cameraStatus}
          log={log}
          boring={boring}
          onToggleBoring={() => setBoring((b) => !b)}
          config={config}
          onConfigChange={setConfig}
          llmStatus={llmStatus}
          ttsStatus={ttsStatus}
        />
      </main>
    </div>
  );
}
