/**
 * Local-LLM line generator. Same `LineGenerator` contract as the template
 * bank (`generateLine.ts`) — a drop-in swap selected by
 * `NarratorConfig.line_generator_engine`, invisible to every caller.
 *
 * The async problem: chat completion on even a 0.5B model takes 100s of ms,
 * but `LineGenerator` is synchronous. Chosen approach (decisions.md D13):
 * generate-ahead. `prefetch(event)` starts inference the moment an event is
 * queued — at least 900ms before its narration slot (the stability gate),
 * often several seconds more (the rate limit). `generateLine`/`foldLine`
 * never await; they read a cache keyed by the event object itself and fall
 * back to the template generator if the line isn't ready, failed, was
 * rejected by the character filter, or the model never loaded (no WebGPU,
 * still downloading, etc). This keeps the narration sampler's 250ms tick
 * fully synchronous — it can never block on the LLM.
 *
 * Model: Qwen2.5-0.5B-Instruct, 4-bit, via WebLLM/WebGPU — the smallest
 * instruct-tuned model in WebLLM's prebuilt catalog (~945MB VRAM,
 * `low_resource_required`). See decisions.md D13 for what else was
 * considered and why this one won.
 */
import type { NarratorConfig } from './config';
import type { NarrationEvent } from './events';
import { createLineGenerator, type LineGenerator } from './generateLine';
import { ALSO_PREFIXES, BANNED_WORDS } from './templates';

const MODEL_ID = 'Qwen2.5-0.5B-Instruct-q4f16_1-MLC';

/** Only gates spice 0/1 — spice 2 already permits these. */
const SWEARS = /\bdamn\b|\bhell\b/i;

const SYSTEM_PROMPT = `You are YAP, a deadpan nature-documentary narrator watching a room through a camera. Voice rules:
- Dry, terse, unimpressed. Never enthusiastic, never an exclamation mark.
- One sentence, 4 to 14 words. This is a log line, not a monologue.
- Always name the object and say what happened to it. The fact survives the joke.
- Roast the habitat -- the room, the mess, the clutter -- never a person's appearance or identity.
- Lowercase. No hashtags, no emoji, no addressing the viewer, no talking about being an AI.
- If the event says uncertain: true, you MUST hedge between object and alternative_object. Never confidently pick one -- "I don't know" is more interesting than a guess.
Examples of the voice, for tone only -- never reuse these verbatim:
- "the bottle has left. as bottles do."
- "a laptop. the screen time defence begins."
- "3 cups now. none of them recent."
- "the chair remains. as expected."`;

export type LlmEngineState = 'idle' | 'loading' | 'ready' | 'unavailable' | 'error';

export interface LlmStatus {
  state: LlmEngineState;
  /** 0..1 while `state === 'loading'`. */
  progress: number;
  lastInferenceMs: number | null;
  error?: string;
}

type LlmStatusListener = (status: LlmStatus) => void;

interface CacheEntry {
  status: 'pending' | 'ready' | 'error';
  text?: string;
}

/** Minimal shape used from `@mlc-ai/web-llm`'s `MLCEngine`, kept local so this file has no top-level import of it. */
interface ChatEngine {
  chat: {
    completions: {
      create(req: {
        messages: { role: 'system' | 'user'; content: string }[];
        max_tokens: number;
        temperature: number;
      }): Promise<{ choices: { message: { content?: string | null } }[] }>;
    };
  };
}

function eventPrompt(event: NarrationEvent, config: NarratorConfig): string {
  const idleMinutes = Math.round((event.idle_ms ?? event.duration_in_frame) / 60000);
  return [
    `event: ${event.type}`,
    `object: ${event.object}`,
    `count: ${event.count}`,
    event.type === 'still_present' ? `idle_minutes: ${idleMinutes}` : null,
    event.uncertain
      ? `uncertain: true, alternative_object: ${event.alternativeObject} -- the tracker cannot tell "${event.object}" and "${event.alternativeObject}" apart. Hedge between the two (e.g. "maybe", "or", "hard to say"). Do not confidently assert either one.`
      : null,
    `spice_level: ${config.spice_level} (0 = clean, 1 = default snark, 2 = mild swears allowed)`,
    'Write one narration line for this event, following the voice rules.',
  ]
    .filter((l): l is string => l !== null)
    .join('\n');
}

/** Words that signal the line actually hedged, for the uncertain-event check below. */
const HEDGE_CUES = /\bor\b|\bmaybe\b|\bperhaps\b|unclear|unsure|not sure|hard to say|no idea|who knows/i;

/**
 * Enforces the character bible and the word ceiling on raw model output.
 * Returns null to signal "reject, fall back to template" rather than let a
 * bad line through. When `hedge` is set (the event is uncertain), the LLM is
 * only ever allowed to *restyle* the hedge, never resolve it — a line that
 * doesn't actually hedge (names the alternative, or uses a hedge word) is
 * rejected exactly like a banned word or a swear, not just discouraged.
 */
