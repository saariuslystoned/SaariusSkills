# PR108 Permission Overlay Repair Proof

## Executive Summary

This proof attests the targeted repair of the permission overlay verification logic and install-reload plan in PR #108.
All confirmed documentation and verification bugs have been resolved without weakening production security guards, without writing to the maintained path, and without sending any model turns or prompts.
Core verifier repair was accepted and preserved; Step 3 shell variable expansion was corrected on separate lines; Step 1 backup was hardened with unique `mktemp -d` directories under `~/Developer` preserving only approved non-secret policy records; and a focused offline regression test was added verifying clean shell invocation argv.

## Control Provenance & Context

- **Worktree**: `/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930`
- **Branch**: `codex/cursor-luna-model-selection-20260930`
- **Base commit**: `cc4070ebd7861f07ca3e24f7744d779fb13a472f`
- **Prior HEAD**: `531a5c28f41e62b095a547bac62f478d9285cc92`
- **Maintained installation source**: `/Users/bobbybones/Developer/worktrees/saariusskills-plugin-107-merged`
- **Approved policy record**: `/Users/bobbybones/Developer/_machine-runs/acpx-0193-followup-20260929/personal-acp-permission-policy.json`
  - Digest (SHA256): `6df86276b4ecb212e0230266bebcc352b8ba5f63759a279ff1bdf8c40bfa7139`
  - Content: `mode: "approve-all"`, `lanes: ["cursor-acp", "antigravity-acp", "grok-acp"]`
- **Approved manifest digest**: `b279b63e05a60f56aecb3b90db2e0c9280b2487bf3352d9902ef0101736c94ea`
- **Writer**: Native Antigravity ACP assistant (`approve-all` route)
- **Prompts sent**: 0.
- **Maintained path writes**: 0.

## Control Receipts & Prior Runs

- **Parent 150-Tracked-Plugin-Path Smoke**:
  [`parent-smoke.json`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/proof/cursor-model-selection/20260930/permission-overlay-repair/parent-smoke.json)
  - 18 cases passed on 150 tracked plugin paths.
  - Validates clean source, inline runner parity, production base environment ignore, approved overlay pass, wrong digest rejection, control tamper rejections (command, args, env keys, permission values, partial overlays, bridge bytes, duplicate json keys), and missing argument pairs.
  - Manifest hash: `b279b63e05a60f56aecb3b90db2e0c9280b2487bf3352d9902ef0101736c94ea`.
  - Policy hash: `6df86276b4ecb212e0230266bebcc352b8ba5f63759a279ff1bdf8c40bfa7139`.
- **Native Repair Terminal Receipt**:
  [`native-repair-terminal.json`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/proof/cursor-model-selection/20260930/permission-overlay-repair/native-repair-terminal.json)
  - Job ID: `eea3b524-0b93-4ce7-878d-4bb0cf6bbd05`.
  - Canonical terminal status: `completed`, `taskComplete: true`, `cleanupReady: true`, `complete: true`, `remediation: "none"`, `stopReason: "end_turn"`.
- **Initial Cancelled Terminal Receipt**:
  [`initial-cancelled-terminal.json`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/proof/cursor-model-selection/20260930/permission-overlay-repair/initial-cancelled-terminal.json)
  - Job ID: `dc5e5086-f68b-4af4-9f8c-2285cb6b96ef`.
  - Status: `cancelled`, `taskComplete: true`, `cleanupReady: true`, `complete: true`.
- **Preflight Argv Interception Proof**:
  [`preflight-argv-review.json`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/runs/cursor-model-selection-runs/20260930/coordinator/preflight-argv-review.json)
  - Harmless interception proof proving that one-line env prefix before command expansion causes shell argument expansion to evaluate empty strings before assignment, intercepting blank flags without executing any global command.

## Targeted Gaps Closed

1. **Step 3 Shell Block Variable Assignment Fix**:
   - `proof/cursor-model-selection/20260930/install-reload-plan.md` Step 3 previously assigned `WORKTREE`, `MAINTAINED_PATH`, `REVIEWED_COMMIT`, `APPROVED_POLICY`, and `APPROVED_POLICY_SHA256` as a single prefix to the `python3` command. Because the shell expands arguments before running prefix assignments, executing in a clean shell passed blank values and a truncated script path `/proof/...`.
   - Fixed Step 3 to assign variables on separate complete shell lines BEFORE invoking `python3`, ensuring full path and non-blank argument expansion while keeping explicit policy/digest and source/cache validations intact.

2. **Step 1 Truly Unique Backup & Non-Secret Scope**:
   - `proof/cursor-model-selection/20260930/install-reload-plan.md` Step 1 updated to create a unique temporary directory under `~/Developer` using `mktemp -d "$HOME/Developer/_machine-runs/cursor-backup-XXXXXX"` instead of deterministic paths.
   - Preserves only approved NON-SECRET policy settings and known records into the unique backup directory, avoiding blind whole `.mcp.json` copies that could carry unknown env values or stale product controls.
   - Clarified that inventorying and protecting other maintained source changes remains owner/approval-gated with no actual copy, install, or private maintained path mutation performed during candidate development.

