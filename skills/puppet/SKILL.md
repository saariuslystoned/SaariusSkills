---
name: puppet
description: "Launch, steer, checkpoint, and halt transcript-blind YOLO harness sessions through a fail-closed local controller: plan, doctor, launch, send, status, halt first; qualification, matched-control, and campaign recovery live in references."
---

# Puppet

> **Warning:** Puppet live execution is YOLO-only. It requires unrestricted or
> always-approve mode with the harness sandbox off, granting the target the
> operator account's machine access; there is no prompted fallback.

Use Puppet as a small lifecycle and acceptance controller, not a generic
launcher or transcript reader. Separately gate external effects, accounts,
security, secrets, spending, and destructive actions.

## The ordinary operator loop

Invoke the skill-local CLI:

```bash
python3 <skill-root>/scripts/puppet.py <command> ...
```

The regular lifecycle for one qualified harness target is:

```text
plan -> doctor -> launch -> send -> status -> halt
```

1. **Onboard once.** Prepare or rejoin one durable private profile per user,
   harness, and account with `onboard` (or the single-target `profile-init` /
   `profile-status`). Reuse every `ready` profile without prompting; a login
   handoff is a human-only account action for a profile the provider reports
   logged out. See
   [subscription-profiles.md](references/subscription-profiles.md).
2. **Compile a plan.** `plan` builds a source-only operator packet before any
   profile, doctor, launch, or lifecycle command:

   ```bash
   python3 <skill-root>/scripts/puppet.py plan \
     --contract <contract.json> \
     --manifest <manifest.json> \
     --authorization <authorization.json> \
     --profile-root <private-profile> \
     --prompt-file <launch-prompt.txt> \
     --session <session-id> \
     --run-root <private-run-root> \
     [--repo <exact-target-git-root>]
   ```

   Omit `--repo` only when the current directory is inside the target Git
   tree; from a cockpit or another repository, pass the exact target Git root.
   The body-free result binds the repository, branch, commit, tree,
   controller/input fingerprints, private roots, blockers, and exact command
   arrays, but always reports `launch_authorized: false`; it checks no login
   state and creates no profile, tmux server, session, or harness process.
   Treat every listed command as proposed operator work, not authority to run
   it. Resolve the reported blockers and make a separate human choice before
   any live launch. An unqualified target's plan is doctor-only and carries a
   human gate; see
   [qualification-contract.md](references/qualification-contract.md).
3. **Doctor.** `doctor --profile-root <private-profile>` validates the current
   executable, YOLO mapping, repository, authorization, tmux, proof root, and
   collision state. Stop on a missing, invalid, unauthenticated, or
   adapter-mismatched private profile; an active target/store lock; ambiguous
   executable identity; incomplete unrestricted mapping; missing sandbox-off
   control; prompt-in-argv transport; dirty or overlapping worktree; or
   missing proof-root writability.
4. **Launch.** `launch` creates one deterministic user-private tmux
   socket/session from a controller-verified manifest, waits through the
   adapter's bounded structural startup settle, rechecks process/pane
   identity, and then delivers the initial prompt through a protected file or
   literal tmux buffer, never as a process argument. The settle reduces
   startup races; only a validated handoff proves the harness consumed the
   prompt. `launch` requires the selected profile explicitly, passes only that
   profile's closed home/config environment to the exact target, and never
   falls back to an operator-global harness home. Claude and Cursor each have
   one narrow, bounded pre-prompt startup-screen gate — the only
   ordinary-operation terminal reads Puppet performs; their exact reducer
   contracts live in
   [qualification-contract.md](references/qualification-contract.md).
5. **Send.** Pin one adapter-qualified `session_profile` in the contract.
   Puppet applies that profile's native command only to the initial launch
   message; later `send` calls are ordinary steering messages. For AGY,
   Puppet also rejects `/btw`, `/side`, and caller-supplied profile prefixes.
6. **Status.** Use `status` and bounded `wait` calls for structural state and
   validated checkpoints. Do not use `capture-pane`, `pipe-pane`, or terminal
   text; after the ready handoff, never capture or read pane text for any
   target.
7. **Checkpoint.** Import handoffs with `checkpoint`, inspect the bounded
   referenced artifact, and record controller findings with `review`. Use
   `accept` only after independently verifying the exact checkpoint and
   terminal criteria.
8. **Halt.** Use `halt` only for the exact registered target. Preserve tmux
   and proof.

Run at most one live lane per harness target and one mutation owner per
source slice. Different harness targets may proceed independently only with
their own leases, isolated worktrees, state, sessions, and proof roots.

## The concurrent fast path

For any warm, qualified mix of one through five regular harnesses, use
`scripts/puppet_launch.py run` under
[fast-launch-contract.md](references/fast-launch-contract.md). It serializes
worktree allocation, compiles selected plans, and starts harnesses
concurrently through `scripts/puppet_fanout.py`; keep live acknowledgement
explicit and runtime failures lane-local. Use its
explicit `checkpoint` lifecycle only when a bounded handoff is wanted; keep
qualification out of ordinary runs. Ordinary runs never
probe/qualify or inspect auth stores; multi-target mutation names one selected
owner. Support lanes keep only named read/test modes; do not add automatic
routing, sibling halt, `/goal`, `/loop`, or `/teamwork-preview`.

## Before any live session

1. Resolve the target repository explicitly. From a cockpit or another repo,
   require an explicit target path. From inside the target, use its Git root
   unless the user overrides it. Give every mutating target a fresh worktree;
   keep the immutable controller, state, and proof outside that worktree.
2. Read the target repository instructions and the task contract.
3. Read [yolo-contract.md](references/yolo-contract.md) and require a local,
   uncommitted acknowledgement for this exact campaign.
