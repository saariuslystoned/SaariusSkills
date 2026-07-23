# Transport schema

Herdr-Puppet uses three versioned JSON records:

- `herdr-puppet.plan.v1`: source-only intent plus the explicit parent
  capability.
- `herdr-puppet.lease.v1`: exact owned tab/pane/terminal/SSH identity and the
  next legal send sequence.
- `herdr-puppet.event.v1`: append-only controller journal event.

The JSON Schemas in this directory are normative for their public fields:

- [plan.schema.json](plan.schema.json)
- [lease.schema.json](lease.schema.json)
- [event.schema.json](event.schema.json)

## Plan lifecycle

`plan` is non-mutating. A plan is usable only when its doctor and workspace
observations match live Herdr state. Creating a tab changes `state` from
`planned` to an independently stored lease with `state: active`.

## Lease lifecycle

A lease binds:

```text
session
workspace_id
tab_id
pane_id
terminal_id
ssh.pid
ssh.argv
ssh.target
next_seq
```

The lease file is updated atomically after a successful `pane.send_input`. A
caller supplies the expected sequence; equality with `next_seq` is mandatory.
The controller sends `text` plus `keys: ["enter"]` as one newline-delimited
JSON request to the exact, current-user-owned Unix socket bound in the lease.
It rechecks the socket file identity after connecting and before dispatch.
That inode check narrows path-replacement races; it does not prove a native
Herdr server incarnation. A lost, malformed, or mismatched acknowledgement is
an unknown delivery outcome. Never retry that sequence: stop and use
`qualification-reconcile-send` only after independent evidence establishes
that the original input was applied.
Non-empty prompt content is accepted only through standard input or a UTF-8
file, with a 256 KiB limit; empty or whitespace-only input is rejected before
socket access. Prompt content never appears in the controller or Herdr process
argument vector. The controller never writes or copies prompt content, so
callers own the lifecycle of any input file. If an orchestration bridge cannot
reliably half-close stdin, avoid a long canonical-PTY paste: create one private
task-owned input file, use `--text-file`, require the exact sequence
acknowledgement, and remove only that file immediately afterward. This proves
input acceptance only, not shell or harness execution.

`lease-preserve` atomically changes an active lease to `preserved`, records one
bounded reason, and performs no Herdr mutation. A preserved tab remains visible
but cannot receive controller input.

Do not infer a missing ID or repair a mismatch by searching labels. Recovery
remains disabled until remote-process adoption and crash behavior are
qualified.

Herdr 0.7.3 does not expose native server-incarnation identity. The records
therefore state `incarnation_proven: false`; reconnect or handoff invalidates
the live lease until full structural requalification.

## Journal lifecycle

The controller journal is append-only JSONL. Store:

- timestamps, command names, result classifications, and sequence numbers;
- exact structural IDs needed to diagnose authority joins;
- prompt or nonce hashes rather than prompt/response content;
- strict checkpoint classes rather than contract-beacon text;
- concise operator observations and improvement candidates.

Do not store pane text, scrollback, environment values, credentials, account
identifiers, or auth logs. Curate and redact a separate public proof before
committing any dogfood result.
