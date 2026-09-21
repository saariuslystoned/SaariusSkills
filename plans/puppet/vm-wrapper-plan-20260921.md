# Host-owned VM ACP wrapper lane — 2026-09-21

Status: bounded research and decision packet. No VM, ACP provider, credential,
desktop, account, upstream, or Puppet transport mutation was performed here.

## Decision

Place the first VM lane after the relevant local ACP/controller foundations and
before any optional computer-use composition:

```text
local ACP dogfood + controller lifecycle proof
        -> prepared guest/auth/transport readiness
        -> one host-owned wrapper + one guest ACP coding task
        -> independent patch/test/remote-cleanup proof
        -> one repeat run
        -> optional visual desktop proof
```

The smallest useful first proof is one prepared Parallels guest, one ACP-capable
harness, and one small non-secret fixture. It may use a direct host wrapper
around `acpx`; it does not need a newly promoted Puppet transport or a new
upstream launcher API. Formal Puppet qualification remains a separate claim.

## Evidence boundary and current ownership

The existing Parallels task is `01a0c06b-de79-7a03-887b-a1ec04887911`,
“Prove one coding agent inside a Parallels…”, in
`/Users/bobbybones/.codex/worktrees/dc52/x-api`, branch
`codex/cursor-guest-broker-20260920`. Its accepted run is
`runs/parallels-coding-agent-proof-runs/20260920T200509Z-4717/`.

Observed, non-secret receipt:

- Host `aiworker-01`; prepared VM `aiworker-01-macos-clean-base`, UUID
  `{b98e38c2-2d06-403c-872f-6315bc68b461}`.
- Guest `parallels-01@10.211.55.3`, hostname
  `aiworker-01-macos-clean-base.shared`, macOS `26.5.2`, arm64.
- VM start, host-to-guest transport, SSH identity, and no task-owned guest
  processes at closeout were observed.
- Standard guest PATH lacked `acpx` and every checked coding harness. Explicit
  Node/npm existed at `/usr/local/bin`, but no ACP session, model activity,
  coding artifact, test result, or cancellation proof was claimed.
- The latest owner handoff is waiting at the supported-auth boundary: an
  owner-present unlock of the existing guest login keychain and parent-owned,
  value-free CP-1 bootstrap verification. This is not a successful guest ACP
  receipt. No token, auth file, browser store, or vault value was inspected.

The authoritative receipts are the owner's `STATE.md`, `PROOF.md`,
`RESULT.md`, `events.jsonl`, `heartbeat`, `guest-readiness.txt`, and
`transport.txt`. Historical recipe notes remain design input, not fresh
permission or proof. Do not resume, duplicate, or supersede that owner.

The current SaariusSkills main is `49a4640`, the PR #61 merge. PR #63 remains
the active Antigravity proof lane, PR #64 is a reviewed Cursor candidate at
`84a6dad`, and PR #62 is historical candidate evidence. The parent run records
one accepted native AGY 3.8 useful implementation, not formal Puppet
qualification, sustained reliability, VM qualification, or quota attribution.
The current Puppet candidate pin `acpx2e05de52` through upstream #689 remains
frozen; this plan does not change it.

## Ownership map

| Boundary | Owns | Does not prove or own |
| --- | --- | --- |
| Puppet/controller | task identity, admission, budget, candidate/worktree identity, evidence schema, independent verdict, replacement fencing, and final acceptance | remote process death merely because a local command exited |
| ACPX | local ACP child, stdio/protocol connection, session identity, prompt queue, reconnect/load, cancel/close, and its documented local cleanup | SSH/container transport, guest workspace mapping, remote supervision, or a VM lifecycle |
| Host wrapper | exact wrapper/session identity, SSH or container command, remote cwd mapping, guest launch identity, reconnect/query/termination, and host-side artifact transfer | generic ACP protocol semantics or Puppet acceptance |
| VM/Crabbox/Parallels host | VM/provider/lease identity, guest boundary, VM start/stop policy, SSH route, host-owned remote cleanup, and desktop attachment when supported | model judgement, patch acceptance, or guest app semantics |
| Independent verifier | clean-root diff/test checks, artifact integrity, and later visual/state assertion | the implementing agent's self-report as sole proof |

