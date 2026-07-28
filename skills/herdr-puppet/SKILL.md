---
name: herdr-puppet
description: Plan, launch, drive, observe, and journal explicitly owned remote coding-agent panes in a persistent Herdr session. Use when a user asks Codex to puppet AGY or another harness through Herdr, keep a remote TUI visible across client detach/reattach, run a bounded Herdr transport qualification, recover bounded Screen Sharing or VNC observation when Computer Use cannot resolve a visible window, or inspect and improve a Herdr-Puppet dogfood run. Do not use it to adopt arbitrary tabs, read ordinary terminal transcripts, or control a parent Herdr session without an explicit capability.
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
- [references/desktop-observation-fallback.md](references/desktop-observation-fallback.md)
  when Computer Use cannot resolve a visible Screen Sharing or VNC window and
  the route needs operator-visible desktop proof.

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
   journal. The plan's exact `proof_root` is the one allowed journal
   `run_root`; initialization and every later journal use reject any alternate
   or copied root. `qualification-create-tab` preflights that matching
   initialized journal and refuses to create a tab or lease when it is absent
   or belongs to another run.
5. Run structural `status --plan-json` before tab creation. Once a lease
   exists, stop rechecking the now-consumed plan: its owned label is expected
   to exist and plan status must reject it. Use `status --lease-json` or
   `maintenance-checkpoint` before every later mutation. Stop on any session,
   workspace, tab, pane, terminal, label, socket, or SSH-target mismatch.
   Current operations accept only the canonical lease-v1 shape. If a historical
   lease lacks the additive readiness/file fields or carries the former
   `harness_readiness: status_verified` value, run the explicit
   `lease-migrate-v1` adapter before status, journal refresh, probe,
   preservation, or cleanup.
6. For a live qualification, create a new deterministic tab through
   `qualification-create-tab`. The controller focuses that exact newly created
   tab in the plan's target workspace so the run is operator-visible and Herdr
   output waits can observe it. Herdr 0.7.3 focus is server-owned, so this
   intentionally changes the isolated operator session's visible workspace and
   tab; it grants no authority to navigate, adopt, or close any other tab.
   Never adopt an existing tab or process.
7. Use `qualification-run` for shell commands, including the harmless shell
   STATUS preflight and an AGY noninteractive launcher. Supply the command
   through `--stdin` or a bounded UTF-8 `--text-file`; never place it in the
   controller's arguments. The adapter invokes Herdr 0.7.3 `pane run` once and
   records only the command hash. Its acknowledgement proves only that the
   Herdr CLI returned success. It does not prove shell execution, harness
   readiness, prompt acceptance, MCP readiness, task start, or task completion.
8. Follow the qualification order exactly: atomic shell STATUS preflight,
   strict STATUS beacon wait with `--lines 80 --timeout-ms 480000`, atomic AGY
   launcher, then the terminal beacon wait with
   `--lines 80 --timeout-ms 480000`. Give the controller process a larger
   `--timeout-seconds 510` envelope. The matching STATUS checkpoint advances
   shell readiness only and is the follow-on `qualification-run` gate; a
   successful API acknowledgement is not.
   For AGY noninteractive `--print` runs (notably 1.1.7), put the actual task in
   a separate private file on the leased remote SSH target, register its exact
   remote path before launch, and reference only that path from the launcher:
   `agy --prompt @/exact/task-owned-prompt-file --print-timeout 420s`.
   The duration requires a Go unit such as `s`. Do not feed the AGY task
   through positional argv or AGY stdin. Retain that task file until
   source-bound or terminal evidence proves the process consumed it, then
   remove only that exact file and record bounded remote-removal evidence in
   the final maintenance checkpoint. The controller never tests a remote path
   with its local filesystem.
9. Use `qualification-send` only for ordinary interactive harness prompts
   after `qualification-harness-ready` records explicit operator confirmation
   against the exact leased source and ready input surface. Shell STATUS never
   authorizes pane input, including sequence 1. Noninteractive AGY remains on
   `qualification-run`.
   Serialize sends and let the lease reject stale, skipped, duplicate, or
   replayed sequences. Send ordinary AGY steering as a plain message with no
   slash-command prefix.
   Never inject `/teamwork-preview` automatically. Use it only when the
   operator explicitly requests a separately bounded 4-20-helper fan-out; one
   AGY root remains the integration writer, and that experimental hierarchy
   requires its own topology, accounting, timeout, and cleanup proof. Preserve
   an operator-selected slash command verbatim. Supply prompts through
   `--stdin` or a bounded UTF-8 `--text-file`, never controller argv. Treat
   `herdr_input_outcome_unknown` as a hard stop and never retry speculatively.
   A send receipt remains scoped to `herdr_pane_input_only` and proves no
   shell, harness, prompt, MCP, or task readiness.
