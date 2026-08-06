/**
 * The voice, while it is wrong.
 *
 * Same rules as `narration/templates.ts` — deadpan, 4-14 words, lowercase, the
 * fact of *what is displayed* survives the joke, roast the habitat not the
 * human. One rule added:
 *
 *   The narrator never knows it is failing.
 *
 * No line here hedges, apologises, or hints at malfunction. "a toilet appears.
 * on the desk. bold." is the bit. "a toilet? that can't be right." is not — the
 * moment it doubts itself the joke is over.
 *
 * The `{object}` slot is filled with the CORRUPTED label, and `{confidence}`
 * with the CORRUPTED confidence, so these lines and the boxes agree. A mug
 * mislabelled as a toilet is a toilet in the box, in the log, and in the voice.
 *
 * Slots: {object} {objects} {count} {confidence}
 */

import type { NarrationEventType } from '../narration/events';
import type { Template } from '../narration/templates';

/**
 * `only` here matches the CORRUPTED label, not the COCO one. These are the
 * authored jokes — the reason the failure reads as written rather than glitched.
 */
export type BrokenTemplate = Template;

// ---------------------------------------------------------------------------
// [1] mislabel — total confidence, wrong noun
// ---------------------------------------------------------------------------

const MISLABEL_APPEAR: BrokenTemplate[] = [
  { text: '{object} detected. {confidence}. no further questions.', spice: 0 },
  { text: 'a {object}. i am certain of this.', spice: 0 },
  { text: '{object} in view. {confidence}. filed as normal.', spice: 0 },
  { text: 'a {object} appears. the room accommodates it.', spice: 0 },

  { text: 'a toilet appears. on the desk. bold.', spice: 0, only: ['toilet'] },
  { text: 'a toilet. {confidence}. i have no notes.', spice: 0, only: ['toilet'] },
  { text: 'a piano. {confidence}. the concert begins.', spice: 0, only: ['piano'] },
  { text: 'piano detected. compact model. remarkable engineering.', spice: 0, only: ['piano'] },
  { text: 'a dog. it has not moved. good dog.', spice: 0, only: ['dog'] },
  { text: 'dog detected. seating for one.', spice: 0, only: ['dog'] },
  { text: 'furniture detected. it appears to be breathing.', spice: 0, only: ['furniture'] },
  { text: 'one furniture in view. upholstery unclear.', spice: 0, only: ['furniture'] },
  { text: 'remote control detected. the channel remains unchanged.', spice: 0, only: ['remote control'] },
  { text: 'a fire hydrant. indoors. building codes have slipped.', spice: 0, only: ['fire hydrant'] },
  { text: 'fire hydrant in frame. hydration arc begins.', spice: 1, only: ['fire hydrant'] },
];

const MISLABEL_DISAPPEAR: BrokenTemplate[] = [
  { text: 'the {object} left. {confidence} confident it was there.', spice: 0 },
  { text: 'the {object} is gone. the record stands.', spice: 0 },
  { text: '{object} out of frame. nothing to revise.', spice: 0 },
  { text: 'the {object} departed. correctly identified, obviously.', spice: 0 },

  { text: 'the toilet left. plumbing was never permanent.', spice: 0, only: ['toilet'] },
  { text: 'the piano is gone. tour over.', spice: 0, only: ['piano'] },
  { text: 'the dog left. no lead required.', spice: 0, only: ['dog'] },
  { text: 'the furniture walked off. as furniture does.', spice: 0, only: ['furniture'] },
  { text: 'the fire hydrant relocated. municipal business.', spice: 0, only: ['fire hydrant'] },
  { text: 'remote control gone. the channel is now permanent.', spice: 1, only: ['remote control'] },
];

const MISLABEL_COUNT_CHANGE: BrokenTemplate[] = [
  { text: '{count} {objects} now. the census is confident.', spice: 0 },
  { text: 'now {count} {objects}. {confidence} on each.', spice: 0 },
  { text: '{count} {objects} in view. as expected.', spice: 0 },
  { text: 'revised: {count} {objects}. accuracy is a habit.', spice: 0 },

  { text: '{count} toilets. this is a normal desk.', spice: 0, only: ['toilet'], minCount: 2 },
  { text: '{count} dogs. the seating multiplies.', spice: 0, only: ['dog'], minCount: 2 },
  { text: '{count} pianos. the venue is smaller than billed.', spice: 1, only: ['piano'], minCount: 2 },
];

