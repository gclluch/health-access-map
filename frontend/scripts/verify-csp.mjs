// Verify the production Content-Security-Policy against a real browser render (BACKLOG D2).
//
// Serves the built dist/ with the EXACT CSP + security headers from nginx.conf, loads it in
// headless Chromium, and fails if: any CSP violation fires, the Carto basemap is blocked, or a
// required origin is missing from the policy. This is the headed-browser check the nginx comment
// asks for ("VERIFY in a real browser before trusting this in prod"), runnable in CI.
//
//   node scripts/verify-csp.mjs        (run `npm run build` first; needs network for Carto)
import { createServer } from 'node:http';
import { readFileSync, existsSync, statSync } from 'node:fs';
import { join, extname, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const dist = join(root, 'dist');
const nginxConf = readFileSync(join(root, 'nginx.conf'), 'utf8');

// Pull the CSP and the other security headers straight out of nginx.conf so this test fails the
// moment the deployed policy drifts from what we verified.
const cspMatch = nginxConf.match(/Content-Security-Policy "([^"]+)"/);
if (!cspMatch) { console.error('FAIL: no Content-Security-Policy found in nginx.conf'); process.exit(1); }
const CSP = cspMatch[1];

// Origins the app provably needs; a policy missing any of these would break the live map.
const REQUIRED = ['https://basemaps.cartocdn.com', 'https://*.basemaps.cartocdn.com',
  'https://fonts.gstatic.com', 'https://fonts.googleapis.com'];
const missing = REQUIRED.filter((o) => !CSP.includes(o));
if (missing.length) { console.error('FAIL: CSP missing required origins:', missing); process.exit(1); }

if (!existsSync(join(dist, 'index.html')) || !existsSync(join(dist, 'metrics.json'))) {
  console.error('FAIL: dist/ not built (run `npm run build` with real public/ payloads first)');
  process.exit(1);
}

const MIME = {
  '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css',
  '.json': 'application/json', '.geojson': 'application/geo+json', '.pmtiles': 'application/octet-stream',
  '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.woff2': 'font/woff2',
};

// Static server that stamps the real prod headers (byte ranges for pmtiles so tiles stream).
const server = createServer((req, res) => {
  const urlPath = decodeURIComponent((req.url || '/').split('?')[0]);
  let file = join(dist, urlPath === '/' ? 'index.html' : urlPath);
  if (!existsSync(file) || !statSync(file).isFile()) file = join(dist, 'index.html'); // SPA fallback
  const body = readFileSync(file);
  res.setHeader('Content-Security-Policy', CSP);
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Content-Type', MIME[extname(file)] || 'application/octet-stream');
  res.setHeader('Accept-Ranges', 'bytes');
  const range = req.headers.range;
  if (range && /^bytes=\d*-\d*$/.test(range)) {
    const [a, b] = range.replace('bytes=', '').split('-');
    const start = a ? Number(a) : 0;
    const end = b ? Number(b) : body.length - 1;
    res.statusCode = 206;
    res.setHeader('Content-Range', `bytes ${start}-${end}/${body.length}`);
    res.end(body.subarray(start, end + 1));
  } else {
    res.end(body);
  }
});

await new Promise((r) => server.listen(0, r));
const port = server.address().port;
const url = `http://localhost:${port}/`;

const browser = await chromium.launch({
  args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader'],
});
const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
const violations = [];
const blocked = [];
page.on('console', (m) => {
  const t = m.text();
  if (/content security policy|refused to (load|connect|apply)/i.test(t)) violations.push(t);
});
page.on('pageerror', (e) => violations.push('pageerror: ' + e.message));
page.on('requestfailed', (r) => {
  const u = r.url();
  if (/cartocdn\.com|fonts\.g(oogleapis|static)\.com/.test(u)) blocked.push(`${u} (${r.failure()?.errorText})`);
});
let carto = 0;
page.on('requestfinished', (r) => { if (r.url().includes('cartocdn.com')) carto += 1; });

await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
await page.waitForTimeout(8000); // let the basemap + tiles load under the policy

// The map canvas must exist and have painted (deck/maplibre WebGL canvas).
const canvasOk = await page.evaluate(() => {
  const c = document.querySelector('canvas');
  return !!c && c.width > 0 && c.height > 0;
});

await browser.close();
await new Promise((r) => server.close(r));

const problems = [];
if (violations.length) problems.push(`${violations.length} CSP violation(s): ${violations.slice(0, 4).join(' | ')}`);
if (blocked.length) problems.push(`${blocked.length} blocked dependency request(s): ${blocked.slice(0, 4).join(' | ')}`);
if (!carto) problems.push('Carto basemap tiles never loaded (0 cartocdn requests) - basemap likely blocked');
if (!canvasOk) problems.push('map canvas did not render');

if (problems.length) {
  console.error('CSP VERIFY FAILED:\n - ' + problems.join('\n - '));
  process.exit(1);
}
console.log(`CSP VERIFY PASSED: 0 violations, ${carto} Carto tile requests OK, fonts OK, canvas rendered.`);
console.log('Policy:', CSP.slice(0, 90) + '...');
