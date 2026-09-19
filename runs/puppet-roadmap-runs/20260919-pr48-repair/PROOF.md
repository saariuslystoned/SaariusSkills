# Proof

## Baseline

- PR: https://github.com/saariuslystoned/SaariusSkills/pull/48
- Reviewed/current head: `9d95cc057a0c7e07f8e83fe121548f731c362a9e`
- Worktree: `/Users/bobbybones/.codex/worktrees/bcc5/SaariusSkills`
- Branch: `codex/puppet-roadmap-stage1-20260918`
- Worktree was clean before repair.

## Review findings being repaired

1. Qualification scope must include actual authority-bearing dependencies, including subscription profile code, and receipt validation must invalidate on authority drift without invalidating unrelated harnesses.
2. Registry transport compatibility must explicitly handle existing v2 records and preserve old tmux status/halt exact-identity behavior.
3. Cursor model proof must independently bind requested model to verified catalog/runtime resolution, reject wrong-model/fallback, and allow legitimate requested/observed equality.

## Truthful scope correction

- AGY/Cursor/later-builder slices are fixture-only proof and not live E2E completion.
- The in-memory process fixture does not resolve Linux issue #21.
- Live qualification remains pending; the next concrete real-AGY lifecycle slice is separate from this bounded repair pass.

## Reproduction

- Qualification scope reproduction: mutate `scripts/puppet_lib/subscription_profiles.py` in a copied skill root and run `compare_qualification_compatibility`; result was `invalidations=[]`. Shared ownership lacked that path (`shared_has_subscription_profiles=False`).
- Registry reproduction: launch a test-owned tmux session, remove `transport` from its existing `schema_version: 2` record, then call status and halt; both returned `ValidationError: session registry fields do not match schema`.
- Cursor model reproduction: `prove_observed_model(fixture_observation(observed_model="arbitrary-unverified-model", runtime_model="arbitrary-unverified-model"), requested_model="cursor-grok-4.6-high")` returned success for the arbitrary model.

## Qualification-scope ownership inventory

Proved by import/ownership on the receipt, preflight, and launch-binding path; no extra files added without that evidence.

- Shared receipt/transport/controller/authority already owned: `adapter_manifest.py`, `authority.py`, `session.py`, `probe.py`, `transport.py`, `profile_login.py`, `puppet.py`.
- Missing shared owner: `scripts/puppet_lib/subscription_profiles.py`. Used by `session` preflight/binding, `probe` preflight/binding, and `adapter_manifest` receipt launch-binding/`subscription_binding_environment`.
- Left unowned: `subscription_onboarding.py` is CLI first-use planning only, not receipt/preflight/binding.
- Target-local reuse left unchanged: Grok subscription adoption stays in grok target sources; unrelated harness sources stay out of shared.

## Qualification-scope worker result

- Schema unchanged: `puppet.qualification-scope/v1`.
- Added only `scripts/puppet_lib/subscription_profiles.py` to `_SHARED_SOURCE_PATHS`.
- Post-fix same mutation yields `transport_or_shared_authority_changed` plus `compatibility_scope_fingerprint_changed`.
- Unrelated harness drift still reusable; shared `authority.py` drift still invalidates.
- No live/account actions. Source left uncommitted. Registry and Cursor model slices untouched.

Changed files:

- `skills/puppet/scripts/puppet_lib/qualification_scope.py`
- `tests/test_puppet_qualification_reuse.py`

Commands/results:

- `python3 -m unittest tests.test_puppet_qualification_reuse -v` → 10 tests OK in 0.181s
- `python3 -m compileall -q skills/puppet/scripts/puppet_lib/qualification_scope.py tests/test_puppet_qualification_reuse.py` → `COMPILEALL_OK`
- `git diff --check` → `DIFF_CHECK_OK`

## Parent verification of second review repairs

- Parent independently reran the P1 qualification/receipt suite → 57 tests OK in 2.525s.
- Parent independently reran the P2 Cursor/catalog suite → 33 tests OK in 5.942s; the three-test cross-target preservation check also passed.
- Parent reran `python3 -m unittest discover -s tests -p 'test_puppet_*.py' -q` → 946 tests OK in 310.390s.
- Parent reran compileall over all touched Puppet scripts/tests → `COMPILEALL_OK`.
- Parent reran `git diff --check` → `DIFF_CHECK_OK`.
- No live harness, account, or external send action was taken; live qualification remains false.
- Parent commit: `3afcdbe` (`puppet: close PR48 review findings`).

