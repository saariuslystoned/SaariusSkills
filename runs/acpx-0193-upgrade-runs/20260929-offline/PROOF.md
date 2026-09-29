# Proof packet

## Implementation

The new isolated worktree contains the bounded dependency upgrade for all three ACP bridge packages:

- `bridge/cursor-acp/package.json` and lockfile
- `bridge/antigravity-acp/package.json` and lockfile
- `bridge/grok-acp/package.json` and lockfile

The source/tag identity is pinned separately from the historical PR96 candidate identity. The antigravity runtime contract records the published npm metadata, including a null npm `gitHead`, and the cursor contract keeps the historical candidate commit unchanged.

## Artifact verification

The published npm artifact was inspected in a private temporary directory before editing repository files:

- npm version: `0.19.3`
- release tag commit: `6b4714c7aaac8c38b1fe38354848d2546f65d87d`
- tarball SHA-256: `670c6c707fc5c38f4fd71de4ab85d59d6571d09c090ecf39a2e52bc07306af60`
- `dist/runtime.js` SHA-256: `e12930a2d060551f6c72a1b4122fd2e1cb8b8d105106cef706aef88ed177d40f`
- `dist/agent-registry.js` SHA-256: `4473862f86362f2d10e1a41fc9df439230a0caf5d0f326ea774d3dc75973724d`
- npm integrity: `sha512-5YvCb+NG3XzDapxzrQRDS6zGN13mWZeugaeoq03kh9NCTFgJGzt7lrdC4jT2YXp9UV6Ieg8H+AYxs2y2+g1Z/g==`

Lockfiles were regenerated with `npm install --package-lock-only --ignore-scripts --no-audit --no-fund`; no shared runtime store or installed plugin was modified.

Private installs used `npm ci --ignore-scripts --no-audit --no-fund` separately in each bridge worktree directory. Direct bridge regressions passed: Cursor 76 passed / 11 skipped, Antigravity 66 passed, and Grok 66 passed. The repository `npm run check` wrapper was not accepted as a pass because its OpenClaw Node test-isolation worker hung in `recovery.test.mjs` after the bridge suite; only the exact task-owned check processes were stopped.

## Review and release gates

This packet is an implementation checkpoint. Focused offline tests, commit, draft PR, independent review, and the official legacy Spark2 review rail remain required. Live provider qualification, installed update, and merge remain separately gated.
