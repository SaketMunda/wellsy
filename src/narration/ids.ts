/**
 * Monotonic ids for log rows. Rows used to be keyed on `Date.now()`, which
 * collides when two entries land inside the same millisecond and React
 * quietly drops one.
 */
let next = 1;

export function nextLogId(): number {
  return next++;
}
