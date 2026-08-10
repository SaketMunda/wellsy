/**
 * Speech output. Two engines behind one surface: `speak`, `stopSpeaking`,
 * `primeSpeech`, `pickVoice` never change shape regardless of which is active.
 *
 * `system` — Web Speech `speechSynthesis`. Zero dependencies, ships in the
 * browser. Three quirks are handled here, all of which present as "nothing
 * happens and no error is thrown":
 * 1. `getVoices()` is empty on first call in Chrome; voices arrive later on a
 *    `voiceschanged` event.
 * 2. Browsers gate speech behind a user gesture. Speech driven by a timer, as
 *    ours is, gets dropped unless the synth was primed inside a real click.
 * 3. `speak()` called in the same tick as `cancel()` is silently discarded in
 *    Chrome, and the synth can be left in a paused state.
 *
 * `local-tts` — Kokoro-82M (`kokoro-js`, dynamically imported, never bundled
 * into the main chunk), rendered through the Web Audio API so `stopSpeaking`
 * can actually cut off in-flight synthesis (`AudioBufferSourceNode.stop()`),
 * not just cancel the next line. Same user-gesture rule applies: the
 * `AudioContext` is created/resumed synchronously inside `primeSpeech`, even
 * though the model itself loads and speaks async afterwards — an
 * already-unlocked context stays unlocked for later async `start()` calls.
 * See decisions.md D13 for why Kokoro over the alternatives, and why `system`
 * stays wired in as the fallback for load failure or an unsupported browser.
 */

export type VoiceEngine = 'system' | 'local-tts';
export type TtsEngineState = 'idle' | 'loading' | 'ready' | 'unavailable' | 'error';

export interface TtsStatus {
  engine: VoiceEngine;
  state: TtsEngineState;
  /** 0..1 while `state === 'loading'`. */
  progress: number;
  lastSynthMs: number | null;
  error?: string;
}

export interface RawAudioLike {
  audio: Float32Array;
  sampling_rate: number;
}

let voices: SpeechSynthesisVoice[] = [];
let primed = false;
let engine: VoiceEngine = 'system';

let ttsStatus: TtsStatus = { engine: 'system', state: 'idle', progress: 0, lastSynthMs: null };
let statusListener: (status: TtsStatus) => void = () => {};

function setTtsStatus(patch: Partial<TtsStatus>) {
  ttsStatus = { ...ttsStatus, ...patch };
  statusListener(ttsStatus);
}

export function onTtsStatus(listener: (status: TtsStatus) => void): void {
  statusListener = listener;
}

export function getTtsStatus(): TtsStatus {
  return ttsStatus;
}

export function setVoiceEngine(next: VoiceEngine): void {
  engine = next;
  setTtsStatus({ engine: next });
}

function synth(): SpeechSynthesis | undefined {
  return typeof window === 'undefined' ? undefined : window.speechSynthesis;
}

function loadVoices() {
  voices = synth()?.getVoices?.() ?? [];
}

if (synth()) {
  loadVoices();
  // Chrome populates the list asynchronously.
  synth()?.addEventListener?.('voiceschanged', loadVoices);
}

/** Deadpan needs a flat read, so skip anything theatrical. */
const NOVELTY = /bubbles|jester|zarvox|bells|boing|trinoids|whisper|good news|bad news|wobble|superstar|organ|cellos|albert|fred/i;

export function pickVoice(): SpeechSynthesisVoice | null {
  if (voices.length === 0) loadVoices();
  const english = voices.filter((v) => v.lang?.toLowerCase().startsWith('en'));
  if (english.length === 0) return null;
  const plain = english.filter((v) => !NOVELTY.test(v.name));
  return plain.find((v) => v.default) ?? plain[0] ?? english[0];
}

function speakSystem(text: string): void {
  const s = synth();
  if (!s) return;
  // Never let speech lag more than one line behind the log.
  s.cancel();
  // Chrome discards an utterance queued in the same tick as cancel().
  setTimeout(() => {
    if (s.paused) s.resume();
    const utter = new SpeechSynthesisUtterance(text);
    const voice = pickVoice();
    if (voice) utter.voice = voice;
    utter.rate = 0.9;
    utter.pitch = 1.0;
    s.speak(utter);
  }, 0);
}

// ---------------------------------------------------------------------------
// Local TTS adapter — factored out so it can be driven by fakes in tests
// instead of a real model and a real AudioContext.
// ---------------------------------------------------------------------------

