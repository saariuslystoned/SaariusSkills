# Proof

## Baseline

- Worktree: `/Users/bobbybones/.codex/worktrees/bcc5/SaariusSkills`
- Branch: `codex/puppet-roadmap-stage1-20260918`
- HEAD: `d66bd666a2def1a92ba3bbfbecbdadfaa6cbfee6`
- Accepted Grok admission code: `b75569e`
- Grok proof closeout: `d66bd66`
- `origin/main`: `a8de5b9245cd457cc35ca2e223a11040d0772f47`
- Implementation commit: `f51138e7e89f0d49ef5c8575fa0f3fc6e95ca24d`

## Readiness

- Native Cursor ACP readiness passed for the exact workspace.
- Requested model: `cursor-grok-4.6-high`
- Selected/current model: `grok-4.6[effort=high,fast=true]`
- Matching model IDs: exactly one.
- Live Codex: not claimed. All builder-admission proof is a deterministic observation/receipt fixture.

## What landed

Stage 6 added the narrow Codex-only builder admission contract after the existing paired-qualification and source-only authority gates:

- New Codex target-source module `codex_admission.py` with observation, receipt, admission, and lifecycle schemas
- Codex is admitted as a builder only from a current paired-qualification receipt projection plus observed doctor/runtime metadata
- Observed model must appear in Codex doctor/runtime metadata, must be `observed_only`, and must not equal the requested selector or `<default>` / `current_default`
- Runtime identity must match `codex-cli 0.145.0` (`EXPECTED_EXECUTABLE_SHA256`, `EXPECTED_VERSION_TEXT`, `EXPECTED_VERSION_SHA256`)
- Workspace proof requires path, branch, head, and tree; a path alone is not enough
- Session and halt proof require matching controller session plus Codex canonical UUIDv4 identity, not ACP conversation ids or a plain `run_id`
- Terminal/result proof covers state and result identity
- Stale, unauthorized, or public-launch-claiming paired receipts fail closed as body-safe `qualification_receipt_invalid` blockers
- Wrong-target, selector-only, wrong-model, wrong-workspace, generic `acp`, `cursor-acp`, `agy-print`, and Herdr observations fail closed
- Stage-2 worker completion, controller acceptance, confirmed halt, progress cursor, and bounded final outcome stay distinct; `SOURCE_ACCEPTED` still does not emit `final_outcome`
- `CodexBuilderAdmissionController.available()` and `CodexBuilderAdmissionFixture.available()` remain false; `require_live_codex_builder` keeps the existing source-only launch-authority gate
- Fixtures do not open a live Codex process and do not fall back to tmux, `agy-print`, `cursor-acp`, or generic `acp`
- `codex_admission.py` is Codex target-source only so admission edits do not invalidate other targets
- Operator-plan field set stays frozen; `plan --transport` still only binds/refuses and does not add plan fields
- Tmux, `agy-print`, and `cursor-acp` remain the implemented transports; Herdr and generic `acp` stay unsupported
- Shared caller/transport files were not edited
- Prior accepted stage proof directories were not edited

## Tests

Focused file (OK):

```text
python3 -m unittest tests.test_puppet_codex_admission -q
# 13 tests, 0.013s
```

Focused Codex plus qualification reuse (OK):

```text
python3 -m unittest tests.test_puppet_codex_admission \
  tests.test_puppet_codex_launch tests.test_puppet_codex_qualification \
  tests.test_puppet_codex_workspace_plane \
  tests.test_puppet_qualification_reuse -q
# 83 tests, 4.296s
```

Focused plus contracts/CLI/packaging and preserved transports (OK):

```text
python3 -m unittest tests.test_puppet_codex_admission \
  tests.test_puppet_cursor_acp tests.test_puppet_agy_print \
  tests.test_puppet_agy_print_lifecycle tests.test_puppet_transport \
  tests.test_puppet_caller tests.test_puppet_contracts \
  tests.test_puppet_qualification_reuse tests.test_puppet_cli \
  tests.test_puppet_packaging -q
# 106 tests, 19.846s
```

Caller-path plus session/authority/tmux/dead-lease (OK):

```text
python3 -m unittest tests.test_puppet_codex_admission \
  tests.test_puppet_cursor_acp tests.test_puppet_agy_print_lifecycle \
  tests.test_puppet_agy_print tests.test_puppet_transport \
  tests.test_puppet_caller tests.test_puppet_contracts \
  tests.test_puppet_cli tests.test_puppet_qualification_reuse \
  tests.test_puppet_packaging tests.test_puppet_session \
  tests.test_puppet_authority tests.test_puppet_tmux \
  tests.test_puppet_grok_dead_lease -q
# 224 tests, 124.309s
```

Full Puppet discovery (OK):

```text
python3 -m unittest discover -s tests -p 'test_puppet_*.py' -q
# 919 tests, 176.591s
# OK
```

Hygiene:

- `python3 -m compileall -q` on touched Puppet scripts and tests: OK
- `git diff --check`: OK
- Forbidden bridge/package-path/credential scan: none

## Parent verification

- Parent independently reviewed the Codex admission module, tests, target-local qualification-scope change, and stage proof.
- Parent `python3 -m compileall -q` on all touched Puppet scripts/tests: OK.
- Parent `git diff --check`: OK.
- Parent full Puppet discovery: `python3 -m unittest discover -s tests -p 'test_puppet_*.py' -q` — 919 tests, 213.615s, OK.
- The scoped implementation commit contains only Codex admission code/tests and target-local qualification-scope assertions; no unrelated source changes were found.

## Remaining blockers

- Live Codex process is still not claimed; `CodexBuilderAdmissionController.available()` and `require_live_codex_builder` stay fail-closed
- Generic `acp` remains unsupported; Claude builder admission is a later stage
- Herdr as a Puppet run transport — explicitly unsupported
- Operator-plan packet still cannot carry transport fields (frozen fanout/Codex entry schema)
- Tmux settle still lives in the shared transport/authority fingerprint
- Implementation commit: `f51138e7e89f0d49ef5c8575fa0f3fc6e95ca24d`.
- Proof closeout commit: pending.
