/**
 * Phase 0 baseline: tiny static file server for the production build.
 *
 * Serves awaaz_pakistan/dist on a fixed port for Lighthouse + perf.mjs. This
 * replaces `vite preview` in the benchmark driver because the npm -> vite child
 * process launched under PowerShell Start-Process proved unreliable across
 * back-to-back headless-Chrome runs (the server died after the first run,
 * producing CHROME_INTERSTITIAL_ERROR and ERR_CONNECTION_REFUSED). A plain
 * long-lived Node server removes that flakiness while still serving the exact
 * production bundle.
 *
 * SPA fallback: unknown non-asset paths return index.html so client routes such
 * as /admin resolve, matching how the app is deployed.
 *
 * Usage:  node static_server.mjs <distDir> <port>
 */
import http from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import path from 'node:path';

const distDir = path.resolve(process.argv[2] || 'dist');
const port = Number(process.argv[3] || 4173);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
};

function resolveFile(urlPath) {
  const clean = decodeURIComponent(urlPath.split('?')[0]);
  let fp = path.join(distDir, clean);
  if (!fp.startsWith(distDir)) return null; // path traversal guard
  if (existsSync(fp) && statSync(fp).isFile()) return fp;
  // SPA fallback for client-side routes without a file extension.
  if (!path.extname(clean)) {
    const index = path.join(distDir, 'index.html');
    if (existsSync(index)) return index;
  }
  return null;
}

const server = http.createServer((req, res) => {
  const fp = resolveFile(req.url || '/');
  if (!fp) {
    res.statusCode = 404;
    res.end('Not found');
    return;
  }
  res.setHeader('Content-Type', TYPES[path.extname(fp)] || 'application/octet-stream');
  res.setHeader('Cache-Control', 'no-store');
  createReadStream(fp).pipe(res);
});

server.listen(port, '127.0.0.1', () => {
  process.stdout.write(`static_server listening http://127.0.0.1:${port} serving ${distDir}\n`);
});