interface LocalTtsModel {
  generate(text: string): Promise<RawAudioLike>;
}

interface LocalTtsDeps {
  loadModel(onProgress: (progress: number) => void): Promise<LocalTtsModel>;
  playAudio(raw: RawAudioLike): Promise<void> | void;
  stopAudio(): void;
}

export function createLocalTtsAdapter(deps: LocalTtsDeps, onStatus: (status: TtsStatus) => void) {
  let modelPromise: Promise<LocalTtsModel> | null = null;
  let status: TtsStatus = { engine: 'local-tts', state: 'idle', progress: 0, lastSynthMs: null };

  function set(patch: Partial<TtsStatus>) {
    status = { ...status, ...patch };
    onStatus(status);
  }

  function ensureModel(): Promise<LocalTtsModel> {
    if (!modelPromise) {
      set({ state: 'loading', progress: 0 });
      modelPromise = deps.loadModel((progress) => set({ progress })).then(
        (model) => {
          set({ state: 'ready', progress: 1 });
          return model;
        },
        (err: unknown) => {
          const unavailable = typeof err === 'object' && err !== null && 'yapUnavailable' in err;
          set({ state: unavailable ? 'unavailable' : 'error', error: String(err) });
          throw err;
        },
      );
    }
    return modelPromise;
  }

  return {
    async speak(text: string): Promise<void> {
      const model = await ensureModel();
      const start = performance.now();
      const raw = await model.generate(text);
      set({ lastSynthMs: performance.now() - start });
      await deps.playAudio(raw);
    },
    stop(): void {
      deps.stopAudio();
    },
    getStatus: () => status,
  };
}

let audioCtx: AudioContext | undefined;
let currentSource: AudioBufferSourceNode | undefined;

function ensureAudioContext(): AudioContext | undefined {
  if (typeof window === 'undefined') return undefined;
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return undefined;
  audioCtx ??= new Ctor();
  // Must be called from the gesture handler that unlocked it, even though it resolves async.
  if (audioCtx.state === 'suspended') void audioCtx.resume();
  return audioCtx;
}

async function playRawAudio(raw: RawAudioLike): Promise<void> {
  const ctx = ensureAudioContext();
  if (!ctx) return;
  try {
    currentSource?.stop();
  } catch {
    // Already stopped/finished — fine.
  }
  const buffer = ctx.createBuffer(1, raw.audio.length, raw.sampling_rate);
  buffer.getChannelData(0).set(raw.audio);
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.connect(ctx.destination);
  currentSource = source;
  source.start();
}

async function loadKokoro(onProgress: (progress: number) => void): Promise<LocalTtsModel> {
  if (typeof window === 'undefined' || !window.AudioContext) {
    throw Object.assign(new Error('Web Audio is not available in this browser'), {
      yapUnavailable: true,
    });
  }
  const { KokoroTTS } = await import('kokoro-js');
  const tts = await KokoroTTS.from_pretrained('onnx-community/Kokoro-82M-v1.0-ONNX', {
    dtype: 'q8',
    device: 'wasm',
    progress_callback: (p: { status: string; progress?: number }) => {
      if (p.status === 'progress' && typeof p.progress === 'number') onProgress(p.progress / 100);
    },
  });
  // af_heart: Kokoro's top-graded ("A" overall) English voice, female —
  // the least robotic option available, and what was asked for.
  return { generate: async (text) => tts.generate(text, { voice: 'af_heart' }) };
}

const localTts = createLocalTtsAdapter(
  {
    loadModel: loadKokoro,
    playAudio: playRawAudio,
    stopAudio: () => {
      try {
        currentSource?.stop();
      } catch {
        // Already stopped/finished — fine.
      }
      currentSource = undefined;
    },
  },
  (status) => setTtsStatus(status),
);

export function speak(text: string): void {
  if (engine === 'local-tts' && ttsStatus.state !== 'unavailable') {
    localTts.speak(text).catch((err: unknown) => {
      console.warn('local-tts failed, falling back to the system voice:', err);
      speakSystem(text);
    });
    return;
  }
  speakSystem(text);
}

export function stopSpeaking(): void {
  synth()?.cancel();
  localTts.stop();
}

/**
 * Must be called synchronously from a user gesture (the voice toggle's click).
 * Speaks a short line in character, which both satisfies the gesture
 * requirement and tells you immediately that audio actually works.
 */
export function primeSpeech(): void {
  if (primed) return;
  primed = true;
  loadVoices();
  ensureAudioContext();
  speak('voice enabled. regrettably.');
}
