import puppeteer from 'puppeteer';
import { mkdirSync } from 'node:fs';

const OUT = '/tmp/tau-burst';
mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  headless: true,
  args: ['--use-fake-ui-for-media-stream', '--no-sandbox'],
});
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 800 });
await page.goto('http://localhost:5186/?engine=1&bench=1');
await page.keyboard.press(' ');
await new Promise((r) => setTimeout(r, 3000)); // let camera+engine warm up

console.log('capturing burst now — move a hand quickly across frame');
const N = 14;
const INTERVAL_MS = 300;
for (let i = 0; i < N; i++) {
  await page.screenshot({ path: `${OUT}/f${String(i).padStart(2, '0')}.png` });
  await new Promise((r) => setTimeout(r, INTERVAL_MS));
}
console.log(`saved ${N} frames to ${OUT}, ${INTERVAL_MS}ms apart`);
await browser.close();