3. **Production `BASE` Literal Restored & Environment Override Removed**:
   - `proof/cursor-model-selection/20260930/compare-installed-source.py` contains hardcoded `BASE = "cc4070ebd7861f07ca3e24f7744d779fb13a472f"`.
   - `SAARIUS_VERIFIER_BASE` environment override completely removed. Production ancestry and branch checks have no bypass, env, or args.
   - Core verifier accepted without modification.

4. **Strict JSON Types, Values & Generic Duplicate Key Rejection**:
   - Implemented typed recursive comparison `strict_typed_equal(a, b)` preventing JSON numbers and booleans from conflating (`1 != True`).
   - Manifest comparison uses canonical JSON serialization (`json.dumps(..., sort_keys=True, separators=(",", ":"))`) and strict typed comparison.
   - `parse_json_no_duplicates` rejects duplicate keys with generic diagnostic `fail(f"duplicate key in {label} JSON")` without echoing arbitrary user keys.
   - Policy file and SHA256 are opt-in; exact `approve-all` mode and exact 3 lanes enforced.

5. **Focused Offline Regression for Step 3 Preflight Argv**:
   - Added `test_step3_bash_block_preflight_argv` to `tests/test_permission_overlay.py`.
   - Extracts the actual Step 3 bash block from `install-reload-plan.md` using regex.
   - Intercepts `python3` with a harmless fake executable in a private fixture that captures `sys.argv[1:]` to JSON and exits 0 immediately.
   - Starts with all Step 3 variables (`WORKTREE`, `MAINTAINED_PATH`, `REVIEWED_COMMIT`, `APPROVED_POLICY`, `APPROVED_POLICY_SHA256`) unset in the shell environment.
   - Asserts the script path is absolute and non-blank (`/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/proof/cursor-model-selection/20260930/compare-installed-source.py`), and all flag values (`--worktree`, `--commit`, `--installed`, `--approved-policy`, `--approved-policy-sha256`) are non-blank and match expected values.
   - Never executes real source sync or global/plugin commands.
   - Retains all existing 20 test cases and wrapper extraction.

## Verification Evidence

| Test Suite | Commands Executed | Result | Duration |
| :--- | :--- | :--- | :--- |
| Focused Permission Overlay | `python3 -m unittest -v tests/test_permission_overlay.py` | **21 passed, 0 failed** | 1.61s |
| Full Repository Discovery | `python3 -m unittest discover tests` | **90 passed, 0 failed** | 59.58s |

### Test Breakdown
- `test_ledger` (22 tests): all passed.
- `test_packaging` (14 tests): all passed.
- `test_permission_overlay` (21 tests): all passed.
- `test_phone_proof` (19 tests): all passed.
- `test_picker` (5 tests): all passed.
- `test_reconcile` (9 tests): all passed.

## Artifact Manifest

- Standalone verifier: [`compare-installed-source.py`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/proof/cursor-model-selection/20260930/compare-installed-source.py)
- Install & reload plan: [`install-reload-plan.md`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/proof/cursor-model-selection/20260930/install-reload-plan.md)
- Unit tests: [`test_permission_overlay.py`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/tests/test_permission_overlay.py)
- Parent 150-path smoke receipt: [`parent-smoke.json`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/proof/cursor-model-selection/20260930/permission-overlay-repair/parent-smoke.json)
- Native repair terminal receipt: [`native-repair-terminal.json`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/proof/cursor-model-selection/20260930/permission-overlay-repair/native-repair-terminal.json)
- Initial cancelled terminal receipt: [`initial-cancelled-terminal.json`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/proof/cursor-model-selection/20260930/permission-overlay-repair/initial-cancelled-terminal.json)
- Proof report: [`PROOF.md`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/proof/cursor-model-selection/20260930/permission-overlay-repair/PROOF.md)
- Proof test log: [`test-suite.log`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/proof/cursor-model-selection/20260930/permission-overlay-repair/test-suite.log)
- Run state: [`STATE.md`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/runs/cursor-model-selection-runs/20260930/permission-overlay-repair/STATE.md)
- Run events: [`events.jsonl`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/runs/cursor-model-selection-runs/20260930/permission-overlay-repair/events.jsonl)
- Run heartbeat: [`heartbeat`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/runs/cursor-model-selection-runs/20260930/permission-overlay-repair/heartbeat)
- Run receipt: [`receipt.json`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/runs/cursor-model-selection-runs/20260930/permission-overlay-repair/receipt.json)
- Run test log: [`python-tests.log`](file:///Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930/runs/cursor-model-selection-runs/20260930/permission-overlay-repair/python-tests.log)

## Hand-off Status

Status: **`WAITING_FOR_HUMAN`**.
Worktree has no uncommitted changes outside the designated repair and proof artifacts. No files have been staged, committed, or pushed. Zero writes occurred to the maintained path. Ready for parent maintainer commit, push, CI, local install reload, and approved tiny Luna Medium prompt.
