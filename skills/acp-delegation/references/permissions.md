# Supported and effective permissions

All three bridges resolve `SAARIUS_ACP_PERMISSION_MODE` from the bridge server's
startup environment. Supported values are `approve-reads` (default) and
`approve-all` (explicit break-glass). `nonInteractivePermissions` stays `fail`.
Under approve-reads, the first write or exec that requires approval fails with
`PERMISSION_PROMPT_UNAVAILABLE`. Under approve-all those tool prompts may be
approved; runtime/model/auth/workspace failures and repo gates still apply.
An invalid value reports `INVALID_PERMISSION_MODE` and is not task-ready.

Readiness and submission both expose `permission.permissionMode`, `source`,
`supportedModes`, `toolApproval`, and `configuration`. These describe bridge
tool approval, not a guarantee that a tool or model task will succeed.

## Configure the selected server

There is currently **no per-job or per-conversation permission override** in
readiness/delegate. Do not pass invented mode arguments. The mode lasts for the
server process and affects all jobs on that server. Use a dedicated host/server
instance for narrower scope; avoid changing a shared instance with active jobs.
Even an idle shared server may serve unrelated consumers: use a dedicated
instance unless prior authorization explicitly covers the selected server's
shared scope. Task-level approval alone does not cover unrelated jobs.
Restoring approve-reads also requires restarting that instance. Per-job scoping
is a possible follow-up, not a supported API in this change.

After user authorization, change only the selected server's non-secret mode
setting using the host's MCP configuration. Do not read whole host configs that
may contain credentials; use a targeted supported edit or ask for the exact
host action if no such edit is available. Do not edit installed cached bridge
code or set unrelated environments.

| Host/attach | Configuration path | Required activation |
| --- | --- | --- |
| Codex path/local plugin | Selected `mcpServers` entry's `env.SAARIUS_ACP_PERMISSION_MODE` in the plugin's `.mcp.json` | Reload/restart the Codex host so the MCP server is recreated; verify in a fresh task. A terminal export cannot change the running desktop process. |
| Cursor plugin | Selected entry's `env.SAARIUS_ACP_PERMISSION_MODE` in `.cursor-plugin/mcp.json` | Reload the plugin/MCP host to recreate that server, then call native readiness. Cursor's shipped manifest has Grok and Antigravity only. |
| Claude Code plugin | Host startup environment `SAARIUS_ACP_PERMISSION_MODE=approve-all`, passed through by `.claude-plugin/plugin.json`; alternatively the selected plugin-qualified server override in Claude Code MCP configuration | Start a fresh Claude Code session with that environment/override; confirm `/mcp` and native readiness. A plugin update is also needed when the installed version predates the passthrough. |
| Direct bridge/launcher | Process environment on `node bridge/acp-runtime/launcher.mjs <lane>` | Start a new server process under the authorized environment; this is a supported attach configuration, not a substitute worker client. |
| Hop | Environment on the **worker's** bridge launcher via the host-owned hop wrapper | Restart the selected attach and worker bridge. SSH does not automatically forward the local mode; configure the worker wrapper explicitly. |

For path installs the selected server entry can include this non-secret fragment
alongside its existing command, args, cwd and other environment settings:

```json
"env": { "SAARIUS_ACP_PERMISSION_MODE": "approve-all" }
```

Preserve other settings. Published/cached plugins may not offer a persistent
editable manifest: use the host's supported per-server override or a maintained
path install instead of editing the cache. If that host mechanism is unknown,
report the exact remaining action: configure this selected MCP server's startup
environment and restart it. Do not claim the plugin lacks approve-all.

## Verify before mutation

Call the selected native readiness tool for the exact worker-absolute workspace.
Require runtime `ready: true`, the correct advertised model and workspace, and
`permission.permissionMode: "approve-all"` with write/exec tool approval true.
The readiness probe sends no model turn. A setup script's `MCP_READY` only proves
startup, not that a running host has reloaded. If tools are absent, run the
selected lane's documented setup check and use its exact repair command; then
reload the host and verify natively. Keep unsupported capability, dependency
repair, authorization missing, and reload pending as distinct outcomes.

After bounded submission confirm its receipt reports the same effective mode.
If the user already authorized it, only request missing configuration/reload;
do not ask again whether approve-all is allowed. Carry that authorization,
verified effective mode, and pending host actions into the next-session handoff.