This follows Peter Steinberger's decision on [acpx #637](https://github.com/openclaw/acpx/issues/637#issuecomment-5751590763):
`acpx` keeps its local child and ACP session lifecycle; SSH/container wrappers
are custom agent commands and the wrapper forms session identity; hosts own
remote termination and workspace mapping. The same decision declines a public
launcher callback, separate remote-cwd convention, and remote-supervision
guarantee. A wrapper implementation therefore does not require another
upstream approval, and this plan does not revive the rejected launcher API.

## Admission order

### 1. Finish only the relevant local foundation

Before a VM run, close the local route's current controller correctness and
lifecycle gates, use native AGY for AGY hardening and Cursor for Cursor
hardening, and make a deliberate exact-pin adoption decision. A useful local
ACP task plus independent cleanup evidence is enough to begin preparing one
VM; do not wait for every future harness, desktop provider, or formal Puppet
transport rung.

Admission requires:

1. exact source/runtime/provider identities and a clean owner worktree;
2. real useful coding work, not ACK/readiness-only evidence;
3. controller-observed completion, failure, and owned cleanup; and
4. no unresolved route-identity or cleanup finding that the guest proof would
   merely hide.

The upstream main at `c1bdc53901e444d6d5ef094a0b91637fe1960b75` is the merged
#692 flow-artifact fix. Parent adjudication says it is not used by the current
`createAcpRuntime`/`memorySessionStore` candidate and is not a reason to churn
the frozen pin.

### 2. Prepare one guest without claiming a run

The existing VM owner should establish, through supported owner-approved
setup, the exact guest Node runtime, pinned `acpx`, one harness, advertised
model/config identity, and supported authentication readiness. The readiness
receipt must be value-free and record:

- host, provider/VM UUID, guest hostname/user, and remote workspace root;
- resolved wrapper command identity and exact `acpx`/harness versions;
- whether authentication is already usable inside the guest; and
- whether the host can reconnect and inspect the task-owned remote identity.

The guest keychain and broker boundary remain human/owner-gated. One-time
setup may prepare a later process-local or guest-local broker path, but no host
auth-file copy, token-in-argv, token-in-persistent-state, browser-store read,
or repeated authorization bypass is part of this plan. Subscription access and
transport compatibility do not establish AI Ultra/model entitlement.

### 3. Run one bounded guest ACP task

Use one small non-secret fixture and one harness. The wrapper starts the guest
ACP server through the existing `acpx --agent <resolved-wrapper-command>`
composition, records the exact task/run/session/workspace identities, and
returns a patch plus independent test evidence. Keep installation/setup time
separate from model activity. Do not add fan-out, a second harness, a new
framework, or visual interaction to this first proof.

The first pass must show:

- ACP initialize and `session/new` (or supported load/resume) reached the
  intended guest workspace;
- the agent made the expected small edit and tests pass independently;
- the returned patch/artifacts bind to the same task, guest, wrapper, and
  workspace identities; and
- the host independently established remote worker termination before clearing
  ownership.

### 4. Repeat once, then consider visuals

Repeat the same prepared-guest recipe with a distinct run identity and prove
that no undocumented interactive setup was required. A second run is the
minimum evidence for repeatability; it is not a universal reliability claim.
Only after the coding/cleanup path is stable should the existing Crabbox,
Parallels desktop, AGY computer-use, or Cua surfaces be composed for an
observe -> bounded action -> fresh observation -> independent assertion proof.
Computer-use is a later extension, not a prerequisite for the first ACP-in-VM
proof.

## Proposed first proof contract

Use four identities and keep them separate:

