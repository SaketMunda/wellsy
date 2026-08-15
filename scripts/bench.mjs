#!/usr/bin/env node
// Day 7 measurement harness. Drives the app in headless Chrome (fake camera
// device) through scenarios A-E from day7-prompt.md and writes raw JSON per
// scenario to scripts/bench-output/. day7-baseline.md is the human-readable
// digest of what this produces — this script is instrumentation, not a
// feature (see .claude/day7-prompt.md's boundaries).
//
// Requires: scripts/bench-assets/{moving,still}.y4m — run
// scripts/generate-bench-assets.sh first. Run against `npm run dev`
// (not the production preview) because local-tts (Kokoro) only works there
// — see decisions.md D13.
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';
import puppeteer from 'puppeteer';

const PORT = 5183;
const BASE_URL = `http://localhost:${PORT}/?bench=1`;
const OUT_DIR = new URL('./bench-output/', import.meta.url);
mkdirSync(OUT_DIR, { recursive: true });

const MOVING_VIDEO = new URL('./bench-assets/moving.y4m', import.meta.url).pathname;
const STILL_VIDEO = new URL('./bench-assets/still.y4m', import.meta.url).pathname;

const RUN_MS = 60_000;
// D13 measured LLM cold load at ~45-63s on a clean run. In this session the
// same load hung in the 'loading' state for 7+ minutes without ever
// resolving to ready/error — genuinely stuck, not just slow (confirmed by
// waiting past 420s with zero progress). Waiting longer doesn't help, so the
// harness gives up after a bounded wait and proceeds with whatever state
// exists rather than blocking indefinitely — see runScenario below.
const READY_TIMEOUT_MS = 90_000;

function configFor(engine, voiceOn) {
  return JSON.stringify({
    voice_enabled: voiceOn,
    line_generator_engine: engine === 'template' ? 'template' : 'local-llm',
    voice_engine: engine === 'local' ? 'local-tts' : 'system',
  });
}

const SCENARIOS = [
  { id: 'A', label: 'detection only, narration off, voice off', video: MOVING_VIDEO, config: configFor('template', false), narrationOn: false, askQuestion: false },
  { id: 'B', label: 'A + template narration on', video: MOVING_VIDEO, config: configFor('template', false), narrationOn: true, askQuestion: false },
  { id: 'C', label: 'B + local-llm + local-tts', video: MOVING_VIDEO, config: configFor('local', true), narrationOn: true, askQuestion: false },
  { id: 'D', label: 'C + push-to-talk question mid-run', video: MOVING_VIDEO, config: configFor('local', true), narrationOn: true, askQuestion: true },
  { id: 'E', label: 'idle scene, full stack loaded, nothing moving', video: STILL_VIDEO, config: configFor('local', true), narrationOn: true, askQuestion: false },
];

async function waitForServer() {
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch(`http://localhost:${PORT}/`);
      if (res.ok) return;
    } catch {
      // not up yet
    }
    await sleep(500);
  }
  throw new Error('dev server did not come up in time');
}

