# Install and reload plan

This plan is reviewable only. It was not executed. Do not hot-edit
`~/.codex`, global Cursor settings or cache, or an installed plugin cache.
Do not delegate, and do not send a Cursor prompt, until the gates below are true.

## Reference Documentation

- Official OpenAI CLI Marketplace Documentation:
  - `https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli`
  - `https://learn.chatgpt.com/docs/developer-commands`
- CLI commands supported: `codex plugin marketplace add/list/upgrade/remove` and `codex plugin add`.
  (Note: `codex plugin marketplace upgrade` is intended for Git snapshot checkouts; for maintained local directory sources, local registration is preserved directly. Phantom commands such as `marketplace update` and `plugin install` are neither advertised nor supported by the CLI).
- **Source separation & architecture**:
  - **Reviewed author worktree** (`/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930`): Clean author checkout and immutable comparison source. Public defaults remain unchanged without local permission elevation.
  - **Maintained private installation source** (`/Users/bobbybones/Developer/worktrees/saariusskills-plugin-107-merged`): The active `saarius-skills` marketplace root registered in `codex plugin marketplace list`, maintaining host-local configurations including Bobby's authorized three-lane `SAARIUS_ACP_PERMISSION_MODE=approve-all` overlay.
  - **Approved policy record** (`/Users/bobbybones/Developer/_machine-runs/acpx-0193-followup-20260929/personal-acp-permission-policy.json`, SHA256: `6df86276b4ecb212e0230266bebcc352b8ba5f63759a279ff1bdf8c40bfa7139`): Explicit non-secret authorization requiring the three-lane overlay (`cursor-acp`, `antigravity-acp`, `grok-acp`) to be preserved across every supported plugin refresh.

## Snapshot Context

- Reviewed author worktree root: `/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930`
- Branch: `codex/cursor-luna-model-selection-20260930`
- Base commit: `cc4070ebd7861f07ca3e24f7744d779fb13a472f`
- Prior committed HEAD: `531a5c28f41e62b095a547bac62f478d9285cc92`
- Patch state: PR108 P2 repair candidate resolving installed-source permission overlay verification and install reload sequence without overwriting host configuration; uncommitted candidate working tree on prior head `531a5c28f41e62b095a547bac62f478d9285cc92`.
- Plan target HEAD: once parent commits this reviewed repair patch, the approved reviewed commit HEAD will be `[REVIEWED_COMMIT_HEAD]`. Do not label base commit `cc4070e` as the patch head.
- Maintained path install root: `/Users/bobbybones/Developer/worktrees/saariusskills-plugin-107-merged`
- Manifest versions remain unchanged: Plugin `0.4.2`, Bridge `0.1.0`. Public repository defaults remain strictly unchanged.

## Approval-Gated Install & Reload Sequence

No commands are executed globally by the assistant. The sequence below is approval-gated for parent execution:

1. **Inventory & Preserve Existing Registrations and Host Overlay**:
   Audit existing marketplace registrations and verify that `saarius-skills` points to the maintained path installation source:
   ```bash
   codex plugin marketplace list
   ```
   Expected registration output confirms:
   `saarius-skills -> /Users/bobbybones/Developer/worktrees/saariusskills-plugin-107-merged`.
   Do NOT deregister or point supported install at the clean author checkout (`/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930`), as doing so drops Bobby's approved permission overlay.

   Inventory and preserve the authorized host `.mcp.json` overlay in the maintained private installation source before refresh.
   Save a unique run backup under `~/Developer` using a temporary directory (avoiding shared `/tmp` locations and avoiding blind full `.mcp.json` copy):
   ```bash
   mkdir -p "$HOME/Developer/_machine-runs"
   BACKUP_DIR=$(mktemp -d "$HOME/Developer/_machine-runs/cursor-backup-XXXXXX")
   # Preserve only approved NON-SECRET policy settings/known record into unique backup directory
   # (do NOT make a blind whole .mcp.json copy that may carry unknown env values or stale product controls)
   cp /Users/bobbybones/Developer/_machine-runs/acpx-0193-followup-20260929/personal-acp-permission-policy.json "$BACKUP_DIR/personal-acp-permission-policy.json"
   ```
   Verify policy SHA256 matches approved digest:
   ```bash
   shasum -a 256 "$BACKUP_DIR/personal-acp-permission-policy.json"
   # Approved: 6df86276b4ecb212e0230266bebcc352b8ba5f63759a279ff1bdf8c40bfa7139
   ```
   Inventory and protection of other maintained source changes remains owner/approval-gated.
   No actual copy, install, or private maintained path mutation is performed now.

