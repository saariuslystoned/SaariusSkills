# Qualification contract

## Scope

Qualification is a temporary evidence mode for proving the transport. It is not
ordinary operation and does not make an arbitrary operator tab controller-owned.

The first useful dogfood run should:

1. pass `doctor` and create a non-mutating plan;
2. initialize an append-only controller journal;
3. create exactly one new tab in the authorized workspace;
4. verify the exact tab, pane, terminal, and foreground SSH target;
5. start one harness only after its own runtime posture is separately approved;
6. send one bounded task prompt with the next lease sequence;
7. use one generated nonce checkpoint;
8. prove client detach/reattach without changing the leased identities;
9. preserve the tab when persistence is requested;
10. record gaps and improvement candidates without copying transcript text.

## Prompt mode

Ordinary AGY turns are plain messages. Herdr-Puppet must not add a slash command
unless the operator chose that command for the specific turn.

Herdr-Puppet never selects or injects `/teamwork-preview`. Teamwork and
custom-agent behavior are separate capability research, not a stronger
transport mode. An independently admitted experiment may pass an explicitly
chosen native command as opaque caller content, but its topology, joins, and
results do not become Herdr-Puppet qualification evidence.

## Checkpoint and token waits

`qualification-beacon-wait` and `qualification-token-probe` are the only
transcript-aware operations in the initial skill. Both use Herdr's blocking
`wait output` primitive and must:

- require `--allow-live-qualification`;
- operate on the exact leased pane;
- wait with bounded recent lines and a finite timeout;
- compare against one caller-provided nonce;
- emit only match state and hashes;
- never emit or persist surrounding pane text.

The normal controller loop uses `qualification-beacon-wait`. In each task
prompt, assign one unique nonce and require exactly one terminal line:

```text
HERDR_PUPPET_STATUS <nonce>
HERDR_PUPPET_ACTION_REQUIRED <nonce>
HERDR_PUPPET_DONE <nonce>
```

The waiter uses an anchored regular expression, validates the returned line
again, emits only the checkpoint class, and journals only that class, the
revision, and a nonce hash. `ACTION_REQUIRED` is a human gate. The lower-level
token probe is for transport diagnosis and reports only match/no-match.

The native waiter scans existing recent content before subscribing to new
output, so every checkpoint nonce must be unique per send. Matching is
line-based and does not itself prove output happened after the wait began.

## Dogfood review

Review `events.jsonl`, `STATE.md`, and `PROOF.md` from the controller run root.
Classify observations as:

- `keep`: promote a repeatable behavior or guard into the skill;
- `repair`: fix a concrete failure before the next send;
- `defer`: preserve a useful idea outside the current slice;
- `reject`: do not encode a one-off workaround;
- `human_gate`: stop for additional authority.

Do not treat an AGY response or a clean visual tab as sufficient proof. Join
behavior to the exact lease, sequence, nonce checkpoint, source commit, and
redacted run packet.

At a human gate or other terminal controller stop, run `lease-preserve`.
Preservation is local and non-destructive: it keeps the Herdr tab visible while
making all later send, reconcile, probe, and beacon operations fail closed.
