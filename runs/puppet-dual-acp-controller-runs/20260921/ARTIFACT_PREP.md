# Dual ACP controller artifact preparation

- repository: `saariuslystoned/SaariusSkills`
- worktree: `/Users/bobbybones/Developer/worktrees/saariusskills-dual-acp-controller-20260921`
- branch: `codex/puppet-dual-acp-controller-20260921`
- SaariusSkills base: `d0f0644f4ef4c84286d5307966514cf52cededc8`
- upstream repository: `openclaw/acpx`
- upstream source commit: `f8883645c261e07b2df7f9c3b4ad243b62d8168a` (`#678`)
- upstream source tree: `f4a4d33b33cdf5b57345e8420f24992953aed5e0`
- source archive SHA-256: `109b78327975061ffa80023da77d71b022d4f76d52c9ec216479457c3d1ecbf3`
- package: `acpx@0.18.0` exact-source local tarball
- artifact: `runs/puppet-dual-acp-controller-runs/20260921/artifacts/acpx-0.18.0.tgz`
- artifact SHA-256: `642d4c299bd58b275ca1a360196f3077fc4f84997e2654542f492b1e0001c162`
- runtime entry: `package/dist/runtime.js`
- package install: `pnpm install --frozen-lockfile --ignore-scripts`
- package build: `pnpm run build:quiet`
- package command: `npm pack --ignore-scripts --pack-destination .../artifacts`

The pack command emitted the package `prepare` hook message for `husky` while
creating the local tarball; no publication or shared installation occurred.

## Actual packed runtime import closure

Hashed from relative JavaScript imports reachable from `package/dist/runtime.js`:

| package-relative file | SHA-256 |
| --- | --- |
| `package/dist/agent-registry-DdKB-zia.js` | `ee56531aff530a9e319f77ca7a14fbaf9abc883bf6c27008b93eed71443236a0` |
| `package/dist/ipc-CCJ2waMg.js` | `d3b7a1bf7da1ffab5aade3807ead047a8c6ec800e83e6c370fcea75199e06996` |
| `package/dist/queue-owner-runtime-COxM7rJy.js` | `3d14a07018f86e3e36027e5bb9df119c5670988adc6a9f03530b88d9f7d4997a` |
| `package/dist/runtime.js` | `089b8706773cb9b31a38682857782632d0d9d31536622d9b36a6ebccb16a254a` |
| `package/dist/watch-B7jHtFtm.js` | `9b3f10f364eb3bd4cbb7297ebfa70b0b6d0fee5d984d9f9d6ffe3526081f8931` |

Count: 5 reachable JavaScript files.

No live Cursor or Antigravity qualification was launched during preparation.

## Refresh 2e05de52 exact-source artifact

The f888 archive above is preserved at
`runs/puppet-dual-acp-controller-runs/20260921/artifacts/acpx-0.18.0.tgz`
and is now a rejected historical fence. The current pin is a separate
task-local root:

- upstream source commit: `2e05de525dd1ab62e9e74bf02d91e3638920fcf3` (through `#689`)
- upstream source tree: `c612e764ead5d8eaa409956fb1b11c008a7579ed`
- PR head: `27e58b7dba7aa4e6e4bc0cc175ad6cdbc00587c7`
- PR base: `d4916ce050582c7415632c4e7cf84d285d268fa9`
- stale npm gitHead: `8699be1b6428fa7584acc6f07d87f5aec8945f58`
- artifact: `runs/puppet-dual-acp-controller-runs/20260921/artifacts-refresh-2e05de52/acpx-0.18.0.tgz`
- artifact SHA-256: `5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614`
- runtime root: `runs/puppet-dual-acp-controller-runs/20260921/runtime-refresh-2e05de52`
- runtime entry: `package/dist/runtime.js`
- runtime entry SHA-256: `ffdb6949b2239d991f63970514ad99677b19db1839313127a55ad9fcd30a4683`
- checkout: `runs/puppet-dual-acp-controller-runs/20260921/upstream-2e05de52` detached at the exact target
- package install: `pnpm install --frozen-lockfile --ignore-scripts` with pnpm 11.26.0
- package build: `pnpm run build:quiet`

### Actual packed runtime import closure

Hashed from relative JavaScript imports reachable from `package/dist/runtime.js`.
These names are the current packed chunks, not the historical f888 four-plus-entry list.

| package-relative file | SHA-256 |
| --- | --- |
| `package/dist/agent-registry-Ct2yWPW7.js` | `5091abb775cb9cfc36bc210acd84a830bd5a413db2ba61eab8a0ef22817230ba` |
| `package/dist/ipc-Bn8rocUR.js` | `33b50f531ae5bb3d39a56b9f325249631721aee54c764b1ce5a2f72a1eff98c0` |
| `package/dist/queue-owner-runtime-B-uQhwMC.js` | `fc4f3b27e6c003646539fc933a38c80886e1cdabf38d6f33a4abc7185d8b0d5b` |
| `package/dist/runtime.js` | `ffdb6949b2239d991f63970514ad99677b19db1839313127a55ad9fcd30a4683` |
| `package/dist/watch-yKB9yCio.js` | `06254f5cf0af1ee1b5855c0380469ea5f6b691d7f693cfa519288adb7798c635` |

Count: 5 reachable JavaScript files. Installed task-local bytes matched these
digests. `#687` was not cherry-picked. No publication or shared installation.
