---
name: puppet
description: "Control transcript-blind YOLO harness sessions through census, exact real probes, recovery, qualification, checkpoints, and controller-only acceptance."
---

# Puppet

> **Warning:** Puppet live execution is YOLO-only. It requires the target's
> current unrestricted or always-approve mode and disables the harness sandbox
> wherever that control exists. The target receives the operator account's
> machine access. Prompted, sandboxed, or partly automatic launches are not a
> fallback.

Use Puppet as a small lifecycle and acceptance controller, not as a generic
launcher or transcript reader. Keep delivery, external effects, accounts,
security, secrets, spending, and destructive actions separately gated.

## Before a live session

1. Compile a source-only operator plan before running profile, doctor, launch,
   or lifecycle commands. From inside the target repository, `plan` resolves
   the current Git root. From a cockpit or another repository, pass `--repo`
   with the exact target Git root. The body-free result binds the repository,
   branch, commit, tree, controller fingerprints, input artifact hashes,
   private roots, blockers, and exact command arrays, but always reports
   `launch_authorized: false`; it neither checks login state nor creates a
   profile, tmux server, session, or harness process.
2. Resolve the target repository explicitly. From a cockpit or another repo,
   require an explicit target path. From inside the target, use its Git root
   unless the user overrides it. Give every mutating target a fresh worktree;
   keep the immutable controller, state, and proof outside that worktree.
3. Read the target repository instructions and the task contract.
4. Read [yolo-contract.md](references/yolo-contract.md) and require a local,
   uncommitted acknowledgement for this exact campaign.
5. Run `adapter_lab.py census` without launching an agent. Treat every generated
   capability as doctor-only until a real conformance probe qualifies the exact
   executable, adapter, platform, and protocol fingerprints. Enable it only
   with `adapter_lab.py qualify` and the accepted receipt from that probe. A
   probe also requires the separately supplied campaign ID, canonical goal
   repository root, and exact repository/commit/path/SHA-256 goal tuple.
   Regular probes require the exact authenticated Puppet-owned private profile
   and bind its closed launch environment; they never borrow an operator-global
   harness home.
6. Run `puppet.py doctor --profile-root <private-profile>`. Stop on a missing,
   invalid, unauthenticated, or adapter-mismatched private profile; an active
   target/store lock; ambiguous executable identity; incomplete unrestricted
   mapping; missing sandbox-off control; prompt-in-argv transport; dirty or
   overlapping worktree; or missing proof-root writability.
7. Run at most one live lane per harness target and one mutation owner per
   source slice. Different harness targets may proceed independently only with
   their own leases, isolated worktrees, state, sessions, and proof roots.

`--goal-repo` names the canonical local Git root. `--goal-repository`,
`--goal-commit`, `--goal-path`, and `--goal-sha256` must exactly match the
submitted authorization; they are independent expected values, not inferred
from the authorization file.

Never kill, rename, attach to, reuse, or repurpose a pre-existing process or
tmux session. Never inspect `.env`, credentials, auth logs, session stores,
conversation stores, terminal scrollback, or transcripts.

Puppet ships editable baseline layers under `templates/instructions/`. Prefer a
bounded per-run user addendum for customization; changing a shipped layer or
template root creates a new instruction-policy fingerprint and requires fresh
qualification. The initial-message wrapper is a safe composition transport,
not proof that a harness-native global, workspace, or additive plane works.

Subscription authentication is profile-scoped. Use `profile-init` to create a
Puppet-owned mode-0700 home/config root and obtain an exact human-run login
handoff; Puppet does not copy an existing credential or perform login itself.
After the operator completes that account action, use `profile-status` to retain
only an allowlisted login state. Codex, Claude, Cursor, and Grok have current
private-profile recipes. AGY stays unsupported here until its installed CLI
exposes an authentication-preserving private config-root selector.
`doctor` and `launch` require the selected profile explicitly. `launch` passes
only that profile's closed home/config environment to the exact target and
revalidates its manifest, executable, directory identities, login state, and
environment fingerprint immediately before target start. It never falls back
to an operator-global harness home.

## Operate a session

Invoke the skill-local CLI:

```bash
python3 <skill-root>/scripts/puppet.py <command> ...
```

Compile the first operator packet with:

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

Omit `--repo` only when the current directory is inside the target Git tree.
Redirect the JSON result if a durable packet is needed; `plan` itself does not
write an output file. Treat every listed command as proposed operator work, not
as authority to run it. Resolve the reported blockers and make a separate human
choice before any live launch.

Use this sequence:

1. If the selected private profile is not authenticated, run `profile-init`,
   give its `login_command` to the human, and verify it with `profile-status`.
   The login handoff is an explicit account action and never runs unattended.