async function runScenario(browser, scenario) {
  console.log(`\n=== Scenario ${scenario.id}: ${scenario.label} ===`);
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });

  page.on('pageerror', (err) => console.log('  [pageerror]', err.message));
  page.on('console', (msg) => {
    if (msg.type() === 'error') console.log('  [console.error]', msg.text());
  });

  await page.evaluateOnNewDocument((cfgJson) => {
    localStorage.setItem('yap.narrator.config', cfgJson);
  }, scenario.config);

  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });

  // Click the actual "Start camera" button rather than sending a synthetic
  // Space keypress: a keypress fired right after `domcontentloaded` races
  // React's mount — observed silently doing nothing (no error, camera never
  // starts) when the keydown listener wasn't attached yet. Waiting for the
  // real button to exist and clicking it has no such race.
  await page.waitForSelector('.btn-primary', { timeout: 30_000 });
  await page.click('.btn-primary');

  // Wait for camera+model live, and (if this scenario needs them) the LLM
  // and TTS to finish loading — cold LLM load alone is ~45-63s (D13), and we
  // don't want that inside the timed window. Polled manually (not
  // page.waitForFunction) so progress prints along the way — a silent
  // 4-minute wait gives no signal on whether it's downloading or stuck.
  const needLlm = scenario.config.includes('local-llm');
  const needTts = scenario.config.includes('local-tts');
  const readyDeadline = Date.now() + READY_TIMEOUT_MS;
  let lastLog = 0;
  let gaveUpWaiting = false;
  for (;;) {
    const s = await page.evaluate(() => window.__yapStatus);
    const llmDone = !needLlm || s?.llmState === 'ready' || s?.llmState === 'unavailable' || s?.llmState === 'error';
    const ttsDone = !needTts || s?.ttsState === 'ready' || s?.ttsState === 'unavailable' || s?.ttsState === 'error';
    if (s?.live && llmDone && ttsDone) break;
    if (Date.now() > readyDeadline) {
      // Don't block indefinitely on a model load that may simply never
      // resolve in this session (observed: 'loading' for 7+ minutes with
      // zero progress). Proceed with whatever state exists — a stuck-loading
      // scenario is itself real data about this session's network
      // conditions, worth recording rather than discarding the whole run.
      console.log(`  [gave up waiting] scenario ${scenario.id} not ready after ${READY_TIMEOUT_MS}ms — proceeding with last status ${JSON.stringify(s)}`);
      gaveUpWaiting = true;
      break;
    }
    if (Date.now() - lastLog > 15_000) {
      console.log(`  ...waiting: ${JSON.stringify(s)}`);
      lastLog = Date.now();
    }
    await sleep(1000);
  }

  const status = await page.evaluate(() => window.__yapStatus);
  console.log('  ready:', status, gaveUpWaiting ? '(gave up waiting for full load)' : '');

  // Narration defaults to on; scenario A wants it off.
  if (!scenario.narrationOn) {
    await page.keyboard.press('n');
  }

  // Reset the ring buffer now that load noise is out of the window.
  await page.evaluate(() => window.__yapBench.reset());

  // CDP TaskDuration = cumulative main-thread busy time (seconds) since the
  // page loaded. Delta over the window / wall-clock window = the fraction of
  // one CPU core the renderer's main thread kept busy — the closest thing to
  // an Activity-Monitor CPU% reading this headless, non-interactive
  // environment can produce for a specific process. It excludes the GPU
  // process and compositor thread, so it's a floor, not the whole number —
  // stated plainly in day7-baseline.md, not presented as the whole story.
  const cdp = await page.target().createCDPSession();
  await cdp.send('Performance.enable');
  const metricsBefore = await cdp.send('Performance.getMetrics');
  const wallStart = Date.now();

  let askedAt = null;
  if (scenario.askQuestion) {
    await sleep(RUN_MS / 2 - 1500);
    askedAt = Date.now() - wallStart;
    await page.keyboard.down('t');
    await sleep(2500); // hold, like a spoken question
    await page.keyboard.up('t');
    await sleep(RUN_MS / 2 - 1000);
  } else {
    await sleep(RUN_MS);
  }

  const metricsAfter = await cdp.send('Performance.getMetrics');
  const dump = await page.evaluate(() => window.__yapBench.dump());
  const finalStatus = await page.evaluate(() => window.__yapStatus);
  const panelText = await page.evaluate(() => document.body.innerText);

  const wallMs = Date.now() - wallStart;
  const taskBefore = metricsBefore.metrics.find((m) => m.name === 'TaskDuration')?.value ?? 0;
  const taskAfter = metricsAfter.metrics.find((m) => m.name === 'TaskDuration')?.value ?? 0;
  const cpuFraction = ((taskAfter - taskBefore) * 1000) / wallMs; // seconds->ms over ms

  const record = {
    scenario: scenario.id,
    label: scenario.label,
    runMs: wallMs,
    cpuFraction,
    askedAtMs: askedAt,
    readyStatus: status,
    gaveUpWaiting,
    finalStatus,
    dump,
    panelText,
  };
  writeFileSync(new URL(`./scenario-${scenario.id}.json`, OUT_DIR), JSON.stringify(record, null, 2));
  console.log(`  wrote scenario-${scenario.id}.json — ${dump.frameDeltas.length} frame samples, ${dump.longTasks.length} long tasks`);

  // The fake video capture device only serves one active session cleanly —
  // stop the camera (releases the MediaStream track) before closing the
  // page, or the next scenario's getUserMedia can hang indefinitely.
  await page.click('.btn-primary');
  await sleep(500);
  await page.close();
  return record;
}

async function main() {
  console.log('Starting dev server...');
  const server = spawn('npm', ['run', 'dev', '--', '--port', String(PORT), '--strictPort'], {
    stdio: 'inherit',
    env: { ...process.env },
  });
  server.on('error', (err) => {
    console.error('dev server failed to start', err);
    process.exit(1);
  });

  try {
    await waitForServer();

    const only = process.argv[2]; // optional: node scripts/bench.mjs D
    const scenarios = only ? SCENARIOS.filter((s) => s.id === only.toUpperCase()) : SCENARIOS;

    // The fake-video-capture file is a launch-time Chrome flag, so scenarios
    // sharing a video share one browser (and one on-disk profile) — that
    // lets the ~945MB LLM + Kokoro TTS download once and warm-load for every
    // later scenario in the group, instead of a multi-minute cold load
    // every single time (see D13's measured cold/warm numbers).
    const groups = new Map();
    for (const s of scenarios) {
      if (!groups.has(s.video)) groups.set(s.video, []);
      groups.get(s.video).push(s);
    }

    for (const [video, group] of groups) {
      const profileDir = new URL(`./chrome-profile-${video.split('/').pop()}/`, OUT_DIR).pathname;
      const browser = await puppeteer.launch({
        headless: true,
        protocolTimeout: 300_000, // this machine runs other concurrent processes; CDP calls have been observed to stall well past puppeteer's 180s default under load
        userDataDir: profileDir,
        args: [
          '--use-fake-device-for-media-stream',
          '--use-fake-ui-for-media-stream',
          `--use-file-for-fake-video-capture=${video}`,
          '--enable-unsafe-webgpu',
          '--enable-features=Vulkan',
          '--autoplay-policy=no-user-gesture-required',
          '--window-size=1280,800',
        ],
      });
      try {
        for (const scenario of group) {
          await runScenario(browser, scenario);
        }
      } finally {
        await browser.close();
      }
    }
  } finally {
    server.kill('SIGTERM');
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
