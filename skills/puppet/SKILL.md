---
name: puppet
description: Bootstrap/preflight Puppet controller for adapter-disabled YOLO sessions: strict, transcript-blind, controller-only, and checkpoint-driven.
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

1. Read the target repository instructions and the task contract.
2. Read [yolo-contract.md](references/yolo-contract.md) and require a local,
   uncommitted acknowledgement for this exact campaign.
3. Run `adapter_lab.py census` without launching an agent. Treat every generated
   capability as doctor-only until a real conformance probe qualifies the exact
   executable, adapter, platform, and protocol fingerprints. Enable it only
   with `adapter_lab.py qualify` and the accepted receipt from that probe.
4. Run `puppet.py doctor`. Stop on an active target/store lock, ambiguous
   executable identity, incomplete unrestricted mapping, missing sandbox-off
   control, prompt-in-argv transport, dirty or overlapping worktree, or missing
   proof-root writability.
5. Run only one target and one mutation owner at a time.

Never kill, rename, attach to, reuse, or repurpose a pre-existing process or
tmux session. Never inspect `.env`, credentials, auth logs, session stores,
conversation stores, terminal scrollback, or transcripts.

## Operate a session

Invoke the skill-local CLI:

```bash
python3 <skill-root>/scripts/puppet.py <command> ...
```

Use this sequence:

1. `doctor` validates the current executable, YOLO mapping, repository,
   authorization, tmux, proof root, and collision state.
2. `launch` creates one deterministic user-private tmux socket/session from a controller-verified
   manifest. Deliver the initial prompt through a protected file or literal
   tmux buffer, never as a process argument.
3. Give the human the exact command from `attach-command`; do not have the
   controller attach or read the pane.
4. Use `status` and bounded `wait` calls for structural state and validated
   checkpoints. Do not use `capture-pane`, `pipe-pane`, or terminal text.
5. Use `send` with stdin or `--message-file`. For AGY, Puppet adds exactly one
   `/teamwork-preview` prefix and rejects `/btw`, `/side`, and duplicates.
6. Import handoffs with `checkpoint`, inspect the bounded referenced artifact,
   and record controller findings with `review`.
7. Use `accept` only after independently verifying the exact checkpoint and
   terminal criteria. A target cannot review or accept itself.
8. Use `halt` only for the exact registered target. Preserve tmux and proof.

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

## Stop conditions

Stop and preserve a precise blocker when identity is ambiguous, a lock belongs
to another owner, a mapping or transport is unproved, transcript reading would
be required, a checkpoint is malformed, exact halt is uncertain, review stays
required after two repairs, or an external human gate appears. Never weaken a
guardrail or substitute a fake harness for real conformance.
