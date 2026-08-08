/**
 * The voice.
 *
 * Every line YAP says comes from this file. The rules, in short:
 *
 * - Deadpan, dry, unimpressed. Nature-documentary narrator who has seen too
 *   much. Never enthusiastic. Never an exclamation mark.
 * - 4-14 words, one sentence, maybe two. It's a log, not a monologue.
 * - The fact survives the joke. Every line names the object and says what
 *   happened to it. "the bottle has left. as bottles do." is a line.
 *   "lol wild in here" is not.
 * - Roast the habitat, never the human. Objects, the room, the mess, the cold
 *   coffee, the screen time. Never appearance, body, or identity.
 *
 * Slots: {object} {objects} {count} {minutes_idle}
 * ({objects} is the plural form, so count_change lines read as English.)
 */

import type { NarrationEventType } from './events';

export interface Template {
  /** The line, with slots. Filled by the engine, never at authoring time. */
  text: string;
  /**
   * Minimum `spice_level` this line is allowed at. 0 lines are always in play;
   * 2 lines carry a mild swear and only appear when the user opts in.
   */
  spice: 0 | 1 | 2;
  /**
   * Restrict to specific COCO labels. Object-specific jokes are what make the
   * narrator feel authored rather than generated, so a handful of common
   * labels get their own lines. Omitted = applies to anything.
   */
  only?: string[];
  /**
   * `still_present` only: minimum idle minutes before this line unlocks. The
   * bank escalates from mildly bored to openly worried as the room stays still.
   */
  minMinutes?: number;
  /**
   * Minimum object count this line is valid for. Lines that spell a plural out
   * by hand ("{count} cups") need this so they never say "1 cups".
   */
  minCount?: number;
  /**
   * `count_change` only: restricts a line that asserts which way the count
   * moved. "more than before" is a lie about a decrease, and the fact always
   * outranks the joke. Omitted = safe in either direction.
   */
  direction?: 'up' | 'down';
}

/** Words the voice never uses. Enforced by test, not by vigilance. */
export const BANNED_WORDS = ['journey', 'unlock', 'transform', 'amazing', 'incredible'];

/** Hard ceiling on a filled line. Longer than this stops being a punchline. */
export const MAX_WORDS = 14;

// ---------------------------------------------------------------------------
// appear
// ---------------------------------------------------------------------------

const APPEAR: Template[] = [
  { text: '{object} detected. presumably on purpose.', spice: 0 },
  { text: 'a {object}. bold interior design choices here.', spice: 0 },
  { text: '{object} enters frame. the plot remains thin.', spice: 0 },
  { text: 'a {object} appears. no one asked, but here we are.', spice: 0 },
  { text: '{object} spotted. filing that under "sure".', spice: 0 },
  { text: 'a {object} arrives. the ecosystem barely notices.', spice: 0 },
  { text: 'new {object} in view. the collection grows.', spice: 0 },
  { text: '{object} detected. we will see how long that lasts.', spice: 0 },
  { text: 'a {object} joins us. nothing moves.', spice: 0 },
  { text: 'a {object} turns up. the room absorbs it.', spice: 0 },
  { text: '{object} in view. noted, without ceremony.', spice: 0 },
  { text: 'a {object} now exists here. that is the update.', spice: 0 },
  { text: '{object} on scene. expectations remain low.', spice: 1 },
  { text: 'a {object} slides into view. subtle.', spice: 1 },
  { text: '{object} in frame now. standards were already low.', spice: 1 },
  { text: 'a {object}. we are doing this now, apparently.', spice: 1 },
  { text: '{object} appears. the room accepts it without question.', spice: 1 },
  { text: 'a {object} materialises. someone has been busy.', spice: 1 },
  { text: '{object} detected. i will pretend that is normal.', spice: 1 },
  { text: 'a {object}. the habitat continues its slow decline.', spice: 1 },
  { text: 'a damn {object}. the room asked for nothing.', spice: 2 },
  { text: '{object} detected. hell of a time for it.', spice: 2 },

  // object-specific
  { text: 'one person detected. presumably on purpose.', spice: 0, only: ['person'] },
  { text: 'a person appears. the furniture braces.', spice: 1, only: ['person'] },
  { text: 'a bottle appears. hydration arc begins.', spice: 0, only: ['bottle'] },
  { text: 'phone detected. focus not detected.', spice: 0, only: ['cell phone'] },
  { text: 'a laptop. the screen time defence begins.', spice: 1, only: ['laptop'] },
  { text: 'a cup enters. its contents are already cold.', spice: 0, only: ['cup'] },
  { text: 'a book appears. optimistic.', spice: 1, only: ['book'] },
  { text: 'a keyboard. the productivity theatre opens.', spice: 1, only: ['keyboard'] },
  { text: 'a potted plant. someone is trying. sort of.', spice: 1, only: ['potted plant'] },
];