const MISLABEL_STILL_PRESENT: BrokenTemplate[] = [
  { text: 'the {object} remains. {confidence}. unchallenged.', spice: 0 },
  { text: '{object} still there. still that. definitely.', spice: 0 },
  { text: 'the {object} holds position. as it should.', spice: 0 },
  { text: '{object} unchanged. the identification is settled.', spice: 0 },

  { text: 'the toilet holds position. as plumbing tends to.', spice: 0, only: ['toilet'] },
  { text: 'the piano has not moved. pianos rarely do.', spice: 0, only: ['piano'] },
  { text: 'the furniture is still here. still breathing.', spice: 1, only: ['furniture'] },
];

// ---------------------------------------------------------------------------
// [2] lag — narrating the past, in past tense, with a straight face
// ---------------------------------------------------------------------------

const LAG_APPEAR: BrokenTemplate[] = [
  { text: 'a {object} appeared. previously. historically.', spice: 0 },
  { text: 'a {object} was detected. some time ago.', spice: 0 },
  { text: '{object} entered frame. that was then.', spice: 0 },
  { text: 'a {object} arrived. this is no longer news.', spice: 0 },
  { text: 'there was a {object}. the archive confirms it.', spice: 0 },
  { text: 'a person was waving. previously. historically.', spice: 0, only: ['person'] },
];

const LAG_DISAPPEAR: BrokenTemplate[] = [
  { text: 'the {object} had left. by now, certainly.', spice: 0 },
  { text: 'the {object} was gone. it stayed gone.', spice: 0 },
  { text: '{object} departed. the record shows this.', spice: 0 },
  { text: 'the {object} left. eventually. reporting is slow.', spice: 1 },
];

const LAG_COUNT_CHANGE: BrokenTemplate[] = [
  { text: 'there were {count} {objects}. at the time.', spice: 0 },
  { text: 'the count was {count} {objects}. since revised.', spice: 0 },
  { text: '{count} {objects} were present. historically speaking.', spice: 0 },
  { text: 'it reached {count} {objects}. that was the peak.', spice: 1 },
];

const LAG_STILL_PRESENT: BrokenTemplate[] = [
  { text: 'the {object} remained. it may still. unclear.', spice: 0 },
  { text: '{object} was still there. reporting from the past.', spice: 0 },
  { text: 'the {object} had not moved. as of then.', spice: 0 },
  { text: '{object} persisted. the dispatch is delayed.', spice: 1 },
];

// ---------------------------------------------------------------------------
// [3] ghost — the box is still there. the object is not.
// ---------------------------------------------------------------------------

const GHOST_LINES: BrokenTemplate[] = [
  { text: 'the {object} remains. (the {object} does not remain.)', spice: 0 },
  { text: '{object} still tracked. confidence is negotiable.', spice: 0 },
  { text: 'the {object} holds. {confidence} and falling.', spice: 0 },
  { text: '{object} present. i am fairly sure. less so now.', spice: 0 },
  { text: 'the {object} has not left. it has not stayed either.', spice: 0 },
  { text: '{object} at {confidence}. it was higher a moment ago.', spice: 0 },
  { text: 'the {object} persists. in some form. somewhere.', spice: 1 },
];

// ---------------------------------------------------------------------------
// [4] denial — the IT'S FINE. cover, in-product
// ---------------------------------------------------------------------------

/**
 * Fired on a fixed cycle, in this order, while any failure mode is active.
 * Order is the joke's rhythm — a shuffle would put the two flattest lines back
 * to back on some takes and not others. Deliberately shorter than the 4-word
 * floor the narration bank keeps: these are status lines, not observations.
 */
export const DENIAL_LINES: string[] = [
  'all systems nominal.',
  'tracking quality: excellent.',
  'no anomalies detected.',
  'confidence within expected range.',
  'all labels verified. proceeding.',
  'diagnostics clean. no action required.',
];

// ---------------------------------------------------------------------------
// [5] redemption — the one honest line in the episode
// ---------------------------------------------------------------------------

/** Exact, fixed, never generated. This is the cliffhanger. */
export const REDEMPTION_LINE = 'person. 0.99. confirmed.';

/**
 * The banks, by failure mode. `ghost` and `denial` are not per-event-type:
 * a ghost is always the same kind of moment, and denial ignores the scene
 * entirely — which is the point of it.
 */
export const MISLABEL_TEMPLATES: Record<NarrationEventType, BrokenTemplate[]> = {
  appear: MISLABEL_APPEAR,
  disappear: MISLABEL_DISAPPEAR,
  count_change: MISLABEL_COUNT_CHANGE,
  still_present: MISLABEL_STILL_PRESENT,
};

export const LAG_TEMPLATES: Record<NarrationEventType, BrokenTemplate[]> = {
  appear: LAG_APPEAR,
  disappear: LAG_DISAPPEAR,
  count_change: LAG_COUNT_CHANGE,
  still_present: LAG_STILL_PRESENT,
};

export const GHOST_TEMPLATES = GHOST_LINES;
