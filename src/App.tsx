import { useCallback, useEffect, useState } from 'react';
import { useCamera } from './vision/useCamera';
import { useDetector } from './vision/useDetector';
import { useNarrator } from './narration/useNarrator';
import { HudCanvas } from './hud/HudCanvas';
import { StatusPanel } from './hud/StatusPanel';
import { SubtitleTrack } from './hud/SubtitleTrack';
import { BootSequence } from './hud/BootSequence';
import { ShortcutOverlay } from './hud/ShortcutOverlay';
import './App.css';

/** True while the OS/browser asks for reduced motion — re-read live if the
 * user flips the setting mid-session, not just once on load. */
function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

/** A shortcut shouldn't fire while the user is typing into a real control. */
function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable;
}

export default function App() {
  const [active, setActive] = useState(false);
  const [narrating, setNarrating] = useState(true);
  const [boring, setBoring] = useState(false);
  const [hudDrawMs, setHudDrawMs] = useState(0);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const reducedMotion = usePrefersReducedMotion();

  const { videoRef, status: cameraStatus, error: cameraError } = useCamera(active);
  const { frameRef, status: modelStatus, error: modelError, stats } = useDetector(videoRef, active);
  const narratorEnabled = active && narrating && modelStatus === 'ready';
  const { log, config, setConfig, llmStatus, ttsStatus } = useNarrator(frameRef, narratorEnabled);

  const live = cameraStatus === 'live' && modelStatus === 'ready';
  const error = cameraError ?? modelError;

  const onDrawMs = useCallback((ms: number) => setHudDrawMs(ms), []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (isTypingTarget(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      switch (e.key) {
        case ' ':
          e.preventDefault();
          setActive((a) => !a);
          break;
        case 'n':
        case 'N':
          if (active) setNarrating((n) => !n);
          break;
        case 'b':
        case 'B':
          setBoring((b) => !b);
          break;
        case 'v':
        case 'V':
          setConfig({ voice_enabled: !config.voice_enabled });
          break;
        case '?':
          setShortcutsOpen((s) => !s);
          break;
        case 'Escape':
          setShortcutsOpen(false);
          break;
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [active, config.voice_enabled, setConfig]);

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
          <button
            className="btn"
            onClick={() => setShortcutsOpen((s) => !s)}
            aria-pressed={shortcutsOpen}
            title="Keyboard shortcuts"
          >
            ?
          </button>
        </div>
      </header>

      <main className="stage">
        <div className="viewport">
          <video ref={videoRef} className="video" playsInline muted />
          <HudCanvas
            videoRef={videoRef}
            frameRef={frameRef}
            active={active}
            reducedMotion={reducedMotion}
            onDrawMs={onDrawMs}
          />
          <SubtitleTrack log={log} boring={boring} visible={narratorEnabled} />

          {!active && (
            <div className="curtain">
              <p className="curtain-title">Perception offline</p>
              <p className="curtain-sub">
                Start the camera to begin real-time detection. Video never leaves this device.
              </p>
            </div>
          )}

          {active && !live && !error && (
            <BootSequence cameraStatus={cameraStatus} modelStatus={modelStatus} narratorEnabled={narratorEnabled} />
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
          hudDrawMs={hudDrawMs}
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

      {shortcutsOpen && <ShortcutOverlay onClose={() => setShortcutsOpen(false)} />}
    </div>
  );
}
