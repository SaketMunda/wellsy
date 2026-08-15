#!/usr/bin/env node
// Generates the Day 7 explainer diagrams as PNGs into .claude/day7-images/.
// Reference material for motion graphics — not the final on-screen art.
import { mkdirSync, writeFileSync } from 'node:fs';
import puppeteer from 'puppeteer';

const OUT_DIR = new URL('../.claude/day7-images/', import.meta.url);
mkdirSync(OUT_DIR, { recursive: true });

const FONT = 'font-family="ui-monospace, Menlo, monospace"';

async function renderSvgToPng(name, width, height, svgInner) {
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
body { margin: 0; background: #0d1117; }
</style></head><body>
<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
  <rect width="${width}" height="${height}" fill="#0d1117" />
  ${svgInner}
</svg>
</body></html>`;
  const htmlPath = new URL(`./_${name}.html`, OUT_DIR);
  writeFileSync(htmlPath, html);
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewport({ width, height });
  await page.goto(`file://${htmlPath.pathname}`);
  await page.screenshot({ path: new URL(`./${name}.png`, OUT_DIR).pathname });
  await browser.close();
  console.log('wrote', name + '.png');
}

// ---------------------------------------------------------------------------
// 1. Architecture before/after
// ---------------------------------------------------------------------------
{
  const W = 1600, H = 800;
  const svg = `
  <text x="60" y="50" fill="#e6edf3" font-size="26" font-weight="bold" ${FONT}>Where perception runs</text>
  <text x="60" y="78" fill="#8b949e" font-size="15" ${FONT}>Days 1-6 vs. Day 7+ (V2 pivot)</text>

  <!-- BEFORE -->
  <text x="80" y="140" fill="#ff7b72" font-size="18" font-weight="bold" ${FONT}>BEFORE — Days 1-6</text>
  <rect x="80" y="160" width="680" height="440" rx="12" fill="#161b22" stroke="#30363d" stroke-width="2"/>
  <text x="420" y="195" text-anchor="middle" fill="#e6edf3" font-size="16" font-weight="bold" ${FONT}>ONE BROWSER TAB</text>

  <rect x="110" y="220" width="620" height="60" rx="8" fill="#1c2128" stroke="#f0883e" stroke-width="1.5"/>
  <text x="420" y="255" text-anchor="middle" fill="#f0883e" font-size="14" ${FONT}>Detection rAF loop — TF.js / WebGL — 60Hz, always on</text>

  <rect x="110" y="292" width="620" height="60" rx="8" fill="#1c2128" stroke="#f0883e" stroke-width="1.5"/>
  <text x="420" y="327" text-anchor="middle" fill="#f0883e" font-size="14" ${FONT}>HUD draw rAF loop — Canvas2D — 60Hz, always on</text>

  <rect x="110" y="364" width="620" height="60" rx="8" fill="#1c2128" stroke="#f0883e" stroke-width="1.5"/>
  <text x="420" y="399" text-anchor="middle" fill="#f0883e" font-size="14" ${FONT}>Narration sampler — 4Hz, always on</text>

  <rect x="110" y="436" width="300" height="60" rx="8" fill="#1c2128" stroke="#a371f7" stroke-width="1.5"/>
  <text x="260" y="471" text-anchor="middle" fill="#a371f7" font-size="13" ${FONT}>LLM — WebGPU</text>

  <rect x="420" y="436" width="300" height="60" rx="8" fill="#1c2128" stroke="#a371f7" stroke-width="1.5"/>
  <text x="570" y="471" text-anchor="middle" fill="#a371f7" font-size="13" ${FONT}>TTS / ASR — WASM</text>

  <text x="420" y="530" text-anchor="middle" fill="#ff7b72" font-size="14" font-weight="bold" ${FONT}>ZERO Web Workers — everything shares one JS main thread</text>
  <text x="420" y="556" text-anchor="middle" fill="#8b949e" font-size="13" ${FONT}>3 inference runtimes (WebGL / WebGPU / WASM), 1 GPU, no coordination</text>
  <text x="420" y="582" text-anchor="middle" fill="#8b949e" font-size="13" ${FONT}>Runs at full rate always — whether or not anyone needs the answer</text>

  <!-- arrow -->
  <path d="M 800 400 L 870 400" stroke="#58a6ff" stroke-width="3" marker-end="url(#arrow)"/>
  <text x="835" y="385" text-anchor="middle" fill="#58a6ff" font-size="20" ${FONT}>→</text>

  <!-- AFTER -->
  <text x="890" y="140" fill="#3fb950" font-size="18" font-weight="bold" ${FONT}>AFTER — Day 7+</text>
  <rect x="890" y="160" width="630" height="440" rx="12" fill="#161b22" stroke="#30363d" stroke-width="2"/>
  <text x="1205" y="195" text-anchor="middle" fill="#e6edf3" font-size="16" font-weight="bold" ${FONT}>BROWSER TAB (HUD only)</text>

  <rect x="920" y="220" width="570" height="55" rx="8" fill="#1c2128" stroke="#3fb950" stroke-width="1.5"/>
  <text x="1205" y="253" text-anchor="middle" fill="#3fb950" font-size="14" ${FONT}>React HUD — renders whatever the engine sends</text>

  <text x="1205" y="300" text-anchor="middle" fill="#58a6ff" font-size="22" ${FONT}>⇅ local connection</text>

  <text x="1205" y="345" fill="#e6edf3" font-size="16" font-weight="bold" text-anchor="middle" ${FONT}>PYTHON ENGINE — separate process</text>
  <rect x="920" y="365" width="570" height="55" rx="8" fill="#1c2128" stroke="#3fb950" stroke-width="1.5"/>
  <text x="1205" y="398" text-anchor="middle" fill="#3fb950" font-size="14" ${FONT}>T0 — capture + motion gate — own process, always cheap</text>

  <rect x="920" y="435" width="570" height="55" rx="8" fill="#1c2128" stroke="#8b949e" stroke-width="1.5" stroke-dasharray="5,4"/>
  <text x="1205" y="468" text-anchor="middle" fill="#8b949e" font-size="14" ${FONT}>T1 — detection — on motion, not always (Day 8+)</text>

  <rect x="920" y="505" width="570" height="55" rx="8" fill="#1c2128" stroke="#8b949e" stroke-width="1.5" stroke-dasharray="5,4"/>
  <text x="1205" y="538" text-anchor="middle" fill="#8b949e" font-size="14" ${FONT}>T2/T3 — LLM, depth, TTS/ASR — on demand only (Day 10+)</text>

  <text x="1205" y="582" text-anchor="middle" fill="#3fb950" font-size="14" font-weight="bold" ${FONT}>Process-per-workload, latest-wins queue depth 1</text>

  <text x="60" y="680" fill="#8b949e" font-size="13" ${FONT}>Day 7 built and verified the T0 layer only — capture, motion gate, process boundary. No model yet.</text>
  <text x="60" y="705" fill="#8b949e" font-size="13" ${FONT}>The dashed boxes (T1/T2/T3) are the Day 8+ plan, shown here for context, not shipped this session.</text>
  `;
  await renderSvgToPng('01-architecture-before-after', W, H, svg);
}

// ---------------------------------------------------------------------------
// 2. Tier scheduler T0-T3
// ---------------------------------------------------------------------------
{
  const W = 1600, H = 780;
  const tiers = [
    { t: 'T0 — ALWAYS', desc: 'frame differencing motion gate, voice-activity detection', cost: '~1-3% CPU · no neural nets', color: '#3fb950', built: 'BUILT + MEASURED DAY 7' },
    { t: 'T1 — AMBIENT SENSE', desc: 'detection + tracking, only when motion clears the gate', cost: '5-10 Hz, one small model', color: '#58a6ff', built: 'PLANNED DAY 8' },
    { t: 'T2 — DEEP LOOK', desc: 'depth, segmentation, pose, OCR, open-vocab relabel, face', cost: 'on demand, rare, bounded', color: '#a371f7', built: 'PLANNED DAY 12-13' },
    { t: 'T3 — RESPOND', desc: 'STT → intent → LLM → TTS, only after wake word / push-to-talk', cost: 'expensive, rare, user is waiting', color: '#f0883e', built: 'PLANNED DAY 10-11' },
  ];
  let rows = '';
  tiers.forEach((tier, i) => {
    const y = 140 + i * 150;
    rows += `
    <rect x="80" y="${y}" width="1440" height="120" rx="10" fill="#161b22" stroke="${tier.color}" stroke-width="2"/>
    <rect x="80" y="${y}" width="14" height="120" fill="${tier.color}"/>
    <text x="120" y="${y + 40}" fill="${tier.color}" font-size="20" font-weight="bold" ${FONT}>${tier.t}</text>
    <text x="120" y="${y + 70}" fill="#e6edf3" font-size="15" ${FONT}>${tier.desc}</text>
    <text x="120" y="${y + 98}" fill="#8b949e" font-size="14" ${FONT}>${tier.cost}</text>
    <text x="1500" y="${y + 65}" text-anchor="end" fill="${i === 0 ? '#3fb950' : '#6e7681'}" font-size="13" font-weight="bold" ${FONT}>${tier.built}</text>
    `;
  });
  const svg = `
  <text x="60" y="55" fill="#e6edf3" font-size="26" font-weight="bold" ${FONT}>The attention budget — four tiers</text>
  <text x="60" y="85" fill="#8b949e" font-size="15" ${FONT}>"JARVIS answers. He does not narrate." — v2-architecture-research.md §2</text>
  ${rows}
  <text x="60" y="745" fill="#8b949e" font-size="13" ${FONT}>Priority inversion is explicit: when T3 is answering a question, T1 drops its rate to give it the machine.</text>
  `;
  await renderSvgToPng('02-tier-scheduler', W, H, svg);
}

// ---------------------------------------------------------------------------
// 3. Stuck download bar
// ---------------------------------------------------------------------------
{
  const W = 1600, H = 680;
  const maxMin = 8;
  const barLeft = 300;
  const barW = 1000;
  function bar(y, label, minutes, color, note) {
    const w = Math.min(barW, (minutes / maxMin) * barW);
    return `
    <text x="${barLeft - 20}" y="${y + 30}" text-anchor="end" fill="#e6edf3" font-size="15" ${FONT}>${label}</text>
    <rect x="${barLeft}" y="${y}" width="${barW}" height="44" fill="#1c2128" stroke="#30363d"/>
    <rect x="${barLeft}" y="${y}" width="${w}" height="44" fill="${color}"/>
    <text x="${barLeft}" y="${y + 66}" fill="${color}" font-size="15" font-weight="bold" ${FONT}>${note}</text>
    `;
  }
  const svg = `
  <text x="60" y="55" fill="#e6edf3" font-size="26" font-weight="bold" ${FONT}>Model load time: measured then, measured now</text>
  <text x="60" y="85" fill="#8b949e" font-size="15" ${FONT}>Qwen2.5-0.5B cold load, ${'"'}loading${'"'} → ready</text>

  ${bar(150, 'D13 (Day 4 session)', 63 / 60, '#3fb950', '45-63s — resolved normally')}
  ${bar(270, 'D13 warm reload', 11 / 60, '#58a6ff', '~11s — cache hit')}
  ${bar(390, 'Day 7 (this session)', 8, '#ff7b72', '7+ min — never resolved, harness gave up waiting')}

  <line x1="${barLeft}" y1="500" x2="${barLeft + barW}" y2="500" stroke="#30363d"/>
  <text x="${barLeft}" y="524" fill="#8b949e" font-size="13" ${FONT}>0 min</text>
  <text x="${barLeft + barW}" y="524" text-anchor="end" fill="#8b949e" font-size="13" ${FONT}>8 min</text>

  <text x="60" y="580" fill="#e6edf3" font-size="15" ${FONT}>Outbound network worked the whole time (curl, plain Puppeteer page both fetched huggingface.co fine).</text>
  <text x="60" y="608" fill="#e6edf3" font-size="15" ${FONT}>The failure was specific to large chunked model-shard fetches inside headless Chrome under load —</text>
  <text x="60" y="636" fill="#ff7b72" font-size="15" font-weight="bold" ${FONT}>three independent, uncoordinated loading pipelines, caught failing in the act.</text>
  `;
  await renderSvgToPng('03-stuck-download', W, H, svg);
}

// ---------------------------------------------------------------------------
// 4. Scenario A-E CPU bars
// ---------------------------------------------------------------------------
{
  const W = 1600, H = 660;
  const scenarios = [
    { id: 'A', label: 'Detection only', cpu: 72.7, lines: 0 },
    { id: 'B', label: '+ template narration', cpu: 74.1, lines: 8 },
    { id: 'C', label: '+ local-llm/tts (loading)', cpu: 76.2, lines: 8 },
    { id: 'D', label: '+ push-to-talk', cpu: 74.7, lines: 8 },
    { id: 'E', label: 'IDLE — nothing moving', cpu: 72.4, lines: 0 },
  ];
  const barLeft = 300;
  const barMaxW = 800;
  const maxCpu = 100;
  let rows = '';
  scenarios.forEach((s, i) => {
    const y = 130 + i * 90;
    const w = (s.cpu / maxCpu) * barMaxW;
    const color = s.id === 'E' ? '#ff7b72' : '#58a6ff';
    rows += `
    <text x="${barLeft - 20}" y="${y + 34}" text-anchor="end" fill="#e6edf3" font-size="16" font-weight="bold" ${FONT}>${s.id}</text>
    <text x="${barLeft - 20}" y="${y + 52}" text-anchor="end" fill="#8b949e" font-size="12" ${FONT}>${s.label}</text>
    <rect x="${barLeft}" y="${y}" width="${barMaxW}" height="56" fill="#1c2128" stroke="#30363d"/>
    <rect x="${barLeft}" y="${y}" width="${w}" height="56" fill="${color}"/>
    <text x="${barLeft + w + 16}" y="${y + 34}" fill="${color}" font-size="18" font-weight="bold" ${FONT}>${s.cpu}%</text>
    <text x="${barLeft + barMaxW + 110}" y="${y + 34}" fill="#8b949e" font-size="14" ${FONT}>${s.lines} lines produced</text>
    `;
  });
  const svg = `
  <text x="60" y="55" fill="#e6edf3" font-size="26" font-weight="bold" ${FONT}>CPU floor is flat, whether anything is happening or not</text>
  <text x="60" y="85" fill="#8b949e" font-size="15" ${FONT}>Main-thread busy fraction, per scenario — day7-baseline.md</text>
  ${rows}
  <text x="60" y="620" fill="#ff7b72" font-size="16" font-weight="bold" ${FONT}>Scenario E: ~72% of one CPU core, continuously, for zero narration lines in a full minute.</text>
  `;
  await renderSvgToPng('04-scenario-cpu-flat', W, H, svg);
}

console.log('done');
