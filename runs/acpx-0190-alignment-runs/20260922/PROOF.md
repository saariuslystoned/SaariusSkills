# ACPx 0.19.0 alignment draft

Additive review note for the OpenClaw target snapshot. This file does not
rewrite historical 0.18.0 or earlier run/proof artifacts.

## Target material

| Field | Value |
| --- | --- |
| OpenClaw target snapshot | `9c1b487adec0f2a3ca892d67c14f900c9d929bc7` |
| `@openclaw/acpx` | `2026.9.6` |
| Published package | `acpx@0.19.0` |
| npm integrity | `sha512-sgG0CkhuvVxgfiksXjIPEl9hsHZW0CpxywPdQeoIP5D31gwZE4nrnddLUUqaSCLb1UIM7LFPBL5qdvy15/+B6Q==` |
| tarball sha256 | `5a61820401cfed668ce3ad77a2feaebdd9e496a037ba28b2afca3224e7505c6d` |
| `package/dist/runtime.js` sha256 | `88a9799088146a191360a297bec94fb9006853a4420bef6257635a6b10520e1b` |
| published gitHead | unpublished; none invented |

`9c1b487adec0f2a3ca892d67c14f900c9d929bc7` is an ancestor of current OpenClaw
main `d15cac3f06178f7aa6a49d746ae2201dcd3eb4a4`. The post-target `d15cac3`
commit is not part of this alignment and does not change
`extensions/acpx` or the lock. This draft uses only the release-contained
target pin, not `d15` source and not `acpx@0.19.1`.

## Native bridge pin

Both `bridge/cursor-acp` and `bridge/antigravity-acp` now pin published
`acpx@0.19.0` in `package.json`, `package-lock.json`, and
`THIRD_PARTY_NOTICES.md`. Lockfile integrity matches the published npm
integrity above. Local `npm install --ignore-scripts` in those bridge
directories is the only install used; no shared plugin install was run.

The last independently inspected Antigravity source commit
`50a47ad10a75431cbc276ec9b555d11fe1f69c84` remains recorded as the 0.17.1
watch identity. It is not a claimed `acpx@0.19.0` gitHead.

## Candidate closure

Current candidate identity still names the local exact-source 0.18.0 tarball
at `runs/puppet-dual-acp-controller-runs/20260921/artifacts-refresh-2e05de52/acpx-0.18.0.tgz`
with artifact sha256
`5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614`.
That hash is preserved. Historical `#648`, refresh, and `f888` fences are
unchanged.

Current fields that had to change for a truthful ordinary pin:

- ordinary native pin: `0.19.0`
- published npm version: `0.19.0`
- published npm is not the candidate merge tarball

Qualification remains `synthetic_only`. No live provider, AGY turn, VM, or
shared install.

## Public runtime proof

Focused Node tests import the installed published package's
`acpx/runtime` (`createAcpRuntime`) and `acpx/agent-registry`
(`createAgentRegistry`) and check offline constructor shape only.
