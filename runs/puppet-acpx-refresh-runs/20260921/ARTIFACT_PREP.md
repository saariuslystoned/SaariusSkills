# acpx candidate refresh artifact preparation

- upstream repository: `https://github.com/openclaw/acpx.git`
- frozen merged source commit: `ce8c3689fe830fd5c6199a8a683dc979d180af1d` (`#672`, `fix(runtime): release events when turn observers stop reading`)
- source tree: `04661dbf3af3b3c2a11d16c3061b40e20ce29f4a`
- source archive SHA-256: `bc093bc9b1ef12efeba9b444460d07a1a4e77e141328dd28779d7581840489ec`
- source checkout: `/Users/bobbybones/Developer/worktrees/saariusskills-acpx-refresh-20260921/runs/puppet-acpx-refresh-runs/20260921/upstream-ce8c3689`
- package version: `0.18.0` (candidate-only; not a release or ordinary pin)
- runtime entry: `package/dist/runtime.js`
- artifact: `/Users/bobbybones/Developer/worktrees/saariusskills-acpx-refresh-20260921/runs/puppet-acpx-refresh-runs/20260921/artifacts/acpx-0.18.0.tgz`
- artifact bytes: `599898`
- artifact SHA-256: `ad9bc677a6687268010da9c57b83fd96d2d35eddafdb55a6e043fd70679cc342`
- tools: Node `v22.23.1`, pnpm `11.26.0`
- preparation commands: `pnpm install --frozen-lockfile --ignore-scripts`; `pnpm run build:quiet`; `npm pack --ignore-scripts --pack-destination .../artifacts`
- note: npm pack emitted the package's `prepare` hook message; all work remained in the task-local upstream checkout and no release/publication occurred.

## Actual runtime JavaScript import closure

Resolved from the packed `package/dist/runtime.js` relative imports and recursively followed through the package payload:

| package-relative file | SHA-256 |
| --- | --- |
| `package/dist/runtime.js` | `3069c9150a2d363ba9b8a2f9017421c8a7cfa830b76b862632d9e043ee1b0a9b` |
| `package/dist/ipc-BJj6maTF.js` | `ad21638d1f1b268cbcb37c277fe967a939ab724038f9a56513027d64d4a0f0f8` |
| `package/dist/queue-owner-runtime-BrlBT0l1.js` | `05006d0379e816a4ad6c4a8e07662de1fa43f89a89350c3220610dbdd292ffa8` |
| `package/dist/agent-registry-DdKB-zia.js` | `ee56531aff530a9e319f77ca7a14fbaf9abc883bf6c27008b93eed71443236a0` |
| `package/dist/watch-DBPaCPrt.js` | `62fb992328ee60519a65a98612a644c49910b63f31ab0344232f32768a54cd15` |

The remaining package files are retained in the archive and are not silently omitted from provenance; this table is the loaded runtime JS closure only.
