# ACPx 0.19.1 alignment draft

Additive review note for the OpenClaw target snapshot. This file does not
rewrite historical 0.19.0, 0.18.0, or earlier run/proof artifacts.

## Target material

| Field | Value |
| --- | --- |
| OpenClaw target snapshot | `482a4b2c499a053b173c5d36d78cf67b9137e013` |
| `@openclaw/acpx` | `2026.9.7` |
| OpenClaw dependency | `acpx@0.19.1` |
| Published package | `acpx@0.19.1` |
| npm tarball | `https://registry.npmjs.org/acpx/-/acpx-0.19.1.tgz` |
| npm integrity | `sha512-zKVZVM6tHGXmdXU+sC30jdFLzz0ZpNLMorYKH+it3XcuEcvFl20sLbHPqfdjfsLfV+PmhRDEm1b9Np5KxgFHow==` |
| tarball sha256 | `f99d74e81085121563c917f4509758fb78bf1fa30424e469193c09837592bbf0` |
| `package/dist/runtime.js` sha256 | `5dfd93c5345bd039f9ab8f50afdf1b621e7ba46c41575d07c2637aa31dea546e` |
| `package/dist/agent-registry.js` sha256 | `bbc57d4f195f93ceb93b4a71fa9c0d51e9717867d728623e97c8e8f81c18f48c` |
| npm pack | 40 files; 634.5 kB package / 2.8 MB unpacked |
| engines | Node `>=22.13.0` |
| published gitHead | unpublished; none invented |

`482a4b2c499a053b173c5d36d78cf67b9137e013` is verified current OpenClaw
main. That commit depends on published `acpx@0.19.1` through
`@openclaw/acpx` `2026.9.7`. This is an upstream dependency watch, not a
published-package gitHead, not the 0.18.0 Puppet candidate, and not
Puppet/provider qualification or live VM/provider migration.

## Native bridge pin

Both `bridge/cursor-acp` and `bridge/antigravity-acp` now pin published
`acpx@0.19.1` in `package.json`, `package-lock.json`, and
`THIRD_PARTY_NOTICES.md`. Lockfile integrity matches the published npm
integrity above. Local `npm install --ignore-scripts` in those bridge
directories is the only install used; no shared plugin install was run.

The last independently inspected Antigravity source commit
`50a47ad10a75431cbc276ec9b555d11fe1f69c84` remains recorded as the 0.17.1
watch identity. It is not a claimed `acpx@0.19.1` gitHead.

## Candidate closure

Current candidate identity still names the local exact-source 0.18.0 tarball
at `runs/puppet-dual-acp-controller-runs/20260921/artifacts-refresh-2e05de52/acpx-0.18.0.tgz`
with artifact sha256
`5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614`
and merge commit `2e05de525dd1ab62e9e74bf02d91e3638920fcf3`.
That hash and commit are preserved. Historical `#648`, refresh, and `f888`
fences are unchanged. This pin does not relabel the active Puppet
candidate as 0.19.1 and does not claim an all-runtime migration.

Current fields that had to change for a truthful ordinary pin:

- ordinary native pin: `0.19.1`
- published npm version: `0.19.1`
- published npm is not the candidate merge tarball

Qualification remains `synthetic_only`. No live provider, AGY turn, VM, or
shared install. PR77 model-default changes are out of scope.

## Public runtime proof

Focused Node tests import the installed published package's
`acpx/runtime` (`createAcpRuntime`) and `acpx/agent-registry`
(`createAgentRegistry`), check offline constructor shape, and exercise a
local synthetic-peer turn plus owned-child retirement on both bridges.
