# Dual ACP controller implementation proof and adjudication

## Boundary

The existing named `cursor-acp` controller/caller path now consumes
 runtime-derived observations from the pinned public `createAcpRuntime`
 surface. Ordinary launch, native defaults, MCP broker policy, and live
 Cursor/AGY qualification stay unavailable. Repair cycle 1 now connects the
 distinct AGY candidate through the existing session/caller path; source
 acceptance remains a parent gate.

## Worktree

- worktree: `/Users/bobbybones/Developer/worktrees/saariusskills-dual-acp-controller-20260921`
- branch: `codex/puppet-dual-acp-controller-20260921`
- base: `d0f0644f4ef4c84286d5307966514cf52cededc8`
- worker job ID: `59754615-f2c0-41b9-a2e8-d41d999ba4cb`
- Antigravity worker job ID: `7214ec87-9b2b-4c6b-a5b1-69cab059854f`
- repair worker job ID: `35e20824-58e5-46b9-bb14-402098b36b69`
- lifecycle worker job ID: `faeec797-3fa7-4893-a0d0-f5c6d289267c`
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
gitignored. Both native worker jobs are terminal; the AGY proof reports
`cleanupReady=true`.

## Prior AGY worker adjudication

The AGY job completed at the exact requested model with 371 observed events
and 227 tool calls, but without a textual handoff. The resulting source
delta is preserved in the worktree for parent review. Independent Python
collection fails before tests run because
`skills/puppet/scripts/antigravity_acpx.py` imports nonexistent
`puppet_lib.io`; the fallback import path fails under the repository test
layout as well. The delta also rewrites shared `contracts.py`, removing the
base `Contract` model and mandatory authority gates, which is outside the
requested AGY integration boundary.

The attempted pre-repair bridge command was:

```text
node --test test/broker.test.mjs test/cleanup-compatibility.test.mjs test/owner-death-cleanup.test.mjs test/setup.test.mjs
```

It failed at module loading because local `acpx` (and the bridge's other npm
dependencies) were not installed. This was secondary to the Python import
failure. The failed source delta remained preserved until repair cycle 1.

## Repair cycle 1 acceptance evidence

The single authorized Cursor repair job completed with exact model
`grok-4.6[effort=high,fast=true]` and canonical cleanup. It restored the
existing `Contract` API and mandatory hard gates, reused `puppet_lib.safety`
and existing typed-error signatures, and added explicit AGY session/caller
dispatch while keeping `available()` false for ordinary/default promotion.

```text
python3 -m unittest tests.test_puppet_contracts tests.test_puppet_transport tests.test_puppet_cursor_acp_runtime tests.test_puppet_cursor_acpx tests.test_puppet_cursor_acp tests.test_puppet_antigravity_acp tests.test_puppet_antigravity_acp_runtime tests.test_puppet_antigravity_acpx tests.test_puppet_packaging -v
Ran 96 tests ... OK

node --test test/puppet-adapter.test.mjs test/candidate-runtime.test.mjs
tests 30; pass 30; fail 0

node --test test/broker.test.mjs test/cleanup-compatibility.test.mjs test/owner-death-cleanup.test.mjs test/setup.test.mjs test/controller-runtime-driver.test.mjs
tests 33; pass 33; fail 0

python3 -m unittest discover -s tests -v
Ran 1309 tests ... OK
```

The 96 focused Python tests include both actual frozen public-runtime
synthetic controller consumers, model/identity rejection, body-free bounded
event drain, cleanup success, unsupported backend discard with proven local
cleanup, uncertain-cleanup fencing, unsupported permissions/questions, and
ordinary availability remaining false. The exact acpx source pin and
artifact digest above are unchanged. No live qualification or provider
credential action was used.

## Repair cycle 2 independent adjudication

The single authorized repair worker was Cursor ACP job
`f3b870e8-94af-42da-a9e9-fe9819ce335c`, completed at the exact
`grok-4.6[effort=high,fast=true]`. Its canonical worker proof is at
`/Users/bobbybones/.local/state/saarius-skills/cursor-acp-delegation/runs/f3b870e8-94af-42da-a9e9-fe9819ce335c/{STATE.md,PROOF.md,events.jsonl}`.

The worker delta independently passed:

```text
python3 -m unittest tests.test_puppet_cursor_acp_runtime tests.test_puppet_antigravity_acp_runtime tests.test_puppet_cursor_acp tests.test_puppet_antigravity_acp -v
Ran 58 tests ... OK

bridge/cursor-acp supplied-artifact bridge run
tests 30; pass 30; fail 0; skipped 0

bridge/antigravity-acp supplied-artifact bridge run
tests 33; pass 33; fail 0; skipped 0

clean git-archive checkout with the worker diff applied
Cursor: tests 30; pass 23; fail 0; skipped 7
Antigravity controller driver: tests 1; pass 0; fail 0; skipped 1
```

The clean-checkout AGY result is an explicit skip because the task-owned
optional `acpx-0.18.0.tgz` is absent; it is not counted as public-runtime
success. The supplied-artifact AGY case passed only when that exact local
artifact was present.

The repair is not source-accepted because normal candidate construction still
omits the trusted candidate executable. Exact direct caller-path reproductions
against the worker delta are:

```text
_cursor_acp_structured_launch(..., prompt="caller task ...")
ValidationError: cursor-acp candidate executable is missing

_antigravity_acp_structured_launch(..., prompt="caller task ...")
ValidationError: antigravity-acp candidate executable is missing
```

Both default factories have an `executable` parameter and both Node drivers
reject a candidate payload without one. The structured launch callers receive
the already-resolved manifest executable in `launch()`, but do not forward it
to either factory. The missing consumer seam is therefore still on the actual
caller path; the worker source remains uncommitted pending parent rescope.

## Task-owned consumer lifecycle

The single authorized lifecycle worker was Cursor ACP job
`faeec797-3fa7-4893-a0d0-f5c6d289267c`. It started from checkpoint
`d0732a15d587633151bab39f22ba467812c1288b`. Default structured launch now
resolves a trusted route binding before calling the default factory. Cursor
binds `/Users/bobbybones/.local/bin/cursor-agent` plus `acp`. Antigravity
binds the pinned ACP server, colocated helper, platform argv, `GEMINI_HOME`,
and sanitized process environment from the existing broker policy. Arbitrary
executable/env payloads are not production trust proof. Synthetic peers stay
test-only at the resolver boundary.

The public return is a live `AcpConsumerOwner` plus a body-free continuation.
`owner.next_turn(continuation, ...)` and `owner.finish(continuation)` reuse
the retained runner. A continuation identifier cannot recover the runner
without that process-local owner. Cross-process resume is unsupported.

```text
python3 -m unittest tests.test_puppet_contracts tests.test_puppet_transport tests.test_puppet_cursor_acp_runtime tests.test_puppet_cursor_acpx tests.test_puppet_cursor_acp tests.test_puppet_antigravity_acp tests.test_puppet_antigravity_acp_runtime tests.test_puppet_antigravity_acpx tests.test_puppet_packaging -v
Ran 110 tests ... OK
# includes default-factory owner lifecycle for both routes, using
# build_*_candidate_runner with no runtime= injection, two useful task
# strings, non-default advertised models, fresh request IDs, finish, and
# exact synthetic child exit

node --test test/*.test.mjs   # bridge/cursor-acp
tests 65; pass 65; fail 0; skipped 0

node --test test/*.test.mjs   # bridge/antigravity-acp
tests 33; pass 33; fail 0; skipped 0
```

The exact f888 acpx source pin and artifact digest above are unchanged. No
live qualification or provider action was used.
