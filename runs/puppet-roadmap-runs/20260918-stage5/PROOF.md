# Proof

## Baseline

- Worktree: `/Users/bobbybones/.codex/worktrees/bcc5/SaariusSkills`
- Branch: `codex/puppet-roadmap-stage1-20260918`
- HEAD: `01165c76cfd44125cfba420813ff8e5b946d6acb`
- Accepted stage-4 code: `23300af`
- Stage-4 proof closeout: `01165c7`
- `origin/main`: `a8de5b9245cd457cc35ca2e223a11040d0772f47`
- Commit: pending parent commit

## Readiness

- Native Cursor ACP readiness passed for the exact workspace.
- Requested model: `cursor-grok-4.6-high`
- Selected/current model: `grok-4.6[effort=high,fast=true]`
- Live Cursor ACP: not claimed. All ACP proof is a deterministic observation/runner fixture.

Acceptance scope: code and deterministic fixture proof only. Live Cursor ACP qualification remains pending; no live E2E completion is claimed.

## What landed

Stage 5 added the narrow Puppet-owned Cursor ACP adapter/transport boundary on the stage-4 caller/transport path:

- New named transport `cursor-acp` with `CursorAcpController` plus observation/binding/resume/halt/lifecycle schemas
- Generic `acp` stays named and unsupported for every target, including Cursor
- `cursor-acp` is valid only for the Cursor target; AGY/Codex/other contracts and observations fail closed
- Requesting `cursor-acp` never falls back to tmux or `agy-print`; unavailable, unbound, mismatched, or selector-only observations are body-safe caller blockers with remedies
- Observed model must appear in ACP runtime metadata and must not equal the requested selector
- Workspace proof requires path, branch, head, and tree; a path alone is not enough
- Resume and halt proof require matching ACP session and conversation identity
- Terminal/result proof covers state and result identity
- Stage-2 worker completion, controller acceptance, confirmed halt, progress cursor, and bounded final outcome stay distinct; `SOURCE_ACCEPTED` still does not emit `final_outcome`
- `CursorAcpController.available()` and `CursorAcpRunnerFixture.available()` remain false; fixtures do not open a live Cursor ACP process
- `cursor_acp.py` is Cursor target-source only so ACP edits do not invalidate other targets
- Operator-plan field set stays frozen; `plan --transport` still only binds/refuses and does not add plan fields
- Tmux and `agy-print` default binding, capability rows, and registered-session runtime stay unchanged
- Herdr remains explicitly unsupported

## Tests

Focused file (OK):

```text
python3 -m unittest tests.test_puppet_cursor_acp -q
# 16 tests, 4.957s
```

Focused plus contracts/CLI/packaging and preserved transports (OK):

```text
python3 -m unittest tests.test_puppet_cursor_acp tests.test_puppet_agy_print \
  tests.test_puppet_agy_print_lifecycle tests.test_puppet_transport \
  tests.test_puppet_caller tests.test_puppet_contracts \
  tests.test_puppet_qualification_reuse tests.test_puppet_cli \
  tests.test_puppet_packaging -q
# 93 tests, 15.420s
```

Caller-path plus session/authority/tmux/dead-lease (OK):

```text
python3 -m unittest tests.test_puppet_cursor_acp tests.test_puppet_agy_print_lifecycle \
  tests.test_puppet_agy_print tests.test_puppet_transport tests.test_puppet_caller \
  tests.test_puppet_contracts tests.test_puppet_cli \
  tests.test_puppet_qualification_reuse tests.test_puppet_packaging \
  tests.test_puppet_session tests.test_puppet_authority \
  tests.test_puppet_tmux tests.test_puppet_grok_dead_lease -q
# 211 tests, 106.937s
```

Hygiene:

- `python3 -m compileall -q` on Puppet scripts and touched tests: OK
- `git diff --check`: OK
- Forbidden bridge/package-path scan: none

Parent independently reran the 93-test focused-preservation suite, the 211-test caller/session/authority suite, and full Puppet discovery:

```text
python3 -m unittest discover -s tests -p 'test_puppet_*.py' -q
# 894 tests, 164.287s
# OK
```

Parent also reran `compileall` and `git diff --check`; both passed.

## Remaining blockers

- Live Cursor ACP process is still not claimed; `CursorAcpController.available()` stays fail-closed
- Generic `acp` remains unsupported; later builder admission (Grok ACP, Codex, Claude) is a later stage
- Herdr as a Puppet run transport — explicitly unsupported
- Operator-plan packet still cannot carry transport fields (frozen fanout/Codex entry schema)
- Tmux settle still lives in the shared transport/authority fingerprint
- Parent implementation and proof commit: `fa12809` (`puppet: add Cursor ACP ownership boundary`).
