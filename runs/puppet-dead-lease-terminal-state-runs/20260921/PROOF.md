# Dead-lease terminal-state repair proof

## Native job

- native_job_id: `15b75753-6b9a-4ab6-9741-9736899c7290`
- source: Cursor ACP job file `~/.local/state/saarius-skills/cursor-acp-delegation/jobs/15b75753-6b9a-4ab6-9741-9736899c7290.json`
- createdAt: `2026-09-21T17:35:14.904Z`
- workspace: `/Users/bobbybones/Developer/worktrees/saariusskills-dead-lease-terminal-state-20260921`
- rejected_ids: owner handoff `01a0c01d-4a3b-7123-80eb-44a9ae9228f8`; Cursor conversation `d648dc81-6ce8-45cf-84c1-99006f94fd9f` is not the native job id
- fallback_worker: none
- retry: none
- local_source_finish: none

## Checkout

- worktree: `/Users/bobbybones/Developer/worktrees/saariusskills-dead-lease-terminal-state-20260921`
- branch: `codex/puppet-dead-lease-terminal-state-20260921`
- base: `origin/main` `49a46404854db7c9c7e7935b351e47fb771beaca`
- starting_head: `49a46404854db7c9c7e7935b351e47fb771beaca`
- starting_tree: `938ef948a6a1218ad055a17d5d297c633b936167`
- starting_status: clean, tracking `origin/main`
- PR63/PR64 worktrees and branches: not opened

## Motivation

PR63 CI run [35630314313](https://github.com/saariuslystoned/SaariusSkills/actions/runs/35630314313) failed on Ubuntu in `test_replay_of_the_same_halted_generation_is_idempotent`. Parent triage: `_prove_recorded_process_birth_gone` -> `process_birth_identity` -> `_linux_process_executable_record` / `os.readlink('/proc/<pid>/exe')` `FileNotFoundError` -> `ProcessVanished`, then a second `os.kill(pid, 0)` still succeeded and the helper raised `IdentityError('recorded Grok process state is ambiguous')`. Relevant session/registry/test blobs were identical on PR63, its base, and current main `49a4640`. This is a mainline dead-lease sampling race, not a PR63-introduced defect.

## Repair

`_prove_recorded_process_birth_gone` still fail-closes on same-birth alive, permission-denied, unknown/malformed state, and a running PID whose executable is unavailable. Confirmed `ProcessLookupError` remains absence. A typed `ProcessVanished` while the PID remains is not treated as gone. Only a later positive kernel state sample whose first character is `Z` or `X` counts as terminal/zombie. Replacement birth identities still pass. AGY `_pid_gone` was not copied and AGY sources were not edited.

## Changed files

- `skills/puppet/scripts/puppet_lib/session.py`
- `tests/test_puppet_grok_dead_lease.py`
- `runs/puppet-dead-lease-terminal-state-runs/20260921/STATE.md`
- `runs/puppet-dead-lease-terminal-state-runs/20260921/PROOF.md`
- `runs/puppet-dead-lease-terminal-state-runs/20260921/events.jsonl`
- `runs/puppet-dead-lease-terminal-state-runs/20260921/heartbeat`

## Checks

```text
$ python3 -m compileall -q skills/puppet/scripts/puppet_lib/session.py tests/test_puppet_grok_dead_lease.py
COMPILEALL_OK

$ git diff --check
DIFF_CHECK_OK

$ python3 -m unittest tests.test_puppet_grok_dead_lease.GrokDeadLeaseProcessBirthProofTests -v
Ran 4 tests in 0.006s
OK

$ python3 -m unittest tests.test_puppet_grok_dead_lease -v
Ran 14 tests in 33.799s
OK
```

The previously failing `test_replay_of_the_same_halted_generation_is_idempotent` passed in the local dead-lease suite. Offline mocks reproduced `ProcessVanished` plus a still-killable PID, accepted only positive `Z`/`X` samples, and kept unknown/live/denied/malformed samples rejected.

## Self-review

Source changes remain untrusted until parent review. Findings from this worker's own read:

- Exception-type-as-proof is not used; `ProcessVanished` plus a live PID still requires a positive state sample.
- Empty, multi-token, non-zero, permission-denied, and `S`/`R`/`??` samples stay unknown and fail closed.
- Same-birth equality still raises `still alive`; replacement birth still returns.
- First- and second-probe `PermissionError` stay ambiguous.
- Registry/AGY/authority files were not edited.

## Limits

- No provider or live qualification.
- No shared install, reload, or reset.
- No CI rerun to mask the Ubuntu failure.
- No VMs, desktops, or unrelated real process start/kill.
- Tests mock `os.kill`, process identity, and `ps`; the Ubuntu `/proc/<pid>/exe` race was reproduced offline, not re-run on Ubuntu CI.
- No merge and no upstream publication beyond one draft repair PR.
