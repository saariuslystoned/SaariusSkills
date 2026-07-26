---
name: herdr-puppet
description: Plan, launch, drive, observe, and journal explicitly owned remote coding-agent panes in a persistent Herdr session. Use when a user asks Codex to puppet AGY or another harness through Herdr, keep a remote TUI visible across client detach/reattach, run a bounded Herdr transport qualification, or inspect and improve a Herdr-Puppet dogfood run. Do not use it to adopt arbitrary tabs, read ordinary terminal transcripts, or control a parent Herdr session without an explicit capability.
---

# Herdr-Puppet

Drive one explicitly owned remote-agent pane while leaving the operator's
parent Herdr session alone. Treat labels as presentation and exact IDs plus a
lease as authority.

## Load the contracts

Read:

- [references/authority-contract.md](references/authority-contract.md) before
  planning or mutating a live Herdr session.
- [references/transport-schema.md](references/transport-schema.md) before
  creating, validating, or recovering a lease.
- [references/qualification-contract.md](references/qualification-contract.md)
  before any live qualification or bounded token probe.

Use `scripts/herdr_puppet.py` for deterministic calls. Do not replace it with
hand-composed Herdr mutations when the script owns the operation.

## Run the controller loop

1. Obtain an explicit parent-session capability: exact session, workspace ID,
   workspace label, expected SSH target, run ID, source slice, proof root, and
   allowed mode.
2. Run `doctor`. Require the supported Herdr version and protocol, one live
   named session, and an unambiguous workspace.
3. Run `plan`. Save the JSON plan outside public source when it contains local
   paths or host/account identity.
4. Initialize a controller journal before any live tab mutation. Record
   structural events, prompt hashes, sequence numbers, checkpoint results,
   failures, and concise observations; never copy pane output into the
   journal. `qualification-create-tab` preflights the matching initialized
   journal and refuses to create a tab or lease when it is absent or belongs
   to another run.
5. Run structural `status --plan-json` before tab creation. Once a lease
   exists, stop rechecking the now-consumed plan: its owned label is expected
   to exist and plan status must reject it. Use `status --lease-json` or
   `maintenance-checkpoint` before every later mutation. Stop on any session,
   workspace, tab, pane, terminal, label, socket, or SSH-target mismatch.
6. For a live qualification, create a new deterministic tab through
   `qualification-create-tab`. Never adopt an existing tab or process.
7. Start the harness, then prove its input surface is ready before sending the
   real task. Accept the operator's explicit observation of the exact leased
   tab's ready input surface, a bounded harness-specific token that can appear
   only after input readiness, or a unique task-owned readiness artifact
   written by a harmless no-target preflight and bound to the run nonce and
   source identity. A product name, banner, startup text, fixed delay, process
   liveness, and successful Herdr input acknowledgement do not prove harness
   readiness or prompt submission. If an artifact preflight is used, absence
   is not permission to resend it; reconcile or supersede the run.
8. Send ordinary AGY steering as a plain message with no slash-command prefix.
   Never inject `/teamwork-preview` automatically. Use it only when the
   operator explicitly requests a separately bounded 4-20-helper fan-out; one
   AGY root remains the integration writer, and that experimental hierarchy
   requires its own topology, accounting, timeout, and cleanup proof.
   Preserve any operator-selected slash command verbatim; do not add, remove,
   or replace a plugin prefix chosen for that turn.
9. Drive only that leased pane through `qualification-send`. Serialize sends
   and let the lease reject stale, skipped, duplicate, or replayed sequences.
   Supply a non-empty prompt through `--stdin` or a bounded UTF-8 `--text-file`;
   never place prompt content in process arguments. Treat
   `herdr_input_outcome_unknown` as a hard stop: reconcile the same sequence
   from independent structural evidence before any later send, and never retry
   the prompt speculatively. When an orchestration bridge cannot reliably
   half-close standard input, do not paste a long prompt into its canonical PTY.
   Use a private task-owned `--text-file`, require the exact sequence
   acknowledgement, and then remove only that local transport file.
   For AGY noninteractive `--print` runs (notably 1.1.7),
   `qualification-send` should carry only a short launcher command. Put the
   actual AGY task in a separate private file and reference only its path:
   `agy --prompt @/exact/task-owned-prompt-file --print-timeout <bounded>`.
   Do not feed the AGY task through positional argv or AGY stdin in this mode.
   Retain that separate AGY prompt file until source-bound readiness or
   terminal evidence proves the process consumed it. The caller must then
   remove only that exact file; maintenance records whether it remains.
   Treat its success receipt as `herdr_pane_input_only`: it does not prove the
   harness was ready, accepted the prompt, started work, loaded an extension,
   or called a tool.
10. Use `qualification-beacon-wait` for a generated checkpoint nonce during a
   declared qualification. Require the harness to emit exactly one line shaped
   as `HERDR_PUPPET_<STATUS|ACTION_REQUIRED|DONE> <nonce>`. The command returns
   only the checkpoint class and hashes, never pane text. Use
   `qualification-token-probe` only for lower-level transport diagnosis. A
    `not_matched` result proves only that the strict line was absent from the
    bounded window; it does not prove the worker, SSH process, harness, or tab
    went offline and is not itself a human gate.
    A separately validated terminal artifact may prove the task result and
    justify explicit `lease-preserve`, but it must not be rewritten as a
    matched `DONE` checkpoint.
    The waiter has an independent controller hard timeout. `DONE` and
    `ACTION_REQUIRED` automatically preserve the lease while leaving the tab
    visible. When the operator reports the exact nonce line directly from the
    exact owned tab, treat that checkpoint as terminal, journal the
    observation, and preserve immediately; process or receipt polling cannot
    override it.
