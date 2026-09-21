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

## Consumer release and AGY env repair

This native Cursor repair started from exact
`83935f3ad55e1f2f51a154f948d7d25f63cf26e4` /
`fbe9eb21d36668a884dc59400122d855115ae002`. It repairs only the two
accepted findings.

F1: `AcpConsumerOwner._release` now always attempts task-owned runtime
shutdown after `runner.finish`, even when finish fails. The original
operation or finish error is preserved if shutdown also fails. Proven
local release (`child_exit.exited is True`) retires the continuation.
Uncertain release keeps the held runner, records truthful non-exit
evidence, fences cleanup, and refuses another turn. Backend persistent
state discard stays separate from local worker release.

F2: official AGY candidate launch no longer merges the allowed
environment over ambient `os.environ`. The Node driver process starts
with only the validated allowed map, then replaces `process.env` with
that same map before the pinned public runtime is created. Forged extra
`process_env` keys fail closed. `agentProcessEnv` is still not passed
through `createVerifiedCandidateAcpRuntime`; acpx continues to start
from `process.env`. Synthetic peer launches stay test-only and do not
carry a candidate environment.

```text
python3 -m unittest tests.test_puppet_contracts tests.test_puppet_transport tests.test_puppet_cursor_acp_runtime tests.test_puppet_cursor_acpx tests.test_puppet_cursor_acp tests.test_puppet_antigravity_acp tests.test_puppet_antigravity_acp_runtime tests.test_puppet_antigravity_acpx tests.test_puppet_packaging -v
Ran 119 tests ... OK
# includes prior two-turn/normal-finish and failed-next-turn owner
# lifecycle for both routes, plus finish-failure shutdown, combined
# finish/shutdown error precedence, actual synthetic-child release, forged
# process_env rejection, and official candidate env isolation against the
# pinned public runtime using literal synthetic sentinel names

node --test test/*.test.mjs   # bridge/cursor-acp
tests 65; pass 65; fail 0; skipped 0

node --test test/*.test.mjs   # bridge/antigravity-acp
tests 34; pass 34; fail 0; skipped 0
# includes official candidate create failing closed without allowedProcessEnv
```

The exact f888 acpx source pin and artifact digest above are unchanged. No
live qualification, pin refresh, publication, or merge.

## Upstream refresh 2e05de52

This native Cursor implementation started from accepted
`e999f88092ef8e07c7dd1736b31c69bfeacb738b` /
`108303e6ec6f105280f7aee972f9ddb09087167b`. It refreshes only the candidate
identity/materialization pin to exact merged upstream acpx
`2e05de525dd1ab62e9e74bf02d91e3638920fcf3` / tree
`c612e764ead5d8eaa409956fb1b11c008a7579ed`. The old f888 archive, digest, and
import identities remain on disk and are now rejected historical fences.
`#687` was not cherry-picked.

### Current provenance tuple

| Field | Value |
| --- | --- |
| source | https://github.com/openclaw/acpx/commit/2e05de525dd1ab62e9e74bf02d91e3638920fcf3 |
| status | `merged_unreleased` |
| merge/source commit | `2e05de525dd1ab62e9e74bf02d91e3638920fcf3` (through `#689`) |
| source tree | `c612e764ead5d8eaa409956fb1b11c008a7579ed` |
| PR head | `27e58b7dba7aa4e6e4bc0cc175ad6cdbc00587c7` |
| PR base | `d4916ce050582c7415632c4e7cf84d285d268fa9` |
| stale npm gitHead | `8699be1b6428fa7584acc6f07d87f5aec8945f58` |
| published npm | `acpx@0.18.0` does **not** contain the merge |
| ordinary production pin | `acpx@0.16.0` |
| artifact | task-owned local `runs/puppet-dual-acp-controller-runs/20260921/artifacts-refresh-2e05de52/acpx-0.18.0.tgz` |
| artifact SHA-256 | `5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614` |
| runtime root | `runs/puppet-dual-acp-controller-runs/20260921/runtime-refresh-2e05de52` |
| runtime entry | `package/dist/runtime.js` |
| runtime entry SHA-256 | `ffdb6949b2239d991f63970514ad99677b19db1839313127a55ad9fcd30a4683` |

