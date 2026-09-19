# Proof

## Baseline

- Worktree: `/Users/bobbybones/.codex/worktrees/bcc5/SaariusSkills`
- Branch: `codex/puppet-roadmap-stage1-20260918`
- HEAD: `3743d4aac863e9a5c200a8b4c90f04ba284fd3f2`
- Accepted stage-5 code: `fa12809`
- Stage-5 proof closeout: `3743d4a`
- `origin/main`: `a8de5b9245cd457cc35ca2e223a11040d0772f47`
- Commit: pending parent commit

## Readiness

- Native Cursor ACP readiness passed for the exact workspace.
- Requested model: `cursor-grok-4.6-high`
- Selected/current model: `grok-4.6[effort=high,fast=true]`
- Matching model IDs: exactly one.
- Live Grok: not claimed. All builder-admission proof is a deterministic observation/receipt fixture.

## What landed

Stage 6 added the narrow Grok-only builder admission contract after the existing qualification and authority gates:

- New Grok target-source module `grok_admission.py` with observation, receipt, admission, and lifecycle schemas
- Grok is admitted as a builder only from a current paired-qualification receipt projection plus observed runtime metadata
- Observed model must appear in Grok runtime metadata and must not equal the requested selector
- Runtime identity must match Build 0.2.112 (`GROK_EXECUTABLE_SHA256`, `GROK_BUILD_VERSION`, `GROK_RUNTIME_BASENAME`)
- Workspace proof requires path, branch, head, and tree; a path alone is not enough
- Session and halt proof require matching controller session plus Grok UUIDv4 identity, not ACP conversation ids
- Terminal/result proof covers state and result identity
- Stale or unauthorized qualification receipts fail closed as body-safe `qualification_receipt_invalid` blockers
- Wrong-target, selector-only, wrong-model, wrong-workspace, generic `acp`, `cursor-acp`, `agy-print`, and Herdr observations fail closed
- Stage-2 worker completion, controller acceptance, confirmed halt, progress cursor, and bounded final outcome stay distinct; `SOURCE_ACCEPTED` still does not emit `final_outcome`
- `GrokBuilderAdmissionController.available()` and `GrokBuilderAdmissionFixture.available()` remain false; `require_live_grok_builder` keeps the existing launch-authority gate
- Fixtures do not open a live Grok process and do not fall back to tmux, `agy-print`, `cursor-acp`, or generic `acp`
- `grok_admission.py` is Grok target-source only so admission edits do not invalidate other targets
- Operator-plan field set stays frozen; `plan --transport` still only binds/refuses and does not add plan fields
- Tmux, `agy-print`, and `cursor-acp` remain the implemented transports; Herdr and generic `acp` stay unsupported
- Shared caller/transport files were not edited

## Tests

Focused file (OK):

```text
python3 -m unittest tests.test_puppet_grok_admission -q
# 12 tests, 0.005s
```

Focused Grok plus qualification reuse (OK):

```text
python3 -m unittest tests.test_puppet_grok_admission \
  tests.test_puppet_grok_launch tests.test_puppet_grok_qualification \
  tests.test_puppet_grok_evidence tests.test_puppet_grok_halt \
  tests.test_puppet_grok_workspace_plane \
  tests.test_puppet_qualification_reuse -q
# 85 tests, 4.293s
```

Focused plus contracts/CLI/packaging and preserved transports (OK):

```text
python3 -m unittest tests.test_puppet_grok_admission \
  tests.test_puppet_cursor_acp tests.test_puppet_agy_print \
  tests.test_puppet_agy_print_lifecycle tests.test_puppet_transport \
  tests.test_puppet_caller tests.test_puppet_contracts \
  tests.test_puppet_qualification_reuse tests.test_puppet_cli \
  tests.test_puppet_packaging -q
# 105 tests, 16.259s
```

Caller-path plus session/authority/tmux/dead-lease (OK):

```text
python3 -m unittest tests.test_puppet_grok_admission \
  tests.test_puppet_cursor_acp tests.test_puppet_agy_print_lifecycle \
  tests.test_puppet_agy_print tests.test_puppet_transport \
  tests.test_puppet_caller tests.test_puppet_contracts \
  tests.test_puppet_cli tests.test_puppet_qualification_reuse \
  tests.test_puppet_packaging tests.test_puppet_session \
  tests.test_puppet_authority tests.test_puppet_tmux \
  tests.test_puppet_grok_dead_lease -q
# 223 tests, 104.784s
```

Hygiene:

- `python3 -m compileall -q` on Puppet scripts and touched tests: OK
- `git diff --check`: OK
- Forbidden bridge/package-path scan: none

Parent independently reran the 105-test preservation suite and full Puppet discovery:

```text
python3 -m unittest discover -s tests -p 'test_puppet_*.py' -q
# 906 tests, 191.421s
# OK
```

Parent also reran `compileall` and `git diff --check`; both passed.

## Remaining blockers

- Live Grok process is still not claimed; `GrokBuilderAdmissionController.available()` and `require_live_grok_launch` stay fail-closed
- Generic `acp` remains unsupported; Codex and Claude builder admission is a later stage
- Herdr as a Puppet run transport — explicitly unsupported
- Operator-plan packet still cannot carry transport fields (frozen fanout/Codex entry schema)
- Tmux settle still lives in the shared transport/authority fingerprint
- Parent implementation and proof commit: `b75569e` (`puppet: admit Grok builder after qualification`).
