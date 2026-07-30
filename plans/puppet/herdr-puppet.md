# Herdr-Puppet Plan

Status: historical discovery plan; implementation now proceeds in PR #9.

The current transport product boundary and qualification thresholds are
normative in [`dual-transport.md`](dual-transport.md). Where this discovery
plan predicts implementation behavior, lifecycle gates, or a one-harness
acceptance threshold differently, the dual-transport plan and the current
Herdr-Puppet skill contracts take precedence.

## Decision

Build `herdr-puppet` first as a separate experimental skill. Do not add it
directly to Puppet's qualified runtime surface.

The skill should remain narrow:

- Puppet owns plans, leases, target admission, checkpoints, review, acceptance,
  and exact halt authority.
- Herdr-Puppet owns Herdr session/workspace/tab/pane projection and its
  structural transport evidence.
- The target harness runs on a remote worker reached through one SSH PTY per
  Herdr pane.
- The human watches the target harness's native TUI in Herdr.

After Herdr-Puppet qualifies independently, Puppet may extract a transport
interface and admit both `tmux` and `herdr` backends. Herdr-Puppet must not
duplicate Puppet's controller, qualification ledger, or acceptance logic.

## Why It Starts Separately

Puppet PR
[`#5`](https://github.com/saariuslystoned/SaariusSkills/pull/5) is intentionally
and deeply bound to:

- private tmux sockets and server identity;
- tmux pane and process identity;
- tmux prompt delivery;
- read-only tmux viewers;
- preserved tmux terminal evidence.

Its current contract also forbids controller terminal reads and reuse of
pre-existing target sessions.

The Herdr discovery proof deliberately used an existing operator Herdr session
and bounded pane reads to validate exact response tokens. That is strong
transport discovery, but it is not Puppet qualification. A separate skill
avoids weakening Puppet's tmux baseline while Herdr ownership, provenance,
persistence, and recovery are hardened.

## Proven Primitive

The 2026-07-23 live proof showed that Herdr 0.7.3 can:

1. host a remote macOS worker through SSH;
2. host three uniquely labeled AGY tabs;
3. maintain one AGY 1.1.5 process per tab;
4. accept three controller prompts dispatched concurrently through the Herdr
   pane API;
5. display three exact responses in their corresponding human-visible tabs;
6. operate with no tmux server on the remote worker.

See [`herdr-puppet-proof.md`](herdr-puppet-proof.md) and
[`herdr-puppet-behavior-report.json`](herdr-puppet-behavior-report.json).

The proof does not yet establish:

- safe Herdr client detach and reattach;
- recovery after a Herdr server crash;
- fail-closed operation after tab, pane, SSH, TTY, or remote-process drift;
- Puppet-compatible transcript-blind ordinary operation;
- authority to reuse an arbitrary operator-owned Herdr session.

## Target Architecture

```text
Puppet controller
        |
        | plan, lease, policy, checkpoints, review, acceptance
        v
Herdr-Puppet
        |
        | exact session + workspace + owned tab/pane handles
        v
Herdr server
        |
        | one SSH PTY per owned pane
        v
remote worker
        |
        | one harness process per PTY
        v
AGY or another qualified harness

Human Herdr client -------- native live view of the same owned panes
```

Herdr replaces tmux as the terminal substrate for this transport. Do not hide a
tmux attach inside a Herdr tab and call it a Herdr transport.

## Ownership Contract

Never infer authority from labels such as `agy` or a workspace's display name.
Every mutation must join to a Herdr-Puppet-created lease containing:

- Herdr executable path, version, protocol, and file identity;
- Herdr session name, socket incarnation, and server process birth identity;
- parent workspace ID and expected remote-host binding;
- owned tab ID, pane ID, terminal ID, and deterministic label;
- local SSH PID, birth identity, executable identity, argv, and target;
- remote host identity, account identity, TTY, harness PID, process birth
  identity, and executable fingerprint;
- Puppet run ID, harness target, repository/worktree, proof root, and allowed
  mode;
- monotonically increasing command sequence and per-message nonce.

The parent Herdr session remains operator-owned. Herdr-Puppet receives only an
explicit capability for one session and one workspace. It may mutate or close
only tabs and panes named in its own lease. It must never stop, repair, replace,
or reconfigure the parent Herdr session.

Labels are presentation, not identity. Use a deterministic form such as:

```text
puppet-agy-<run-short>-<ordinal>
```

## Transcript Boundary

Ordinary operation must remain Puppet-compatible and transcript-blind:

- `launch` and `send` may deliver bytes to an exact owned pane.
- `status` may inspect structural Herdr, SSH, TTY, and process metadata.
- `wait` must use structured checkpoints or process state, not terminal text.
- controller proof must not persist prompts, terminal output, account
  identifiers, or scrollback.
- the human may view the native harness TUI directly in Herdr.

Qualification may expose one separate `qualification-token-probe` operation.
It may read a small bounded pane window only to match a generated nonce, must
redact unrelated text, and must never be available in ordinary operation.

## Initial Command Surface

Use deterministic scripts rather than hand-composed Herdr calls:

```text
doctor
plan
launch
send
status
wait
view
halt
recover
qualification-token-probe
```

All commands emit strict JSON.

- `plan` is non-mutating.
- `doctor` verifies exact Herdr, SSH, and harness capabilities.
- `launch` creates only new, owned tabs.
- `halt` targets only exact owned remote processes and panes.
- `halt` preserves proof and never stops the parent Herdr server.

## Concurrency Contract

Start with a hard maximum of three harness panes per admitted run.

- Serialize writes within one pane.
- Permit dispatch across distinct owned panes concurrently.
- Bind every send to `(run_id, tab_id, pane_id, seq, nonce)`.
- Reject duplicate, stale, skipped, or replayed sequence numbers.
- Admit one mutation owner per source slice even when three harness panes exist.
- Treat multiple panes as execution capacity, not authority for conflicting
  concurrent writes.
- Preserve Puppet's aggregate helper and target-side mutation limits.

The first concurrency receipt must prove:

- exactly three owned tabs;
- exactly three local SSH foreground processes;
- exactly three remote harness processes with distinct PIDs and TTYs;
- three distinct prompts dispatched before waiting for any response;
- three exact nonce responses in the matching panes;
- no fourth harness process and no tmux server;
- all original process identities remain after the responses.

## Persistence Semantics

Claim only client-detach persistence:

- disconnecting a Herdr client must leave the Herdr server, panes, SSH
  processes, and remote harnesses running;
- reconnecting to the exact session must show the same tab/pane identities and
  live TUIs.

Do not claim crash persistence. A Herdr server crash can terminate its PTYs,
SSH processes, and remote harnesses. `recover` must reconcile exact identities
and either re-adopt still-live owned processes with proof or fail closed. It
must never silently relaunch or attach to label-matched replacements.

## Implementation Phases

### Phase 0 — Admission Preconditions

1. Verify one exact supported Herdr version and protocol.
2. Verify the parent session is healthy and unambiguous.
3. Verify the requested workspace resolves to the expected remote host.
4. Verify no existing tab or process is being repurposed.

Stop on any lifecycle fence or ambiguous identity.

### Phase 1 — Create the Experimental Skill

Initialize:

```text
skills/herdr-puppet/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── authority-contract.md
│   ├── transport-schema.md
│   └── qualification-contract.md
└── scripts/
    ├── herdr_puppet.py
    └── herdr_puppet_lib/
```

Keep `SKILL.md` concise, put schemas in `references/`, and implement fragile
identity and lifecycle operations in deterministic scripts.

The first implementation slice should ship only `doctor`, `plan`, structural
`status`, schemas, and test fixtures. Keep live `launch`, `send`, and `halt`
disabled until the parent-session capability and identity joins pass
adversarial tests.

### Phase 2 — Static and Adversarial Tests

Cover:

- wrong Herdr version or protocol;
- wrong session, workspace, tab, pane, terminal, SSH target, or remote host;
- duplicate labels with different identities;
- pane replacement and PID reuse;
- stale socket incarnation;
- out-of-band tab rename, move, close, or SSH replacement;
- sequence replay and cross-pane nonce substitution;
- malformed or oversized JSON;
- transcript-shaped fields in ordinary-mode proof;
- attempts to stop the parent Herdr session;
- attempts to adopt a pre-existing tab or harness process.

### Phase 3 — Live 1×1 Qualification

1. Create one owned tab in an explicitly authorized workspace.
2. Prove native harness display, structural identity, one prompt, one
   checkpoint, human visibility, targeted halt, and preserved proof.
3. Prove client detach and reattach without process replacement.
4. Prove ordinary `status` and `wait` never read pane text.

### Phase 4 — Live 3×1 Concurrency Qualification

Repeat the discovery proof through the Herdr-Puppet CLI with dispatch
timestamps, per-pane nonces, PID/TTY joins, a negative fourth-process check, and
no-tmux proof.

### Phase 5 — Puppet Integration

Only after Phases 0–4 pass:

1. Extract a transport interface from Puppet's tmux-bound session core.
2. Keep tmux as the qualified portable default.
3. Add Herdr as an independently qualified optional transport.
4. Version terminal-evidence schemas; never reinterpret old tmux receipts.
5. Preserve Puppet's transcript-blind controller boundary.
6. Require exact transport qualification in every adapter manifest and lease.

Do not add Herdr branches inside a class named or modeled as
`TmuxController`. The transport distinction must remain explicit in state,
receipts, recovery, and promotion.

## Acceptance Gates

Herdr-Puppet is ready to propose for Puppet integration only when:

- exact version, protocol, socket, and server identity are bound;
- the parent-session capability is explicit and narrow;
- ordinary mode is transcript-blind;
- 1×1 launch/send/status/wait/halt/recover passes;
- client detach and reattach preserves exact identities;
- three-pane concurrent dispatch passes twice with fresh runs;
- wrong-target and out-of-band mutation probes fail closed;
- no tmux process or socket participates in the Herdr transport;
- cleanup targets only owned tabs and processes;
- proof is redacted, durable, and joined to an exact skill commit;
- independent review approves the exact head.

## Relationship to Puppet Teamwork

Puppet PR
[`#6`](https://github.com/saariuslystoned/SaariusSkills/pull/6) plans
hierarchical Antigravity teamwork inside a harness. Herdr-Puppet solves a
different layer:

- Herdr-Puppet concurrency: multiple top-level, human-visible harnesses.
- Teamwork concurrency: leaders and subagents inside one harness.

Keep their budgets and mutation ownership separate. A combined campaign must
cap the product of top-level panes and per-harness helpers rather than assuming
both limits can be independently maximized.

## First Implementation Slice

Open a separate implementation PR after this plan lands:

1. initialize `skills/herdr-puppet/` with the packaged skill creator;
2. implement only read-only discovery and source-only planning;
3. define versioned authority, lease, and proof schemas;
4. add fixtures and adversarial unit tests;
5. leave all live mutations disabled.

That slice should establish the authority boundary before adding the exciting
part.
