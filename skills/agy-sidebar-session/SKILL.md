---
name: agy-sidebar-session
description: Start, message, inspect, fork, wait on, stop, and export top-level Antigravity 2.0 sidebar sessions across any project using the local agentapi CLI and LanguageServerService ConnectRPC endpoints. Use when asked to open or manage a sidebar session, message another conversation, or call local LanguageServerService RPCs.
---

# Antigravity Sidebar Session & Local RPC Control (`agy-sidebar-session`)

Use the bundled [`scripts/agy-session.py`](scripts/agy-session.py) helper (or direct `agentapi` commands) to create and orchestrate top-level Antigravity 2.0 sidebar conversations and call any of the 365 local `LanguageServerService` ConnectRPC methods natively—without driving the GUI via computer use.

## Why this exists

- Antigravity's built-in `invoke_subagent` tool creates a nested child drawer (`nesting_depth > 0`) rather than a top-level sidebar session.
- Antigravity ships [`~/.gemini/antigravity/bin/agentapi`](references/language-server-rpcs.md) (wrapping `language_server agentapi`) and a local ConnectRPC server (`ANTIGRAVITY_LS_ADDRESS` + `ANTIGRAVITY_CSRF_TOKEN`, auto-discovered from `~/.gemini/antigravity/daemon/hub_*.json` when running outside an agent shell).
- Calling `agentapi new-conversation` (with `ANTIGRAVITY_PROJECT_ID` set to the target project UUID) creates a real top-level sidebar conversation (`nesting_depth: 0`, `hideFromConversationList: false`) under any registered project.

## Quick Commands (`scripts/agy-session.py`)

Run the helper via `python3 <skill-dir>/scripts/agy-session.py <subcommand>`:

```bash
# 1. Start a new top-level sidebar session in the current project (or any project by name/path/UUID)
python3 scripts/agy-session.py new \
  --project x-api \
  --title "New X-API Session" \
  --prompt "Stand by for instructions in this new x-api session."

# Pin a model tier (flash_lite|flash|pro) or exact model ID, or an agent profile
python3 scripts/agy-session.py new \
  --project SaariusSkills \
  --model pro \
  --title "Skill Packaging Audit" \
  --prompt "Run packaging tests and report status."

# 2. Send a message to any top-level sidebar conversation (cross-session inbox)
python3 scripts/agy-session.py send \
  --conversation <conversation-uuid> \
  --title "Optional Updated Title" \
  --message "Here is the follow-up context..."

# 3. List all registered Antigravity sidebar projects (UUID, name, git folder URI)
python3 scripts/agy-session.py projects

# 4. List recent top-level sidebar conversations (optionally filtered by --project or --limit)
python3 scripts/agy-session.py list --project x-api --limit 10

# 5. Inspect live metadata for a conversation ID
python3 scripts/agy-session.py metadata <conversation-uuid>

# 6. Export a conversation trajectory cleanly to Markdown
python3 scripts/agy-session.py export-md <conversation-uuid>

# 7. Fork an existing conversation into a new sidebar conversation
python3 scripts/agy-session.py fork <conversation-uuid>

# 8. Wait for another sidebar conversation to finish its turn and become idle
python3 scripts/agy-session.py wait <conversation-uuid> --timeout-seconds 120

# 9. Cancel / stop a running conversation turn
python3 scripts/agy-session.py stop <conversation-uuid>

# 10. Check advertised models and live quota buckets
python3 scripts/agy-session.py models
python3 scripts/agy-session.py quota

# 11. Call any of the 365 LanguageServerService ConnectRPC methods directly
python3 scripts/agy-session.py rpc ListBackgroundTasks '{}'
python3 scripts/agy-session.py rpc GetMcpServerStates '{}'
```

## Direct `agentapi` CLI Reference

When you only need the 3 built-in CLI commands inside the current project, you can also invoke `agentapi` directly:

```bash
# Start a conversation in the current project (or prefix ANTIGRAVITY_PROJECT_ID=<uuid>)
~/.gemini/antigravity/bin/agentapi new-conversation \
  --title="Session Title" \
  --model=pro \
  "Initial prompt for the new session"

# Send a message to any conversation ID
~/.gemini/antigravity/bin/agentapi send-message \
  --title="Optional Title" \
  <conversation_id> \
  "Message content"

# Get live conversation metadata
~/.gemini/antigravity/bin/agentapi get-conversation-metadata <conversation_id>
```

> [!IMPORTANT]
> Always place `--title`, `--model`, and `--profile` **after** the subcommand (`agentapi new-conversation --title="..." "<prompt>"`), never before `new-conversation`.

## Safety & Privacy Boundaries

- **Never print or log `ANTIGRAVITY_CSRF_TOKEN`** or raw daemon discovery files containing tokens. `scripts/agy-session.py` reads the token in-memory and never echoes it.
- **Destructive RPCs require explicit user confirmation (`WAITING_FOR_HUMAN`)**: never invoke `DeleteAllUserData`, `DeleteProject`, `DeleteCascadeTrajectory`, `DeleteWorktree`, `GitPush`, or `AuthLogout` unless the user explicitly asks for that exact destructive action.

## Complete 365 RPC Catalog

Read [`references/language-server-rpcs.md`](references/language-server-rpcs.md) for the complete categorized catalog of all 365 `LanguageServerService` RPC endpoints + 3 `agentapi` CLI commands + daemon environment variables.
