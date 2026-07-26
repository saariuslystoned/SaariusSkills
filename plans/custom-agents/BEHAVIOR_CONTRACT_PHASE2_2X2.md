# Behavior contract: guarded 2x2 custom-subagent fan-out

Version: `2026-07-26.phase2-2x2`

## Purpose

Prove functional nested fan-out through ordinary Antigravity custom subagents,
without Teamwork Preview, Puppet, global agents/plugins, transcript inspection,
or product mutation.

Phase 1E is the admission boundary. Raw direct unknown-name selection remains
unqualified; every parent launch must use the exact-count guard.

## Campaign shape

Run two fresh parent sessions. In each round, one primary custom parent invokes
the same two custom child profiles:

```text
round A: parent -> [left child, right child] -> joined result
round B: parent -> [left child, right child] -> joined result
```

This is the issue's first `2x2` campaign: two independent parent rounds, each
with two child branches. The three definitions and hidden markers stay byte
identical across rounds; each round receives a fresh challenge and disposable
workspace.

The parent profile:

- `mainAgent: true`;
- `subagent: false`;
- tools: `invoke_subagent`, `write_to_file`;
- names both child `TypeName` values and one parent-only join path;
- contains no child marker or child result path;
- requires one `invoke_subagent` call with one two-entry `Subagents` array,
  using `Workspace: inherit`.

Each child profile:

- `mainAgent: false`;
- `subagent: true`;
- tool: `write_to_file`;
- contains only its own hidden marker and random child-only result path;
- contains neither the sibling marker/path nor the parent join path;
- writes one exact child result before returning the same bounded JSON to the
  parent.

## External oracle

Before launch, the controller:

1. verifies the parent occurs exactly once in bounded workspace discovery;
2. verifies all three profile hashes and empty results;
3. makes the join directory OS-unwritable while leaving only the two child
   result files writable.

During the run:

1. the controller observes only result size and mtime;
2. both child files must change after launch;
3. once both are non-empty, the controller quarantines the complete `.agents`
   tree and makes the workspace root read-only;
4. only then does it unlock the existing join directory;
5. the parent join must change after that release.

After exit, exact validators require:

- two child results with the correct agent, challenge, hidden marker, schema,
  and status;
- one parent join with the correct parent marker and both returned child
  markers;
- child mtimes no later than the join mtime;
- only the three result files in the workspace;
- only the three unchanged profiles in quarantine;
- no timeout, unexpected path, raw retention, or foreign-state contact.

The parent cannot forge a qualifying child artifact from its prompt or profile:
it lacks both hidden child markers and both child result paths. A child cannot
forge its sibling because it lacks the sibling marker and path. The join cannot
be created before the controller observes both child writes because its
directory is OS-locked.

## F1 — Fixture separation

Expected: three exact profile hashes; the parent contains neither child marker
nor child result path; each child contains neither sibling marker nor sibling
path; all result files are empty and the join gate is locked.

## F2 — Guarded parent discovery

Expected: each round finds exactly one parent name, admits the parent, retains
only discovery counts/digests, and starts one fresh parent process.

## F3 — Round A fan-out and join

Expected: both hidden child identities and the gated parent join pass the
external oracle in round A.

## F4 — Round B fan-out and join

Expected: the same three profile hashes pass with a fresh challenge and fresh
workspace in round B.

## F5 — Functional fan-out claim

Expected: both rounds produce two independently grounded child artifacts before
one parent join. The parent contract uses one two-entry `Subagents` array, which
the official CLI defines as concurrent subagent invocation.

The proof does not inspect a tool trace or transcript. It therefore qualifies
functional two-branch fan-out and join, while recording scheduler concurrency
and exact tool-call count as documented semantics rather than independently
observed internals.

## F6 — Teamwork independence

Expected: no `/teamwork-preview` invocation, dependency, fixture, or artifact;
PR #6 remains unchanged historical research.

## F7 — Bounded lifecycle

Expected: two parent CLI processes, four declared child branches, no timeout,
no permission prompt, no lingering exact-owned raw artifact, and no resume of
any prior or foreign conversation.

## F8 — Cleanup and promotion gate

Expected: committed machine-readable proof, exact-owned remote roots cleaned,
and no product source or external state changed.

Only a complete two-of-two pass may admit the 4x4 reliability campaign.

## Budget and safety

- parent CLI processes: at most `2`;
- declared nested child branches: at most `4`;
- total agent sessions: at most `6`;
- model invocations: at most `12`;
- per-round timeout: `180 seconds`;
- campaign wall cap: `720 seconds`;
- stop on the first failed round;
- no merge, deploy, publish, global install, auth/settings/permission change,
  customer traffic, device action, transcript/pane/log-content read, product
  mutation, or foreign process/session contact.
