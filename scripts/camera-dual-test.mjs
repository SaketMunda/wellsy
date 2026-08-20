import puppeteer from 'puppeteer';

const browser = await puppeteer.launch({
  headless: true,
  args: ['--use-fake-ui-for-media-stream', '--no-sandbox'], // NOT fake-device — real camera
});
const page = await browser.newPage();
await page.goto('http://localhost:5185/');
const result = await page.evaluate(async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    const track = stream.getVideoTracks()[0];
    const settings = track.getSettings();
    await new Promise((r) => setTimeout(r, 1500));
    const stillLive = track.readyState;
    stream.getTracks().forEach((t) => t.stop());
    return { ok: true, settings, stillLive };
  } catch (e) {
    return { ok: false, error: e.message, name: e.name };
  }
});
console.log(JSON.stringify(result, null, 2));
await browser.close();
