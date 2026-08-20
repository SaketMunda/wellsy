import { useCallback, useEffect, useRef, useState } from 'react';
import { useCamera } from './vision/useCamera';
import { useDetector } from './vision/useDetector';
import { useEngineSocket } from './vision/useEngineSocket';
import { useNarrator } from './narration/useNarrator';
import { describeScene, queryObject } from './narration/describeScene';
import { HudCanvas } from './hud/HudCanvas';
import { StatusPanel } from './hud/StatusPanel';
import { SubtitleTrack, type Transcript } from './hud/SubtitleTrack';
import { BootSequence } from './hud/BootSequence';
import { ShortcutOverlay } from './hud/ShortcutOverlay';
import { HELP_TEXT, parseIntent } from './voice/parseIntent';
import { useVoiceInput } from './voice/useVoiceInput';
import { createBenchRecorder, type BenchRecorder } from './bench/frameRecorder';
import './App.css';

declare global {
  interface Window {
    __yapBench?: BenchRecorder;
    __yapStatus?: { live: boolean; llmState: string; ttsState: string; detectFps: number; lineCount: number };
  }
}

const BENCH_MODE = new URLSearchParams(window.location.search).get('bench') === '1';
// Day 9: the HUD gains a second frame source (the Python engine, over a
// local WebSocket) without losing its first (in-browser TF.js, D28's
// browser-only build stays alive behind this flag — day9-prompt.md's
// explicit boundary, not the default).
const ENGINE_MODE = new URLSearchParams(window.location.search).get('engine') === '1';

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
  // Two frame sources, one Frame shape (src/vision/types.ts) — HudCanvas,
  // hudState.ts and drawHud.ts don't know which one is live. Both hooks are
  // called unconditionally (rules of hooks); only the selected one's `active`
  // flag actually does work, so the idle one is a no-op.
  const detector = useDetector(videoRef, active && !ENGINE_MODE);
  const engine = useEngineSocket(videoRef, active && ENGINE_MODE);
  const { frameRef, stats } = ENGINE_MODE ? engine : detector;
  const modelStatus = ENGINE_MODE ? engine.status : detector.status;
  const modelError = ENGINE_MODE ? engine.error : detector.error;
  // A stale engine (no message in ~1s, day9-prompt.md) still has a populated
  // frameRef from its last message — narration and the HUD keep running on
  // that held frame, same discipline as a still scene's re-emitted tracks.
  // Only idle/loading/error actually block readiness.
  const modelReady = modelStatus === 'ready' || modelStatus === 'stale';
  const narratorEnabled = active && narrating && modelReady;
  const { log, config, setConfig, llmStatus, ttsStatus, speakAnswer, stopAll } = useNarrator(frameRef, narratorEnabled);

  const live = cameraStatus === 'live' && modelReady;
  const error = cameraError ?? modelError;
  const engineStale = ENGINE_MODE && modelStatus === 'stale';

  const onDrawMs = useCallback((ms: number) => setHudDrawMs(ms), []);

  const [transcript, setTranscript] = useState<Transcript | null>(null);

  // Deterministic, not the LLM (decisions.md Day 6) — a control action like
  // "stop" must never depend on a model that can hallucinate.
  const handleTranscript = useCallback(
    (text: string) => {
      setTranscript({ text, at: Date.now() });
      const intent = parseIntent(text);
      switch (intent.type) {
        case 'stop':
          // "stop" is a full stop, not just a cut-off of the current line —
          // it also silences ambient narration, same as "sleep", so it
          // doesn't start talking again a few seconds later. Say "wake up"
          // to resume.
          stopAll();
          setNarrating(false);
          break;
        case 'wake':
          setNarrating(true);
          speakAnswer('waking up.');
          break;
        case 'sleep':
          setNarrating(false);
          speakAnswer('going quiet.');
          break;
        case 'describe_scene':
          speakAnswer(describeScene(frameRef.current.tracks));
          break;
        case 'query_object':
          speakAnswer(queryObject(frameRef.current.tracks, intent.object));
          break;
        case 'help':
          speakAnswer(HELP_TEXT);
          break;
        case 'unknown':
          speakAnswer("i only handle a few commands. say help to hear them.");
          break;
      }
    },
    [frameRef, speakAnswer, stopAll],
  );

  const { start: startListening, stop: stopListening, micStatus, recording, asrStatus } = useVoiceInput(handleTranscript);
  const listeningKeyDown = useRef(false);

  // Day 7 instrumentation, ?bench=1 only — see src/bench/frameRecorder.ts.
  // A harness (Puppeteer) reads/resets state via window.__yapBench; this
  // effect is a no-op in every other mode.
  useEffect(() => {
    if (!BENCH_MODE) return;
    const recorder = createBenchRecorder();
    recorder.start();
    window.__yapBench = recorder;
    return () => {
      recorder.stop();
      delete window.__yapBench;
    };
  }, []);

  // Bench-only: lets the harness poll readiness (camera+model live, LLM/TTS
  // loaded) and scenario-E's "how much actually happened" numbers, without
  // guessing at timings or scraping the DOM. No effect outside ?bench=1.
  useEffect(() => {
    if (!BENCH_MODE) return;
    window.__yapStatus = {
      live,
      llmState: llmStatus.state,
      ttsState: ttsStatus.state,
      detectFps: stats.fps,
      lineCount: log.length,
    };
  }, [live, llmStatus.state, ttsStatus.state, stats.fps, log.length]);

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
        case 't':
        case 'T':
          // Held key, not a toggle — ignore OS key-repeat so this fires once per press.
          if (!listeningKeyDown.current) {
            listeningKeyDown.current = true;
            void startListening();
          }
          break;
        case '?':
          setShortcutsOpen((s) => !s);
          break;
        case 'Escape':
          // A hard, instant stop — no voice, no ASR round-trip, nothing to
          // mishear. Closes the shortcut overlay too if it's open.
          setShortcutsOpen(false);
          stopAll();
          setNarrating(false);
          break;
      }
    }
    function onKeyUp(e: KeyboardEvent) {
      if (e.key === 't' || e.key === 'T') {
        if (listeningKeyDown.current) {
          listeningKeyDown.current = false;
          stopListening();
        }
      }
    }
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
    };
  }, [active, config.voice_enabled, setConfig, startListening, stopListening, stopAll]);

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
            aria-pressed={recording === 'recording'}
            data-warn={recording === 'transcribing' ? 'true' : undefined}
            title="Hold to talk (or press and hold T). Audio is transcribed on-device and never leaves this browser. Press Escape for an instant stop that doesn't need voice."
            onMouseDown={(e) => {
              e.preventDefault();
              void startListening();
            }}
            onMouseUp={stopListening}
            onMouseLeave={() => recording === 'recording' && stopListening()}
            onTouchStart={(e) => {
              e.preventDefault();
              void startListening();
            }}
            onTouchEnd={stopListening}
          >
            {recording === 'recording' ? 'Listening…' : recording === 'transcribing' ? 'Transcribing…' : 'Hold to talk'}
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
          <SubtitleTrack log={log} boring={boring} visible={active} transcript={transcript} />

          {/* Staleness must be visible, not silent (day9-prompt.md) — the HUD
              never claims to know something it doesn't currently know, same
              discipline as UNIDENTIFIED (D22). This lives in App.tsx, not
              src/hud/, so drawHud.ts stays untouched by the engine path. */}
          {engineStale && (
            <div className="stale-banner" role="status">
              engine signal lost — showing last known frame
            </div>
          )}

          {!active && (
            <div className="curtain">
              <p className="curtain-title">Perception offline</p>
              <p className="curtain-sub">
                Start the camera to begin real-time detection. Video never leaves this device.
              </p>
            </div>
          )}

          {active && !live && !error && (
            // BootSequence's ModelStatus type predates the engine's extra
            // 'stale' state; 'stale' implies "was ready", and this only
            // renders pre-`live` anyway, so the boot sequence never actually
            // needs to represent it — coerced here rather than widening the
            // type in src/hud/ for a state that can't reach this component.
            <BootSequence
              cameraStatus={cameraStatus}
              modelStatus={modelStatus === 'stale' ? 'ready' : modelStatus}
              narratorEnabled={narratorEnabled}
            />
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
          trackMs={stats.trackMs}
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
          micStatus={micStatus}
          asrStatus={asrStatus}
        />
      </main>

      {shortcutsOpen && <ShortcutOverlay onClose={() => setShortcutsOpen(false)} />}
    </div>
  );
}
