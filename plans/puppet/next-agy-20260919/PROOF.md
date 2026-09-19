# Proof

## Scope and identity

- Exact worktree: `<worktree>/SaariusSkills`
- Exact branch: `codex/puppet-next-agy-20260919`
- Exact baseline: `89846223be4d900108a5f7c4a9c8f1faa662eae9`
- Native implementation-worker readiness: `<cursor-agent> acp`, requested `cursor-grok-4.6-high`, selected `grok-4.6[effort=high,fast=true]`.
- Installed AGY preflight: `<agy>`, version `1.2.7`; help advertises `--model`, `--effort`, `--input-format stream-json`, `--output-format stream-json`, and `--conversation`.

## PR #42 disposition

PR #42 is open and unmerged. Its scoped requalification, selector binding,
and model/effort invalidation behavior is present in the merged baseline's
reviewed source. Its AGY transport remains fixture-only (`AgyPrintController.available()`
false and `live_agy_claimed` false), so this task ports only the required live
runtime/controller gap rather than merging its historical branch wholesale.

## Evidence log

- Route read from `<route>/20260919-next-agy/ROUTE.md`.
- Cursor ACP readiness passed in the exact worktree; no model turn was sent by readiness.
- AGY executable/help preflight passed without reading secrets or auth stores.
- Bounded native stream-json smoke returned `init.model=gemini-3.8-flash-high`, a conversation ID, and terminal `result.status=SUCCESS`; the accepted user envelope includes `type=user`, `event=user`, and an object-valued message. This smoke was protocol discovery only and did not qualify Puppet or prove a live lifecycle.
- Independent native AGY two-turn smoke in disposable repo `/tmp/puppet-next-agy-live.zGermw` observed `init.model=gemini-3.8-flash-high`, cwd equal to that repo, conversation `240fd464-782d-4a70-a56c-d4ca7ca18e52`, two successful turns, and exact file content `AGY_TURN_ONE`. This is runtime capability evidence only; Puppet public-controller proof remains pending.
- Source implementation independently repaired after worker output: bounded retry across immediate exec-transition sampling, body-free native event reduction, pipe cleanup on abandon, exact effort propagation, qualification-scope binding, and public status/send/wait/halt routing.
- Focused verification: `python3 -m unittest tests.test_puppet_agy_print_runtime -q` → 10 passed; `python3 -m unittest tests.test_puppet_agy_print -q` → 14 passed; `python3 -m unittest tests.test_puppet_agy_print_lifecycle tests.test_puppet_transport tests.test_puppet_qualification_reuse -q` → 30 passed; `python3 -m py_compile skills/puppet/scripts/puppet_lib/agy_print.py skills/puppet/scripts/puppet_lib/session.py` → passed.
- Native parser regression used actual AGY envelope shapes: top-level `event=init|step_update|result` with nested metadata. Model `gemini-3.8-flash-high`, cwd, conversation, step progress, and `SUCCESS` terminal state were reduced; body/transcript fields were not retained.
- Final public-controller live proof used `<agy>` version `1.2.7`, exact `gemini-3.8-flash-high`, exact `high`, native argv `--print= --input-format stream-json --output-format stream-json --model gemini-3.8-flash-high --effort high --dangerously-skip-permissions --disable-slash-commands --log-file /dev/null`, disposable repo `/private/tmp/puppet-next-agy-live.zGermw`, branch `master`, head `cc3dd87019c2f0d8b6f1ec51e6a7ed108e3da0a9`, tree `4b825dc642cb6eb9a060e54bf8d69288fbee4904`, session `agy-public-controller-final`, conversation `99a45042-27e3-4e0a-9944-f6ba2f5d1cea`, two turns, observed step count `32`, proof file content `AGY_PUBLIC_CONTROLLER_FINAL`, owned target PID `40476`, owned child PIDs `40550,40551,40552`, and halt proof `pid_gone=true` with only those four PIDs signaled.
- Final live proof did not persist raw AGY stream output or inspect secrets; only bounded metadata and task-owned disposable file content were retained here.
- Full discovery: `python3 -m unittest discover -s tests -p 'test_*.py'` ran 1,237 tests and reported three Cursor doctor errors from the existing Darwin process-inventory `row remained unavailable` race plus three proof-packet path failures. The three affected Cursor tests passed alone; the packaging test passed after redacting machine-local home paths from this public proof packet. No AGY-focused test failed in discovery.
- Cursor ACP job `1abc7f49-4173-4ec9-a3b5-b42501045904` failed closed with `BRIDGE_RESTARTED` before terminal result; worktree inspection showed no source changes from that attempt.
- Cursor ACP job `6f6a9cbe-4ae5-4d1f-9d52-354ad2d72c89` produced the bounded process-backed source slice but its focused `py_compile`/unit-test command hung in a task-owned child process during verification; the job was cancelled natively at `2026-09-19T04:14:39Z`. Parent repair and independent verification are required.
- Follow-up source-slice closeout in this worktree: public `agy-print` store lifecycle, installed help-probe `available()`, task-owned compiled fake subprocess tests, and AGY-vs-shared qualification invalidation tests. Focused unittest/`py_compile` passed. No live AGY public-controller run. `#38` upstream-link browse left to parent.
