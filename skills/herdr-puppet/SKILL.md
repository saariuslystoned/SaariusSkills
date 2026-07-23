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
4. Initialize a controller journal. Record structural events, prompt hashes,
   sequence numbers, checkpoint results, failures, and concise observations;
   never copy pane output into the journal.
5. Run structural `status` before every mutation. Stop on any session,
   workspace, tab, pane, terminal, label, socket, or SSH-target mismatch.
6. For a live qualification, create a new deterministic tab through
   `qualification-create-tab`. Never adopt an existing tab or process.
7. Send ordinary AGY steering as a plain message with no slash-command prefix.
   Never inject `/teamwork-preview` automatically. Use it only when the
   operator explicitly requests a separately bounded 4-20-helper fan-out; one
   AGY root remains the integration writer, and that experimental hierarchy
   requires its own topology, accounting, timeout, and cleanup proof.
8. Drive only that leased pane through `qualification-send`. Serialize sends
   and let the lease reject stale, skipped, duplicate, or replayed sequences.
   Supply prompt content through `--stdin` or a bounded UTF-8 `--text-file`;
   never place prompt content in process arguments. Treat
   `herdr_input_outcome_unknown` as a hard stop: reconcile the same sequence
   from independent structural evidence before any later send, and never
   retry the prompt speculatively.
9. Use `qualification-beacon-wait` for a generated checkpoint nonce during a
   declared qualification. Require the harness to emit exactly one line shaped
   as `HERDR_PUPPET_<STATUS|ACTION_REQUIRED|DONE> <nonce>`. The command returns
   only the checkpoint class and hashes, never pane text. Use
   `qualification-token-probe` only for lower-level transport diagnosis.
10. Preserve the owned tab with `lease-preserve` at a human gate, superseded
    route, completed milestone, or operator stop. Preservation changes only
    the controller lease and rejects further input; it does not close the tab.
11. Review the journal after each useful checkpoint. Promote only repeatable
    lessons into this skill; keep transient incident detail in the run packet.

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
  --proof-root <path>

python3 scripts/herdr_puppet.py status --plan-json <plan.json>

python3 scripts/herdr_puppet.py journal-init \
  --plan-json <plan.json> \
  --run-root <run-root>

python3 scripts/herdr_puppet.py journal-show \
  --run-root <run-root>

python3 scripts/herdr_puppet.py qualification-beacon-wait \
  --lease-json <lease.json> \
  --nonce <unique-checkpoint-nonce> \
  --run-root <run-root> \
  --allow-live-qualification

python3 scripts/herdr_puppet.py qualification-send \
  --lease-json <lease.json> \
  --seq <next-seq> \
  --stdin \
  --run-root <run-root> \
  --allow-live-qualification \
  < <task-owned-prompt-file>

python3 scripts/herdr_puppet.py lease-preserve \
  --lease-json <lease.json> \
  --reason <human_gate|route_superseded|milestone_complete|operator_stop>
```

Live qualification commands additionally require
`--allow-live-qualification`. That flag confirms transport mutation only. It
does not authorize unrestricted harness flags, pushes, pull requests, merges,
deploys, sends, spending, secret access, account/security changes, or
destructive cleanup.

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
- Leave `halt` and `recover` unavailable until exact remote-process identity
  and fail-closed recovery have independent qualification.
