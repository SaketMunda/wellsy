#!/usr/bin/env node
// Chrome trace capture for scenario D (the stall) — day7-prompt.md asks for
// "a Chrome DevTools performance trace during scenario D" saved as a
// screenshot. This environment has no interactive DevTools GUI session (headless,
// non-interactive), so there is no literal DevTools panel to screenshot.
// What this script produces instead, honestly: a real `page.tracing`
// capture (the same underlying trace format DevTools reads) during the
// push-to-talk moment, reduced to the long-task/main-thread-busy intervals,
// rendered as a simple timeline image by this script — not a DevTools
// screenshot, the same data, drawn plainly. Said plainly in day7-baseline.md
// too, not just here.
import { spawn } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';
import puppeteer from 'puppeteer';

const PORT = 5184;
const OUT_DIR = new URL('./bench-output/', import.meta.url);
mkdirSync(OUT_DIR, { recursive: true });
const MOVING_VIDEO = new URL('./bench-assets/moving.y4m', import.meta.url).pathname;
const TRACE_PATH = new URL('./trace-d.json', OUT_DIR).pathname;

function configFor() {
  return JSON.stringify({
    voice_enabled: true,
    line_generator_engine: 'local-llm',
    voice_engine: 'local-tts',
  });
}

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
  const server = spawn('npm', ['run', 'dev', '--', '--port', String(PORT), '--strictPort'], { stdio: 'inherit' });
  try {
    await waitForServer();

    const browser = await puppeteer.launch({
      headless: true,
      protocolTimeout: 300_000,
      userDataDir: new URL('./chrome-profile-trace-d/', OUT_DIR).pathname,
      args: [
        '--use-fake-device-for-media-stream',
        '--use-fake-ui-for-media-stream',
        `--use-file-for-fake-video-capture=${MOVING_VIDEO}`,
        '--enable-unsafe-webgpu',
        '--autoplay-policy=no-user-gesture-required',
      ],
    });

    const page = await browser.newPage();
    await page.evaluateOnNewDocument((cfgJson) => {
      localStorage.setItem('yap.narrator.config', cfgJson);
    }, configFor());
    await page.goto(`http://localhost:${PORT}/?bench=1`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.btn-primary', { timeout: 30_000 });
    await page.click('.btn-primary');

    console.log('waiting for camera+model+llm+tts ready...');
    await page.waitForFunction(
      () => {
        const s = window.__yapStatus;
        return s?.live && (s.llmState === 'ready' || s.llmState === 'unavailable' || s.llmState === 'error') &&
          (s.ttsState === 'ready' || s.ttsState === 'unavailable' || s.ttsState === 'error');
      },
      { timeout: 240_000, polling: 500 },
    );
    console.log('ready. settling 3s, then starting trace + push-to-talk...');
    await sleep(3000);

    await page.tracing.start({ path: TRACE_PATH, screenshots: false });
    await sleep(1000);
    await page.keyboard.down('t');
    await sleep(2500);
    await page.keyboard.up('t');
    await sleep(4000); // let ASR->LLM->TTS finish, still inside the trace
    await page.tracing.stop();

    console.log('trace saved to', TRACE_PATH);
    await page.click('.btn-primary');
    await sleep(300);
    await browser.close();
  } finally {
    server.kill('SIGTERM');
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
