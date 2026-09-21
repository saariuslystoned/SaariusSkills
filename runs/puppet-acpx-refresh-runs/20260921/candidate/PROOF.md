# Puppet acpx candidate refresh proof

## Boundary

Disabled candidate-only Puppet adapter for one named local Cursor transport
(`cursor-acp`). The adapter now binds exact merged acpx main
`ce8c3689fe830fd5c6199a8a683dc979d180af1d` (`#672`) without claiming a
released npm package or changing ordinary launch.

The candidate helper materializes the exact local artifact under a new
task-owned runtime root and exercises the actual public `createAcpRuntime`
export with a deterministic local synthetic ACP peer. Draft PR #60 exists.
This repair cycle is a provider job only. It is not LIVE CANDIDATE
qualification, a production pin, or a merge.

Historical `#648` / `ac22c3c8f6d077b542f19524afbe5409e46c56e8` identity,
artifact digest `fe9ba256...`, and runtime root remain rejected fences.

## Worktree

- worktree: `/Users/bobbybones/Developer/worktrees/saariusskills-acpx-refresh-20260921`
- branch: `codex/puppet-acpx-refresh-20260921`
- base: `faa332ca8b3eb7da6662f127d6e3a55056f3db9d`
- public PR: https://github.com/saariuslystoned/SaariusSkills/pull/60 (draft)
- production enablement: none

## Provenance tuple

| Field | Value |
| --- | --- |
| source | https://github.com/openclaw/acpx/commit/ce8c3689fe830fd5c6199a8a683dc979d180af1d |
| status | `merged_unreleased` |
| merge/source commit | `ce8c3689fe830fd5c6199a8a683dc979d180af1d` |
| source tree | `04661dbf3af3b3c2a11d16c3061b40e20ce29f4a` |
| PR head | `c64b2751f0b8ca6e9d5613e98f7ed87f778de1b5` |
| PR base | `7879505dcf79448cd71cafd82a21aa6c937a3f3e` |
| stale npm gitHead | `8699be1b6428fa7584acc6f07d87f5aec8945f58` |
| published npm | `acpx@0.18.0` does **not** contain the merge |
| candidate package version | `0.18.0` local exact-source tarball |
| ordinary production pin | `acpx@0.16.0` |
| artifact | task-owned local `runs/puppet-acpx-refresh-runs/20260921/artifacts/acpx-0.18.0.tgz` |
| artifact SHA-256 / integrity | `ad9bc677a6687268010da9c57b83fd96d2d35eddafdb55a6e043fd70679cc342` |

Integrity is the tarball digest. A SHA-256 of descriptive metadata is
rejected.

## Actual runtime JavaScript import closure

Hashed from the packed `package/dist/runtime.js` relative imports, not a
hard-coded historical four-chunk list:

| package-relative file | SHA-256 |
| --- | --- |
| `package/dist/runtime.js` | `3069c9150a2d363ba9b8a2f9017421c8a7cfa830b76b862632d9e043ee1b0a9b` |
| `package/dist/ipc-BJj6maTF.js` | `ad21638d1f1b268cbcb37c277fe967a939ab724038f9a56513027d64d4a0f0f8` |
| `package/dist/queue-owner-runtime-BrlBT0l1.js` | `05006d0379e816a4ad6c4a8e07662de1fa43f89a89350c3220610dbdd292ffa8` |
| `package/dist/agent-registry-DdKB-zia.js` | `ee56531aff530a9e319f77ca7a14fbaf9abc883bf6c27008b93eed71443236a0` |
| `package/dist/watch-DBPaCPrt.js` | `62fb992328ee60519a65a98612a644c49910b63f31ab0344232f32768a54cd15` |

## Test labels

- **synthetic / fake public runtime**: ownership, cleanup fencing, conversation
  rejection, body-free events, bounded discarded-event metadata, and cutover
  gates. These do not load the packed runtime.
- **observed / actual public runtime + local synthetic peer**: artifact
  materialization, imported payload hashes, one bound turn, capability
  snapshot isolation, static-catalog reconnect mode/config/model replay, and
  result-only event consume/discard. These skip only when the local tarball
  is absent.

`#672` is treated as event-iterator cleanup after iteration ends. It is not
claimed to prove never-started or indefinitely slow observers.

Discarded-event metadata is a fixed-bound unique-type summary plus an honest
`event_count`. Unknown or empty types are retained as `unknown`. The default
path still drains through completion; a metadata cap does not cancel the
task. An explicit consume `limit` still ends the iterator through `return()`.

Repair implementation job: `80c22421-0e7a-488e-bf0f-53a5eabb55c3`, exact
Cursor ACP Grok route. Worker proof:
`/Users/bobbybones/.local/state/saarius-skills/cursor-acp-delegation/runs/80c22421-0e7a-488e-bf0f-53a5eabb55c3/PROOF.md`.

Reconnect proof uses the static synthetic-peer catalog only. It does not
claim `#675` changing-catalog or `#666` generic-mode behavior.

## Remaining route limits

- Ordinary Cursor `acpx@0.16.0` and AGY pins are unchanged.
- Installed plugin/broker behavior is unchanged.
- Draft PR #60 exists. This repair is a provider job with no LIVE CANDIDATE
  qualification, publish, release, or merge.
- No controller/native-view/default enablement.
- Static-catalog reconnect remains the explicit reconnect limit.
- Open upstream dependencies `#670`, `#674`, `#673`, `#676`, and `#669`
  have not landed; see `ADOPTION-MATRIX.md`.

## Implementation

- `skills/puppet/scripts/cursor_acpx.py`
- `tests/test_puppet_cursor_acpx.py`
- `bridge/cursor-acp/puppet-adapter.mjs`
- `bridge/cursor-acp/test/puppet-adapter.test.mjs`
- `bridge/cursor-acp/test/candidate-peer.mjs`
- `bridge/cursor-acp/test/candidate-runtime.test.mjs`
- `runs/puppet-acpx-refresh-runs/20260921/runtime/.gitignore`

Ordinary `cursor_acp.py`, transport/session/qualification modules, native
defaults, `broker.mjs`, `server.mjs`, and the bridge `acpx@0.16.0` pin are
unchanged.

## Checks

```text
$ shasum -a 256 runs/puppet-acpx-refresh-runs/20260921/artifacts/acpx-0.18.0.tgz
ad9bc677a6687268010da9c57b83fd96d2d35eddafdb55a6e043fd70679cc342  runs/puppet-acpx-refresh-runs/20260921/artifacts/acpx-0.18.0.tgz

$ python3 -m unittest tests.test_puppet_cursor_acpx tests.test_puppet_packaging -v
Ran 23 tests in 0.096s
OK
# 14 cursor-acpx identity/ownership tests + 9 PR48 packaging contracts
# local artifact test executed; no skip

$ npm run check
node --check broker.mjs server.mjs puppet-adapter.mjs
tests 65
pass 65
fail 0
skipped 0
# supplied artifact tests executed, including actual public-runtime
# capability isolation, static-catalog reconnect, event consume/discard,
# and the 100000-event bounded-metadata regression

$ python3 -m unittest tests.test_puppet_cursor_acpx tests.test_puppet_packaging -v
Ran 23 tests in 0.095s
OK

$ npm run check
tests 65
pass 65
fail 0
skipped 0

$ git diff --check faa332ca8b3eb7da6662f127d6e3a55056f3db9d
# clean
```

This repair used a provider job. No LIVE CANDIDATE qualification, live
Cursor/provider turn, or production promotion.