2. `doctor` validates the current executable, YOLO mapping, repository,
   authorization, tmux, proof root, and collision state.
3. `launch` creates one deterministic user-private tmux socket/session from a
   controller-verified manifest, waits through the adapter's bounded structural
   startup settle, rechecks process/pane identity, and then delivers the initial
   prompt through a protected file or literal tmux buffer, never as a process
   argument. The settle reduces startup races; only a validated handoff proves
   the harness consumed the prompt.
4. Give the human the exact command from `attach-command`. When the operator
   opts in and the local surface supports visible macOS terminal launch, use
   `open-view` to open that command in a separate iTerm or Terminal window. It
   uses a short-lived one-use ticket and reports success only after a new
   read-only tmux client is structurally observed; an app-launch return code is
   not viewer proof. Request a fresh command after expiry or any failed check. It
   must open the harness's native, unfiltered live TUI on the exact Puppet-owned
   private socket/session in read-only mode: no capture, transcript, log mirror,
   renderer, summary, or controller mediation. The human may attach and detach
   without changing the target. Do not have the controller attach or read the
   pane.
5. Use `status` and bounded `wait` calls for structural state and validated
   checkpoints. Do not use `capture-pane`, `pipe-pane`, or terminal text.
6. Pin one adapter-qualified `session_profile` in the contract. Puppet applies
   that profile's native command only to the initial launch message; later
   `send` calls are ordinary steering messages. For AGY, Puppet also rejects
   `/btw`, `/side`, and caller-supplied profile prefixes.
7. Import handoffs with `checkpoint`, inspect the bounded referenced artifact,
   and record controller findings with `review`.
8. Use `accept` only after independently verifying the exact checkpoint and
   terminal criteria. A target cannot review or accept itself.
9. Use `halt` only for the exact registered target. Preserve tmux and proof.

Pass B probes and normal live sessions share one fixed, checkout-independent
authority root with one lock, projection, and durable lease history per target.
Different harness targets may run independently; a caller-selected proof or
state root cannot create a second lane for the same target. A lossy legacy
global projection keeps older controllers fenced while any per-target lane is
active. If a probe is interrupted, use `adapter_lab.py recover` with the same
target, run ID, controller, campaign, goal, manifest, mapping, authorization,
and proof root. Recovery reconciles the persisted exact identities and may halt
that exact target; it never relaunches.

Read [operating-contract.md](references/operating-contract.md) for lifecycle and
ownership rules, [adapter-contract.md](references/adapter-contract.md) before
changing adapters, and [prompt-patterns.md](references/prompt-patterns.md) when
building a contract or handoff.

## Checkpoint authority

Use source-free `conformance` handoffs for the shared real-harness probe. They
bind run, nonce, phase, sequence, executable, adapter, protocol, and artifact
fingerprints and must omit `candidate_commit`. Use `source` handoffs for
implementation work; they require a full exact commit. Any identity drift
invalidates the corresponding verdict.

Targets publish claims and evidence references. The controller alone records
`repair`, `conformance_accept`, `source_accept`, `block`, or `fail`, and alone
performs terminal acceptance. Learn only from exact commits, validated bounded
handoffs, controller-run tests, and independent reviews.

## Self-hosting boundary

Keep the supervising Puppet release immutable for a live session. Give the
target a separate candidate worktree. Never execute candidate code while that
candidate is mutating. Bootstrap Puppet returns `unsupported` for `promote` and
`close`; promotion enters a later accepted surface only after exact-head tests,
real conformance, independent review, controller acceptance, and rollback proof.

Read [proof-provenance.md](references/proof-provenance.md) before reusing prior
work. Historical, private, branch-only, uncommitted, terminal-derived, or
license-unclear evidence is design input until its exact delta is re-proved.

## Controller authority boundary

Qualification receipts require inclusion in Puppet's fixed per-account local
controller ledger and remain bound to the current executable, adapter,
platform, protocol, goal, terminal state, tmux server, and proof artifacts.
This prevents a caller-selected proof root from qualifying itself. It remains a
cooperative same-UID mechanism, not cryptographic containment against hostile
code already running as the operator; the YOLO warning still governs the trust
boundary.

## Stop conditions

Stop and preserve a precise blocker when identity is ambiguous, a lock belongs
to another owner, a mapping or transport is unproved, transcript reading would
be required, a checkpoint is malformed, exact halt is uncertain, review stays
required after two repairs, controller-ledger inclusion is missing, an active
lease belongs to another run, exact recovery is required, or an external human gate appears. Never weaken a
guardrail or substitute a fake harness for real conformance.