1. `puppet_run`: controller task/admission ID, candidate SHA/tree, budget,
   local proof root, and final verdict.
2. `acpx_session`: exact resolved custom-agent command string, ACP record/session
   ID, local `cwd`, and local child observations. The command string is part of
   the acpx scope key, so a wrapper must remain stable for resume.
3. `remote_execution`: provider/VM or container identity, guest hostname/user,
   remote workspace path, wrapper launch ID, and a remote process identity
   (PID plus birth identity where available, or an equivalent host-supervised
   identity). This is host-owned, not inferred from an ACP session ID.
4. `artifacts`: patch/diff, test output, structured ACP completion, sanitized
   wrapper/remote cleanup receipt, and any later screenshots. Each artifact
   names its producing identity and is checked by the controller/verifier.

The wrapper should expose only a narrow, value-free result shape. It may
translate local task input into the remote command, set the remote cwd, and
stream ACP stdio. It must not turn local `cwd` into an unverified remote path,
or claim that wrapper exit equals remote worker exit.

Required failure behavior:

| Event | Required result |
| --- | --- |
| SSH disconnect during a live turn | Mark transport uncertain; retain the task/lease fence. Reconnect to the exact VM and remote identity before resuming or cleaning. Never start a replacement from a stale local PID. |
| Reconnect succeeds | Query the same wrapper/remote identity, reconcile ACP session state, and either resume/load the same session or close it. A new session is not a transparent recovery. |
| Reconnect fails | Return `remote_cleanup_unknown`, preserve artifacts and ownership, and require an owner decision. Do not report success or auto-admit replacement work. |
| Cancel or timeout | Ask ACPX to cancel/close its local session, then invoke the wrapper/host's remote termination path and independently query the remote identity. Preserve the primary error if cleanup also fails. |
| Wrapper exits first | Treat only the local wrapper as exited. Verify the guest process/session separately; if unknown, retain the fence. |
| Remote worker exits first | Record remote exit and then settle local ACPX cleanup. Do not infer patch correctness from process exit. |
| Artifact transfer fails | Keep the run incomplete; retain the remote lease/fence until artifacts or a bounded failure receipt are recovered. |

This contract deliberately relies on existing primitives: ACPX custom-agent
commands, session/load or reconnect, `--cwd`, runtime process observations,
host SSH/Parallels/Crabbox operations, and Puppet's controller-owned evidence
and fencing. A real missing primitive should be named only after the same
failure is reproduced without Puppet.

## Capability and security boundary

