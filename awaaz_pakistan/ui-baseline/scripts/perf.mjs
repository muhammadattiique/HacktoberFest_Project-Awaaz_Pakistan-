/**
 * Phase 0 baseline: frontend runtime performance (load time + 3D FPS).
 *
 * Uses Playwright (installed ephemerally outside the project, same convention
 * as capture.mjs) driving installed Edge/Chrome via CDP. Applies a mid-range
 * phone profile: 390x844 mobile viewport + 4x CPU throttling. Measures:
 *   - home dashboard/hero load time (navigation + first contentful paint)
 *   - 3D avatar canvas FPS via requestAnimationFrame counting (~10 s)
 *   - admin dashboard load time (authorised via sessionStorage demo key)
 *
 * Writes JSON to stdout; the PowerShell orchestrator captures it into
 * results/baseline/frontend.json. Does NOT add Playwright to project deps.
 *
 * Env:
 *   PLAYWRIGHT_MODULE  path to ephemeral playwright (default: %TEMP%/awaaz_pw)
 *   AWAAZ_BASE_URL     preview server base URL (default http://127.0.0.1:4173)
 *   EDGE_PATH          browser executable (default installed Edge)
 */
import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';

const require = createRequire(import.meta.url);
const playwrightPath =
  process.env.PLAYWRIGHT_MODULE ||
  path.join(os.tmpdir(), 'awaaz_pw', 'node_modules', 'playwright');
const { chromium } = require(playwrightPath);

const baseURL = process.env.AWAAZ_BASE_URL || 'http://127.0.0.1:4173';
const edgePath =
  process.env.EDGE_PATH ||
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const CPU_THROTTLE = 4; // mid-range phone
const FPS_WINDOW_MS = 10000;

const profile = {
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 3,
  isMobile: true,
  hasTouch: true,
  userAgent:
    'Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36',
};

async function navTiming(page) {
  return page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0] || {};
    const fcp = performance.getEntriesByName('first-contentful-paint')[0];
    return {
      dom_content_loaded_ms: nav.domContentLoadedEventEnd ? Math.round(nav.domContentLoadedEventEnd) : null,
      load_event_ms: nav.loadEventEnd ? Math.round(nav.loadEventEnd) : null,
      first_contentful_paint_ms: fcp ? Math.round(fcp.startTime) : null,
      response_end_ms: nav.responseEnd ? Math.round(nav.responseEnd) : null,
    };
  });
}

async function measureFps(page) {
  return page.evaluate((windowMs) => {
    return new Promise((resolve) => {
      let frames = 0;
      const start = performance.now();
      function tick(now) {
        frames += 1;
        if (now - start >= windowMs) {
          const elapsed = (now - start) / 1000;
          resolve({ frames, elapsed_s: Number(elapsed.toFixed(2)), fps: Number((frames / elapsed).toFixed(1)) });
        } else {
          requestAnimationFrame(tick);
        }
      }
      requestAnimationFrame(tick);
    });
  }, FPS_WINDOW_MS);
}

async function withCdpThrottle(page) {
  const client = await page.context().newCDPSession(page);
  await client.send('Emulation.setCPUThrottlingRate', { rate: CPU_THROTTLE });
  return client;
}

const result = {
  profile: {
    viewport: profile.viewport,
    cpu_throttle_x: CPU_THROTTLE,
    fps_window_ms: FPS_WINDOW_MS,
    note: 'Mid-range phone emulation via CDP CPU throttle + mobile viewport. Software/host GPU, not a real device.',
  },
  base_url: baseURL,
  pages: {},
};

const browser = await chromium.launch({ executablePath: edgePath, headless: true });
try {
  // Home (hero contains the 3D avatar canvas)
  {
    const context = await browser.newContext(profile);
    const page = await context.newPage();
    await withCdpThrottle(page);
    const t0 = Date.now();
    await page.goto(`${baseURL}/`, { waitUntil: 'load' });
    const nav = await navTiming(page);
    await page.waitForTimeout(1500); // let the scene warm up
    const canvasPresent = await page.locator('canvas').count();
    const fps = canvasPresent > 0 ? await measureFps(page) : { note: 'no canvas found' };
    result.pages.home = {
      wall_goto_ms: Date.now() - t0,
      navigation_timing: nav,
      canvas_count: canvasPresent,
      three_d_fps: fps,
    };
    await context.close();
  }

  // Admin dashboard (authorised via demo key in sessionStorage)
  {
    const context = await browser.newContext(profile);
    await context.addInitScript(() => {
      sessionStorage.setItem('awaaz_admin_key', 'awaaz-admin-2024');
    });
    const page = await context.newPage();
    await withCdpThrottle(page);
    const t0 = Date.now();
    await page.goto(`${baseURL}/admin`, { waitUntil: 'load' });
    const nav = await navTiming(page);
    await page.waitForTimeout(1500);
    result.pages.dashboard = {
      wall_goto_ms: Date.now() - t0,
      navigation_timing: nav,
      note: 'Admin route is the current dashboard; data from demo fallback when backend absent.',
    };
    await context.close();
  }
} finally {
  await browser.close();
}

process.stdout.write(JSON.stringify(result, null, 2));