## P2 Cursor catalog-evidence worker

- Native Cursor ACP job: `c120b10c-0867-41ed-94fe-acaa7083168c`, exact workspace and `cursor-grok-4.6-high` route.
- Scope: require explicit verified catalog evidence through direct, lifecycle, controller, runner, and structured caller proof; static catalog remains an explicitly supplied fixture only.
- Status: completed in this workspace as uncommitted source. P1 qualification-scope/receipt source left unchanged. No live Cursor route was built.

## Worker and parent verification

- Qualification-scope repair completed in this workspace as uncommitted source plus this proof packet.
- Parent independently reran `python3 -m unittest tests.test_puppet_qualification_reuse -q`: 10 tests OK.
- Parent independently reran compileall and `git diff --check`: OK.
- Registry compatibility repair completed in this workspace as uncommitted source plus this proof packet. Qualification-scope source was left unchanged in this slice. Cursor model repair remains pending.

## Registry compatibility worker result

- Schema unchanged: `SESSION_REGISTRY_SCHEMA_VERSION = 2`.
- Explicit classes: `current_v2` requires and validates the stored transport binding; `pre_transport_v2` is the exact prior field set and is implicit tmux. No stored binding is invented.
- New `create`/`activate` writes still require `current_v2`. Load/status/halt accept exact pre-transport v2 without weakening current transport validation.
- Legacy v1, future schema, extra/missing/mixed fields, and malformed or unimplemented transport bindings fail closed.
- Post-fix reproduction: same stripped v2 record loads; status and halt keep the exact process/tmux/socket/pane identity; halted record stays schema 2 with no `transport` field; `tmux_preserved=true`.
- No live/account actions. Source left uncommitted. Qualification-scope and Cursor model sources untouched in this slice.

Changed files:

- `skills/puppet/scripts/puppet_lib/registry.py`
- `skills/puppet/scripts/puppet_lib/session.py`
- `tests/test_puppet_authority.py`
- `tests/test_puppet_session.py`

Commands/results:

- Reproduction: launch test-owned tmux session, strip `transport` from `schema_version=2` record → `STATUS_ERROR ValidationError: session registry fields do not match schema`; `HALT_ERROR ValidationError: session registry fields do not match schema`
- `python3 -m unittest tests.test_puppet_authority.AuthorityTests.test_session_collision_and_supervisor_hash_drift_fail tests.test_puppet_session tests.test_puppet_transport -q` → 35 tests OK in 56.311s
- `python3 -m compileall -q skills/puppet/scripts/puppet_lib/registry.py skills/puppet/scripts/puppet_lib/session.py tests/test_puppet_session.py tests/test_puppet_authority.py tests/test_puppet_transport.py` → `COMPILEALL_OK`
- `git diff --check` → `DIFF_CHECK_OK`

## Parent verification of registry compatibility

- Parent independently reran `python3 -m unittest tests.test_puppet_authority tests.test_puppet_session tests.test_puppet_transport -q` → 86 tests OK in 54.618s.
- Parent independently reran compileall for the changed registry/session/tests → `COMPILEALL_OK`.
- Parent independently reran `git diff --check` → `DIFF_CHECK_OK`.
- The old-v2 status/halt test preserved exact process/tmux/socket/pane identity; no new binding was invented for the legacy record.

## Cursor model worker result

- Native first attempt `e95b5cc0-3a96-4b29-96c8-07f70b331580` failed with `BRIDGE_RESTARTED`; no source result was accepted.
- Resubmission `a940c5e9-6e7c-4e1d-a4b4-0f3530306766` completed the repair in this workspace. Requested selector `cursor-grok-4.6-high` binds independently to verified runtime `grok-4.6[effort=high,fast=true]`.
- Local verified catalog/selector resolves that selector independently of observation. `prove_observed_model`, `CursorAcpController.caller_result`, and `_cursor_acp_structured_launch` pass that catalog-bound expected runtime and never use `observation['observed_model']['id']` or `observation['runtime']['model_id']` as expected-model authority.
- Post-fix reproduction: the same arbitrary/unverified observation with `requested_model=cursor-grok-4.6-high` raises `IdentityError: observed Cursor ACP model is unverified`. Passing the observation ID as `expected_observed_model` raises mismatch against the catalog bind.
- Rejected: wrong verified model, fallback/default, unavailable selector, unverified/arbitrary IDs.
- Allowed: requested/observed equality when the requested selector resolves to that exact runtime model.
- Preserved: generic ACP unsupported, no tmux/agy-print fallback, `CursorAcpController.available() is False`, live Cursor unclaimed.
- Qualification-scope and registry compatibility sources were left unchanged in this slice except the narrow `_cursor_acp_structured_launch` caller bind.
- No live/account actions. Source left uncommitted.