2. **Synchronize Reviewed Source into Maintained Path Installation & Carry Host Overlay**:
   Carry existing approved host permissions into the maintained private installation source BEFORE supported plugin refresh:
   - Synchronize tracked product source from the approved reviewed commit into `/Users/bobbybones/Developer/worktrees/saariusskills-plugin-107-merged` (e.g. updating tracked plugin manifests, bridge, and skills).
   - Ensure the approved three-lane overlay is preserved in the maintained installation source `.mcp.json`:
     `cursor-acp`, `antigravity-acp`, and `grok-acp` each contain `env.SAARIUS_ACP_PERMISSION_MODE = "approve-all"`.
   - Inventory and preserve all protected maintained-source changes; never blind overwrite or reset.
   - Keep non-secret policy settings separate.
   - The reviewed author worktree remains completely clean and immutable as comparison source.

3. **Verify Maintained Source BEFORE Plugin Refresh**:
   Before executing the plugin refresh, validate the maintained installation source against the clean reviewed worktree and explicit approved policy:
   ```bash
   WORKTREE="/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930"
   MAINTAINED_PATH="/Users/bobbybones/Developer/worktrees/saariusskills-plugin-107-merged"
   REVIEWED_COMMIT="<40-character-hex-commit-hash>"
   APPROVED_POLICY="/Users/bobbybones/Developer/_machine-runs/acpx-0193-followup-20260929/personal-acp-permission-policy.json"
   APPROVED_POLICY_SHA256="6df86276b4ecb212e0230266bebcc352b8ba5f63759a279ff1bdf8c40bfa7139"
   python3 "$WORKTREE/proof/cursor-model-selection/20260930/compare-installed-source.py" \
     --worktree "$WORKTREE" \
     --commit "$REVIEWED_COMMIT" \
     --installed "$MAINTAINED_PATH" \
     --approved-policy "$APPROVED_POLICY" \
     --approved-policy-sha256 "$APPROVED_POLICY_SHA256"
   ```

4. **Refresh Supported Plugin from Maintained Marketplace**:
   Refresh the plugin from the maintained local marketplace root using supported CLI semantics:
   ```bash
   codex plugin add saarius-skills@saarius-skills
   ```

5. **Prepare Installed Root Runtime**:
   Resolve `SAARIUS_PLUGIN_ROOT` to the directory where the host installed the plugin (e.g. `~/.codex/plugins/...`).
   Run preparation exclusively within that installed root:
   ```bash
   node "$SAARIUS_PLUGIN_ROOT/bridge/acp-runtime/prepare.mjs" --bridge cursor-acp
   ```
   (Use `--replace-invalid` only if integrity check detects identity quarantine).
   Preparation runs locked `npm ci` with lifecycle scripts disabled. It sends zero model turns.

