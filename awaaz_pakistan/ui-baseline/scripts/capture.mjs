import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const playwrightPath = process.env.PLAYWRIGHT_MODULE || path.join(os.tmpdir(), 'awaaz_pw', 'node_modules', 'playwright');
const { chromium } = require(playwrightPath);
const here = path.dirname(fileURLToPath(import.meta.url));
const outputDir = path.resolve(here, '..');
const baseURL = process.env.AWAAZ_BASE_URL || 'http://127.0.0.1:5173';
const edgePath = process.env.EDGE_PATH || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const widths = [390, 768, 1440];
const heightFor = (width) => width === 390 ? 844 : width === 768 ? 1024 : 900;
const settle = async (page, delay = 1500) => {
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(delay);
};
const shot = async (page, name, fullPage = false) => {
  await settle(page);
  await page.screenshot({ path: path.join(outputDir, `${name}_${page.viewportSize().width}.png`), fullPage });
};

const browser = await chromium.launch({ executablePath: edgePath, headless: true });
try {
  for (const width of widths) {
    const context = await browser.newContext({ viewport: { width, height: heightFor(width) }, reducedMotion: 'reduce' });
    await context.addInitScript(() => {
      sessionStorage.setItem('awaaz_admin_key', 'awaaz-admin-2024');
      const track = { stop() {} };
      const stream = { getTracks: () => [track] };
      Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia: async () => stream }, configurable: true });
      class FakeRecorder {
        static isTypeSupported() { return true; }
        constructor() { this.state = 'inactive'; this.mimeType = 'audio/webm'; }
        start() { this.state = 'recording'; }
        stop() { this.state = 'inactive'; this.ondataavailable?.({ data: new Blob(['baseline-audio'], { type: this.mimeType }) }); this.onstop?.(); }
      }
      Object.defineProperty(window, 'MediaRecorder', { value: FakeRecorder, configurable: true });
      const audioNode = { connect() {} };
      class FakeAudioContext {
        constructor() { this.state = 'running'; }
        createAnalyser() { return { fftSize: 256, frequencyBinCount: 128, getByteFrequencyData(a) { a.fill(12); } }; }
        createMediaStreamSource() { return audioNode; }
        close() { this.state = 'closed'; return Promise.resolve(); }
      }
      Object.defineProperty(window, 'AudioContext', { value: FakeAudioContext, configurable: true });
    });
    const page = await context.newPage();

    await page.goto(`${baseURL}/`);
    await shot(page, 'home', true);

    await page.locator('#report').scrollIntoViewIfNeeded();
    await page.getByRole('button', { name: 'Start Recording Voice Complaint' }).click();
    await shot(page, 'recording');
    await page.getByRole('button', { name: 'Stop Recording' }).click();

    const report = page.locator('#report');
    await report.locator('button').nth(2).click();
    const textarea = report.locator('textarea');
    await textarea.fill('Vendor in F-10 Markaz is charging above the official price.');

    await page.route('**/api/complaints/text', async route => {
      await new Promise(resolve => setTimeout(resolve, 5000));
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        id: 'baseline-success-001', transcript_raw: 'Vendor in F-10 Markaz is charging above the official price.',
        detected_language: 'English', category: 'PERA - Overpricing', urgency: 'High', item_name: 'Potato',
        reported_price: 200, official_price: 100, percentage_overcharge: 100, is_violation: true,
        native_response: 'Your complaint has been registered and routed for enforcement.',
        routing_agency: 'PERA - Price Enforcement', helpline_reference: '1717', location_area: 'F-10 Markaz'
      }) });
    });
    const submit = report.locator('button').filter({ hasText: /Submit|Report|شکایت/i }).last();
    await submit.click();
    await page.waitForTimeout(800);
    await shot(page, 'uploading');
    await page.waitForTimeout(5000);
    await shot(page, 'success');

    await page.unroute('**/api/complaints/text');
    await page.route('**/api/complaints/text', route => route.fulfill({ status: 422, contentType: 'application/json', body: '{"detail":"Baseline forced validation error"}' }));
    await textarea.fill('Force validation error for baseline.');
    await submit.click();
    await page.waitForTimeout(500);
    await shot(page, 'error');

    await page.goto(`${baseURL}/admin`);
    await shot(page, 'admin');
    await shot(page, 'dashboard');

    await page.goto(`${baseURL}/baseline-not-a-route`);
    await shot(page, 'not-found');
    await context.close();
  }
} finally {
  await browser.close();
}
console.log(`Captured UI baseline at ${outputDir}`);
