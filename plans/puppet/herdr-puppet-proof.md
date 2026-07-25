# Herdr-Puppet Discovery Proof

Observed: 2026-07-23

## Goal

Determine whether a controller can steer AGY processes on a remote worker while
the same native AGY TUIs remain human-visible in uniquely labeled Herdr tabs,
without tmux.

## Result

Pass for the transport primitive and three-pane concurrent dispatch.

This is not Puppet qualification. It used a pre-existing operator Herdr
session, ordinary Herdr pane delivery, and bounded pane reads for exact-token
validation.

## Observed Topology

```text
operator Herdr session
└── remote-worker workspace
    ├── tab/pane: agy-proof-1
    ├── tab/pane: agy-proof-2
    └── tab/pane: agy-proof-3
```

Each pane's foreground controller-side process was an independent SSH client
targeting the same remote worker. The worker reported exactly three distinct
AGY processes. The remote tmux inventory reported no tmux server.

## Concurrent Dispatch

Three Herdr pane sends were issued concurrently before waiting for responses:

| Tab | Expected token | Observed token |
| --- | --- | --- |
| `agy-proof-1` | `AGY_CONCURRENCY_ONE_20260723` | exact match |
| `agy-proof-2` | `AGY_CONCURRENCY_TWO_20260723` | exact match |
| `agy-proof-3` | `AGY_CONCURRENCY_THREE_20260723` | exact match |

After all responses, the same three remote AGY process identities remained and
no tmux server appeared.

## Earlier 1×1 Anti-Cheat Probe

The original pane returned two different exact tokens to two different prompts:

- `HERDR_PUPPET_PROOF_20260723`
- `HERDR_PUPPET_VARIATION_20260723`

This ruled out a single static or cached response.

## Passed Clauses

- Herdr displayed a live AGY TUI reached over SSH.
- The controller delivered input to the exact Herdr pane.
- Matching AGY output appeared in the same pane.
- Three uniquely labeled tabs hosted three distinct AGY processes.
- Three prompts were dispatched concurrently and returned matching outputs.
- The remote AGY process count remained exactly three.
- No tmux server participated.
- The Herdr server remained running throughout the proof.

## Blocked or Unproved Clauses

- Herdr client detach and reattach was not exercised.
- Herdr server crash recovery was not exercised.
- The parent operator-session lifecycle was not independently qualified for
  reuse by a controller.
- No Puppet lease, controller ledger, structured checkpoint, or acceptance
  receipt governed this discovery proof.
- Bounded pane reads are valid for this explicit behavior probe but
  incompatible with Puppet's ordinary transcript-blind runtime contract.

## Public Boundary

Account identifiers, machine paths, network addresses, process IDs, and
unrelated terminal content are omitted. No credentials, auth stores,
environment files, browser sessions, tokens, or private keys were inspected.
