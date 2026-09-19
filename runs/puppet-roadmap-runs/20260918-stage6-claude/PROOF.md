# Proof

## Baseline

- Worktree: `/Users/bobbybones/.codex/worktrees/bcc5/SaariusSkills`
- Branch: `codex/puppet-roadmap-stage1-20260918`
- HEAD: `4dda99f206b256c44b4adf2a23b1484640839488`
- Accepted Grok admission code: `b75569e`
- Accepted Codex admission code: `f51138e`
- Codex proof closeout: `4dda99f`
- `origin/main`: `a8de5b9245cd457cc35ca2e223a11040d0772f47`

## Readiness

- Native Cursor ACP readiness passed for the exact workspace.
- Requested model: `cursor-grok-4.6-high`
- Selected/current model: `grok-4.6[effort=high,fast=true]`
- Matching model IDs: exactly one.
- Live Claude: not claimed. All builder-admission proof is a deterministic observation/receipt fixture.

Acceptance scope: code and deterministic fixture proof only. Live Claude qualification remains pending; no live E2E completion is claimed.

## What landed

Stage 6 added the narrow Claude-only builder admission contract after the existing paired-qualification and source-only authority gates:

- New Claude target-source module `claude_admission.py` with observation, receipt, admission, and lifecycle schemas
- Claude is admitted as a builder only from a current paired-qualification receipt projection plus observed runtime metadata
- Observed model must carry Claude's existing `resolved_identity` field, must not be `current_default` / `unavailable` / `default`, and must not equal the requested selector
- Runtime identity must match Claude Code `2.1.215` (`CLAUDE_VERSION`, `CLAUDE_VERSION_OBSERVATION_SHA256`)
- Workspace proof requires path, branch, head, and tree; a path alone is not enough
- Session and halt proof require matching controller session plus Claude `session_id` (the existing `--session-id` contract), not `codex_session_id`, `grok_session_id`, or ACP `conversation_id`
- Terminal/result proof covers state and result identity
- Stale, unauthorized, or public-launch-claiming paired receipts fail closed as body-safe `qualification_receipt_invalid` blockers
- Wrong-target, selector-only, wrong-model, wrong-workspace, generic `acp`, `cursor-acp`, `agy-print`, and Herdr observations fail closed
- Stage-2 worker completion, controller acceptance, confirmed halt, progress cursor, and bounded final outcome stay distinct; `SOURCE_ACCEPTED` still does not emit `final_outcome`
- `ClaudeBuilderAdmissionController.available()` and `ClaudeBuilderAdmissionFixture.available()` remain false; `require_live_claude_builder` keeps the existing matched-control/source-only launch-authority gate
- Fixtures do not open a live Claude process and do not fall back to tmux, `agy-print`, `cursor-acp`, or generic `acp`
- `claude_admission.py` is Claude target-source only so admission edits do not invalidate other targets
- Operator-plan field set stays frozen; `plan --transport` still only binds/refuses and does not add plan fields
- Tmux, `agy-print`, and `cursor-acp` remain the implemented transports; Herdr and generic `acp` stay unsupported
- Shared caller/transport files were not edited
- Prior accepted stage proof directories were not edited

## Tests

Focused file (OK):

```text
python3 -m unittest tests.test_puppet_claude_admission -q
# 13 tests, 0.005s
```

Focused Claude plus qualification reuse and preserved Grok/Codex admission (OK):

```text
python3 -m unittest tests.test_puppet_claude_admission \
  tests.test_puppet_claude_paired_qualification \
  tests.test_puppet_claude_startup_gates \
  tests.test_puppet_qualification_reuse \
  tests.test_puppet_codex_admission tests.test_puppet_grok_admission \
  tests.test_puppet_cursor_acp tests.test_puppet_agy_print \
  tests.test_puppet_transport tests.test_puppet_caller -q
# 123 tests, 14.104s
```

Focused plus contracts/CLI/packaging and preserved transports (OK):

```text
python3 -m unittest tests.test_puppet_claude_admission \
  tests.test_puppet_cursor_acp tests.test_puppet_agy_print \
  tests.test_puppet_agy_print_lifecycle tests.test_puppet_transport \
  tests.test_puppet_caller tests.test_puppet_contracts \
  tests.test_puppet_qualification_reuse tests.test_puppet_cli \
  tests.test_puppet_packaging -q
# 106 tests, 15.407s
```

Full Puppet discovery (OK):

```text
python3 -m unittest discover -s tests -p 'test_puppet_*.py' -q
# 932 tests, 172.717s
# OK
```

Hygiene:

- `python3 -m compileall -q` on touched Puppet scripts and tests: OK
- `git diff --check`: OK
- Forbidden bridge/package-path/credential scan: none

## Parent verification

- Parent independently reviewed the Claude admission module, tests, target-local qualification-scope change, and stage proof.
- Parent focused preservation/qualification tests: 123 tests, 14.168s, OK.
- Parent `python3 -m compileall -q` on all touched Puppet scripts/tests: OK.
- Parent `git diff --check`: OK.
- Parent full Puppet discovery: `python3 -m unittest discover -s tests -p 'test_puppet_*.py' -q` — 932 tests, 200.443s, OK.
- The scoped implementation commit contains only Claude admission code/tests and target-local qualification-scope assertions; no unrelated source changes were found.

## Remaining blockers

- Live Claude process is still not claimed; `ClaudeBuilderAdmissionController.available()` and `require_live_claude_builder` stay fail-closed
- Generic `acp` remains unsupported
- Herdr as a Puppet run transport — explicitly unsupported
- Operator-plan packet still cannot carry transport fields (frozen fanout/Codex entry schema)
- Tmux settle still lives in the shared transport/authority fingerprint
- Implementation commit: `c0616a7b68ad4b72cd3fa68cf265b0b49fcf50a9`.
- Stage accepted after parent verification.
- Implementation commit: `c0616a7b68ad4b72cd3fa68cf265b0b49fcf50a9`.
- Proof closeout commit: `5d9e90c`.
