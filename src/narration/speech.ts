/**
 * Web Speech output. Zero dependencies — this ships in the browser.
 *
 * Three browser quirks are handled here, all of which present as "nothing
 * happens and no error is thrown":
 *
 * 1. `getVoices()` is empty on first call in Chrome; voices arrive later on a
 *    `voiceschanged` event.
 * 2. Browsers gate speech behind a user gesture. Speech driven by a timer, as
 *    ours is, gets dropped unless the synth was primed inside a real click.
 * 3. `speak()` called in the same tick as `cancel()` is silently discarded in
 *    Chrome, and the synth can be left in a paused state.
 */

let voices: SpeechSynthesisVoice[] = [];
let primed = false;

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

/**
 * Must be called synchronously from a user gesture (the voice toggle's click).
 * Speaks a short line in character, which both satisfies the gesture
 * requirement and tells you immediately that audio actually works.
 */
export function primeSpeech(): void {
  const s = synth();
  if (!s || primed) return;
  primed = true;
  loadVoices();
  speak('voice enabled. regrettably.');
}

export function speak(text: string): void {
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

export function stopSpeaking(): void {
  synth()?.cancel();
}
