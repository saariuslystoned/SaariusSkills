# Cursor candidate route-identity repair proof

## Boundary

Local product wiring only. Official Cursor candidate `ensureSession` now
resolves the registered Cursor executable. Synthetic tests keep agent
`candidate`. No provider turn, live Cursor/Antigravity qualification,
shared install, reset, merge, or upstream publication.

## Worktree

- worktree: `/Users/bobbybones/Developer/worktrees/saariusskills-cursor-route-identity-20260921`
- branch: `codex/puppet-cursor-route-identity-20260921`
- starting base: `49a46404854db7c9c7e7935b351e47fb771beaca`
- starting tree: `938ef948a6a1218ad055a17d5d297c633b936167`
- job: `4990e283-63d2-44b3-a57e-7e0766c350b8`
- owner: `01a0c01d-4a3b-7123-80eb-44a9ae9228f8`
- prior PR61 worktree: not touched

## Defect

`CursorAcpNodeRuntime` created the official runtime with agent `cursor` and
registered the executable under that key. `CursorAcpRuntimeRunner._ensure_owned_handle`
hardcoded `agent: candidate`. The official public registry then tried to
spawn command `candidate`, producing `Failed to spawn agent command: candidate`
before any provider turn. The synthetic driver registry ignored the requested
key, so in-process and synthetic-peer tests hid the mismatch.

## Repair

`ensureSession` now uses `require_cursor_acp_runtime_agent`: official /
`qualified_archive` stays `cursor`; synthetic peer and in-process fixtures
stay `candidate`. Arbitrary names are rejected. The synthetic driver
registry now resolves only `candidate`. No alias, silent fallback, or
expanded model acceptance.

## Provenance

| Field | Value |
| --- | --- |
| source commit | `2e05de525dd1ab62e9e74bf02d91e3638920fcf3` |
| artifact | task-local copy of `acpx-0.18.0.tgz` at the existing pin path |
| artifact SHA-256 | `5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614` |
| materialization source | `/Users/bobbybones/Developer/worktrees/saariusskills-dual-acp-controller-20260921/runs/puppet-dual-acp-controller-runs/20260921/artifacts-refresh-2e05de52/acpx-0.18.0.tgz` |

Archive and `node_modules` remain untracked.

## Checks

```text
$ python3 -m unittest tests.test_puppet_cursor_acp_runtime tests.test_puppet_cursor_acpx -v
Ran 35 tests in 17.047s
OK
# includes official public-registry/ensureSession regression
# + existing ownership, cleanup, continuation, and synthetic identity tests

$ node --test test/candidate-runtime.test.mjs
tests 18
pass 18
fail 0
skipped 0
# includes official public createAgentRegistry + ensureSession regression
# candidate ensureSession still fails with Failed to spawn agent command: candidate
# cursor ensureSession resolves the local synthetic peer executable
```

The official regression registers a local peer through the pinned public
`createAgentRegistry` / `createAcpRuntime` path. It is not a mock that
accepts every key and does not only assert a captured string. It does not
invoke Cursor, Antigravity, or any provider.

## Remaining limits

- Ordinary/default `available()` remains false.
- No live Cursor or Antigravity qualification.
- No shared plugin install/reset.
- No upstream submission, merge, or publication from this worker.