// ---------------------------------------------------------------------------
// disappear
// ---------------------------------------------------------------------------

const DISAPPEAR: Template[] = [
  { text: 'the {object} left. it said nothing.', spice: 0 },
  { text: 'the {object} has left. as {objects} do.', spice: 0 },
  { text: '{object} gone. no forwarding address.', spice: 0 },
  { text: 'the {object} exited. nobody mourned.', spice: 0 },
  { text: 'the {object} is gone. good for it.', spice: 0 },
  { text: '{object} out of frame. we move on.', spice: 0 },
  { text: 'the {object} departed. the room did not react.', spice: 0 },
  { text: 'no more {object}. the void returns.', spice: 0 },
  { text: 'the {object} is elsewhere now. living its life.', spice: 0 },
  { text: 'the {object} slipped out. quietly, at least.', spice: 0 },
  { text: '{object} removed from the picture. literally.', spice: 0 },
  { text: 'the {object} is not there anymore. that is all.', spice: 0 },
  { text: '{object} gone. i had grown attached. briefly.', spice: 1 },
  { text: 'the {object} withdrew. tactically, i assume.', spice: 1 },
  { text: '{object} left frame. no explanation offered.', spice: 1 },
  { text: 'the {object} gave up. relatable.', spice: 1 },
  { text: '{object} vanished. bold, honestly.', spice: 1 },
  { text: 'the {object} escaped. we all want that.', spice: 1 },
  { text: '{object} no longer present. standards drop further.', spice: 1 },
  { text: 'the {object} walked. i respect the commitment.', spice: 1 },
  { text: 'the damn {object} left. no note.', spice: 2 },
  { text: '{object} gone to hell knows where. fine.', spice: 2 },

  // object-specific
  { text: 'phone is gone. productivity rumour unconfirmed.', spice: 0, only: ['cell phone'] },
  { text: 'the person left. the chair kept the shape.', spice: 1, only: ['person'] },
  { text: 'the bottle has left. as bottles do.', spice: 0, only: ['bottle'] },
  { text: 'the cup is gone. the ring on the desk remains.', spice: 1, only: ['cup'] },
  { text: 'the laptop closed. touching grass, allegedly.', spice: 1, only: ['laptop'] },
];

// ---------------------------------------------------------------------------
// count_change
// ---------------------------------------------------------------------------

const COUNT_CHANGE: Template[] = [
  { text: '{count} {objects} now. the situation develops.', spice: 0 },
  { text: 'make that {count} {objects}. escalation.', spice: 0, direction: 'up' },
  { text: '{count} {objects} in view. someone is collecting.', spice: 0, direction: 'up' },
  { text: 'down to {count} {objects}. attrition.', spice: 0, direction: 'down' },
  { text: '{count} {objects} left. the room thins out.', spice: 0, direction: 'down' },
  { text: 'now {count} {objects}. we are counting these apparently.', spice: 0 },
  { text: '{count} {objects}. a trend emerges.', spice: 0 },
  { text: '{count} {objects} present. the room adjusts.', spice: 0 },
  { text: 'revised: {count} {objects}. accuracy over drama.', spice: 0 },
  { text: '{count} {objects} in frame. the maths checks out.', spice: 0 },
  { text: '{count} {objects} visible. the census continues.', spice: 0 },
  { text: 'the count is {count} {objects}. that happened.', spice: 0 },
  { text: '{count} {objects}. the arrangement shifted. barely.', spice: 0 },
  { text: 'we are at {count} {objects}. no further comment.', spice: 0 },
  { text: '{count} {objects} now. this is the situation.', spice: 1 },
  { text: '{count} {objects}. i stopped asking why.', spice: 1 },
  { text: '{count} {objects}. more than before. barely news.', spice: 1, direction: 'up' },
  { text: '{count} {objects} now. the habitat responds to nothing.', spice: 1 },
  { text: '{count} {objects}. someone lost track. it was not me.', spice: 1 },
  { text: 'up to {count} {objects}. no one intervened.', spice: 1, direction: 'up' },
  { text: 'the {object} population is {count}. noted without enthusiasm.', spice: 1 },
  { text: '{count} {objects}. we adapt. we always adapt.', spice: 1 },
  { text: '{count} damn {objects}. the room has opinions.', spice: 2 },
  { text: '{count} {objects}. how the hell. fine.', spice: 2 },

  // object-specific
  { text: '{count} cups now. none of them recent.', spice: 0, only: ['cup'], minCount: 2 },
  { text: '{count} bottles. the hydration arc continues.', spice: 1, only: ['bottle'], minCount: 2 },
  { text: '{count} people now. a gathering, technically.', spice: 1, only: ['person'], minCount: 2 },
  { text: '{count} chairs. seating for a party that never comes.', spice: 1, only: ['chair'], minCount: 2 },
];

