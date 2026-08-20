#!/usr/bin/env node
// Day 9 measurement harness. Headless Chrome (fake camera device) + the
// Python engine (--synthetic-intermittent, no real camera in this session —
// see .claude/day9-results.md) driving the HUD over ?engine=1. Measures
// rAF delta distribution, message rate, CPU, still-scene behaviour, and
// engine-kill staleness. Instrumentation, not a feature — day9-prompt.md's
// own boundary rule, same as scripts/bench.mjs.
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';
import puppeteer from 'puppeteer';

const PORT = 5184;
const BASE_URL = `http://localhost:${PORT}/?engine=1&bench=1`;
const OUT_DIR = new URL('./bench-output/', import.meta.url);
mkdirSync(OUT_DIR, { recursive: true });
const ENGINE_DIR = new URL('../engine/', import.meta.url).pathname;
const WS_PORT = 8765;

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

async function main() {
  const server = spawn('npm', ['run', 'dev', '--', '--port', String(PORT), '--strictPort'], {
    cwd: new URL('../', import.meta.url).pathname,
    stdio: 'ignore',
  });
  await waitForServer();

  // detached: true so `uv run`'s actual python child (a separate PID `uv`
  // does not exec-replace itself with) lands in its own process group,
  // killable via the negative-PID group kill below. A plain
  // engine.kill('SIGKILL') was found, live, to kill only the `uv` wrapper
  // and orphan `main.py` still holding the WS port — the exact D29 shape
  // of gotcha (kill the child, not the parent) one process layer up.
  const engine = spawn(
    'uv',
    ['run', 'python', 'main.py', '--synthetic-intermittent', '--seconds', '30', '--ws-port', String(WS_PORT)],
    { cwd: ENGINE_DIR, stdio: ['ignore', 'ignore', 'pipe'], detached: true },
  );
  let engineStderr = '';
  engine.stderr.on('data', (d) => { engineStderr += d.toString(); });
  await sleep(2500); // let the model load and the bridge bind

  const browser = await puppeteer.launch({
    headless: true,
    args: [
      '--use-fake-ui-for-media-stream',
      '--use-fake-device-for-media-stream',
      '--enable-unsafe-webgpu',
      '--no-sandbox',
    ],
  });
  const page = await browser.newPage();
  await page.goto(BASE_URL, { waitUntil: 'networkidle0' });

  // Space toggles `active`.
  await page.keyboard.press(' ');
  await sleep(3000);

  const readyState = await page.evaluate(() => window.__yapStatus ?? null);

  await page.evaluate(() => window.__yapBench?.reset());
  await sleep(8000);
  const bench = await page.evaluate(() => {
    const dump = window.__yapBench?.dump();
    window.__yapBench?.stop();
    return dump;
  });
  const metrics = await page.metrics();
  const statusAfter = await page.evaluate(() => window.__yapStatus ?? null);

  // Row 6: kill the engine mid-run, confirm staleness surfaces within ~1s,
  // no freeze/crash.
  const killedAt = Date.now();
  try { process.kill(-engine.pid, 'SIGKILL'); } catch { engine.kill('SIGKILL'); }
  await sleep(400);
  const psCheck = spawn('pgrep', ['-fl', 'main.py']);
  let psOut = '';
  psCheck.stdout.on('data', (d) => { psOut += d.toString(); });
  await new Promise((r) => psCheck.on('close', r));

  let bannerMsAfterKill = null;
  for (let i = 0; i < 40; i++) {
    const visible = await page.evaluate(() => !!document.querySelector('.stale-banner'));
    if (visible) { bannerMsAfterKill = Date.now() - killedAt; break; }
    await sleep(50);
  }
  const staleVisible = bannerMsAfterKill !== null;
  const bannerText = await page.evaluate(() => document.querySelector('.stale-banner')?.textContent ?? null);
  const stillRunning = await page.evaluate(() => document.readyState === 'complete');

  const result = {
    readyState,
    bench,
    taskDurationMs: metrics.TaskDuration,
    statusAfter,
    staleVisible,
    bannerMsAfterKill,
    bannerText,
    engineProcessAfterKill: psOut || '(none — dead)',
    stillRunning,
    engineStderrTail: engineStderr.split('\n').slice(-15).join('\n'),
  };
  writeFileSync(new URL('./day9-bridge.json', OUT_DIR), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));

  await browser.close();
  server.kill();
  try { process.kill(-engine.pid, 'SIGKILL'); } catch { /* already dead */ }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