Preserved f888 evidence: artifact
`runs/puppet-dual-acp-controller-runs/20260921/artifacts/acpx-0.18.0.tgz`
SHA-256 `642d4c299bd58b275ca1a360196f3077fc4f84997e2654542f492b1e0001c162`.
That path/digest/source/tree is rejected as `historical f888`.

### Actual packed import closure

| package-relative file | SHA-256 |
| --- | --- |
| `package/dist/agent-registry-Ct2yWPW7.js` | `5091abb775cb9cfc36bc210acd84a830bd5a413db2ba61eab8a0ef22817230ba` |
| `package/dist/ipc-Bn8rocUR.js` | `33b50f531ae5bb3d39a56b9f325249631721aee54c764b1ce5a2f72a1eff98c0` |
| `package/dist/queue-owner-runtime-B-uQhwMC.js` | `fc4f3b27e6c003646539fc933a38c80886e1cdabf38d6f33a4abc7185d8b0d5b` |
| `package/dist/runtime.js` | `ffdb6949b2239d991f63970514ad99677b19db1839313127a55ad9fcd30a4683` |
| `package/dist/watch-yKB9yCio.js` | `06254f5cf0af1ee1b5855c0380469ea5f6b691d7f693cfa519288adb7798c635` |

Count: 5 reachable JavaScript files from `package/dist/runtime.js`. Materializer
walks the real relative imports and fail-closes on digest/source/tree drift.

### Checks

```text
python3 -m unittest tests.test_puppet_contracts tests.test_puppet_transport tests.test_puppet_cursor_acp_runtime tests.test_puppet_cursor_acpx tests.test_puppet_cursor_acp tests.test_puppet_antigravity_acp tests.test_puppet_antigravity_acp_runtime tests.test_puppet_antigravity_acpx tests.test_puppet_packaging -v
Ran 121 tests in 36.524s
OK
# includes both-route default-factory two-turn/non-default-model/cleanup
# plus owned-shutdown reconnect tests that record actual backend mapping

node --test test/*.test.mjs   # bridge/cursor-acp
tests 66; pass 66; fail 0; skipped 0
# first full pass hit one flaky lock rmdir ENOTEMPTY on
# "separate OS processes serialize stale-lock reclamation"; isolated
# lock.retry and a second full suite both passed 4/4 and 66/66

node --test test/*.test.mjs   # bridge/antigravity-acp
tests 34; pass 34; fail 0; skipped 0
```

Actual public-runtime synthetic proof (not live/provider):

- Cursor and AGY consumers each completed two useful turns, a non-default
  advertised model, and owned cleanup/child-exit evidence against the
  task-local pinned runtime.
- Cursor Node suite exercised processLifecycle `onSpawned`/`onExit` owned-child
  retirement on runtime shutdown, then reconnect with a shared memory store.
  Handle `sessionKey` stayed host-owned. Backend/record IDs were recorded
  rather than assumed stable.
- Python consumers recorded backend mapping after owned driver shutdown and a
  new runtime; sessionKey matched, backend IDs were recorded as observed.

### Remaining route limits and refresh gaps

- Ordinary Cursor `acpx@0.16.0` and AGY pins stay unchanged.
- Installed plugin/broker behavior is unchanged. `available()` stays false.
- No live Cursor or Antigravity qualification, publication, or merge.
- `#683` delegated-terminal retirement is not exercised. The consumer keeps
  `terminal: false` and does not import `permissionMode`/`approve-all`; those
  would violate the delegated-terminal contract.
- `#680`/`#682` Windows/POSIX descendant cleanup and `#681` queue-observer
  ownership are CLI/queue/terminal surfaces this consumer does not use.
