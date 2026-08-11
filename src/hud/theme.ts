/**
 * Palette shared by canvas drawing (`drawHud.ts`) and CSS (`App.css`'s
 * `:root`). CSS can't import a `.ts` module without extra build tooling
 * (out of scope — no new dependencies, D-rule in day5-hud-prompt.md), so
 * `App.css` mirrors these values by hand. If you change a color here,
 * change it there too — both files say so in a comment at the point of use.
 */
export const THEME = {
  cyan: '#22d3ee',
  amber: '#fbbf24',
  danger: '#f87171',
  bg: '#04070d',
  panel: '#080e17',
  text: '#d6e6ef',
  muted: '#5f7d8c',
  line: 'rgba(34, 211, 238, 0.18)',
} as const;