11. Preserve the owned tab with `lease-preserve` at a superseded route,
    operator stop, or a terminal checkpoint reported outside the waiter.
    Preservation changes only the controller lease and rejects further input;
    it does not close the tab.
12. Run `maintenance-checkpoint` at every milestone boundary and before
    leaving the run. Inventory only
    exact run-owned resources already joined by the lease or named in
    structured harness events: tab, pane, terminal, foreground SSH PID,
    task-owned prompt files, and explicitly recorded child processes. Classify
    each as active, preserved, stale, or ambiguous. Require the caller to remove
    only its acknowledged task-owned prompt file, then record its absence.
    Never close a pane or reap a process
    from its label, name, or age; journal repeat residue as a
    `maintenance_candidate` and route exact cleanup through a separately
    authorized owner-specific maintenance tool.
13. When the operator explicitly authorizes cleanup, run
    `cleanup-preserved-tab` with the exact leased tab ID repeated through
    `--confirm-tab-id`. It accepts only a preserved lease and initialized
    journal, closes no other tab, verifies the exact tab and pane disappeared
    and the leased foreground SSH PID is absent, then records the closed state.
    A stale but unrecorded lease may be reconciled only after the same absence
    and PID-absence checks. PID reuse blocks cleanup rather than being treated
    as success. Never target a display ordinal or label.
14. Review the journal after each useful checkpoint. Promote only repeatable
    lessons into this skill; keep transient incident detail in the run packet.

Herdr-Puppet does not select a harness permission posture. Transport
qualification flags authorize only the named Herdr operation. Unrestricted or
auto-approval harness flags such as AGY's `--dangerously-skip-permissions` must
be explicitly authorized and passed by the caller for that bounded launch.
Likewise, closing a preserved tab is a separate exact-target maintenance
action: it requires operator authority, the leased tab identity, and
post-close process-exit proof. Never infer either behavior from "puppet",
"Herdr", a label, or `--allow-live-qualification`.

## Commands

Run from the skill directory:

```bash
python3 scripts/herdr_puppet.py doctor \
  --session <session>

python3 scripts/herdr_puppet.py plan \
  --session <session> \
  --workspace-id <workspace-id> \
  --workspace-label <label> \
  --expected-ssh-target <user@host> \
  --run-id <run-id> \
  --repo <owner/repo> \
  --worktree <path> \
  --proof-root <path> \
  --live-mutation-authorized

python3 scripts/herdr_puppet.py status --plan-json <plan.json>

python3 scripts/herdr_puppet.py journal-init \
  --plan-json <plan.json> \
  --run-root <run-root>

python3 scripts/herdr_puppet.py journal-show \
  --run-root <run-root>

python3 scripts/herdr_puppet.py qualification-create-tab \
  --plan-json <plan.json> \
  --lease-json <lease.json> \
  --run-root <run-root> \
  --allow-live-qualification

python3 scripts/herdr_puppet.py qualification-beacon-wait \
  --lease-json <lease.json> \
  --nonce <unique-checkpoint-nonce> \
  --run-root <run-root> \
  --allow-live-qualification

python3 scripts/herdr_puppet.py qualification-send \
  --lease-json <lease.json> \
  --seq <next-seq> \
  --text-file <task-owned-prompt-file> \
  --run-root <run-root> \
  --allow-live-qualification

python3 scripts/herdr_puppet.py lease-preserve \
  --lease-json <lease.json> \
  --reason <human_gate|route_superseded|milestone_complete|operator_stop>

python3 scripts/herdr_puppet.py maintenance-checkpoint \
  --lease-json <lease.json> \
  --run-root <run-root>

python3 scripts/herdr_puppet.py cleanup-preserved-tab \
  --lease-json <lease.json> \
  --run-root <run-root> \
  --confirm-tab-id <exact-tab-id> \
  --allow-live-cleanup
```

Live qualification commands additionally require
`--allow-live-qualification`. That flag confirms transport mutation only. It
does not authorize unrestricted or auto-approval harness flags, pushes, pull
requests, merges, deploys, sends, spending, secret access, account/security
changes, tab closure, process reaping, or destructive cleanup.

## Preserve the boundary

- Never stop, repair, replace, or reconfigure the parent Herdr session.
- Never infer ownership from a label, current focus, or a familiar process.
- Never reuse pre-existing tabs or harness processes.
- Do not treat Herdr's Agents sidebar as remote-agent authority for a harness
  launched after SSH. Upstream `ogulcancelik/herdr#1170` is a known limitation;
  do not build or claim a custom workaround.
- Never persist prompts, responses, scrollback, account identifiers, auth
  material, or environment contents in a public proof.
- Keep ordinary `status` transcript-blind. Only the separately gated
  qualification token and beacon waits may use Herdr's blocking `wait output`;
  both necessarily receive a bounded surrounding text window in controller
  memory and must discard it without emitting or persisting it.
- Treat the journal as review input, not automatic permission to broaden the
  skill.
- Treat maintenance inventory as routing evidence, not deletion authority.
  `cleanup-preserved-tab` is the only close adapter: it still requires explicit
  operator authority, a preserved exact lease, repeated tab-ID confirmation,
  and verified tab, pane, and foreground-SSH-PID absence.
- Leave `halt` and `recover` unavailable until exact remote-process identity
  and fail-closed recovery have independent qualification.
