# Behavior contract: external custom-agent identity oracle

Version: `2026-07-26.phase1c`

## Purpose

Qualify ordinary AGY custom-agent discovery and exact identity selection
without Teamwork Preview, a global plugin, trusted-workspace settings, raw
transcripts, pane capture, or workspace hooks.

The Phase 1 and Phase 1B failures remain authoritative for their exact heads:

- a naked workspace hook produced no events;
- a workspace observer plugin was absent from CLI plugin discovery.

This revision tests custom agents themselves. Hooks are compatibility findings,
not capability owners.

## Exact runtime

- host: `aiworker-01`, Darwin arm64
- CLI: AGY `1.1.7` at its fingerprinted worker-user path
- workspace binding: absolute `--add-dir`
- surface: headless `--print`
- prompt transport: stdin
- model: `gemini-3.6-flash-low`
- effort: `low`
- execution mode: `accept-edits`
- sandbox: enabled
- permissions bypass: forbidden
- session: fresh only; never continue or resume

Print mode redirects stdout, stderr, and the owned CLI log to exact temporary
files. The controller records only hashes and byte counts, then unlinks those
files without reading or emitting their content.

## Runtime identity oracle

Each positive session receives a fresh, controller-generated workspace and
one agent definition with:

- an unpredictable `saarius-i15-*` name;
- an unpredictable role marker;
- `tools: [write_to_file]`;
- an exact pre-created `.issue15/result.json` target;
- the requested `mainAgent` and `subagent` flags;
- no challenge value.

The prompt contains only a fresh challenge and a generic instruction to follow
the active profile. It contains no agent name, marker, schema, output path, or
expected status.

The controller starts AGY, writes the prompt to stdin, waits a bounded 350 ms
for synchronous profile loading, moves the entire `.agents` directory into an
exact controller-owned quarantine outside the workspace, and makes the
workspace root read-only. The result directory and pre-created result file
remain the only writable fixture targets.

A positive identity requires all of these:

1. filtered discovery found the exact runtime agent before launch;
2. AGY exited `0` before the external deadline;
3. the result changed after profile quarantine;
4. the result exactly matches the controller-held agent name, challenge,
   role marker, schema, and status;
5. postflight finds only `.issue15/result.json` in the workspace and only the
   exact unchanged profile in quarantine;
6. raw outputs are absent after digesting;
7. exact-owned cleanup succeeds and foreign state remains untouched.

Because the marker was unpredictable, absent from the prompt and AGY argv,
and inaccessible after quarantine, a default-agent fallback cannot satisfy
the oracle by reading the definition after launch. Any race that writes before
quarantine, any extra path, any non-zero exit, timeout, or mismatch fails.

## C1 — Fixture integrity

Build each runtime fixture create-only. Retain its safe control record and
profile SHA-256. Verify the profile hash after quarantine and enumerate every
workspace and quarantine file after the run.

Expected: exact paths and hashes only.

## C2 — Discovery

Pipe `agy --add-dir <workspace> agents` directly through the allowlist
inventory filter for the one random agent.

Expected: the exact name is found; raw catalog text is not retained.

## C3 — Four positive identities

Run fresh reconnaissance, implementation, verification, and proof profiles.
Set `subagent: false` on the proof profile to cover its primary-selection
behavior.

Expected: four of four exact identity oracles pass.

## C4 — Unknown agent

Launch a fresh random name absent from a clean disposable workspace using the
same bounded print-mode controller.

Expected: explicit launch failure or no valid result mutation. A default
response is digested and discarded; it is never identity evidence.

## C5 — Malformed definition

Create a random profile with invalid frontmatter, prove filtered discovery
does not qualify it, and attempt bounded selection only if needed to
distinguish rejection from fallback.

Expected: rejection, absence, or no valid result. A hang is a failure.

## C6 — Duplicate and rename

Use fresh no-model workspaces to probe duplicate declared names and a path
rename that leaves the declared name unchanged.

Expected: record exact filtered discovery behavior. Ambiguity cannot qualify
identity.

## C7 — Main/subagent flags

- `subagent: false`: covered by the positive proof-role primary selection.
- `mainAgent: false`: probe filtered primary discovery and bounded selection
  only if discovery alone does not establish exclusion.

Expected: subagent exclusion does not break primary selection; main-agent
exclusion prevents a qualifying primary identity.

## C8 — Removal and no bleed

After a positive run, repeat filtered discovery against its workspace after
the `.agents` directory has been quarantined.

Expected: the runtime agent is absent. No global definition, unrelated
workspace, prior conversation, or foreign process was created or touched.

## Budget and gates

Attempt 01 consumed one of eight issue-level sessions. Phase 1B consumed zero.
Phase 1C may use at most seven fresh sessions and fourteen model invocations:
four positive roles and at most one each for unknown, malformed, and
`mainAgent: false`. C6 and C8 are no-model probes.

Each process has a ninety-second print timeout and exact-child termination on
deadline. Stop on quota failure or the first unexpected write, raw-artifact
retention, cleanup ambiguity, or foreign-state contact.

No merge, deploy, publish, auth/account/settings/permission change, global
agent/plugin install, customer traffic, device mutation, or product mutation
is permitted. Phase 2 remains unadmitted until C1–C8 pass on one unchanged
fingerprint.

