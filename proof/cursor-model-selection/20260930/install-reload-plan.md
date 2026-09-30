# Install and reload plan

This plan is reviewable only. It was not executed. Do not hot-edit
`~/.codex`, global Cursor settings or cache, or an installed plugin cache.
Do not delegate, and do not send a Cursor prompt, until the gates below are true.

## Reference Documentation

- Official OpenAI CLI Marketplace Documentation:
  - `https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli`
  - `https://learn.chatgpt.com/docs/developer-commands`
- CLI commands supported: `marketplace add/remove` and `plugin add`.
- Marketplace root is the worktree ROOT (`/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930`), NOT `$PWD/.agents/plugins` (source paths in marketplace manifests resolve against the repository root).

## Snapshot Context

- Worktree root: `/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930`
- Branch: `codex/cursor-luna-model-selection-20260930`
- Base commit: `cc4070ebd7861f07ca3e24f7744d779fb13a472f`
- Patch state: uncommitted on base `cc4070e`.
- Plan target HEAD: once parent commits this reviewed patch, the approved reviewed commit HEAD will be `[REVIEWED_COMMIT_HEAD]`. Do not label base commit `cc4070e` as the patch head.\n- Manifest versions remain unchanged: Plugin `0.4.2`, Bridge `0.1.0`.

## Approval-Gated Install & Reload Sequence

No commands are executed globally by the assistant. The sequence below is approval-gated for parent execution:

1. **Audit & Preserve Current Source**:
   List existing marketplace registrations to record the previous source location:
   ```bash
   codex plugin marketplace list
   ```
   Note: The existing marketplace registration `saarius-skills` was pinned to an earlier snapshot. Running `add` alone does not replace an existing marketplace registration with the same name.

2. **Deregister Stale Marketplace Registration**:
   Remove the existing registration:
   ```bash
   codex plugin marketplace remove saarius-skills
   ```

3. **Register Reviewed Worktree Root**:
   Add the reviewed worktree ROOT as the marketplace (manifest paths resolve relative to repository root):
   ```bash
   codex plugin marketplace add "/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930"
   ```

4. **Install Plugin from Reviewed Marketplace**:
   Install the plugin package:
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

6. **Verify Installed Source & Hash Against Reviewed Commit**:
   The installed plugin cache does NOT contain a `.git` repository, so running `git status` inside `$SAARIUS_PLUGIN_ROOT` is invalid.
   Instead, execute this read-only Python snippet. It verifies the explicitly approved reviewed git commit against the installed root bytes/SHA256.
   Committed reviewed HEAD does not exist until the parent creates the commit; specify `REVIEWED_COMMIT` explicitly (never guess a commit hash).

   ```bash
   WORKTREE="/Users/bobbybones/Developer/worktrees/saariusskills-cursor-luna-model-selection-20260930" \
   SAARIUS_PLUGIN_ROOT="$SAARIUS_PLUGIN_ROOT" \
   REVIEWED_COMMIT="<40-character-hex-commit-hash>" \
   python3 - <<'EOF'
   import hashlib
   import os
   import re
   import subprocess
   import sys
   from pathlib import Path

   worktree = Path(os.environ["WORKTREE"]).resolve()
   installed = Path(os.environ["SAARIUS_PLUGIN_ROOT"]).resolve()
   reviewed_commit = os.environ.get("REVIEWED_COMMIT", "").strip().lower()

   # Tracked plugin manifests and source directories after reading marketplace manifests:
   # marketplace (.agents/plugins/marketplace.json, .claude-plugin/marketplace.json)
   # plugin manifests (.mcp.json, .claude-plugin, .cursor-plugin, .codex-plugin, plugin.json)
   # bridge implementations and skills
   MANIFEST_PATHS = [
       ".mcp.json",
       ".agents/plugins",
       ".claude-plugin",
       ".cursor-plugin",
       ".codex-plugin",
       "plugin.json",
       "bridge",
       "skills",
   ]

   SECRET_NAMES = {".env", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}
   SECRET_SUFFIXES = (".pem", ".p12", ".key")
   GENERATED_PARTS = {"node_modules", "__pycache__"}

   def fail(msg: str) -> None:
       print(f"FAIL: {msg}", file=sys.stderr)
       sys.exit(1)

   if not worktree.is_dir():
       fail(f"Worktree directory not found: {worktree}")
   if not installed.is_dir():
       fail(f"Installed plugin root not found: {installed}")
   if installed == worktree:
       fail("Installed root must not be the worktree itself")

   # 1. Require explicitly approved REVIEWED_COMMIT full 40-character lowercase hex
   if not re.fullmatch(r"[0-9a-f]{40}", reviewed_commit):
       fail(f"REVIEWED_COMMIT must be an explicitly approved 40-hex commit hash, got: '{reviewed_commit}'")

   # 2. Match worktree HEAD
   head = subprocess.check_output(
       ["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True
   ).strip()
   if reviewed_commit != head:
       fail(f"REVIEWED_COMMIT ({reviewed_commit}) does not match worktree HEAD ({head})")

   # 3. Ensure worktree tracked plugin paths are clean vs HEAD
   diff_rc = subprocess.run(
       ["git", "-C", str(worktree), "diff", "--quiet", "HEAD", "--", *MANIFEST_PATHS]
   ).returncode
   if diff_rc != 0:
       fail("Worktree has uncommitted changes in tracked plugin paths vs HEAD")

   # 4. List tracked files at the approved commit
   raw_tree = subprocess.check_output(
       ["git", "-C", str(worktree), "ls-tree", "-r", "--name-only", "-z", reviewed_commit, "--", *MANIFEST_PATHS]
   )
   tracked_paths = [p.decode("utf-8") for p in raw_tree.split(b"\0") if p]

   compared = 0
   failures = []

   for rel_path in tracked_paths:
       parts = set(Path(rel_path).parts)
       name = Path(rel_path).name
       if rel_path.endswith(".pyc") or bool(parts & GENERATED_PARTS):
           continue
       if name in SECRET_NAMES or name.startswith(".env") or name.endswith(SECRET_SUFFIXES):
           fail(f"Secret path detected in tracked files: {rel_path}")

       # Git show blob bytes from commit
       git_bytes = subprocess.check_output(
           ["git", "-C", str(worktree), "show", f"{reviewed_commit}:{rel_path}"]
       )
       git_hash = hashlib.sha256(git_bytes).hexdigest()

       target = installed.joinpath(*Path(rel_path).parts)
       if not os.path.lexists(target):
           failures.append(f"MISSING {rel_path}")
           continue

       if target.is_symlink():
           installed_bytes = os.fsencode(os.readlink(target))
       elif target.is_file():
           installed_bytes = target.read_bytes()
       else:
           failures.append(f"UNSUPPORTED_TYPE {rel_path}")
           continue

       installed_hash = hashlib.sha256(installed_bytes).hexdigest()
       if git_hash != installed_hash:
           failures.append(f"MISMATCH {rel_path} git={git_hash} installed={installed_hash}")
           continue

       compared += 1

   if failures:
       for f in failures:
           print(f"FAIL: {f}", file=sys.stderr)
       fail(f"Verification failed with {len(failures)} mismatch(es)/missing file(s)")

   if compared == 0:
       fail("No plugin source paths compared")

   print(f"OK: Verified {compared} tracked plugin source paths match {reviewed_commit} exactly in {installed}")
   EOF
   ```

   (A standalone runner is also committed at `proof/cursor-model-selection/20260930/compare-installed-source.py`).

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
