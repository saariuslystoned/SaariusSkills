---
name: antigravity-acp-delegation
description: Use the separately named antigravity-acp MCP lane to diagnose official Google Antigravity ACP setup or delegate one bounded implementation slice. Plugin default is exact advertised id gemini-3.8-flash-high. Distinct from cursor-acp and from native agy-print or Puppet qualification.
---

# Antigravity ACP delegation

Use the `antigravity-acp` MCP server to diagnose official Google Antigravity
ACP setup or delegate one bounded slice. Host the plugin in Codex or Cursor.
The same six tools are **Local** (same-machine parent and worker),
**Always-on** (same local contract on a box that stays up), or **Hop**
(parent hops stdio with `SAARIUS_ACP_HOP_ARGV`; ACpx stays a local child
on the worker). **Gateway** (was A2) stays off. Former aliases: Local was
L; Always-on was A1; Hop was B. This lane talks to Google's official
Antigravity ACP runtime through pinned `acpx@0.19.1`. It is not the Cursor
ACP lane, not native `agy --print`, and not a Puppet transport. Published
install is the plugin, not `~/.cursor/mcp.json`. A cloud Cursor Project
chat cannot call `antigravity_acp_*`.

## Discovery and setup

Tool names may have a plugin/server prefix. Search the available/deferred tool
catalog for `antigravity_acp_readiness` before concluding the route is
unavailable; a short initial tool list is not proof.

If no callable Antigravity ACP tool is found, diagnose setup. From this
installed skill's directory, the package check is:

```bash
node ../../bridge/antigravity-acp/scripts/setup.mjs --check
```

Resolve that relative path against this SKILL.md, not the task's workspace.
`DEPENDENCIES_MISSING` includes an exact repair command. When local setup is
authorized, run that command with `--install`; it installs locked Node
dependencies with lifecycle scripts disabled and verifies MCP initialization
and all six tools. It does not download, install, or update the official
`antigravity-acp` 1.1.1 runtime/helper, open a login, or send a model turn.

The pinned runtime is `antigravity-acp` 1.1.1 at registry revision
`81bf71b55e15f630c4fb8a86d20d3088071d2071`, launched through `acpx` 0.19.1
(published npm integrity, tarball hash, `runtime.js` hash, and
`agent-registry.js` hash; `acpxSourceCommit` is null because that release has
no gitHead; `50a47ad` is only `lastInspectedSourceCommit` for the 0.17.1 watch
identity; OpenClaw main `482a4b2` depending on this package is not a live
qualification). Setup reports the exact platform
archive, helper name, and `GEMINI_HOME` personal-OAuth repair actions. Do not
silently install those binaries.

After repair, reload the Codex app or start a fresh task so its native tool
inventory is rebuilt. `MCP_READY` proves server startup, not that the current
task has reloaded it. If still unavailable, report `MCP_UNAVAILABLE` with the
setup result and the specific reload/registration action needed. Do not replace
this route with Cursor ACP, Puppet, native `agy-print`, Herdr, or tmux unless
the user explicitly authorizes that alternative.

## Operating contract

- Start with `antigravity_acp_readiness` for the exact workspace when the route
  has not been checked in the current task. Require the official
  `antigravity-acp` runtime/helper pin, an explicit `GEMINI_HOME` personal
  OAuth profile, and advertised model discovery. Readiness selects the plugin
  default exact id `gemini-3.8-flash-high` when advertised; it does not treat
  runtime `currentModelId` as the wished default. Never silently fall back to
  `agy --print`, generic `acp`, an API key, a Cloud project, an alternate
  account, paid credits, or overage. `antigravity_acp_delegate` hard-refuses
  when that readiness is red (runtime / auth / model / workspace). Do not treat
  a red readiness report as advice and submit anyway.