Current ACPX source/docs at [c1bdc539](https://github.com/openclaw/acpx/tree/c1bdc53901e444d6d5ef094a0b91637fe1960b75)
confirm the useful composition points:

- [custom agents](https://github.com/openclaw/acpx/blob/c1bdc53901e444d6d5ef094a0b91637fe1960b75/docs/custom-agents.md)
  allow `--agent <command>` and make the resolved command part of session
  scope; the command speaks ACP over stdio.
- [sessions](https://github.com/openclaw/acpx/blob/c1bdc53901e444d6d5ef094a0b91637fe1960b75/docs/sessions.md)
  define local session records, queue ownership, reconnect/load, and local
  close semantics.
- [runtime process lifecycle](https://github.com/openclaw/acpx/blob/c1bdc53901e444d6d5ef094a0b91637fe1960b75/docs/runtime-process-lifecycle.md)
  gives host admission/observation callbacks and explicitly leaves host
  restart reconciliation, arbitrary descendants, and abrupt-owner supervision
  to the host.
- [runtime environment](https://github.com/openclaw/acpx/blob/c1bdc53901e444d6d5ef094a0b91637fe1960b75/docs/runtime-environment.md)
  describes a trusted child-environment overlay; it is not a secret-delivery
  or OS-isolation mechanism.
- [runtime contract](https://github.com/openclaw/acpx/blob/c1bdc53901e444d6d5ef094a0b91637fe1960b75/src/runtime/public/contract.ts)
  exposes `fs`, `terminal`, `agentProcessEnv`, and lifecycle hooks. Disabling
  ACP callbacks is policy for callback handling, not an OS sandbox for the
  agent's own native filesystem/process tools.

The non-secret credential plan is therefore:

1. Parent-owned broker/setup establishes the approved selector and scope once;
   the guest or host wrapper receives only the process-local capability needed
   for this run.
2. The wrapper rejects secrets in argv, persistent state, event logs, ordinary
   artifacts, and model-visible output. Readiness reports only booleans,
   version/identity shapes, and failure classes.
3. Authentication requiring an interactive guest keychain unlock stays an
   explicit owner action. A successful transport probe is not auth proof.
4. Every later run reuses the approved broker/selector contract; it does not
   recreate accounts, copy host credentials, or assume browser/session state.

This plan records architecture only. It does not assert that the current CP-1
bootstrap, guest keychain, or broker delivery is complete.

## Reuse versus host-specific work

Potentially reusable recipe material:

- ACPX's stable custom-agent command/session identity and standard ACP session
  lifecycle;
- a generic value-free wrapper result shape for patch, tests, artifacts, and
  cleanup uncertainty;
- Crabbox's existing required-artifact/download pattern and its declared
  provider capability checks; see [hermetic agent evidence](https://github.com/openclaw/crabbox/blob/46fb70eda185ee82ff46c6948ec5478c00640592/docs/features/hermetic-agent-evidence.md);
- existing Parallels desktop/SSH/artifact surfaces where the selected provider
  actually advertises them; see [Parallels](https://github.com/openclaw/crabbox/blob/46fb70eda185ee82ff46c6948ec5478c00640592/docs/providers/parallels.md)
  and [interactive desktop](https://github.com/openclaw/crabbox/blob/46fb70eda185ee82ff46c6948ec5478c00640592/docs/features/interactive-desktop-vnc.md).

Puppet/host-specific material:

- admission, task budgets, candidate/worktree identity, evidence review,
  replacement fencing, and final verdict;
- the exact VM/lease/guest identity and remote cwd mapping;
- the SSH/container wrapper's process supervision and reconnect policy;
- the existing broker's credential ownership and one-time setup; and
- optional AGY/Cua/OpenClaw desktop routing, exclusive GUI ownership, and
  before/after visual assertions.

OpenClaw's current desktop/computer-use documentation and Cua remain useful
later infrastructure, but they do not turn ACP session connectivity into
computer-use capability and are not proof of this private VM workflow. No new
VM framework, ACP launcher API, or upstream feature request is justified by
this packet. The inspected current references are OpenClaw main
`fbef0baa862c0047c06733ffb137114b499a57c9` ([desktop](https://github.com/openclaw/openclaw/blob/fbef0baa862c0047c06733ffb137114b499a57c9/docs/gateway/cloud-workers/desktop.md),
[computer use](https://github.com/openclaw/openclaw/blob/fbef0baa862c0047c06733ffb137114b499a57c9/docs/nodes/computer-use.md))
and Cua main `9bbfa7dd3e27ca7f1861ede70aaca390174493f9`
([repository](https://github.com/trycua/cua/tree/9bbfa7dd3e27ca7f1861ede70aaca390174493f9)).
Search existing issue #11 and the existing desktop tracker before any future
publication; do not open a duplicate tracker or treat the old five-idea
request as a filing quota.

## Next bounded action

After the relevant local AGY/Cursor/controller gate is accepted, ask the
existing Parallels owner to perform only the supported guest-readiness step,
then return a value-free receipt. If readiness passes, run one wrapper-backed
guest fixture and independently verify patch, tests, ACP session identity, and
remote cleanup. If any failure is remote-specific, preserve the exact failure
and adjudicate whether it belongs to the host wrapper, VM/provider, harness, or
ACPX before considering an upstream report.
