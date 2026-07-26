# Behavior contract: CLI-plugin observer correction

Version: `2026-07-26.phase1b`

## Why this revision exists

The frozen Phase 1 attempt proved explicit-workspace agent discovery and one
exact identity artifact, but `.agents/hooks.json` produced no event file.
That attempt remains a contract violation at its exact source head; this
revision does not upgrade or reinterpret it.

This contract uses the CLI-specific plugin package shape for the observer and
new v2 agent identities. The base clauses C1–C8 in
`BEHAVIOR_CONTRACT.md` remain normative except where this file explicitly
overrides them.

## Exact fixture and workspace binding

- fixture set: `fixtures/custom-agents/phase1b/`
- custom agents:
  - `saarius-issue15-recon-v2`
  - `saarius-issue15-implementation-v2`
  - `saarius-issue15-verification-v2`
  - `saarius-issue15-proof-v2`
- observer plugin: `saarius-issue15-observer`
- plugin path:
  `.agents/plugins/saarius-issue15-observer/`
- workspace binding: absolute `--add-dir <disposable-workspace>`
- hook harness: absolute `ISSUE15_HARNESS` environment path
- global plugin, agent, settings, permission, and auth writes: forbidden

## Pre-model admission

No model session may start until all of these pass:

1. the create-only materializer reports exactly seven files;
2. every materialized hash matches the frozen source;
3. filtered `agy --add-dir <workspace> agents` output contains all four v2
   agent names;
4. filtered `agy --add-dir <workspace> plugin list` output contains the exact
   observer plugin name;
5. no prior owned result, sentinel, event, raw-log, tmux session, or socket is
   present.

Raw agent and plugin catalogs are consumed directly by allowlist filters and
are neither printed nor retained.

## C1 override — fixture integrity

C1 includes four v2 agent definitions, the observer `plugin.json`, its
`hooks.json`, and the copied harness. The workspace contains no naked
`.agents/hooks.json`.

Expected: all seven hashes match before and after execution, and no unexpected
fixture path appears.

## C2 override — discovery

Discovery always passes the absolute workspace through `--add-dir`.

Expected: all four v2 agent names and the exact observer plugin name are
present in their respective filtered summaries.

## C3 override — exact positive identity

For each expected v2 agent:

1. launch one fresh TUI with exact `--add-dir`, `--agent`, model, effort,
   sandbox, and owned raw-log path;
2. provide the observer its event, salt, sentinel, workspace, result, and
   absolute harness paths through the launch environment;
3. load the prompt into the dedicated tmux buffer through stdin with local
   terminal echo disabled, paste it, and submit it;
4. require at least one `PreInvocation`, exactly one allowed
   `write_to_file` `PreToolUse` event for the exact result target, a successful
   post-tool event, and a `Stop` event with `fully_idle: true`;
5. validate the exact bounded identity artifact against the controller-held
   challenge and committed v2 role marker;
6. postflight fixture hashes and exact-owned cleanup.

The prompt contains only the random challenge and a generic instruction to
follow the active profile. It contains no agent name, schema, result path,
role marker, plugin name, or harness path.

Any absent hook event, unexpected tool, wrong result target, second write,
missing fully-idle state, identity mismatch, permission prompt, timeout, or
unexpected workspace change is a failure. It is never inferred as a pass from
the existence of a result file.

The exact `--agent` launch value, filtered discovery, no-read hook trace, and
profile-only role marker together bind active identity. Raw CLI-log metadata
is an optional diagnostic in this revision, not a substitute for those
observables.

## C4–C8

C4–C8 retain their original meaning with the v2 fixture set. They remain
unadmitted until one v2 positive identity passes C1–C3 on this exact
fingerprint.

## Remaining budget

The issue-level Phase 1 budget began at eight sessions. Attempt 01 consumed
one. This revision may use at most:

- seven fresh model sessions;
- fourteen model invocations;
- ten minutes of wall time;
- ninety seconds per session;
- one exact result-file mutation per session.

Stop immediately on an authoritative quota failure or any bound.

## Exit rule

This revision passes only when C1–C8 have explicit results, all four v2
positive identities pass, every negative control fails closed, every raw log
and owned tmux session is clean, and foreign state remains untouched.

If the plugin is absent from filtered discovery, stop without a model call.
If the plugin is listed but emits no first-run event, close the route failed
after that one session. Phase 2 remains unadmitted.

