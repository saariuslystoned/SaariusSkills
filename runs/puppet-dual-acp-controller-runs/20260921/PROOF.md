# Dual ACP controller Cursor slice proof

## Boundary

The existing named `cursor-acp` controller/caller path now consumes
runtime-derived observations from the pinned public `createAcpRuntime`
surface. Ordinary launch, native defaults, MCP broker policy, and live
Cursor/AGY qualification stay unavailable. Antigravity ACP was not
touched.

## Worktree

- worktree: `/Users/bobbybones/Developer/worktrees/saariusskills-dual-acp-controller-20260921`
- branch: `codex/puppet-dual-acp-controller-20260921`
- base: `d0f0644f4ef4c84286d5307966514cf52cededc8`
- worker job ID: `59754615-f2c0-41b9-a2e8-d41d999ba4cb`
- production enablement: none

## Provenance tuple

| Field | Value |
| --- | --- |
| source | https://github.com/openclaw/acpx/commit/f8883645c261e07b2df7f9c3b4ad243b62d8168a |
| status | `merged_unreleased` |
| merge/source commit | `f8883645c261e07b2df7f9c3b4ad243b62d8168a` (`#678`) |
| source tree | `f4a4d33b33cdf5b57345e8420f24992953aed5e0` |
| PR head | `706aeadd9c62550ee7e6ddceffe3d31ede5494d1` |
| PR base | `cc9b96388d682f8dbb17dde6015a5467e3f563fc` |
| stale npm gitHead | `8699be1b6428fa7584acc6f07d87f5aec8945f58` |
| published npm | `acpx@0.18.0` does **not** contain the merge |
| ordinary production pin | `acpx@0.16.0` |
| artifact | task-owned local `runs/puppet-dual-acp-controller-runs/20260921/artifacts/acpx-0.18.0.tgz` |
| artifact SHA-256 | `642d4c299bd58b275ca1a360196f3077fc4f84997e2654542f492b1e0001c162` |

Historical `#648` and refresh `ce8c3689...` identities remain rejected
fences. Integrity is the tarball digest.

## Consumer connection

`CursorAcpRuntimeRunner` is the existing controller runner. Its
`observation()` method validates ownership first, then drives public
`ensureSession` / `getStatus` / `startTurn` / `close`, maps advertised
models, drains events to a body-free bounded type summary, and returns
the existing cursor-acp observation. `require_observation`,
`caller_result`, and `_cursor_acp_structured_launch` consume that
derived observation. `available()` stays false.

Host `conversation_id` stays on Puppet observation/session identity.
Public runtime handles keep `sessionKey`, `backendSessionId`,
`acpxRecordId`, and `runtimeSessionName` separate. No provider
`conversation_id` API is invented.

## Checks

```text
$ python3 -m unittest tests.test_puppet_cursor_acp_runtime tests.test_puppet_cursor_acpx tests.test_puppet_cursor_acp tests.test_puppet_packaging -v
Ran 58 tests in 2.705s
OK
# 8 controller-runtime consumer tests, including actual public runtime
# + 14 cursor-acpx identity/ownership tests + 27 cursor-acp contracts
# + 9 PR48 packaging contracts

$ node --test test/puppet-adapter.test.mjs test/candidate-runtime.test.mjs
tests 30
pass 30
fail 0
skipped 0
# relevant offline adapter/runtime suite; ordinary broker/lock/setup
# tests were not run because they require a shared acpx@0.16.0 install
```

## Remaining route limits

- Ordinary Cursor `acpx@0.16.0` and AGY pins are unchanged.
- Installed plugin/broker behavior is unchanged.
- No live Cursor or Antigravity qualification.
- No publication, merge, or ordinary route promotion.
- The distinct antigravity-acp integration remains for the next worker.
- Public acpx runtime still has no conversation_id API; host conversation
  identity is not copied onto runtime handles.

## Cleanup readiness

Owned handles are closed after a derived turn. Post-creation failures
close only the owned `sessionKey`. Uncertain cleanup fences replacement.
Task-local runtime `node_modules` and the frozen upstream checkout stay
gitignored. Ready for canonical cleanup, then the sequential AGY worker.
