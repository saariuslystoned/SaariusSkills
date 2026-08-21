# Herdr-Puppet beside Crabbox

Status: operator composition decision recorded 2026-08-21. This file is a
path-forward note, not a qualification receipt. It does not claim live Crabbox
composition, doorbell composition, or a Herdr 0.8.2 doctor pass. Those remain
unproved in this repository.

## They are not substitutes

Keep three jobs separate:

| Job | Owner | What it is for |
|---|---|---|
| Exact Herdr transport | this skill | A newly created tab, exact tab/pane/terminal/SSH identity, a sequence-checked lease, a transcript-blind journal, and a human-visible native TUI |
| Remote execute | [Crabbox](https://github.com/openclaw/crabbox) | Select or lease a box, optionally sync a tree, run a command, keep a receipt, and release |
| Lifecycle and acceptance | Puppet | Plans, checkpoints, review, accept, and halt. YOLO-only. Do not install that skill into a deny-by-default sandbox |

A doorbell that already speaks native `herdr agent start` / `herdr agent prompt`
is a fourth job. It opens or continues the caller's Herdr session. It must not
become a Herdr-Puppet client, and Herdr-Puppet must not become that doorbell.

Crabbox will not grow exact Herdr leases, pane identity, or transcript-blind
journals. That is not a gap in Crabbox; it is a different product. Herdr-Puppet
will not grow "run this suite on that box and release it." Stay on upstream
Crabbox for execute. Mold Herdr-Puppet for transport.

Cross-machine reach is not the difference. In a swarmherdr session the sidebar
**fleet spaces are machines**. A new tab in `spark-2` or `aiworker-01` is an
SSH PTY to that box. After the 0.8.2 repair and qualification, an agent already
sitting in the `cp-1` space can use this skill to create those tabs and launch
harnesses across the fleet. Crabbox can reach the same boxes. So can a pane
that is already open on that space and then given native `herdr agent start`.
The products are not competing for "can I touch spark-2." They attach to
different surfaces on that box.

The sidebar also mixes in **worktree spaces** (a repo parent and its nested
job rows). Those are directories on one machine, not themselves machines. A
doorbell that speaks native `herdr agent` usually starts the coding agent in
one of those worktree rows. New tabs there are not fleet tabs; this skill's
destination catalog is the machine-space path.

```text
same swarmherdr session
├── fleet spaces = machines (cp-1, spark-1, spark-2, aiworkers, …)
│     herdr-puppet: new owned tab + remote harness TUI
│     crabbox:     no Herdr tab; command + receipt + release
│     herdr agent: only if a pane on that space already exists
└── worktree spaces = checkouts on one of those machines
      herdr agent start / prompt: the doorbell's native 0.8.2 path
      herdr-puppet: do not treat these as destination machines
      crabbox: optional later, from that agent, still not a tab
```

## Why keep Herdr-Puppet

- Operator-visible panes: the human watches the same TUI the controller leased.
- Exact identity: labels are presentation; mutation requires a lease.
- Transcript-blind ordinary status: no pane scrape as the learning path.
- Moldable for this swarm's Herdr host, without forking Peter's execute plane.

The current doctor still binds Herdr 0.7.3. Live Herdr on the operator host is
0.8.2. That version gap is a repair for this skill, not a reason to replace it
with Crabbox or to teach a doorbell to speak Herdr-Puppet.

## Path forward

Compose on the Herdr host, after a native `herdr agent` is already in the
caller's session:

```text
operator / doorbell
        |
        | native herdr agent start / agent prompt (0.8.2)
        | in a worktree space (usually on the session host)
        v
caller's Herdr session + worktree + coding agent
        |
        +-- herdr-puppet: new tab in a fleet space / other machine
        |                 + leased remote harness the human can watch
        |
        +-- crabbox:      same machine names, no Herdr tab
                          run a command, keep a receipt, release
```

Repair and qualify this skill in that order:

1. Align `doctor` and identity joins with live Herdr 0.8.2. Do not leave 0.7.3
   as the supported surface while the host has moved on.
2. Re-run the five-row qualification on a 0.8.2-bound head. The last public
   bundle (`8ee87d8ed9882043762ca1877e54cb844072d685`) is AGY/Grok PASS, Cursor
   login-blocked, Claude/Codex FAIL. Those outcomes are not a universal pass and
   are not 0.8.2 proof.
3. Keep YOLO Puppet out of OpenShell and other deny-by-default sandboxes.
   Herdr-Puppet and Crabbox stay host-side skills on the machine that already
   owns Herdr and the execute CLI.
4. Do not merge Herdr-Puppet into Puppet until the Phase 5 gates in
   [`herdr-puppet.md`](herdr-puppet.md) pass.
5. Do not add Crabbox commands to this skill. A later operator note may record
   a composed run; this repository must not claim that run until linked evidence
   exists.

## Non-goals

- Do not pick Crabbox *or* Herdr-Puppet.
- Do not teach a Discord or OpenShell agent to speak Herdr-Puppet.
- Do not put Herdr-Puppet or Crabbox inside the OpenShell sandbox.
- Do not treat Crabbox static SSH as Herdr transport.
- Do not hide tmux inside a Herdr tab and call it this skill.