// ---------------------------------------------------------------------------
// still_present — escalates with idle minutes
// ---------------------------------------------------------------------------

const STILL_PRESENT: Template[] = [
  // tier 0 — mildly bored
  { text: 'the {object} remains. as expected.', spice: 0, minMinutes: 0 },
  { text: '{object} still there. no developments.', spice: 0, minMinutes: 0 },
  { text: 'the {object} holds position. riveting.', spice: 0, minMinutes: 0 },
  { text: '{object} unchanged. the tension builds.', spice: 0, minMinutes: 0 },
  { text: 'still a {object}. the story continues to not.', spice: 1, minMinutes: 0 },

  // tier 1 — counting now
  { text: 'still {object}. {minutes_idle} minutes of it.', spice: 0, minMinutes: 5 },
  { text: 'the {object} has not moved in {minutes_idle} minutes. committed.', spice: 0, minMinutes: 5 },
  { text: '{minutes_idle} minutes. the {object} persists.', spice: 0, minMinutes: 5 },
  { text: 'the {object} is winning the staring contest. {minutes_idle} minutes.', spice: 1, minMinutes: 5 },

  // tier 2 — concerned
  { text: 'the {object} is still here. sending thoughts.', spice: 0, minMinutes: 20 },
  { text: '{minutes_idle} minutes with this {object}. we have bonded.', spice: 0, minMinutes: 20 },
  { text: 'the {object} remains. i have stopped expecting change.', spice: 1, minMinutes: 20 },
  { text: '{minutes_idle} minutes of {object}. nature documentaries have pacing.', spice: 1, minMinutes: 20 },

  // tier 3 — openly judgmental
  { text: '{minutes_idle} minutes. the {object} has become furniture.', spice: 0, minMinutes: 45 },
  { text: 'the {object} is still there. i have accepted it as permanent.', spice: 0, minMinutes: 45 },
  { text: '{minutes_idle} minutes of {object}. someone check on the room.', spice: 1, minMinutes: 45 },
  { text: 'the {object} and i have been here {minutes_idle} minutes. neither blinked.', spice: 1, minMinutes: 45 },
  { text: '{minutes_idle} damn minutes of {object}. the room gave up.', spice: 2, minMinutes: 45 },

  // object-specific
  { text: 'person still here. {minutes_idle} minutes. the chair is concerned.', spice: 1, only: ['person'], minMinutes: 20 },
  { text: 'the person has not moved in {minutes_idle} minutes. blink twice.', spice: 1, only: ['person'], minMinutes: 45 },
  { text: 'phone still in hand. {minutes_idle} minutes. focus still missing.', spice: 1, only: ['cell phone'], minMinutes: 5 },
  { text: 'laptop still open. {minutes_idle} minutes. the grass waits.', spice: 1, only: ['laptop'], minMinutes: 20 },
  { text: 'the cup is still there. colder than {minutes_idle} minutes ago.', spice: 1, only: ['cup'], minMinutes: 5 },
];

/** The bank, by event type. */
export const TEMPLATES: Record<NarrationEventType, Template[]> = {
  appear: APPEAR,
  disappear: DISAPPEAR,
  count_change: COUNT_CHANGE,
  still_present: STILL_PRESENT,
};

/**
 * Lines used to fold secondary events into the tail of a narrated line, when
 * more than one thing happened inside the rate-limit window.
 */
export const ALSO_PREFIXES = ['also, ', 'meanwhile, ', 'elsewhere, '];
