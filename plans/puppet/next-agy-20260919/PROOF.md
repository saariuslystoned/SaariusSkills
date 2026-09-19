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
- The prior live native process proof used `<agy>` version `1.2.7`, exact `gemini-3.8-flash-high`, exact `high`, a disposable repo, two turns, a verified task file, and an owned process-tree halt. It was direct controller proof, not public `puppet.py` admission, and is not used as public qualification evidence.
- Final live proof did not persist raw AGY stream output or inspect secrets; only bounded metadata and task-owned disposable file content were retained here.
- Full discovery: `python3 -m unittest discover -s tests -p 'test_*.py'` ran 1,237 tests. After the bounded Darwin inventory repair, the three Cursor doctor cases pass in isolation; one unrelated Codex launch fixture still fails because its expected child artifact is not created. No AGY-focused test failed in discovery.
- Cursor ACP job `1abc7f49-4173-4ec9-a3b5-b42501045904` failed closed with `BRIDGE_RESTARTED` before terminal result; worktree inspection showed no source changes from that attempt.
- Cursor ACP job `6f6a9cbe-4ae5-4d1f-9d52-354ad2d72c89` produced the bounded process-backed source slice but its focused `py_compile`/unit-test command hung in a task-owned child process during verification; the job was cancelled natively at `2026-09-19T04:14:39Z`. Parent repair and independent verification are required.
- Follow-up repair in this worktree: native selector admission before legacy AGY validation, `--new-project` isolation, persisted contract/selector/qualification/deadline identity, explicit halt-before-resume with request-id idempotency, controller review/terminal-criteria acceptance gates, descendant halt proof, transport-specific qualification fingerprints and receipt comparison, and the verified upstream native stream-json decision. Focused AGY/qualification/launch tests (70) and `py_compile` passed. Exact public CLI lifecycle receipt proof remains pending because no current public AGY qualification receipt was available; no helper proof is presented as that receipt.

## PR #49 repair pass (2026-09-19)

- exact branch head: `89fd495902c163c60c0e63b34ef422b5e0139e5a`
- pushed to the existing PR: `https://github.com/saariuslystoned/SaariusSkills/pull/49`
- AGY print/runtime/lifecycle tests: 38 passed
- session integration tests: 31 passed
- authority plus Cursor transport tests: 79 passed
- focused Darwin persistent-row and lingering-exit tests: 2 passed
- `python3 -m compileall -q skills/puppet/scripts` and `git diff --check`: passed
- full discovery reached 1,237 tests; the prior run had three Darwin/Cursor errors and one unrelated Codex doctor-child timing failure. The three Darwin/Cursor cases pass after the final bounded repair; the Codex timing-sensitive fixture remains unresolved.
- PR body was updated with the same evidence and explicitly preserves the public CLI receipt limitation.
