# Dead-lease terminal-state repair proof

## Native job

- native_job_id: `91d5b0fd-e993-4e61-a1eb-66af08563e27`
- source: Cursor ACP job file `~/.local/state/saarius-skills/cursor-acp-delegation/jobs/91d5b0fd-e993-4e61-a1eb-66af08563e27.json`
- createdAt: `2026-09-21T17:44:28.952Z`
- workspace: `/Users/bobbybones/Developer/worktrees/saariusskills-dead-lease-terminal-state-20260921`
- prior_native_job_id: `15b75753-6b9a-4ab6-9741-9736899c7290` (completed; not retried or replaced)
- rejected_ids: owner handoff `01a0c01d-4a3b-7123-80eb-44a9ae9228f8`; Cursor conversation `7c2feda8-cd30-4179-8887-675c2b111707` is not the native job id
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
- source_repair: `2140e8dc3841c3e52db4aec7cd13ca5328c2af96`
- source_tree: `cc96ed5d7ff66178ba00e7021771b22f83c0041d`
- draft_pr: https://github.com/saariuslystoned/SaariusSkills/pull/66
- PR63/PR64 worktrees and branches: not opened

## Motivation

PR63 CI run [35630314313](https://github.com/saariuslystoned/SaariusSkills/actions/runs/35630314313) failed on Ubuntu in `test_replay_of_the_same_halted_generation_is_idempotent`. Parent triage: `_prove_recorded_process_birth_gone` -> `process_birth_identity` -> `_linux_process_executable_record` / `os.readlink('/proc/<pid>/exe')` `FileNotFoundError` -> `ProcessVanished`, then a second `os.kill(pid, 0)` still succeeded and the helper raised `IdentityError('recorded Grok process state is ambiguous')`. Relevant session/registry/test blobs were identical on PR63, its base, and current main `49a4640`. This is a mainline dead-lease sampling race, not a PR63-introduced defect.

The first repair accepted a later positive `Z`/`X` kernel state after any `IdentityError`. Parent accepted the narrow follow-up finding: a generic `IdentityError("malformed birth metadata")` plus a still-killable PID plus state `Z` was treated as terminal. That violates fail-closed rejection of ambiguous or malformed birth metadata.

## Repair

`_prove_recorded_process_birth_gone` still fail-closes on same-birth alive, permission-denied, unknown/malformed state, and a running PID whose executable is unavailable. Confirmed `ProcessLookupError` remains absence. A typed `ProcessVanished` while the PID remains is not treated as gone. Only that justified executable-disappearance class plus a later positive kernel state sample whose first character is `Z` or `X` counts as terminal/zombie. Generic `IdentityError`, `ExecTransitionSamplingError`, malformed or ambiguous birth metadata, and permission-denied identity failures stay rejected even when `ps` reports `Z` or `X`. Replacement birth identities still pass. AGY `_pid_gone` was not copied and AGY sources were not edited.

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
Ran 5 tests in 0.007s
OK

$ python3 -m unittest tests.test_puppet_grok_dead_lease -v
Ran 15 tests in 34.412s
OK
```

The previously failing `test_replay_of_the_same_halted_generation_is_idempotent` passed in the local dead-lease suite. Offline mocks still accept `ProcessVanished` plus a still-killable PID only with positive `Z`/`X` samples. The new negative regression rejects generic `IdentityError("malformed birth metadata")` with both `Z` and `X`. Unknown, live, denied, and malformed samples stay rejected.

## Self-review

Source changes remain untrusted until parent review. Findings from this worker's own read:

- Positive terminal fallback is restricted to `ProcessVanished`; generic `IdentityError` plus `Z`/`X` stays ambiguous.
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
- No merge and no upstream publication beyond the existing draft repair PR.
- In-commit ledger records the source repair identity only; the final PR head is reported externally after the proof/PR metadata commit.
