/**
 * Monotonic ids for log rows.
 *
 * Lives alone so the narrator and the demo layer can both allocate from it
 * without importing each other. Rows used to be keyed on `Date.now()`, which is
 * fine until lag mode replays two entries inside the same millisecond and React
 * quietly drops one.
 */
let next = 1;

export function nextLogId(): number {
  return next++;
}
