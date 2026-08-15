#!/usr/bin/env node
// Renders scenario D's recorded frame-time data as a timeline image.
//
// day7-prompt.md asks for a Chrome DevTools performance trace screenshot of
// scenario D. This environment (headless, non-interactive) has no DevTools
// GUI session to screenshot — there's no panel to capture. What this script
// makes instead, honestly: the *same underlying signal* a DevTools flame
// chart would show for this stall (main-thread frame-time over time, with
// long tasks and the push-to-talk moment marked), from this session's own
// `?bench=1` recording (scripts/bench.mjs), rendered as a plain bar chart —
// not a DevTools screenshot, and labeled as such in day7-baseline.md.
import { readFileSync, writeFileSync } from 'node:fs';
import puppeteer from 'puppeteer';

const dataPath = new URL('./bench-output/scenario-D.json', import.meta.url);
const record = JSON.parse(readFileSync(dataPath, 'utf-8'));
const { dump, askedAtMs } = record;

// Reconstruct absolute time (ms since reset) for each frame delta.
let t = 0;
const points = dump.frameDeltas.map((d) => {
  t += d;
  return { t, d };
});
const maxT = points.length ? points[points.length - 1].t : 1;
const maxD = Math.max(200, ...points.map((p) => p.d));

const W = 1400;
const H = 500;
const padL = 60;
const padB = 40;
const padT = 60;
const plotW = W - padL - 20;
const plotH = H - padT - padB;

function x(tMs) {
  return padL + (tMs / maxT) * plotW;
}
function y(deltaMs) {
  return padT + plotH - (Math.min(deltaMs, maxD) / maxD) * plotH;
}

const bars = points
  .map((p, i) => {
    const prevT = i === 0 ? 0 : points[i - 1].t;
    const barX = x(prevT);
    const barW = Math.max(1, x(p.t) - x(prevT));
    const barH = plotH + padT - y(p.d);
    const color = p.d > 200 ? '#ff4d4d' : p.d > 50 ? '#ffb020' : '#3fb950';
    return `<rect x="${barX.toFixed(1)}" y="${y(p.d).toFixed(1)}" width="${barW.toFixed(1)}" height="${barH.toFixed(1)}" fill="${color}" />`;
  })
  .join('');

const longTaskMarks = (dump.longTasks ?? [])
  .map((lt) => `<rect x="${x(lt.start).toFixed(1)}" y="${padT}" width="${Math.max(2, (lt.duration / maxT) * plotW).toFixed(1)}" height="${plotH}" fill="rgba(255,77,77,0.15)" />`)
  .join('');

const askedLine = askedAtMs != null
  ? `<line x1="${x(askedAtMs).toFixed(1)}" y1="${padT}" x2="${x(askedAtMs).toFixed(1)}" y2="${padT + plotH}" stroke="#58a6ff" stroke-width="2" stroke-dasharray="4,3" />
     <text x="${x(askedAtMs).toFixed(1)}" y="${padT + 20}" fill="#58a6ff" font-size="14" text-anchor="middle" font-family="monospace">push-to-talk held</text>`
  : '';

const gridLines = [0, 16.7, 50, 100, 200].map((d) => {
  const gy = y(d);
  return `<line x1="${padL}" y1="${gy.toFixed(1)}" x2="${padL + plotW}" y2="${gy.toFixed(1)}" stroke="#333" stroke-width="1" />
    <text x="${padL - 8}" y="${(gy + 4).toFixed(1)}" fill="#999" font-size="11" text-anchor="end" font-family="monospace">${d}ms</text>`;
}).join('');

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
body { margin: 0; background: #0d1117; font-family: monospace; }
</style></head><body>
<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <rect width="${W}" height="${H}" fill="#0d1117" />
  <text x="${padL}" y="20" fill="#e6edf3" font-size="15" font-family="monospace">Scenario D — rAF frame delta over time (ms)</text>
  <text x="${padL}" y="38" fill="#8b949e" font-size="12" font-family="monospace">Not a DevTools flame chart — this session's own ?bench=1 recording; headless has no DevTools GUI to screenshot</text>
  ${gridLines}
  ${longTaskMarks}
  ${bars}
  ${askedLine}
  <text x="${padL}" y="${H - 8}" fill="#999" font-size="11" font-family="monospace">time within 60s window (s) — green &lt;16.7ms (60fps) · amber &gt;50ms (dropped frame) · red &gt;200ms (visible freeze, longtask shaded)</text>
</svg>
</body></html>`;

const htmlPath = new URL('./bench-output/scenario-d-chart.html', import.meta.url);
writeFileSync(htmlPath, html);

const browser = await puppeteer.launch({ headless: true });
const page = await browser.newPage();
await page.setViewport({ width: W, height: H });
await page.goto(`file://${htmlPath.pathname}`);
const outPath = new URL('../.claude/day7-scenario-d-timeline.png', import.meta.url).pathname;
await page.screenshot({ path: outPath });
await browser.close();
console.log('wrote', outPath);
