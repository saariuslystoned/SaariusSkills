# Authority contract

## Required capability

Every live run must begin with an operator-approved capability containing:

- exact Herdr executable version and protocol;
- exact named session selector, socket path, live version, and protocol;
- exact parent workspace ID and expected display label;
- exact expected SSH target;
- run ID, harness, source repository/worktree, proof root, and allowed mode;
- an explicit statement that the parent session remains operator-owned.

Herdr 0.7.3 exposes no server PID, boot nonce, start time, or native
incarnation ID. A matching socket path does not prove the same server
incarnation. Treat disconnect, handoff, restart, or ambiguous EOF as lease
invalidation and perform complete requalification before further input.

An agent launched after SSH is not expected to appear truthfully in the local
Herdr Agents sidebar (`ogulcancelik/herdr#1170`). Do not derive remote harness
identity or liveness from that sidebar, and do not build a parallel replacement
inside this skill. Use exact structural identity plus bounded nonce-tagged
contract beacons.

The capability authorizes creation of new run-owned tabs only. It does not
authorize mutation of existing tabs, workspaces, clients, configuration, or the
parent server.

## Identity hierarchy

Join authority in this order:

```text
capability
  -> session selector + socket path + live compatibility
  -> workspace ID
  -> newly created tab ID
  -> pane ID + terminal ID
  -> foreground SSH PID + argv + target
  -> monotonically increasing send sequence
```

A label is never an authority edge. It is checked only as drift evidence after
the exact ID join succeeds.

## Fail-closed conditions

Stop before mutation when any required field is missing, duplicated, stale, or
different from the capability or lease. Also stop when:

- the requested deterministic label already exists;
- more than one pane appears in the new tab;
- the foreground process is not the expected SSH target;
- the tab or pane moved to another workspace;
- the connection dropped, handed off, or restarted, or the socket/protocol
  changed;
- a caller tries to skip or replay a send sequence;
- an operation would target the parent session or an unleased tab.

## Separate gates

Live Herdr qualification authorizes only the exact tab/pane operations in the
lease. Obtain separate authorization for unrestricted harness flags, source
delivery, deploys, sends, spending, secrets, accounts/security, deletion, or
other externally consequential actions.

Maintenance observations do not add deletion authority. A run may inventory
and classify only resources joined through its exact lease or explicitly named
by sanitized structured harness events. Labels, process names, apparent age,
and familiar paths are insufficient cleanup identity. Preserve ambiguous
resources, journal recurring residue as a maintenance candidate, and require a
separately authorized owner-specific reaper before closing panes or terminating
processes.

`maintenance-checkpoint` is the transcript-blind inventory surface. Its
classification and recommendation do not authorize the recommended action.
Report exact tab, pane, and terminal IDs beside any human-facing ordinal or
label so a display position is never mistaken for authority.

`cleanup-preserved-tab` is the bounded owner-specific close surface. It
requires separate operator authority, an initialized journal, a preserved
lease, an exact repeated tab-ID confirmation, and post-close proof that the
leased tab, pane, and foreground SSH PID are absent. PID reuse fails closed
rather than being accepted as absence. It does not close by
label, ordinal, age, focus, or search result, and it never sends a process
termination signal directly.
