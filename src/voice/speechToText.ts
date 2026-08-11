/**
 * Local speech-to-text. The browser ships a free `SpeechRecognition` API,
 * and in Chrome it streams your microphone audio to Google's servers — that
 * is a cloud call, banned outright by decisions.md D10/D-Day6, no exceptions
 * and no toggle. This runs Whisper locally instead, via
 * `@huggingface/transformers` (already on disk transitively through
 * `kokoro-js`, promoted to a direct dependency this session — see
 * package.json and decisions.md).
 *
 * Same adapter shape as `speech.ts`'s local-TTS engine and
 * `llmLineGenerator.ts`'s engine loader: injectable `loadModel` for tests,
 * WebGPU when available with an automatic wasm fallback (transformers.js
 * picks the device itself; this file only feature-detects for logging, it
 * never hard-fails without WebGPU the way the LLM loader does — ASR has to
 * keep working on a machine that only has wasm).
 */

export type AsrEngineState = 'idle' | 'loading' | 'ready' | 'unavailable' | 'error';

export interface AsrStatus {
  state: AsrEngineState;
  /** 0..1 while `state === 'loading'`. */
  progress: number;
  lastTranscribeMs: number | null;
  error?: string;
}

export interface AsrModel {
  transcribe(audio: Float32Array): Promise<string>;
}

interface AsrDeps {
  loadModel(onProgress: (progress: number) => void): Promise<AsrModel>;
}

export function createAsrEngine(deps: AsrDeps, onStatus: (status: AsrStatus) => void) {
  let modelPromise: Promise<AsrModel> | null = null;
  let status: AsrStatus = { state: 'idle', progress: 0, lastTranscribeMs: null };

  function set(patch: Partial<AsrStatus>) {
    status = { ...status, ...patch };
    onStatus(status);
  }

  function ensureModel(): Promise<AsrModel> {
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
    async transcribe(audio: Float32Array): Promise<string> {
      const model = await ensureModel();
      const start = performance.now();
      const text = await model.transcribe(audio);
      set({ lastTranscribeMs: performance.now() - start });
      return text;
    },
    getStatus: () => status,
  };
}

/** Minimal shape used from `@huggingface/transformers`'s ASR pipeline output. */
interface AsrPipelineOutput {
  text?: string;
}

type AsrPipeline = (audio: Float32Array) => Promise<AsrPipelineOutput | AsrPipelineOutput[]>;

async function loadWhisper(onProgress: (progress: number) => void): Promise<AsrModel> {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices) {
    throw Object.assign(new Error('Microphone capture is not available in this browser'), {
      yapUnavailable: true,
    });
  }
  const { pipeline } = await import('@huggingface/transformers');
  const hasWebGpu = 'gpu' in navigator;
  const transcriber = (await pipeline('automatic-speech-recognition', 'Xenova/whisper-tiny.en', {
    // WebGPU when available; transformers.js falls back to wasm on its own
    // otherwise, so this is a preference, not a hard requirement like the
    // LLM loader's WebGPU gate.
    device: hasWebGpu ? 'webgpu' : 'wasm',
    dtype: 'q8',
    progress_callback: (p: { status: string; progress?: number }) => {
      if (p.status === 'progress' && typeof p.progress === 'number') onProgress(p.progress / 100);
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any)) as unknown as AsrPipeline;

  return {
    transcribe: async (audio) => {
      const out = await transcriber(audio);
      const first = Array.isArray(out) ? out[0] : out;
      return first?.text?.trim() ?? '';
    },
  };
}

let engineSingleton: ReturnType<typeof createAsrEngine> | null = null;

/** The real engine, lazily constructed once — mirrors `speech.ts`'s module-level `localTts`. */
export function getAsrEngine(onStatus: (status: AsrStatus) => void): ReturnType<typeof createAsrEngine> {
  engineSingleton ??= createAsrEngine({ loadModel: loadWhisper }, onStatus);
  return engineSingleton;
}

/**
 * Resamples a decoded `AudioBuffer` to mono 16kHz `Float32Array` — the
 * sample rate Whisper expects. Recording happens at the microphone's native
 * rate (commonly 44.1/48kHz); `OfflineAudioContext` re-renders the same
 * signal at the target rate rather than naively dropping samples, which
 * would alias.
 */
export async function resampleTo16kMono(buffer: AudioBuffer): Promise<Float32Array> {
  const TARGET_RATE = 16000;
  if (buffer.sampleRate === TARGET_RATE && buffer.numberOfChannels === 1) {
    return buffer.getChannelData(0).slice();
  }
  const duration = buffer.duration;
  const offline = new OfflineAudioContext(1, Math.ceil(duration * TARGET_RATE), TARGET_RATE);
  const source = offline.createBufferSource();
  source.buffer = buffer;
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();
  return rendered.getChannelData(0).slice();
}
