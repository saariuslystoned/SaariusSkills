# Proof

## Baseline

- Worktree: `/Users/bobbybones/.codex/worktrees/bcc5/SaariusSkills`
- Branch: `codex/puppet-roadmap-stage1-20260918`
- HEAD before stage-2 commit: `aefd65977f482c673a2c66fce9ba1b46ba6ccd55`
- Stage-1 accepted code: `1a3e439b6ffe0a898b19b499968bf21410e6469a`
- `origin/main`: `a8de5b9245cd457cc35ca2e223a11040d0772f47`

## What landed

Stage 2 caller contract and transport boundary on the real doctor/launch/status/accept/halt path:

- One named transport per run (`tmux` implemented; `herdr`, `acp`, `agy-print` refuse, no fallback)
- Capability/proof table in code and `references/adapter-contract.md`
- Body-safe `caller_blockers` plus CLI `blocker` objects with remedy and optional pid/birth/pane
- Monotonic progress cursor from validated checkpoint/beacon markers
- Distinct worker completion, controller acceptance, and confirmed halt
- Bounded speak-safe `final_outcome` after acceptance or confirmed halt
- Existing tmux behavior extracted behind `open_bound_transport` / `open_run_transport`
- Stage-1 `puppet.qualification-scope/v1` schema preserved; `caller.py` and `transport.py` added to shared source paths (deliberate shared-authority invalidation)
- Frozen operator-plan field set left unchanged; `plan --transport` still refuses unsupported ids

## Tests

Focused (OK):

```text
python3 -m unittest tests.test_puppet_transport tests.test_puppet_caller \
  tests.test_puppet_contracts tests.test_puppet_cli \
  tests.test_puppet_qualification_reuse tests.test_puppet_packaging -q
# 48 tests
```

Caller-path plus session/authority/tmux/dead-lease (OK):

```text
python3 -m unittest tests.test_puppet_transport tests.test_puppet_caller \
  tests.test_puppet_contracts tests.test_puppet_cli \
  tests.test_puppet_qualification_reuse tests.test_puppet_packaging \
  tests.test_puppet_session tests.test_puppet_authority \
  tests.test_puppet_tmux tests.test_puppet_grok_dead_lease -q
# 166 tests, 92.210s
```

Broader Puppet discover:

```text
python3 -m unittest discover -s tests -p 'test_puppet_*.py' -q
# 849 tests, 166.101s
# OK

Parent reran the full discovery independently after the worker's earlier cleanup-race observation; the complete run passed without a failure.
```

## Remaining blockers

- AGY structured transport and observed-model proof (#36/#31/#40) — stage 3
- Complete live AGY lifecycle qualification — stage 4
- Cursor ACP under Puppet ownership — stage 5
- Later builder admission (Grok ACP, Codex, Claude) — stage 6
- Herdr as a Puppet run transport — explicitly unsupported
- Intercom caller wiring — Bobby-owned, not this slice
- Operator-plan packet cannot yet carry transport fields (frozen fanout/Codex entry schema)
- Tmux settle still lives in the shared transport/authority fingerprint; `agy-print` isolation from tmux settle is explicitly unsupported until that transport is implemented
- #21 Linux process-identity race remains in later lifecycle/halt scope
- Parent review checks: `git diff --check`, `compileall`, and forbidden bridge/package-path check passed.
- Parent commit: pending (recorded in the closeout event after commit).