Changed files:

- `skills/puppet/scripts/puppet_lib/cursor_acp.py`
- `skills/puppet/scripts/puppet_lib/session.py` (Cursor caller bind only)
- `tests/test_puppet_cursor_acp.py`

Commands/results:

- Reproduction now: `prove_observed_model(fixture_observation(observed_model="arbitrary-unverified-model", runtime_model="arbitrary-unverified-model"), requested_model="cursor-grok-4.6-high")` → `IdentityError: observed Cursor ACP model is unverified`
- `python3 -m unittest tests.test_puppet_cursor_acp tests.test_puppet_transport tests.test_puppet_caller -q` → 29 tests OK in 4.893s
- Additional preservation: grok/codex/claude `test_existing_transports_and_generic_acp_stay_unchanged` → 3 tests OK
- `python3 -m compileall -q skills/puppet/scripts/puppet_lib/cursor_acp.py skills/puppet/scripts/puppet_lib/session.py tests/test_puppet_cursor_acp.py` → `COMPILEALL_OK`
- `git diff --check` → `DIFF_CHECK_OK`

## Parent verification of Cursor model binding and full suite

- Parent independently reran `python3 -m unittest tests.test_puppet_cursor_acp tests.test_puppet_transport tests.test_puppet_caller -q` → 29 tests OK in 4.888s.
- The first full-suite run exposed one compatibility regression in the existing in-memory AGY-print transport-only fixture: `_runtime` attempted to classify a non-registry record as persisted v2. The fix keeps persisted records on the explicit v2 classifier and validates only the transport binding for schema-less in-memory callers.
- Parent reran `python3 -m unittest tests.test_puppet_agy_print tests.test_puppet_session tests.test_puppet_transport -q` → 48 tests OK in 62.135s.
- Parent reran `python3 -m unittest discover -s tests -p 'test_puppet_*.py' -q` → 941 tests OK in 197.989s.
- Parent compileall for all touched Puppet scripts/tests → `COMPILEALL_OK`.
- Parent `git diff --check` → `DIFF_CHECK_OK`.
- Parent commit: `af41be6` (`puppet: repair PR48 qualification and identity boundaries`).

## Second review pass

- Review checkout: `/Users/bobbybones/Developer/worktrees/saariusskills-pr48-review-20260919`.
- Exact reviewed head: `db527dedf3bb0a519c53f7d5c4f2f103f4bd3445`.
- Remaining negative probes reproduced: copied-source edits to `beacons.py` and `signal_exec.py` yielded `invalidations=[]`; complete Cursor proof without catalog evidence still succeeded using the static default catalog.
- P1 native Cursor ACP job: `f6191991-d221-40c7-8fae-c8a862f44bfa`, exact workspace and `cursor-grok-4.6-high` route, submitted for dependency-closure and actual-receipt-validation repair. Cursor model source is not in this slice.

## P1 qualification-scope dependency-closure worker result

- Schema unchanged: `puppet.qualification-scope/v1`.
- Reproduction first: copied-source edits to `beacons.py` and `signal_exec.py` each returned `invalidations=[]`. Shared ownership lacked both paths.
- Import/execution ownership: `session.py` parses beacons via `parse_beacon`; `registry.py` validates stored beacon prefix/kind via `PREFIXES`; `tmux.py` executes `signal_exec.py` as the SIGINT-normalizing target wrapper. No extra files added.
- Added only `scripts/puppet_lib/beacons.py` and `scripts/puppet_lib/signal_exec.py` to `_SHARED_SOURCE_PATHS`.
- Post-fix same mutations: `compare_qualification_compatibility` → `transport_or_shared_authority_changed` plus `compatibility_scope_fingerprint_changed`.
- Actual accepted receipt validation: attested scoped receipt plus current manifest, then `verify_qualification_receipt` with the copied skill root. Same mutations raise `IdentityError: qualification compatibility scope is stale: transport_or_shared_authority_changed,compatibility_scope_fingerprint_changed`. Aggregate `adapter_fingerprint` is not used.
- Unrelated cursor/grok harness drift remains reusable for AGY. Cursor model source (`cursor_acp.py`) untouched. Prior committed repairs at `db527ded` preserved.
- No live/account actions. Source left uncommitted.

