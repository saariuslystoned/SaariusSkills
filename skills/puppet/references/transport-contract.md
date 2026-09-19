# Puppet caller and transport contract

This supersedes PR #10's tmux/Herdr dual-backend design against the current
controller. Authentication, checkpoints, proof, review, acceptance, and
human gates remain transport-independent. A run binds one named transport
before launch and never silently falls back.

## Named transports

| Id | Role |
| --- | --- |
| `tmux` | Portable implemented default. Private socket, exact pane/process birth, ticketed read-only attach. |
| `herdr` | Named and unsupported as a Puppet run transport. Experimental Herdr-Puppet remains a separate skill. |
| `acp` | Named and unsupported. Later Cursor/Grok ACP admission is a later stage. |
| `agy-print` | Implemented structured AGY transport. Observed model, workspace, terminal result, conversation/session resume, owned process-tree halt, and the deterministic start/resume/result/halt lifecycle are proved from runtime metadata plus a process-identity fixture. Live AGY is not claimed. |

Requesting an unimplemented id refuses. Missing tmux does not select Herdr,
ACP, or `agy-print`. Requesting `agy-print` never falls back to tmux.

## Capability and proof

The table in [adapter-contract.md](adapter-contract.md) is the canonical
per-transport proof matrix. Tmux `status` infers liveness from pane and
registered process identity; it does not prove a harness turn result.
Tmux halt proves the registered PID is gone and the pane is dead. Tmux
resume remains unsupported. `agy-print` `status` proves observed model,
workspace, worker terminal/result, and conversation/session identity from
structured runtime metadata. `agy-print` halt proves the owned PID/birth
and confined process tree; a reused, stale, or ambiguous identity fails
closed and is never signaled. `agy-print` resume proves matching session and
conversation identity; a selector or path alone is not resume. Deterministic
lifecycle qualification covers start/bind, matching resume, terminal result,
distinct worker completion, controller acceptance, confirmed halt, and a
bounded final outcome. A process fixture may prove that path. Live AGY is
not claimed.

Puppet owns fresh kernel birth identity and stop/escalation. A caller may
not signal a stale or foreign PID, attach as the controller, or treat a
worker-written file as acceptance.

## Caller outcomes

`plan`, `doctor`, `launch`, `status`, `accept`, and `halt` expose the same
caller fields:

- `transport` — `{schema: puppet.transport-binding/v1, id}`
- `progress_cursor` — monotonic `{checkpoint_id, beacon_sequence, validated_at}`
- `caller_outcome` — distinct `worker_completion`, `controller_acceptance`, and `halt`
- `final_outcome` — bounded speak-safe summary once acceptance or confirmed halt exists

Worker completion means a validated checkpoint id is present. Controller
acceptance is only `ACCEPTED` (`SOURCE_ACCEPTED` is not terminal). Halt
confirmed is `HALTED` after exact owned-target proof. These three states
are never collapsed.

## Actionable blockers

Doctor keeps the existing string `blockers` list and adds
`caller_blockers` with `code`, `changed`, `remedy`, and optional
`pid` / `kernel_birth_id` / `pane`. CLI errors include the same blocker
object when present. Bodies, pane text, and transcripts stay out.

## Qualification evidence

Stage-1 `puppet.qualification-scope/v1` is unchanged: harness, shared
transport/authority, and task scopes stay separate. Adding this contract
to the shared source list is a deliberate shared-authority invalidation.
Splitting tmux settle out of that shared fingerprint waits for a second
implemented transport.
