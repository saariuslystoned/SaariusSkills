# Puppet acpx merged #648 candidate proof

## Boundary

Disabled candidate-only Puppet adapter for one named local Cursor transport
(`cursor-acp`). The adapter now binds exact merged acpx source from PR #648
without claiming a released npm package or changing ordinary launch.

The candidate-only helper now materializes the exact local artifact under a
task-owned runtime root and exercises the actual public `createAcpRuntime`
export with a deterministic synthetic ACP peer. This is not provider/live
qualification, a production pin, or a public PR.

## Worktree

- worktree: `/Users/bobbybones/.codex/worktrees/runtime-proof/SaariusSkills`
- branch: `codex/puppet-acpx-runtime-proof-20260921`
- base: `8219a66c8ac44f14be0acec6c13bf5664571dc4f`
- public PR: none
- production enablement: none

## Provenance tuple

| Field | Value |
| --- | --- |
| source | https://github.com/openclaw/acpx/pull/648 |
| status | `merged_unreleased` |
| merge/source commit | `ac22c3c8f6d077b542f19524afbe5409e46c56e8` |
| PR head | `8de4219c4e87af4dbbc468f0056970d2cda343a2` |
| PR base | `4e4dcf5bdf4689509169861fefe5cea3a334d5f8` |
| stale npm gitHead | `8699be1b6428fa7584acc6f07d87f5aec8945f58` |
| published npm | `acpx@0.18.0` does **not** contain the merge |
| candidate package version | `0.18.0` local exact-source tarball |
| ordinary production pin | `acpx@0.16.0` |
| artifact | `runs/puppet-acpx-merged648-runs/20260921/artifacts/acpx-0.18.0.tgz` |
| artifact SHA-256 / integrity | `fe9ba256bc562b01bff007a2e63017a28daebb2dbc460806a6e7ad0f58d32d29` |

Integrity is the tarball digest. A SHA-256 of descriptive metadata is
rejected.

Merged public surface in the artifact `package/dist/runtime.d.ts` includes
`fs?: boolean` and `terminal?: boolean` on `AcpRuntimeOptions`. The adapter
keeps both explicitly false. Upstream omit-default remains enabled; that is
protocol callback policy, not an OS sandbox, and is not persisted.

## Implementation

- `skills/puppet/scripts/cursor_acpx.py`
- `tests/test_puppet_cursor_acpx.py`
- `bridge/cursor-acp/puppet-adapter.mjs`
- `bridge/cursor-acp/test/puppet-adapter.test.mjs`
- `bridge/cursor-acp/test/candidate-peer.mjs`
- `bridge/cursor-acp/test/candidate-runtime.test.mjs`
- `runs/puppet-acpx-merged648-runs/20260921/runtime/.gitignore`

Ordinary `cursor_acp.py`, transport/session/qualification modules, native
defaults, `broker.mjs`, `server.mjs`, and the bridge `acpx@0.16.0` pin are
unchanged. Shared plugins were not touched.

## Candidate runtime proof

The helper rejects shared bridge/node_modules roots, proves the tarball digest,
installs with lifecycle scripts disabled under the task-owned runtime root, and
loads `runs/puppet-acpx-merged648-runs/20260921/runtime/node_modules/acpx/dist/runtime.js`.
The real public `createAcpRuntime` then completed one synthetic-peer turn with
`fs:false` and `terminal:false`; adapter availability remained false.

The peer records only callback capability booleans. Durable ownership/events
artifacts contain no prompt, response, or transcript body.

## Checks

Commands and results:

```text
$ shasum -a 256 runs/puppet-acpx-merged648-runs/20260921/artifacts/acpx-0.18.0.tgz
fe9ba256bc562b01bff007a2e63017a28daebb2dbc460806a6e7ad0f58d32d29  runs/puppet-acpx-merged648-runs/20260921/artifacts/acpx-0.18.0.tgz

$ python3 -m py_compile skills/puppet/scripts/cursor_acpx.py tests/test_puppet_cursor_acpx.py
(exit 0)

$ python3 -m unittest tests/test_puppet_cursor_acpx.py -v
Ran 14 tests in 0.066s
OK

$ npm ci --ignore-scripts
added 134 packages (locked acpx@0.16.0; not a candidate pin)

$ npm run check
node --check broker.mjs server.mjs puppet-adapter.mjs
npm test
tests 51
pass 51

$ npm install --prefix runs/puppet-acpx-merged648-runs/20260921/runtime --ignore-scripts --no-save runs/puppet-acpx-merged648-runs/20260921/artifacts/acpx-0.18.0.tgz
added 42 packages; lifecycle scripts disabled; task-owned runtime only

$ node --test test/candidate-runtime.test.mjs
tests 3
pass 3

$ git diff --check
(exit 0)
```

Covered: Python/JS identity parity; merged/unreleased status; exact
merge/source vs PR head/base vs stale npm gitHead; local artifact SHA-256;
actual public `createAcpRuntime` loading and one synthetic-peer turn; callback
controls remain disabled; reconnect/retained-owner/cleanup; cutover safeguards
keep `available=false` and ordinary pin `0.16.0`.

No live Cursor/provider action, provider qualification, production promotion, or
public PR.

## Remaining gates

See `CUTOVER-CHECKLIST.md`. Blocker for production: published npm
`acpx@0.18.0` gitHead is stale and does not contain merge
`ac22c3c8f6d077b542f19524afbe5409e46c56e8`.
