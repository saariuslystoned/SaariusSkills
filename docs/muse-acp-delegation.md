# Muse ACP delegation

> **Where the server lives.** The `muse-acp` MCP server ships in the separate
> `ai-shed` plugin ([saari-co/ai-shed](https://github.com/saari-co/ai-shed)); `saarius-skills` ships
> skills and instructions only and must not also bundle the server. Broker
> source, tests, and runtime preparation live in ai-shed. Install steps:
> [the ai-shed plugin reference](../skills/acp-delegation/references/ai-shed-plugin.md).

SaariusSkills is the host policy for one local ACP contract. ACpx is the
local client. ACP is the wire. This lane's worker is Muse, which does
not speak ACP natively: the ACP child is `muse-agent-acp`, a small adapter
(ai-shed's `muse-acp/adapter/`) that translates ACP to Muse Session
Protocol (MSP) over `muse serve` stdio. ai-shed's `muse-agent-acp/server.mjs`
is the standalone entry other ACP clients run directly.

```text
parent (Codex / Claude Code / Cursor plugin)
  -> muse-acp MCP bridge (six tools, host policy)
  -> acpx/runtime (agent "muse", registry override)
  -> muse-agent-acp (ACP server)
  -> MSP over stdio
  -> muse serve (local Muse install, its own login)
```

The six stdio tools are `muse_acp_readiness`, `muse_acp_delegate`,
`muse_acp_status`, `muse_acp_result`, `muse_acp_steer` (fail-closed
unsupported), and `muse_acp_cancel`. The same bridge serves remote-shed
HTTP mode with only `shed_task_*`; see
[remote-shed](../skills/muse-acp-delegation/references/remote-shed.md).

## Adapter contract (ACP <-> MSP)

| ACP | MSP |
| --- | --- |
| `initialize` | `initialize` + `initialized` (schema fingerprint logged to stderr) |
| `session/new` | `session/start` with `workspaceRoot`; models from `model/list` |
| `session/prompt` | `turn/start`; `item/delta` -> `agent_message_chunk`, tool items -> `tool_call`/`tool_call_update`; resolves on `turn/completed` |
| `session/cancel` | `turn/cancel` |
| `session/close` | cancel active turn, forget the session locally (MSP has no close command) |
| `session/set_model`, config `model` | `session/setModel` |
| config `reasoning_effort` | `session/setReasoningEffort` (MSP tiers) |
| `session/request_permission` (client) | from MSP `approval/request`; decision returns as `approval/decide`; a cancelled prompt selects the deny choice (fail closed) |

MSP `userInput/request` (fixed-choice questions) is declined fail-closed via
`userInput/cancel`, matching the shared host policy. MCP servers passed on
ACP `session/new` are currently ignored with a stderr note; MSP session-config
mapping is not implemented yet. Both schemas are machine-exported
(`muse schema` renders the exact MSP bundle for the installed binary, with
a SHA-256 fingerprint the adapter logs at startup), so protocol drift is a
CI diff rather than live requalification.

## Models and reasoning effort

Muse model ids come from the host's provider-dependent MSP catalog, so
this lane hard-codes no default id:

- Omitted `model` means host default: the session's current model, with no
  `session/set_model` call. An empty catalog (for example the `echo`
  provider) is ready only under host default.
- `fallbackModels` is an ordered preference list (at most four exact ids)
  used only when `model` is omitted; an empty list means host default.
- An explicit `model` stays exact, must be advertised, is bound to the job,
  and is rechecked immediately before the prompt. Catalog drift fails the
  job with no prompt and no substitution.
- `SAARIUS_MUSE_ACP_REASONING_EFFORT` pins the ACP `reasoning_effort`
  option (default `high`; MSP tiers `none`, `minimal`, `low`, `medium`,
  `high`, `xhigh`, `max`, `ultra`; `inherit` keeps the CLI default).

## Executable and adapter knobs

The adapter spawns `MUSE_EXECUTABLE` or `muse` on `PATH` as `muse serve`.
Readiness probes `muse --version` and `muse serve --help` (must describe
an MSP session host) without sending a model turn. Optional adapter env:
`MUSE_AGENT_ACP_PROVIDER`, `MUSE_AGENT_ACP_MODEL`, and
`MUSE_AGENT_ACP_SERVE_ARGS` (JSON array of extra `muse serve` flags, for
example `["--no-session-log"]`). Provider login belongs to the local Muse
install; the bridge never starts a login or invents credentials.

## Local development

Broker source and its tests live in [saari-co/ai-shed](https://github.com/saari-co/ai-shed) under
`muse-acp/`. Develop, test, and run the opt-in live smoke there (see that
package's `package.json` scripts); this repository no longer carries the
broker. Adapter tests live in ai-shed's `muse-agent-acp/test/` and run against a
fake MSP host.

## MCP connection

Install the `ai-shed` plugin, not `saarius-skills`, to get this server; follow
[the ai-shed plugin reference](../skills/acp-delegation/references/ai-shed-plugin.md) or ai-shed's README section "Install as a
plugin". In Claude Code the server registers as `plugin:ai-shed:muse-acp` and its
tools as `mcp__plugin_ai-shed_muse-acp__<tool>`. Do not add the server to the
`saarius-skills` manifests: both plugins would register it and start two
brokers.

Installing or updating ai-shed copies source; it does not install the broker's
Node dependencies. After each install/update, prepare the persistent runtime
store from the **installed** ai-shed plugin root (`$AI_SHED_ROOT`, the harness's
plugin cache copy, not a git clone):

```bash
node "$AI_SHED_ROOT/acp-runtime/prepare.mjs" --bridge muse-acp
```

Preparation runs locked `npm ci` with lifecycle scripts disabled in a per-user,
content-addressed runtime store outside the plugin cache. The MCP launcher
reuses that store and performs no network install during MCP initialization.
`setup.mjs --check` remains a dependency/MCP health check and does not install
or send a model turn.

Reload the host or start a fresh task after repair. Verify the native
`muse_acp_readiness` call before delegating. If native tools remain absent, diagnose the
ai-shed install and reload; changing models or switching lanes does not repair
the MCP installation.

## Delegation timeout

`timeoutMs` on `muse_acp_delegate` is the wall-clock budget for that one
ACP turn: 60 minutes when omitted, up to 4 hours when explicitly requested.
It is not session duration and not `muse_acp_result` `waitMs`.
Set `SAARIUS_ACP_TIMEOUT_MS` (milliseconds, default `3600000`, integer bounds `1000..14400000`) to override the broker default timeout; invalid values fail closed at broker startup, and a per-call `timeoutMs` override wins.

## State, proof, and rollback

Job state and compact proof live under the bridge state root
(`SAARIUS_MUSE_ACP_STATE_DIR` or the per-user default), outside the mutating
workspace: `jobs/`, `runs/<jobId>/` with `STATE.md`, `events.jsonl`,
`heartbeat`, and `PROOF.md`. Removing the lane is removing the `ai-shed` plugin (or
its `muse-acp` server) and the prepared runtime; no workspace state is written by setup.

## Hop

Unset `SAARIUS_ACP_HOP_ARGV` is Local or Always-on. Set hop is Hop: the
parent launcher runs the bridge on the worker host over the configured
argv (for example SSH to CP-1), ACpx and `muse serve` stay local to the
worker, and `workspace` is worker-absolute. Prepare the runtime and Muse
login on the worker. Do not hop with `acpx --agent`.

## Remote shed

`SAARIUS_ACP_TRANSPORT=http` (or `npm run serve`) serves only the three
`shed_task_*` tools on loopback behind the operator's Cloudflare Tunnel +
Access, with the same broker contracts and no hop. Setup, env, and the
read-only session viewer are in
[remote-shed](../skills/muse-acp-delegation/references/remote-shed.md).

## Not claimed

No committed live proof receipt exists for this lane yet. This lane does not
claim an official Muse ACP server (none ships upstream), MSP
`session/resume` replay, forwarding MCP servers from ACP `session/new`, active-turn steering,
or any Parallels/VM route.