10. Use `qualification-beacon-wait` for a generated checkpoint nonce during a
   declared qualification. Require the harness to emit exactly one line shaped
   as `HERDR_PUPPET_<STATUS|ACTION_REQUIRED|DONE> <nonce>`. The command returns
   only the checkpoint class and hashes, never pane text. Use
   `qualification-token-probe` only for lower-level transport diagnosis. A
    `not_matched` result proves only that the strict line was absent from the
    bounded window; it does not prove the worker, SSH process, harness, or tab
    went offline and is not itself a human gate. The same submission nonce may
    receive one bounded re-wait after its first `not_matched`; a matched nonce
    is terminal and any third attempt or cross-sequence reuse is rejected.
    Each attempt is durably reserved under the exact lease lock before Herdr
    receives the wait request, so concurrent callers cannot exceed the cap.
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
    Preservation changes only the controller lease and rejects further
    submissions; it does not close the tab.
12. Run `maintenance-checkpoint` at every milestone boundary and before
    leaving the run. Inventory only
    exact run-owned resources already joined by the lease or named in
    structured harness events: tab, pane, terminal, foreground SSH PID,
    controller-local caller text files, registered remote task files, and
    explicitly recorded child processes. Classify
    each as active, preserved, stale, or ambiguous. Require the caller to remove
    only its acknowledged task-owned prompt file. For a remote file, final
    maintenance records the exact registered path and one bounded removal
    evidence class; public receipts emit neither that path nor a path hash.
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

Keep the controller plan file outside the intended run root. `journal-init`
creates that run root atomically and refuses any pre-existing directory,
including one created early merely to hold `plan.json`.

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
  --proof-root <run-root> \
  --live-mutation-authorized

python3 scripts/herdr_puppet.py status --plan-json <plan.json>

python3 scripts/herdr_puppet.py lease-migrate-v1 \
  --lease-json <historical-lease.json>

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

python3 scripts/herdr_puppet.py qualification-run \
  --lease-json <lease.json> \
  --seq <next-seq> \
  --text-file <task-owned-command-file> \
  --run-root <run-root> \
  --allow-live-qualification

python3 scripts/herdr_puppet.py qualification-beacon-wait \
  --lease-json <lease.json> \
  --nonce <unique-checkpoint-nonce> \
  --lines 80 \
  --timeout-ms 480000 \
  --timeout-seconds 510 \
  --run-root <run-root> \
  --allow-live-qualification

python3 scripts/herdr_puppet.py qualification-harness-ready \
  --lease-json <lease.json> \
  --source-repo <exact-leased-repo> \
  --source-worktree <exact-leased-worktree> \
  --operator-id <operator-id> \
  --evidence operator_observed_ready_input \
  --confirm-ready \
  --run-root <run-root> \
  --allow-live-qualification

python3 scripts/herdr_puppet.py qualification-send \
  --lease-json <lease.json> \
  --seq <next-seq> \
  --text-file <task-owned-prompt-file> \
  --run-root <run-root> \
  --allow-live-qualification

python3 scripts/herdr_puppet.py remote-task-file-register \
  --lease-json <lease.json> \
  --remote-path </exact/remote/task-file> \
  --source-repo <exact-leased-repo> \
  --source-worktree <exact-leased-worktree> \
  --confirm-caller-owned \
  --run-root <run-root>

python3 scripts/herdr_puppet.py lease-preserve \
  --lease-json <lease.json> \
  --reason <human_gate|route_superseded|milestone_complete|operator_stop>

python3 scripts/herdr_puppet.py maintenance-checkpoint \
  --lease-json <lease.json> \
  --run-root <run-root> \
  --remote-task-file-removed </exact/remote/task-file> \
  --remote-removal-evidence operator_verified_remote_absence \
  --confirm-remote-removed

python3 scripts/herdr_puppet.py cleanup-preserved-tab \
  --lease-json <lease.json> \
  --run-root <run-root> \
  --confirm-tab-id <exact-tab-id> \
  --allow-live-cleanup
```

For a bounded noninteractive AGY qualification, use this ordered recipe:

```bash
python3 scripts/herdr_puppet.py qualification-run \
  --lease-json <lease.json> --seq 1 \
  --text-file <shell-status-command-file> \
  --run-root <run-root> --allow-live-qualification

python3 scripts/herdr_puppet.py qualification-beacon-wait \
  --lease-json <lease.json> --nonce <shell-status-nonce> --lines 80 \
  --timeout-ms 480000 --timeout-seconds 510 \
  --run-root <run-root> --allow-live-qualification

python3 scripts/herdr_puppet.py remote-task-file-register \
  --lease-json <lease.json> --remote-path </exact/remote/task-file> \
  --source-repo <exact-leased-repo> \
  --source-worktree <exact-leased-worktree> \
  --confirm-caller-owned --run-root <run-root>

python3 scripts/herdr_puppet.py qualification-run \
  --lease-json <lease.json> --seq 2 \
  --text-file <agy-launcher-command-file> \
  --run-root <run-root> --allow-live-qualification

python3 scripts/herdr_puppet.py qualification-beacon-wait \
  --lease-json <lease.json> --nonce <terminal-task-nonce> --lines 80 \
  --timeout-ms 480000 --timeout-seconds 510 \
  --run-root <run-root> --allow-live-qualification
```

The launcher command file references the separate task file and uses a
unit-bearing timeout, for example
`agy --prompt @/exact/task-owned-prompt-file --print-timeout 420s`.

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
