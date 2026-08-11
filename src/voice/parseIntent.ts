/**
 * Deterministic intent parsing. This is the one place in the voice pipeline
 * that is NOT the LLM, on purpose — see decisions.md Day 6. A 0.5B model
 * occasionally hallucinating is an acceptable cost for a joke line and not
 * for deciding whether "stop" actually stops the narrator. Pure function of
 * a transcript string; every branch is a fixed pattern, no model, no async.
 *
 * This is pattern-matching, not language understanding — off-script phrasing
 * ("could you tell me what's around") falls through to `unknown`. Say that
 * plainly; see public-notes.md.
 */

export type Intent =
  | { type: 'wake' }
  | { type: 'sleep' }
  | { type: 'stop' }
  | { type: 'describe_scene' }
  | { type: 'query_object'; object: string }
  | { type: 'help' }
  | { type: 'unknown'; transcript: string };

function normalize(transcript: string): string {
  return transcript
    .toLowerCase()
    .trim()
    .replace(/[.!?]+$/g, '')
    .replace(/\s+/g, ' ');
}

/** Strips a leading article/determiner off an extracted object phrase. */
function stripDeterminer(phrase: string): string {
  return phrase.trim().replace(/^(a|an|the|any)\s+/, '');
}

const STOP = /\bstop\b/;
const WAKE = /\b(wake up|hey yap|wake)\b/;
const SLEEP = /\b(go to sleep|shut up|be quiet|quiet down|hush|sleep now|sleep)\b/;
const HELP = /\b(what can you do|help|what commands|list commands)\b/;
const DESCRIBE = /\b(what do you see|what('?s| is) in front of you|describe the scene|describe scene|what can you see|what is there)\b/;
const QUERY = /\b(?:do you see|can you see|is there|are there)\s+(.+?)\??$/;

/**
 * `stop` is checked first because it has to interrupt mid-sentence (see
 * `useVoiceCommands`'s wiring) and must never be shadowed by a phrase that
 * happens to contain the word "stop" inside a longer sentence. Everything
 * else falls through in a fixed priority order; the first match wins, never
 * a best-match search.
 */
export function parseIntent(transcript: string): Intent {
  const text = normalize(transcript);
  if (!text) return { type: 'unknown', transcript };

  if (STOP.test(text)) return { type: 'stop' };
  if (WAKE.test(text)) return { type: 'wake' };
  if (SLEEP.test(text)) return { type: 'sleep' };
  if (HELP.test(text)) return { type: 'help' };
  if (DESCRIBE.test(text)) return { type: 'describe_scene' };

  const queryMatch = QUERY.exec(text);
  if (queryMatch) {
    const object = stripDeterminer(queryMatch[1]);
    if (object) return { type: 'query_object', object };
  }

  return { type: 'unknown', transcript };
}

/** The literal help text spoken for `help` — kept next to the parser so the list can't drift from what's actually handled. */
export const HELP_TEXT =
  'i handle a few things: wake up, sleep, stop, what do you see, do you see a -- something, and help. anything else, i will say so.';
