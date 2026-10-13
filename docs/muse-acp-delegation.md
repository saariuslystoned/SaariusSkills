# Muse ACP delegation

SaariusSkills is the host policy for one local ACP contract. ACpx is the
local client. ACP is the wire. This lane's worker is Muse, which does
not speak ACP natively: the ACP child is `muse-agent-acp`, a small adapter
(`bridge/muse-acp/adapter/`) that translates ACP to Muse Session
Protocol (MSP) over `muse serve` stdio. `bridge/muse-agent-acp/server.mjs`
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
`userInput/cancel`, matching the shared host policy. ACP `mcpServers` on
`session/new` are currently ignored with a stderr note; MSP session-config
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

```bash
cd bridge/muse-acp
npm run setup        # install locked deps (lifecycle scripts disabled)
npm run doctor       # MCP init + six-tool check, no model turn
npm run check        # syntax + bridge tests + adapter tests
node ../acp-runtime/prepare.mjs --bridge muse-acp
```

Adapter tests live in `bridge/muse-agent-acp/test/` and run against a fake
MSP host; the bridge test suite also drives the real adapter through the
pinned acpx runtime against that fake host.

## Delegation timeout

`timeoutMs` on `muse_acp_delegate` is the wall-clock budget for that one
ACP turn: 60 minutes when omitted, up to 4 hours when explicitly requested.
It is not session duration and not `muse_acp_result` `waitMs`.

## State, proof, and rollback

Job state and compact proof live under the bridge state root
(`SAARIUS_MUSE_ACP_STATE_DIR` or the per-user default), outside the mutating
workspace: `jobs/`, `runs/<jobId>/` with `STATE.md`, `events.jsonl`,
`heartbeat`, and `PROOF.md`. Removing the lane is removing its MCP manifest
entries and prepared runtime; no workspace state is written by setup.

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
`session/resume` replay, ACP `mcpServers` forwarding, active-turn steering,
or any Parallels/VM route.