- `#686` owner-close lease-release is a queue-lease path; this consumer does
  not take CLI queue ownership.
- `#687` remains open/draft and was not cherry-picked. No live stale-queue
  PID-reuse experiment was run.
- Public acpx runtime still has no `conversation_id` API; host conversation
  identity is not copied onto runtime handles.

No live qualification, shared plugin install, credential/usage reset, or PR.

## CI portability repair: task text before official Cursor route

This native Cursor repair started from exact clean PR61 head
`b8672726939a64710c69f4c2839b037d15e36945` / tree
`aff6df13f94c1dff053d6b7a467d19f72c0fb3ca`. It repairs only the Ubuntu
portability failure. The exact-source acpx identity
`2e05de525dd1ab62e9e74bf02d91e3638920fcf3` / tree
`c612e764ead5d8eaa409956fb1b11c008a7579ed` / artifact SHA-256
`5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614` is
unchanged. Ordinary availability, fallback, and authorization behavior are
unchanged.

### Failure

Ubuntu full discovery ran 1334 tests with one failure:

```text
FAIL: test_structured_launch_without_observer_does_not_fall_back
AssertionError: 'task text is missing' not found in
'cursor-acp official route executable is missing'
```

Source excerpt:
`/Users/bobbybones/Developer/worktrees/acpx-upstream-plan-20260920/runs/puppet-overnight-runs/20260921/pr61-ubuntu-failure.txt`

Hermetic macOS reproduction with official Cursor absent:

```text
ambient /Users/bobbybones/.local/bin/cursor-agent exists: True
python3 -m unittest tests.test_puppet_cursor_acp.CursorAcpTransportTests.test_structured_launch_without_observer_does_not_fall_back -v
OK

CURSOR_AGENT_EXECUTABLE=/missing/cursor-acp-official-route \
python3 -m unittest tests.test_puppet_cursor_acp.CursorAcpTransportTests.test_structured_launch_without_observer_does_not_fall_back -v
FAIL: expected 'task text is missing', actual
'cursor-acp official route executable is missing'
```

Default official route still pointed at
`/Users/bobbybones/.local/bin/cursor-agent`. Structured launch resolved that
path before caller task-text validation, so hosts without Cursor failed the
wrong closed error. No process was spawned; the failure was validation order.

### Repair

`_cursor_acp_structured_launch` now requires runtime task text before
`resolve_cursor_acp_route_binding()` on the official default-factory path.
Missing input fails as `task text is missing`. A present task string with the
official executable absent still fails as
`cursor-acp official route executable is missing`. Tmux and agy-print
constructors remain patched/refused; the official route is not spawned.

The existing no-fallback test now hermetically sets
`CURSOR_AGENT_EXECUTABLE=/missing/cursor-acp-official-route` and also proves
the unavailable-official-route closed error. No skip, no Cursor install, no
environment-specific production branching, no pin or authorization change.

### Checks

```text
python3 -m unittest tests.test_puppet_cursor_acp.CursorAcpTransportTests.test_structured_launch_without_observer_does_not_fall_back -v
Ran 1 test ... OK
# ambient Cursor remains installed at the default path; the test fixture
# still hides it. A second run with CURSOR_AGENT_EXECUTABLE=/also-missing/...
# also passed.

python3 -m unittest tests.test_puppet_cursor_acp_runtime tests.test_puppet_cursor_acpx tests.test_puppet_cursor_acp tests.test_puppet_packaging -v
Ran 69 tests in 21.581s
OK

python3 -m unittest discover -s tests -v
Ran 1334 tests in 230.570s
OK
```

Node bridge suites, live Cursor/AGY qualification, shared plugin install,
credential/usage reset, and pin refresh were not run. Scope is this one
caller validation-order plus hermetic fixture. Antigravity structured launch
order was not changed because it was not the failing CI test.

No live qualification, publication, merge, or ordinary route promotion.