- Use `antigravity_acp_delegate` with one absolute workspace path, one parent
  conversation id (`hostConversationId` or `SAARIUS_ACP_HOST_CONVERSATION_ID`),
  one bounded prompt, and a bounded timeout. One parent conversation owns one
  worker. Rebind is owner-gated (`binderId` / `SAARIUS_ACP_BINDER_ID`); cwd is
  not exclusive. Omit `model` to use the plugin default exact
  id `gemini-3.8-flash-high` when that id is advertised. That default ships in
  the plugin contract (skill, broker, readiness). Do not take it from
  `GEMINI_HOME`, `settings.json`, a machine MCP env, or readiness
  `currentModelId`. If `gemini-3.8-flash-high` is not advertised, pass an exact
  advertised model id; do not silently use `gemini-3.7-flash-high` or any other
  current id as the wished default. Do not infer ACP effort from a label;
  effort selection is unsupported until proved. Prefer an isolated worktree
  for source mutations.
- Save the returned job ID. Use `antigravity_acp_status` for progress and
  `antigravity_acp_result` with a bounded wait for the canonical outcome. A
  submitted job, process exit, or progress event is not task success.
- Treat task outcome and cleanup readiness as separate facts. A terminal
  `status` means the task itself ended; `complete` and `cleanupReady` become
  true only after the runtime cleanup is observed complete. If cleanup is
  `pending` or `uncertain`, do not delegate a replacement in that same
  workspace. The bridge returns `WORKSPACE_CLEANUP_PENDING` with bounded job,
  workspace, owner, and cleanup identity; wait for observed cleanup or the
  owner-specific recovery path. Independent workspaces remain admissible.
  Conversation admission persists the job, including exact broker ownership,
  before the binding is published. Only confirmed unstarted or released
  admissions may be replaced by the same owner; once worker startup is
  attempted, the admission stays fenced until cleanup is explicitly proven.
  Live or unobservable workers stay fenced. Do not retry or delete uncertain
  ownership.
- `antigravity_acp_steer` fails closed with `STEERING_UNSUPPORTED`. Wait for
  the canonical terminal result, then explicitly delegate a bounded follow-up.
  Use `antigravity_acp_cancel` when the parent decision changes. A missing
  active session is fail-closed, not a reason to create a replacement session.
- Treat `completed`, `failed`, `cancelled`, and `needs-input` as distinct
  outcomes. The live MCP default is `approve-reads` plus fail on a write or
  exec that would prompt. It does not grant one-path `allow_once`.
  `SAARIUS_ACP_PERMISSION_MODE=approve-all` is an explicit break-glass, not the
  everyday default. The candidate Puppet controller one-path contract stays
  separate. Fixed-choice `interaction_*` questions and elicitation still fail
  closed as `needs-input` or `cancelled`; never auto-answer them. Escalate
  `needs-input` to the user with the bounded reason; do not invent a login
  flow, entitlement proof, or hidden approval.
- Do not claim Google AI Ultra quota attribution from this route. Missing
  login or overage-disabled proof is a setup/input result, not a reason to
  switch accounts or enable billing.
- Review changed files, tests, and proof independently. Keep the worker
  handoff compact. Do not request or expose thought streams, raw ACP
  transcripts, credential stores, auth logs, `.env` files, or tokens.
- Optional host hop (`SAARIUS_ACP_HOP_ARGV` JSON argv on the parent
  launcher) is Hop: same six tools; ACpx stays a local child on the worker;
  `workspace` is worker-absolute. Do not hop with `acpx --agent`. Do not
  treat hop-process exit as remote worker death. Prepare, official 1.1.1,
  and personal OAuth stay on the worker. Hop is proven on the MacBook → CP-1
  path; receipt `proof/b-live-dogfood/RECEIPT.md` (see repo root). A later
  hopped delegate still needs an isolated worktree,
  one intended path, and a stated budget.

## Scope boundary

Unset hop is Local or Always-on. Set hop is Hop (host-owned SSH/container
argv). This lane does not qualify Puppet's Antigravity transport, replace
native `agy-print`, open Gateway (was A2), implement issues #35/#37/#38
wholesale, or authorize deployment, publication, external sends, spending,
account/security changes, or destructive cleanup. It does not claim
Google AI Ultra, Parallels, `acpx --agent ssh`, or that a cloud Project
chat can call `antigravity_acp_*`.
