import puppeteer from 'puppeteer';

const browser = await puppeteer.launch({
  headless: true,
  args: ['--use-fake-ui-for-media-stream', '--no-sandbox'], // real camera, auto-accept permission
});
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 800 });
await page.goto(`http://localhost:${process.env.PORT || 5185}/?engine=1&bench=1`);
await page.keyboard.press(' '); // start
await new Promise((r) => setTimeout(r, 4000));
const status = await page.evaluate(() => window.__yapStatus ?? null);
await page.screenshot({ path: process.env.OUT || '/tmp/real_hud_engine.png' });
console.log(JSON.stringify(status));
await browser.close();
