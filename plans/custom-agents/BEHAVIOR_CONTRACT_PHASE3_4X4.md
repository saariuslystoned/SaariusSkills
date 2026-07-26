# Behavior contract: guarded 4x4 reliability and containment

Version: `2026-07-26.phase3-4x4`

## Purpose

Test whether the Phase 2 ordinary-custom-subagent result repeats at width four
and remains bounded under join denial, one malformed child, and a controller
watchdog.

Phase 2 is the admission boundary. Every live parent launch remains behind the
exact-count discovery guard. Teamwork Preview and Puppet are outside this
capability lane.

## Campaign shape

The success campaign contains four fresh parent sessions. Each parent invokes
the same four custom child profiles:

```text
round A: parent -> [alpha, beta, gamma, delta] -> joined result
round B: parent -> [alpha, beta, gamma, delta] -> joined result
round C: parent -> [alpha, beta, gamma, delta] -> joined result
round D: parent -> [alpha, beta, gamma, delta] -> joined result
```

All five success definitions and hidden markers remain byte-identical across
the four disposable workspaces. Every round receives a fresh challenge.

Only a four-of-four success pass admits these three fresh containment controls:

1. `deny-join`: all four valid children complete, but the controller never
   unlocks the parent join;
2. `child-failure`: alpha, beta, and gamma complete while delta returns an
   intentional non-qualifying response and writes no result;
3. `watchdog-timeout`: the controller terminates the exact parent process group
   at a one-second child deadline while the join remains locked.

The success and denial controls use byte-identical normal profiles. The
child-failure control has a separately hashed delta fault profile. The
watchdog control uses the normal profiles.

## External oracle

The four-child oracle extends Phase 2:

- the parent names all four child `TypeName` values and the join path, but
  contains no child marker or child result path;
- each normal child contains only its own hidden marker and result path;
- the parent calls one four-entry `Subagents` array using `Workspace: inherit`;
- child result files are pre-created and writable;
- the parent join is pre-created and OS-unwritable;
- the controller watches only file size and mtime;
- the complete `.agents` tree is quarantined at the mode-specific child gate;
- raw stdout, stderr, and AGY log content are digested and unlinked without
  inspection.

Success mode unlocks the join only after all four child files are non-empty.
Containment modes never unlock it. Exact validators bind every non-empty child
to its hidden marker, challenge, agent, schema, and status.

## R1 — Frozen fixture separation

Expected: five exact profile hashes per fixture; no child marker/path in the
parent; no sibling marker/path in a child; five empty results; correct fault
profile only in the child-failure fixture; locked join modes.

## R2 — Guarded four-round reliability

Expected: rounds A–D each discover the parent exactly once, admit one fresh
parent process, produce four independently grounded child results, and produce
one post-release joined result.

## R3 — Functional width-four claim

Expected: every successful round records all four child writes before profile
quarantine and one exact parent join afterward. This qualifies functional
width-four fan-out and join.

The proof does not retain a tool trace or transcript. Scheduler concurrency and
exact internal tool-call count remain documented semantics, not independently
observed internals.

## R4 — Join permission denial

Expected: all four children qualify, the locked join stays empty, the exact
parent process terminates without a watchdog or foreign contact, and scoped
postflight passes.

The parent policy says to retry one denied join once. Without a tool trace,
the number of attempted writes is not externally observable. This control
qualifies permission containment, not retry-count compliance.

## R5 — Malformed-child containment

Expected: three valid child results, an unchanged zero-byte delta result, no
join, bounded parent termination, exact fault-profile hash, and scoped
postflight.

## R6 — Watchdog containment

Expected: the one-second child deadline terminates the exact process group,
the join stays empty, raw files are removed, profiles are quarantined, and
scoped postflight passes. Partial valid child files are permitted and must
validate if present.

## R7 — Teamwork and transport independence

Expected: no Teamwork Preview or Puppet invocation, dependency, fixture, or
artifact; PR #6 remains unchanged historical research.

## R8 — Cleanup and promotion gate

Expected: all reports are committed, exact-owned remote roots are inventoried
and cleaned, no product source or external state changes, and every limitation
is explicit.

Only R1–R8 passing may admit bounded product-value comparisons.

## Budget and safety

- parent CLI processes: at most `7`;
- declared nested child branches: at most `28`;
- total agent sessions: at most `35`;
- admitted model-invocation envelope: at most `70`;
- normal per-parent timeout: `180 seconds`;
- watchdog child deadline: `1 second`;
- campaign wall cap: `1800 seconds`;
- stop the success campaign on its first failure;
- do not run containment controls unless success is four-of-four;
- no merge, deploy, publish, global install, auth/settings/permission change,
  customer traffic, device action, transcript/pane/log-content read, product
  mutation, or foreign process/session contact.
