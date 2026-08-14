import { useCallback, useEffect, useRef, useState } from 'react';
import { useCamera } from './vision/useCamera';
import { useDetector } from './vision/useDetector';
import { useNarrator } from './narration/useNarrator';
import { describeScene, queryObject } from './narration/describeScene';
import { HudCanvas } from './hud/HudCanvas';
import { StatusPanel } from './hud/StatusPanel';
import { SubtitleTrack, type Transcript } from './hud/SubtitleTrack';
import { BootSequence } from './hud/BootSequence';
import { ShortcutOverlay } from './hud/ShortcutOverlay';
import { HELP_TEXT, parseIntent } from './voice/parseIntent';
import { useVoiceInput } from './voice/useVoiceInput';
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
  const { log, config, setConfig, llmStatus, ttsStatus, speakAnswer, stopAll } = useNarrator(frameRef, narratorEnabled);

  const live = cameraStatus === 'live' && modelStatus === 'ready';
  const error = cameraError ?? modelError;

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
