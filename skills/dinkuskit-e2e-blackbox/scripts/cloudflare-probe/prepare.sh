#!/usr/bin/env bash
set -euo pipefail
cd /workspace/crabbox/e2e-probe
export PLAYWRIGHT_BROWSERS_PATH=/workspace/crabbox/e2e-probe/browsers
npm ci --ignore-scripts --no-audit --no-fund
./node_modules/.bin/playwright install --with-deps chromium
node --input-type=module <<'JS'
import { writeFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
writeFileSync('prepared.json', JSON.stringify({
  preparedId: randomUUID(),
  node: process.version,
  playwright: require('playwright/package.json').version,
  publicDependenciesOnly: true,
}, null, 2) + '\n', { flag: 'wx' });
console.log('E2E_PUBLIC_PREPARATION_COMPLETE');
JS