Changed files:

- `skills/puppet/scripts/puppet_lib/qualification_scope.py`
- `skills/puppet/scripts/puppet_lib/adapter_manifest.py` (`_source_root` hook into scoped compare only)
- `tests/test_puppet_qualification_reuse.py`

Commands/results:

- Reproduction: `beacons.py` and `signal_exec.py` copied-source probes → `invalidations=[]`
- `python3 -m unittest tests.test_puppet_qualification_reuse tests.test_puppet_adapters tests.test_puppet_claude_admission.ClaudeBuilderAdmissionTests.test_qualification_scope_keeps_claude_admission_target_local tests.test_puppet_codex_admission.CodexBuilderAdmissionTests.test_qualification_scope_keeps_codex_admission_target_local tests.test_puppet_grok_admission.GrokBuilderAdmissionTests.test_qualification_scope_keeps_grok_admission_target_local -q` → 57 tests OK in 1.582s
- New test: `test_shared_runtime_beacon_and_signal_exec_drift_invalidates_comparison_and_receipt` proves both comparison and receipt invalidation
- `python3 -m compileall -q skills/puppet/scripts/puppet_lib/qualification_scope.py skills/puppet/scripts/puppet_lib/adapter_manifest.py tests/test_puppet_qualification_reuse.py` → `COMPILEALL_OK`
- `git diff --check` → `DIFF_CHECK_OK`

## P2 Cursor catalog-evidence worker result

- Reproduction first: complete Cursor proof without catalog evidence used the static default catalog and succeeded.
- `_verified_advertised_model_ids` no longer substitutes `VERIFIED_CURSOR_ACP_CATALOG`. Missing catalog evidence is unverified and fails closed.
- Catalog evidence is forwarded through `prove_observed_model`, `prove_cursor_acp_observation`, `qualify_cursor_acp_lifecycle`, `CursorAcpController.prove`/`qualify_lifecycle`/`caller_result`/`require_catalog`, `CursorAcpRunnerFixture.catalog`, and `_cursor_acp_structured_launch`.
- `VERIFIED_CURSOR_ACP_CATALOG` remains an explicitly supplied deterministic fixture only.
- Callers bind expected runtime from independently supplied catalog evidence. Observation is never catalog or expected-model authority.
- Post-fix: direct, lifecycle, controller, caller, and structured launch without catalog raise `IdentityError: Cursor ACP model catalog is unverified`.
- Explicit fixture catalog succeeds, including legitimate requested/observed equality.
- Rejected: unverified, empty, malformed, unavailable requested mapping, wrong verified model, fallback/default, and observation-as-catalog.
- Preserved: generic ACP unsupported, no tmux/agy-print fallback, `CursorAcpController.available() is False`, live Cursor unclaimed.
- P1 qualification-scope/receipt source (`qualification_scope.py`, `adapter_manifest.py`, `test_puppet_qualification_reuse.py`) left unchanged. Committed repairs at `db527ded` preserved.
- No live/account actions. Source left uncommitted.

Changed files:

- `skills/puppet/scripts/puppet_lib/cursor_acp.py`
- `skills/puppet/scripts/puppet_lib/session.py` (structured launch catalog bind only)
- `skills/puppet/scripts/puppet_lib/transport.py` (forward `catalog` into Cursor ACP controller)
- `tests/test_puppet_cursor_acp.py`

Commands/results:

- Reproduction now: `prove_cursor_acp_observation(fixture_observation(), ...)` without catalog → `IdentityError: Cursor ACP model catalog is unverified`
- `python3 -m unittest tests.test_puppet_cursor_acp tests.test_puppet_transport tests.test_puppet_caller -q` → 33 tests OK in 6.119s
- New tests: `test_direct_proof_without_catalog_fails_closed`, `test_lifecycle_controller_caller_and_launch_require_catalog`, `test_explicit_verified_catalog_succeeds_including_equality`, `test_unverified_empty_unavailable_wrong_and_fallback_catalogs_fail`
- Additional preservation: grok/codex/claude `test_existing_transports_and_generic_acp_stay_unchanged` → 3 tests OK
- `python3 -m compileall -q skills/puppet/scripts/puppet_lib/cursor_acp.py skills/puppet/scripts/puppet_lib/session.py skills/puppet/scripts/puppet_lib/transport.py tests/test_puppet_cursor_acp.py` → `COMPILEALL_OK`
- `git diff --check` → `DIFF_CHECK_OK`
