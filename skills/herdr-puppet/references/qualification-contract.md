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
6. independently prove the harness input surface is ready;
7. send one bounded task prompt with the next lease sequence;
8. use one generated nonce checkpoint;
9. prove client detach/reattach without changing the leased identities;
10. preserve and inventory the tab at the terminal milestone;
11. record gaps and improvement candidates without copying transcript text.

## Prompt mode

Ordinary AGY turns are plain messages. Herdr-Puppet must not add a slash command
unless the operator chose that command for the specific turn.
When the operator chooses a plugin slash command, preserve that exact prefix
for the turn. Do not infer plugin activation from earlier turns.

`/teamwork-preview` is not a stronger form of an ordinary prompt. It is a
separate high-fan-out profile for an intentional hierarchy of roughly 4-20
helpers. Use it only with an explicit helper cap, one AGY root/integration
writer, disjoint helper contracts, terminal/accounted joins, timeouts, and
exact cleanup proof. Never use it for a single-owner preflight, routine
follow-up, status request, or gate acknowledgement.

## Harness readiness

Treat a successful `qualification-send` receipt as pane transport acceptance
only. Before the first real task, require independent readiness evidence from
the operator observing the exact leased tab's ready input surface, a bounded
harness-specific token that cannot appear until input is ready, or a unique
task-owned readiness artifact written by a harmless no-target preflight. Bind
an artifact to the run nonce and source identity, require it to state that the
target was untouched, and check its exact path rather than scanning a broad
run directory. A product name or banner is startup evidence, not input
readiness. Waiting a fixed number of seconds, counting a process, seeing an SSH
client, or finding no receipt file does not prove readiness.

If a launch send lands before the harness is ready, do not immediately resend
the task. Reconcile from independent operator or structural evidence, then use
the next sequence only when duplicate execution is ruled out. Journal the
lesson without copying the prompt or pane.

Plan status and lease status serve different lifecycle moments. Use
`status --plan-json` before `qualification-create-tab`. After a successful
create, the plan's owned label must exist, so plan status is expected to reject
reuse; use `status --lease-json` or `maintenance-checkpoint` for every
post-create structural check.

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

Herdr 0.7.3 returns the bounded matched window to the controller process; the
skill cannot make that native response transcript-blind. Qualification waits
therefore keep the window small, hold it only in memory, extract the strict
match, and discard the response without stdout or journal exposure.

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

The controller subprocess timeout is a hard cap independent of Herdr's native
wait timeout. A native or controller timeout returns `not_matched` and records
only which timeout boundary fired.

`not_matched` is narrowly scoped evidence: no strict checkpoint line matched
inside the bounded wait. It does not mean input delivery failed, the remote
worker went offline, SSH exited, the harness stopped, or a human gate exists.
Do not convert it into any of those claims. Recheck structural status and
independent source/proof artifacts without reading the transcript; then
preserve or supersede the run instead of speculatively resending the same
prompt.

A validated terminal artifact may independently prove that the bounded task
completed. In that case, record the artifact verdict, run
`lease-preserve --reason milestone_complete`, and continue exact cleanup if it
was authorized. Do not report the beacon as matched, and do not synthesize a
`DONE` checkpoint that Herdr did not observe.

The native waiter scans existing recent content before subscribing to new
output, so every checkpoint nonce must be unique per send. Matching is
line-based and does not itself prove output happened after the wait began.

`DONE` and `ACTION_REQUIRED` are terminal for the lease and automatically
preserve it. An operator who directly reports the exact nonce line from the
exact owned tab is also terminal authority: journal that bounded observation
and preserve immediately. Process liveness, receipt polling, or the absence of
a receipt cannot override the checkpoint.

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

At every terminal controller stop, run `maintenance-checkpoint`. Preservation
is local and non-destructive: it keeps the Herdr tab visible while making all
later send, reconcile, probe, and beacon operations fail closed. Maintenance
classifies exact leased resources and routes cleanup; it does not perform it.

## Harness posture and tab lifecycle

Herdr transport qualification never implies YOLO or auto-approval behavior in
the target harness. The caller must separately authorize and pass the exact
harness flag for the bounded launch. The controller journal records transport
identity and sends; it does not reinterpret that flag as push, merge, deploy,
secret, account, device, or cleanup authority.

Closing a completed, failed, or gated tab is also separate from
`lease-preserve`. When the operator authorizes closure, first preserve the
lease, then use `cleanup-preserved-tab` with the exact leased tab ID repeated
as confirmation. The command verifies exact tab and pane absence plus absence
of the leased foreground SSH PID. PID reuse blocks verification. It does not
claim independent proof for remote
harness descendants that were never recorded. Do not add generic close/reap
behavior to qualification, and do not target by label, process name, age, or
focus.
