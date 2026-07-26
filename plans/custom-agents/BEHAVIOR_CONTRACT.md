# Behavior contract: Antigravity custom-agent identity

Version: `2026-07-26.phase1`

## User-visible goal

An operator can place four custom-agent definitions in a disposable workspace,
discover them through the documented CLI surface, select each one in a fresh
session, and observe an identity result that only the selected profile can
produce. Unknown, malformed, disabled, renamed, duplicate, and removed profiles
must never be misreported as the requested custom agent.

## Target

- type: CLI
- executable: exact fingerprinted Antigravity CLI `agy`
- surface: workspace-local custom-agent discovery and fresh TUI selection
- fixture source: `fixtures/custom-agents/phase1/`
- runtime workspace: exact controller-created disposable directory
- credential source: existing operator session only; credentials and auth
  state are never inspected or changed

## Safety posture

- Materialize fixtures create-only into a disposable workspace.
- Never write the global custom-agent directory.
- Launch fresh conversations only.
- Enable the CLI sandbox and do not bypass permissions.
- Deny every model tool except one `write_to_file` call targeting the exact
  disposable identity-result path.
- Do not capture panes, prompts, transcripts, or raw tool arguments.
- Track and clean only the workspace, tmux socket/session, raw CLI log, and
  event files created by the current campaign.

## Tasks

### C1 — Fixture integrity

Materialize the four positive profiles and observer into an empty disposable
git workspace. Verify every materialized file against its committed SHA-256
before and after the session.

Expected: all expected files exist, no unexpected fixture file exists, and
postflight hashes match preflight.

### C2 — Discovery

Run `agy agents` from the disposable workspace and pass its output directly
through the allowlist inventory filter.

Expected: all four exact expected names are present. Raw inventory text and
unrelated agent names are neither printed nor retained.

### C3 — Exact positive identity

For each expected agent, launch one fresh TUI session with the exact
`--agent`, model, effort, and sandbox tuple. Send a random controller challenge
through a tmux stdin buffer. Do not include the expected agent name, output
schema, result path, or role marker in the prompt.

Expected:

- the workspace observer records one actor and no unapproved tool;
- the agent performs exactly one allowed result write;
- the bounded result matches the selected profile's committed agent name,
  role marker, challenge, schema, and status;
- the sanitized CLI-log probe binds the expected agent profile when the
  installed CLI exposes such metadata, otherwise that sub-clause is
  `blocked` rather than inferred;
- the session reaches an observed fully-idle stop and exact-owned teardown.

### C4 — Unknown-name fallback

Launch the same challenge protocol with a name absent from the materialized
catalog.

Expected: explicit launch failure or absence of a valid custom identity result.
A default-agent response, a response without profile evidence, or a valid-looking
result produced after an unapproved read is a failure, not a pass.

### C5 — Malformed definition

In a fresh disposable copy, replace one positive profile with a malformed
frontmatter fixture and run discovery plus selection.

Expected: the malformed profile is rejected, unavailable, or produces an
explicit invalid result. A hang reaches the external deadline and is
classified `fail`; it is never promoted to `blocked`.

### C6 — Duplicate and rename behavior

Probe duplicate `name` values in separate workspace paths, then rename one
profile path without changing its declared name.

Expected: discovery and selection behavior is explicit and repeatable. Any
ambiguous selection fails the exact-identity contract.

### C7 — Main/subagent flags

Probe one profile with `mainAgent: false` and one with `subagent: false`.

Expected: `mainAgent: false` is not selectable as the primary agent;
`subagent: false` does not invalidate primary selection but is recorded for
the later invocation contract. Any observed divergence is reported without
rewriting the expected result after the run.

### C8 — Removal and no-bleed

Remove all fixture definitions from a fresh workspace after a positive
discovery run, then repeat discovery.

Expected: all four names disappear from the workspace-scoped result. No global
definition, other workspace, or unrelated conversation was created, changed,
resumed, or cleaned.

## Anti-cheat probes

- The prompt carries only a fresh challenge and a generic instruction to
  follow the active profile's calibration contract.
- Agent names, result schema, result path, and role markers live only in the
  selected profile and controller manifest.
- A default agent cannot read the profiles because every read or shell tool is
  denied and recorded.
- The hook compares `TargetFile` in memory with the controller-owned exact
  result path without retaining its value.
- One external write sentinel permits at most one result write per session.
- Result validation uses controller-held challenge and committed role marker.
- Raw CLI logs are searched only for values exactly equal to committed agent
  names under allowlisted agent/profile keys.
- Fixture, observer, hook, and workspace postflight hashes detect tampering.
- Unknown-name and removal controls must not produce a qualifying identity.

## Evidence required

- exact source base and branch SHA;
- capability fingerprint validated against its schema;
- materialization manifest and pre/post hashes;
- allowlisted discovery summary;
- sanitized hook events with opaque actor ids;
- bounded identity-result verification summaries;
- sanitized agent-metadata probe or explicit `blocked` sub-clause;
- command names, exit codes, deadlines, and cleanup enums;
- machine-readable behavior report;
- `PROOF.md` with pass/fail/blocked/out-of-scope classification.

## Exit rule

Phase 1 passes only when C1–C8 have explicit results, all four positive
identities pass, every negative control fails closed, no unexpected tool or
write occurs, and exact cleanup succeeds. Missing agent-profile metadata keeps
the corresponding clause blocked and prevents an exact-selection claim.

Phase 2 remains unadmitted until this contract passes on one unchanged
capability fingerprint.

## Out of scope

- `/teamwork-preview`;
- nested fan-out, 2x2, or 4x4 reliability;
- product source mutation;
- global custom-agent installation;
- Puppet transport qualification;
- app-surface equivalence;
- merges, deploys, releases, sends, account changes, or device actions.
