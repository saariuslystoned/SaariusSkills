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
