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

## PR #49 repair pass 2 (2026-09-19)

- exact repair commits: `4da746d`, `ecff5fc`
- Cursor ACP worker job `e7692e33-c502-4e8e-bbc2-204b8b23957c` completed on the exact worktree with selected model `grok-4.6[effort=high,fast=true]`; the public checkpoint-admission slice and four bounded regressions were independently inspected
- targeted repair verification: `python3 -m unittest tests.test_puppet_agy_print_checkpoint tests.test_puppet_agy_print_runtime tests.test_puppet_authority -q` → 72 passed
- transport/probe/qualification verification: 164 passed
- full verification: `python3 -m compileall -q skills/puppet/scripts` and `git diff --check` passed; `python3 -m unittest discover -s tests -p 'test_*.py' -q` → 1,247 passed in 349.622s
- reproduced public failures covered by regressions: first-followup/runtime-fingerprint/prior-checkpoint admission, parent-gone halt, refused-send intent poisoning, silent ledger eviction, failed resume admission, executable drift, and typed Linux process disappearance
- exact public CLI qualification receipt/live proof remains pending; no external sends, deploys, merges, or account changes were performed
- follow-up CI run `35426959846` for exact head `ecff5fcd3e7351be56b602b6afa5ad119033c89d` passed on Ubuntu 24.04 and macOS 26; the prior Ubuntu race was `/proc/<pid>/exe` disappearance still classified as `ProcessExecutableUnavailable`, repaired as typed `ProcessVanished`

## PR #49 repair pass 3 (2026-09-19)

- authoritative audit packet: `<audit-packet>/20260919-pr49-repair3-review/`; supplied probes reproduced all three P1 blockers before edits
- Cursor ACP job `54d7aa3c-f71a-4ed7-a336-e89985625f51` used executable `<cursor-agent> acp`, requested `cursor-grok-4.6-high`, selected `grok-4.6[effort=high,fast=true]`, exact worktree; canonical result and proof paths are under `<proof-root>/54d7aa3c-f71a-4ed7-a336-e89985625f51/`
- worker proof: selected `agy-print` qualification now rejects before fake tmux execution; `python3 -m unittest tests.test_puppet_probe_transport tests.test_puppet_probe tests.test_puppet_qualification_reuse tests.test_puppet_codex_qualification tests.test_puppet_cursor_qualification tests.test_puppet_grok_qualification tests.test_puppet_claude_paired_qualification -q` → 144 passed
- parent focused proof: `python3 -m unittest tests.test_puppet_agy_print_checkpoint tests.test_puppet_agy_print_runtime tests.test_puppet_probe_transport tests.test_puppet_probe -q` → 110 passed; `python3 -m py_compile` for changed Python modules and `git diff --check` passed
- new public regressions cover halt → follow-up envelope → submitted replay without reactivation, post-start identity failure cleanup before lease release, selected transport fail-closed behavior, and source protocol review transitions
- aggregate `python3 -m unittest discover -s tests -q` ran 1,258 tests; one existing timing-sensitive Codex doctor-child assertion failed in aggregate, then passed in exact isolated rerun (`...test_doctor_output_cap_timeout_and_source_drift_fail_closed`)
- exact public CLI AGY qualification receipt/live proof remains pending; no external sends, deploys, merges, or account changes were performed
- corrected exact-head CI run `35445828955` for head `cf1ee26` passed on Ubuntu 24.04 and macOS 26, including test suite, compile, and smoke command surfaces; the preceding run failed only the packaging guard on machine-local home-directory proof paths, which were replaced with placeholders

## PR #49 repair pass 4 (2026-09-19)

- exact repair commit/head: `ff197b71bd6e546728175011aa9cd1cf7ae137d5`
- existing PR: `https://github.com/saariuslystoned/SaariusSkills/pull/49`; state is OPEN and `mergedAt` is null
- authoritative packet `/audit-packet/20260919-pr49-repair4-review/`; supplied review probes reproduced the real-start persistence defect, halted source admission defect, cleanup recovery gap, and proof-path packaging failure
- Cursor ACP job `99d9be46-cd4d-4dd7-9aa0-7c22fe7c5ca4` used the required native route and selected `grok-4.6[effort=high,fast=true]`; canonical proof is under `<proof-root>/99d9be46-cd4d-4dd7-9aa0-7c22fe7c5ca4/`
- worker verification: real controller start/persistence conformance and source public regressions; focused worker suite → 112 passed
- parent verification: `python3 -m unittest tests.test_puppet_agy_print_checkpoint tests.test_puppet_agy_print_runtime tests.test_puppet_probe_transport tests.test_puppet_probe -q` → 113 passed; `py_compile` and `git diff --check` passed
- current-worktree reproduction of the authoritative continuation probe now reports `phase=followup_sent`, `message_id=followup-1`, and successful matching follow-up import; unsupported AGY qualification remains fail-closed
- new recovery regression proves a first cleanup failure preserves the exact active process fence, then a later public halt positively stops the owned generation and reaches HALTED
- full discovery: `python3 -m unittest discover -s tests -q` → 1,261 passed in 227.191s
- exact-head CI run `35452109013` for `ff197b71bd6e546728175011aa9cd1cf7ae137d5` passed on Ubuntu 24.04 and macOS 26, including test suite, compile, and smoke command surfaces
- exact public CLI AGY qualification receipt/live proof remains pending; no external sends, deploys, merges, or account changes were performed

## PR #49 repair pass 5 (2026-09-19)

- exact starting head: `3bae371b6a3555ce8d94986fdbb24222d536d3d2`; PR remained OPEN and unmerged throughout
- authoritative packet: `<audit-packet>/20260919-pr49-repair5-review/`; pre-edit probe reproduced source resume rejection at changed HEAD and source proof replay `ConflictError`
- ACP readiness: exact `<cursor-agent> acp` route, requested `cursor-grok-4.6-high`, selected `grok-4.6[effort=high,fast=true]`
- source-identity implementation worker job `5732d1e4-2a28-404c-9e01-e8d5beafab05` completed on the exact worktree; it rebound `observation.workspace` only after reviewed `source_accept`, retained clean path/branch/ancestry safeguards, and added real commit-A → commit-B tests; worker verification was 13 checkpoint tests plus 27 adjacent AGY tests
- replay implementation job `5ad545b4-6b42-4668-ae21-9345f1785b04` selected the same model but failed with `BRIDGE_RESTARTED` before terminal handoff; the bounded partial diff was independently reviewed, and parent verification covered the resulting replay behavior
- focused verification: `python3 -m unittest tests.test_puppet_agy_print_checkpoint tests.test_puppet_agy_print_runtime tests.test_puppet_probe_transport tests.test_puppet_probe tests.test_puppet_packaging -q` → 125 passed in 47.603s
- full verification: `python3 -m unittest discover -s tests -q` → 1,264 passed in 270.995s; `python3 -m py_compile` and `git diff --check` passed
- post-edit adapted probe no longer rejects the reviewed source HEAD; matching proof replay succeeds without new admission/delivery, changed payload remains refused; unsupported native transport remains fail-closed, while the probe's mocked lease fixture cannot complete authority cleanup after transport refusal
- public AGY qualification receipt/live proof remains pending; no live AGY launch, external sends, deploys, merges, comments, issue edits, or account changes were performed