4. Confirm the target manifest is qualified. Every generated capability is
   doctor-only until a real conformance probe qualifies the exact executable,
   adapter, platform, and protocol fingerprints; the census, probe, pairing,
   and promotion flows live in
   [qualification-contract.md](references/qualification-contract.md).

Never kill, rename, attach to, reuse, or repurpose a pre-existing process or
tmux session. Never inspect `.env`, credentials, auth logs,
session/conversation stores, terminal scrollback, or transcripts. The only
ordinary-operation exceptions are the narrow Claude and Cursor startup-screen
reducers referenced in step 4 of the operator loop: each reads only a bounded
owned pane before ordinary prompt delivery, classifies a fixed
harness-specific allowlist, retains only
gate/selection/workspace-match/size/hash/timing metadata, and discards the raw
bytes.

Puppet ships editable baseline layers under `templates/instructions/`. Prefer
a bounded per-run user addendum for customization; changing a shipped layer or
template root creates a new instruction-policy fingerprint and requires fresh
qualification. The initial-message wrapper is a safe composition transport,
not proof that a harness-native global, workspace, or additive plane works.

## Watching a session

Give the human the exact command from `attach-command`. When the operator
opts in and the local surface supports visible macOS terminal launch, use
`open-view` to open that command in a separate iTerm or Terminal window. It
uses a short-lived one-use ticket and reports success only after a new
read-only tmux client is structurally observed; an app-launch return code is
not viewer proof. Request a fresh command after expiry or any failed check. It
must open the harness's native, unfiltered live TUI on the exact Puppet-owned
private socket/session in read-only mode: no capture, transcript, log mirror,
renderer, summary, or controller mediation. The human may attach and detach
without changing the target. Tmux's owner-execute bit is only an
attached-client state marker and is excluded from socket identity; device,
inode, owner, every other mode bit, group/other access, socket type, and
server/pane/process identities remain exact. Do not have the controller
attach or read the pane.

## Checkpoint authority

Use source-free `conformance` handoffs for the shared real-harness probe. They
bind run, nonce, phase, sequence, executable, adapter, protocol, and artifact
fingerprints and must omit `candidate_commit`. Use `source` handoffs for
implementation work; they require a full exact commit. Any identity drift
invalidates the corresponding verdict.

Targets publish claims and evidence references. The controller alone records
`repair`, `conformance_accept`, `source_accept`, `block`, or `fail`, and alone
performs terminal acceptance. A target cannot review or accept itself. Learn
only from exact commits, validated bounded handoffs, controller-run tests, and
independent reviews.

After `source_accept`, the controller may send one proof-only assignment.
Puppet records its ID and phase; only replay is allowed, and proof waits for
delivery.

## Recovery

Pass B probes and normal live sessions share one fixed, checkout-independent
authority root with one lock, projection, and durable lease history per
target; a caller-selected proof or state root cannot create a second lane for
the same target. If a probe or run is interrupted, use
`adapter_lab.py recover` with the same exact identities; recovery reconciles
persisted state and may halt the exact target, but it never relaunches. One-use reservations,
stop-and-preserve rules, and the sole exceptional
`reconcile-grok-dead-lease` path live in
[campaign-recovery.md](references/campaign-recovery.md).

## Self-hosting boundary

Keep the supervising Puppet release immutable for a live session. Give the
target a separate candidate worktree. Never execute candidate code while that
candidate is mutating. Bootstrap Puppet returns `unsupported` for `promote`
and `close`; promotion enters a later accepted surface only after exact-head
tests, real conformance, independent review, controller acceptance, and
rollback proof.

Read [proof-provenance.md](references/proof-provenance.md) before reusing
prior work. Historical, private, branch-only, uncommitted, terminal-derived,
or license-unclear evidence is design input until its exact delta is
re-proved.

## Controller authority boundary

Qualification receipts require inclusion in Puppet's fixed per-account local
controller ledger and remain bound to the current executable, adapter,
platform, protocol, goal, terminal state, tmux server, and proof artifacts.
This prevents a caller-selected proof root from qualifying itself. It remains
a cooperative same-UID mechanism, not cryptographic containment against
hostile code already running as the operator; the YOLO warning still governs
the trust boundary.

## Stop conditions

Stop and preserve a precise blocker when identity is ambiguous, a lock
belongs to another owner, a mapping or transport is unproved, transcript
reading would be required, a checkpoint is malformed, exact halt is uncertain,
review stays required after two repairs, controller-ledger inclusion is
missing, an active lease belongs to another run, exact recovery is required,
or an external human gate appears. Never weaken a guardrail or substitute a
fake harness for real conformance.

## References

- [operating-contract.md](references/operating-contract.md) — lifecycle and
  ownership rules.
- [fast-launch-contract.md](references/fast-launch-contract.md) — mixed-target
  concurrent operation.
- [qualification-contract.md](references/qualification-contract.md) — census,
  Pass B probes, per-harness pairing and activation transactions, startup
  gates, and promotion.
- [subscription-profiles.md](references/subscription-profiles.md) — durable
  private profiles, onboarding, and login handoffs.
- [campaign-recovery.md](references/campaign-recovery.md) — interrupted-run
  recovery and dead-lease reconciliation.
- [adapter-contract.md](references/adapter-contract.md) — read before changing
  adapters.
- [prompt-patterns.md](references/prompt-patterns.md) — contract and handoff
  authoring.
- [proof-provenance.md](references/proof-provenance.md) — evidence reuse
  rules.
- [yolo-contract.md](references/yolo-contract.md) — the live-execution trust
  boundary.
