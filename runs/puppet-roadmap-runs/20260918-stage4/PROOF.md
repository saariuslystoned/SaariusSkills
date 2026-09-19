# Proof

## Baseline

- Worktree: `/Users/bobbybones/.codex/worktrees/bcc5/SaariusSkills`
- Branch: `codex/puppet-roadmap-stage1-20260918`
- HEAD: `263decd95d9c72bff188df94cb223b58a93197eb`
- Accepted stage-3 code: `bbbb704`
- Stage-3 proof closeout: `263decd`
- `origin/main`: `a8de5b9245cd457cc35ca2e223a11040d0772f47`
- Commit: pending parent commit

## Readiness

- Native Cursor ACP readiness passed for the exact workspace.
- Requested model: `cursor-grok-4.6-high`
- Selected/current model: `grok-4.6[effort=high,fast=true]`
- Live AGY: not claimed. All lifecycle and process-identity proof is a deterministic fixture.

Acceptance scope: code and deterministic fixture proof only. The in-memory process fixture does not resolve Linux issue #21; live AGY lifecycle and real-process identity qualification remain pending.

## What landed

Stage 4 completed the deterministic lifecycle around the stage-3 AGY structured boundary and exercised the fixture-side process-identity path. It does not close Linux issue #21 or claim live qualification:

- `qualify_agy_print_lifecycle` proves start/bind, matching conversation resume, terminal/result, distinct worker completion, controller acceptance, confirmed halt, and a bounded final outcome
- Worker completion, controller acceptance, and halt stay distinct; `SOURCE_ACCEPTED` still does not emit `final_outcome`
- `ProcessIdentityFixture` is an in-memory PID+birth table: exact owned descendants, no signaling of unrelated PIDs, fail-closed on reuse/stale/ambiguous identity
- Halt proof now records `signaled_identities` as pid+birth pairs; duplicate or colliding owned PIDs are ambiguous
- `AgyPrintController.available()` remains false; fixtures do not open a live AGY runtime
- No-fallback `agy-print` and tmux default binding are unchanged; `herdr` and `acp` stay unsupported
- Model/workspace/session observation proof is unchanged; operator-plan field set stays frozen
- Lifecycle helpers live in AGY target-source `agy_print.py` only; shared transport/caller/registry files were not edited

## Tests

Lifecycle fixture file (OK):

```text
python3 -m unittest tests.test_puppet_agy_print_lifecycle -q
# 14 tests, 0.001s
```

`agy-print` focused file (OK):

```text
python3 -m unittest tests.test_puppet_agy_print -q
# 14 tests, 9.563s
```

Focused plus contracts/CLI/packaging (OK):

```text
python3 -m unittest tests.test_puppet_agy_print_lifecycle tests.test_puppet_agy_print \
  tests.test_puppet_transport tests.test_puppet_caller tests.test_puppet_contracts \
  tests.test_puppet_qualification_reuse tests.test_puppet_cli \
  tests.test_puppet_packaging -q
# 77 tests, 11.418s
```

Caller-path plus session/authority/tmux/dead-lease (OK):

```text
python3 -m unittest tests.test_puppet_agy_print_lifecycle tests.test_puppet_agy_print \
  tests.test_puppet_transport tests.test_puppet_caller tests.test_puppet_contracts \
  tests.test_puppet_cli tests.test_puppet_qualification_reuse tests.test_puppet_packaging \
  tests.test_puppet_session tests.test_puppet_authority \
  tests.test_puppet_tmux tests.test_puppet_grok_dead_lease -q
# 195 tests, 115.673s
```

Hygiene:

- `python3 -m compileall -q` on Puppet scripts and touched tests: OK
- `git diff --check`: OK
- Forbidden bridge/package-path scan: none

Parent independently reran the focused 77-test suite, the 195-test caller/session/authority suite, and full Puppet discovery:

```text
python3 -m unittest discover -s tests -p 'test_puppet_*.py' -q
# 878 tests, 171.049s
# OK
```

Parent also reran `compileall` and `git diff --check`; both passed.

## Remaining blockers

- Live AGY process is still not claimed; `AgyPrintController.available()` stays fail-closed
- Shared `registry.send_exact_sigint` Linux/Darwin kernel TOCTOU path was not changed (shared fingerprint); #21 remains pending for real Linux process identity and halt qualification
- Cursor ACP under Puppet ownership — later stage
- Later builder admission (Grok ACP, Codex, Claude) — later stage
- Herdr as a Puppet run transport — explicitly unsupported
- Operator-plan packet still cannot carry transport fields (frozen fanout/Codex entry schema)
- Tmux settle still lives in the shared transport/authority fingerprint
- Parent implementation and proof commit: `23300af` (`puppet: qualify AGY lifecycle and process identity`).
