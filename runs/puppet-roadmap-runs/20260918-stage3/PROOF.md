# Proof

## Baseline

- Worktree: `/Users/bobbybones/.codex/worktrees/bcc5/SaariusSkills`
- Branch: `codex/puppet-roadmap-stage1-20260918`
- HEAD: `608b070f30c4be6253ef37709868bce1d39c4230`
- Accepted stage-2 code: `0926c9f`
- Stage-2 proof closeout: `608b070`
- `origin/main`: `a8de5b9245cd457cc35ca2e223a11040d0772f47`
- Commit: none (uncommitted for parent review)

## Readiness

- Native Cursor ACP readiness passed for the exact workspace.
- Requested model: `cursor-grok-4.6-high`
- Selected/current model: `grok-4.6[effort=high,fast=true]`
- Live AGY: not claimed. All AGY proof is a deterministic observation fixture.

## What landed

Stage 3 named `agy-print` structured transport on the stage-2 caller/transport boundary:

- New `AgyPrintController` plus observation/binding/resume/halt schemas
- Capability/proof table marks `agy-print` implemented; `herdr` and `acp` stay unsupported
- Requesting `agy-print` never falls back to tmux; unavailable/unsupported conditions are body-safe caller blockers with remedies
- Observed model must appear in runtime, process, or session metadata; selector-only and mismatched observations fail closed
- Workspace proof requires path, branch, head, and tree; a path alone is not enough
- Resume proof requires matching session and conversation identity
- Halt proof requires owned PID/birth and a confined process tree
- Stage-2 worker completion, controller acceptance, confirmed halt, progress cursor, and bounded final outcome stay distinct
- Operator-plan field set remains frozen; `plan --transport` still only binds/refuses and does not add plan fields
- Tmux default binding, capability rows, and registered-session runtime stay unchanged
- `agy_print.py` is AGY target-source only so structured-transport edits do not invalidate other targets

## Tests

Focused plus contracts/CLI/packaging (OK):

```text
python3 -m unittest tests.test_puppet_agy_print tests.test_puppet_transport \
  tests.test_puppet_caller tests.test_puppet_contracts \
  tests.test_puppet_qualification_reuse tests.test_puppet_cli \
  tests.test_puppet_packaging -q
# 63 tests, 11.330s
```

`agy-print` focused file (OK):

```text
python3 -m unittest tests.test_puppet_agy_print -q
# 14 tests, 9.554s
```

Caller-path plus session/authority/tmux/dead-lease (OK):

```text
python3 -m unittest tests.test_puppet_agy_print tests.test_puppet_transport \
  tests.test_puppet_caller tests.test_puppet_contracts tests.test_puppet_cli \
  tests.test_puppet_qualification_reuse tests.test_puppet_packaging \
  tests.test_puppet_session tests.test_puppet_authority \
  tests.test_puppet_tmux tests.test_puppet_grok_dead_lease -q
# 181 tests, 109.435s
```

Hygiene:

- `python3 -m compileall -q` on Puppet scripts and touched tests: OK
- `git diff --check`: OK
- Forbidden bridge/package-path scan: none

Parent verification independently reproduced the focused 63-test suite, the 181-test session/authority/tmux/dead-lease suite, and full Puppet discovery:

```text
python3 -m unittest discover -s tests -p 'test_puppet_*.py' -q
# 864 tests, 159.481s
# OK
```

Parent also reran `compileall` and `git diff --check`; both passed.

## Remaining blockers

- Live AGY lifecycle qualification remains later work; this slice never claims a live AGY run
- Cursor ACP under Puppet ownership — later stage
- Later builder admission (Grok ACP, Codex, Claude) — later stage
- Herdr as a Puppet run transport — explicitly unsupported
- Operator-plan packet still cannot carry transport fields (frozen fanout/Codex entry schema)
- Tmux settle still lives in the shared transport/authority fingerprint
- Parent implementation and proof commit: pending (recorded in the closeout event after commit)
