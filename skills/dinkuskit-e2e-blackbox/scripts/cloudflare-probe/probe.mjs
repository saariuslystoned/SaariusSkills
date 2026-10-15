import { chromium } from 'playwright';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { once } from 'node:events';

// Fixed public fixture: no merchant credentials, profiles, cookies, or DUT source.
const runId = process.argv[2];
if (!/^run[12]$/.test(runId ?? '')) throw new Error('Expected run1 or run2');
const outDir = `artifacts/owned-fixture-${runId}`;
await mkdir('artifacts', { recursive: true });
await mkdir(outDir, { recursive: false });
const prepared = JSON.parse(await readFile('prepared.json', 'utf8'));
const result = {
  schema: 'e2e-blackbox-public-probe-v1',
  runId,
  target: 'https://raw.githubusercontent.com/openclaw/crabbox/2bd85693b5fdea67d352516e082b90f8cacfe07b/README.md',
  startedAt: new Date().toISOString(),
  prepared,
  platform: process.platform,
  status: 'FAIL',
};
let browser;
let context;
let tracingStarted = false;
try {
  browser = await chromium.launch({ headless: true });
  result.browser = browser.version();
  context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await context.tracing.start({ screenshots: true, snapshots: true, sources: false });
  tracingStarted = true;
  const externalPage = await context.newPage();
  const response = await externalPage.goto(result.target, { waitUntil: 'load', timeout: 30_000 });
  result.httpStatus = response?.status();
  result.finalUrl = externalPage.url();
  if (result.httpStatus !== 200 || result.finalUrl !== result.target) {
    throw new Error('Immutable public HTTPS source request failed');
  }
  const page = await context.newPage();
  await page.setContent(`<!doctype html><html lang="en"><head>
    <meta charset="utf-8"><title>Crabbox synthetic browser probe</title>
    <style>body{font:22px system-ui;padding:64px;color:#163248;background:#eef6fa}
    button{font:inherit;padding:12px}#result{margin-top:24px;color:#065f46}</style>
    </head><body><h1>Crabbox synthetic browser probe</h1>
    <p>Immutable upstream source reached over HTTPS: HTTP 200.</p>
    <p>This is a public provider fixture, not EmDash acceptance.</p>
    <button onclick="document.getElementById('result').textContent='Click observed'">Exercise browser interaction</button>
    <p id="result">Awaiting click</p></body></html>`);
  await page.getByRole('button', { name: 'Exercise browser interaction', exact: true }).click();
  result.title = await page.title();
  result.heading = await page.getByRole('heading', { name: 'Crabbox synthetic browser probe', exact: true }).count();
  result.interaction = await page.locator('#result').textContent();
  await page.screenshot({ path: `${outDir}/page.png`, fullPage: true });
  if (result.title !== 'Crabbox synthetic browser probe' || result.heading !== 1 || result.interaction !== 'Click observed') {
    throw new Error('Owned synthetic browser fixture assertions failed');
  }
  result.status = 'PASS';
} catch (error) {
  result.error = String(error?.message ?? error);
} finally {
  try {
    if (tracingStarted) await context.tracing.stop({ path: `${outDir}/trace.zip` });
    if (browser) await browser.close();
  } catch (error) {
    result.status = 'FAIL';
    result.cleanupError = String(error?.message ?? error);
  }
}
result.finishedAt = new Date().toISOString();
await writeFile(`${outDir}/result.json`, JSON.stringify(result, null, 2) + '\n');

// Use Crabbox's supported stdout transport, not a private provider endpoint.
// Fixed filenames, bounded size, 32-KiB chunks, digest + end marker detect loss.
async function emit(record) {
  if (!process.stdout.write(`E2E_PUBLIC_ARTIFACT_V1 ${JSON.stringify(record)}\n`)) {
    await once(process.stdout, 'drain');
  }
}
for (const name of ['page.png', 'trace.zip', 'result.json']) {
  let bytes;
  try { bytes = await readFile(`${outDir}/${name}`); }
  catch (error) {
    if (error.code === 'ENOENT') continue;
    throw error;
  }
  if (bytes.length > 16 * 1024 * 1024) throw new Error('Artifact exceeds 16-MiB probe cap');
  const digest = createHash('sha256').update(bytes).digest('hex');
  const chunks = Math.ceil(bytes.length / 32768);
  await emit({ kind: 'begin', runId, name, size: bytes.length, sha256: digest, chunks });
  for (let n = 0; n < chunks; n++) {
    await emit({ kind: 'chunk', runId, name, n, data: bytes.subarray(n * 32768, (n + 1) * 32768).toString('base64') });
  }
  await emit({ kind: 'end', runId, name, sha256: digest });
}
await emit({ kind: 'complete', runId, status: result.status });
process.exitCode = result.status === 'PASS' ? 0 : 1;