export function sanitizeLlmLine(
  raw: string,
  config: NarratorConfig,
  hedge?: { alternativeObject: string | null },
): string | null {
  let line = raw
    .trim()
    .replace(/^["']|["']$/g, '')
    .toLowerCase()
    .replace(/!+/g, '.');
  if (!line) return null;
  if (BANNED_WORDS.some((w) => line.includes(w))) return null;
  if (config.spice_level < 2 && SWEARS.test(line)) return null;
  if (hedge) {
    const namesAlternative = hedge.alternativeObject ? line.includes(hedge.alternativeObject.toLowerCase()) : false;
    if (!namesAlternative && !HEDGE_CUES.test(line)) return null;
  }

  const words = line.split(/\s+/).filter(Boolean);
  if (words.length < 3) return null;
  if (words.length > config.line_max_words) {
    line = words.slice(0, config.line_max_words).join(' ');
  }
  if (!/[.?]$/.test(line)) line += '.';
  return line;
}

/**
 * @param loadEngine Injectable so tests can supply a fake model instead of downloading a real one.
 */
export function createLlmLineGenerator(
  getConfig: () => NarratorConfig,
  onStatus: LlmStatusListener = () => {},
  loadEngine: (onProgress: (progress: number) => void) => Promise<ChatEngine> = defaultLoadEngine,
): LineGenerator {
  const fallback = createLineGenerator(getConfig);
  const cache = new WeakMap<NarrationEvent, CacheEntry>();
  let status: LlmStatus = { state: 'idle', progress: 0, lastInferenceMs: null };
  let enginePromise: Promise<ChatEngine> | null = null;
  /** Serializes inference: most in-browser inference backends aren't safe for concurrent calls, and only one line is ever needed in flight. */
  let chain: Promise<void> = Promise.resolve();

  function setStatus(patch: Partial<LlmStatus>) {
    status = { ...status, ...patch };
    onStatus(status);
  }

  function getEngine(): Promise<ChatEngine> {
    if (!enginePromise) {
      setStatus({ state: 'loading', progress: 0 });
      enginePromise = loadEngine((progress) => setStatus({ state: 'loading', progress })).then(
        (engine) => {
          setStatus({ state: 'ready', progress: 1 });
          return engine;
        },
        (err: unknown) => {
          const unavailable = typeof err === 'object' && err !== null && 'yapUnavailable' in err;
          setStatus({ state: unavailable ? 'unavailable' : 'error', error: String(err) });
          throw err;
        },
      );
    }
    return enginePromise;
  }

  function runPrefetch(event: NarrationEvent) {
    const config = getConfig();
    cache.set(event, { status: 'pending' });
    // Start loading immediately (synchronously sets `loading` status on the
    // first call) — only the actual inference calls are serialized below.
    const engineNow = getEngine();
    chain = chain
      .then(() => engineNow)
      .then(async (engine) => {
        const start = performance.now();
        const reply = await engine.chat.completions.create({
          messages: [
            { role: 'system', content: SYSTEM_PROMPT },
            { role: 'user', content: eventPrompt(event, config) },
          ],
          max_tokens: 30,
          temperature: 0.9,
        });
        setStatus({ lastInferenceMs: performance.now() - start });
        const hedge = event.uncertain ? { alternativeObject: event.alternativeObject } : undefined;
        const clean = sanitizeLlmLine(reply.choices[0]?.message?.content ?? '', config, hedge);
        cache.set(event, clean ? { status: 'ready', text: clean } : { status: 'error' });
      })
      .catch(() => {
        cache.set(event, { status: 'error' });
      });
  }

  return {
    generateLine(event) {
      const entry = cache.get(event);
      if (entry?.status === 'ready' && entry.text) return entry.text;
      return fallback.generateLine(event);
    },

    foldLine(event) {
      const entry = cache.get(event);
      if (entry?.status === 'ready' && entry.text) {
        const prefix = ALSO_PREFIXES[Math.floor(Math.random() * ALSO_PREFIXES.length)];
        return prefix + entry.text;
      }
      return fallback.foldLine(event);
    },

    prefetch(event) {
      if (cache.has(event)) return;
      runPrefetch(event);
    },

    reset() {
      fallback.reset();
    },
  };
}

async function defaultLoadEngine(onProgress: (progress: number) => void): Promise<ChatEngine> {
  if (typeof navigator === 'undefined' || !('gpu' in navigator)) {
    throw Object.assign(new Error('WebGPU is not available in this browser'), {
      yapUnavailable: true,
    });
  }
  const { CreateMLCEngine } = await import('@mlc-ai/web-llm');
  return CreateMLCEngine(MODEL_ID, {
    initProgressCallback: (report) => onProgress(report.progress),
  });
}