6. **Verify Actual Installed Cache AFTER Plugin Refresh**:
   The installed plugin cache does NOT contain a `.git` repository, so running `git status` inside `$SAARIUS_PLUGIN_ROOT` is invalid.\
   Execute this thin inline runner of the canonical standalone verifier. It forwards policy and sha flags independently to guarantee exact parity without drifting implementations or silently dropping flags:

   ```bash
   WORKTREE="/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930" \
   SAARIUS_PLUGIN_ROOT="$SAARIUS_PLUGIN_ROOT" \
   REVIEWED_COMMIT="<40-character-hex-commit-hash>" \
   APPROVED_POLICY="/Users/bobbybones/Developer/_machine-runs/acpx-0193-followup-20260929/personal-acp-permission-policy.json" \
   APPROVED_POLICY_SHA256="6df86276b4ecb212e0230266bebcc352b8ba5f63759a279ff1bdf8c40bfa7139" \
   python3 - <<'EOF'
   import os
   import subprocess
   import sys

   worktree = os.environ["WORKTREE"]
   installed = os.environ["SAARIUS_PLUGIN_ROOT"]
   commit = os.environ["REVIEWED_COMMIT"]
   policy = os.environ.get("APPROVED_POLICY")
   policy_sha = os.environ.get("APPROVED_POLICY_SHA256")

   cmd = [
       sys.executable,
       os.path.join(worktree, "proof/cursor-model-selection/20260930/compare-installed-source.py"),
       "--worktree", worktree,
       "--commit", commit,
       "--installed", installed,
   ]
   if policy:
       cmd.extend(["--approved-policy", policy])
   if policy_sha:
       cmd.extend(["--approved-policy-sha256", policy_sha])

   res = subprocess.run(cmd)
   sys.exit(res.returncode)
   EOF
   ```

   (The canonical standalone runner can also be executed directly with identical arguments:
   `python3 "$WORKTREE/proof/cursor-model-selection/20260930/compare-installed-source.py" --worktree "$WORKTREE" --commit "$REVIEWED_COMMIT" --installed "$SAARIUS_PLUGIN_ROOT" --approved-policy "$APPROVED_POLICY" --approved-policy-sha256 "$APPROVED_POLICY_SHA256"`).

7. **Preserve Other Chats & Controlled Host Reload**:
   - Other chats may have active background jobs running. Never kill or restart background processes unprompted.
   - Open a **fresh chat / session first** to verify whether the host detects the reloaded plugin.
   - Controlled host app reload is only performed if necessary after owner-approved quiescence across all open sessions.

8. **Verify Fresh Native Schema & Zero-Prompt Readiness**:
   - Inspect native MCP schema: verify optional `model` and `effort` parameters are present on `cursor_acp_readiness` and `cursor_acp_delegate`, and tool descriptions reflect `gpt-5.6-luna-medium`.
   - Call native `cursor_acp_readiness` with no prompt.
   - Expected response once reloaded with user-corrected Medium default:
     - `ready: true`
     - `catalogReady: true`
     - `selectionReady: true`
     - `route.model`: `"gpt-5.6-luna[context=272k,reasoning=medium,fast=false]"`
     - `route.effort`: `"medium"`
     - `model.selectedModelId`: `"gpt-5.6-luna[context=272k,reasoning=medium,fast=false]"`
     - `model.selectedEffort`: `"medium"`
     - `model.preferredDefaultAlias`: `"gpt-5.6-luna-medium"`
     - `model.preferredDefaultModelId`: `"gpt-5.6-luna[context=272k,reasoning=medium,fast=false]"`
     - `model.preferredDefaultAvailable`: `true`
     - `promptsSent: 0`

9. **Gates for Tiny Synthetic Native Luna Medium Prompt**:
   - A tiny synthetic native prompt is ALREADY user-authorized within this task (no additional per-prompt modal approval needed).
   - Strict gating criteria (all must be satisfied before prompt):
     1. Live Luna Medium exact ID is confirmed uniquely advertised in the live Cursor ACP catalog (`models.availableModelIds`).
     2. Approved plugin installation and reload verified against reviewed commit (source integrity matching worktree).
     3. New native schema active with matching `selectedModelId` and `currentModelId` equal to `"gpt-5.6-luna[context=272k,reasoning=medium,fast=false]"`.
     4. Effective `approve-all` permission policy.
     5. Execute exactly one tiny synthetic prompt followed immediately by canonical terminal cleanup.
   - **Current status**: Because the host environment has not yet been reloaded (`hostNativeReloaded: false`), the maintainer installation gate persists and NO Cursor prompt is sent during candidate development. The tiny smoke remains gated behind parent maintainer review, git commit/push, approved marketplace reload, and fresh native load verification.
