# Qualification contract

## Scope

Qualification is a temporary evidence mode for proving the transport. It is not
ordinary operation and does not make an arbitrary operator tab controller-owned.

The first useful dogfood run should:

1. pass `doctor`, resolve one named destination, and create a non-mutating
   fresh-tab plan with a sanitized selection receipt;
2. initialize an append-only controller journal;
3. create exactly one new tab in the authorized workspace;
4. verify the exact tab, pane, terminal, and foreground SSH target;
5. submit one harmless shell STATUS preflight through atomic `pane run`;
6. observe its unique STATUS beacon before any follow-on submission;
7. compare a fresh in-row census with one controller-attested harness binding
   (for Claude: `harness_census.py` requires `--run-id`, an absent
   `--claude-hook-root`, the source-owned helper, exact interpreter identity,
   derived `settings_sha256`, and native lifecycle observation bound into
   `herdr-puppet.harness-binding.v3`);
8. for Claude, register all eight possible marker-file paths before launch;
9. start one canonical harness through the dedicated regular launch operation;
10. for Claude, validate and journal the `armed` SessionStart receipt;
11. handle only an exact observed allowlisted pre-readiness startup gate;
12. independently prove the harness input surface is ready;
13. send one bound wrapped task prompt through one atomic `pane.send_input`
    request; use two `enter` keys only for multiline Claude submits and one
    `enter` for all other submits;
14. for Claude, require a bound `initial` receipt with UserPromptSubmit plus
    Stop or StopFailure; only `response_completed` permits steering;
15. send one separately sequenced steering turn and, for Claude, require its
    bound `steering` receipt;
16. use one generated terminal nonce checkpoint;
17. prove a real client detach/reattach without changing leased identities;
18. preserve and inventory the tab at the terminal milestone;
19. record gaps and improvement candidates without copying transcript text.

## Prompt mode

Ordinary AGY turns are plain messages. Herdr-Puppet must not add a slash command
unless the operator chose that command for the specific turn.
When the operator chooses a plugin slash command, preserve that exact prefix
for the turn. Do not infer plugin activation from earlier turns.

Earlier AGY 1.1.7 diagnostics used a task-owned prompt file and an explicit
unit-bearing timeout such as
`agy --prompt @/exact/task-owned-prompt-file --print-timeout 420s`. That shape
is historical evidence, not a supported controller recipe. This version
rejects every harness launcher submitted through `qualification-run`,
including a non-`exec` AGY `--print` command, before Herdr mutation. A supported
noninteractive path requires a separate controller-attested operation with
registered task-file authority, its own sequence and terminal-evidence
contract, and exact removal proof. Until then, use only regular interactive
qualification and do not improvise a `--print` carve-out.

`qualification-run` accepts command text only from `--text-file` or standard
input. The controller therefore keeps command content out of its own argument
vector. Herdr 0.7.3 itself defines `pane run <pane_id> <command>`, so the
downstream Herdr process necessarily receives the bounded command argument.
The adapter redacts that argument from every error and records only its hash.
It does not emit Herdr stdout in the receipt.

`qualification-send` receipts and events record redacted submit metadata
(`submit_key_count` and `submit_key_vector`) to make the key protocol
inspectable without exposing prompt text.

`/teamwork-preview` is not a stronger form of an ordinary prompt. It is a
separate high-fan-out profile for an intentional hierarchy of roughly 4-20
helpers. Use it only with an explicit helper cap, one AGY root/integration
writer, disjoint helper contracts, terminal/accounted joins, timeouts, and
exact cleanup proof. Never use it for a single-owner preflight, routine
follow-up, status request, or gate acknowledgement.

## Atomic shell preflight

Use this exact order before the regular interactive lifecycle:

0. keep `plan.json` outside the intended run root; `journal-init` owns creating
   the absent run root and fails closed if it already exists; pass the plan's
   exact `proof_root` as that run root, because alternate or copied roots are
   rejected;
1. submit a harmless shell STATUS command through `qualification-run`;
2. wait for its unique strict STATUS beacon with
   `qualification-beacon-wait --lines 80 --timeout-ms 480000
   --timeout-seconds 510`.

The first matching STATUS checkpoint satisfies the controller's follow-on
shell-submission gate and advances `shell_readiness` only. It proves only that
the shell command emitted that exact beacon; it does not advance
`harness_readiness` or authorize `qualification-send`. A successful `pane run`
API acknowledgement alone does not prove the shell consumed the command, that
AGY started, that the harness accepted the task, that MCP is ready, or that
execution completed. The run receipt therefore records
`submission_mode: atomic_shell_command` and `execution_acceptance: unverified`.
If the first wait records no checkpoint, the controller may accept one
sequence-2 retry only when the new command is the exact canonical standalone
shell STATUS `printf`, the same initialized journal contains exactly one
successful sequence-1 submission classified as that same strict STATUS probe
plus its failed wait, and no harness launch or readiness transition exists.
The run receipts record `shell_status_probe`, and the retry additionally
records `shell_status_retry: true`. It cannot be used for arbitrary shell
input or repeated at sequence 3.

Ordinary interactive harness prompts remain on `qualification-send`; do not
replace them with shell commands.

## Five-harness regular rows

A campaign row is regular and interactive only when its canonical harness ID
is one of `agy|codex|claude|cursor|grok`, its plan and lease reference one
controller-attested binding, and the runtime launch uses
`qualification-harness-launch`. The binding includes the current remote
executable/version/help fingerprints, an enrolled dedicated-user profile route
for non-cursor rows or a Cursor provisional `interactive_pending` + `null`
status pair before launch, current default model/effort observation or honest
`unavailable` except AGY's explicit `gemini-3.7-flash-high`, the unrestricted launch-vector
hash, controller adapter and protocol fingerprints, exact worktree, instruction
plane, and explicit unsupported capability values. The active schema is
`herdr-puppet.harness-binding.v3`. Historical v1/v2 bindings are historical
evidence only and must be superseded by fresh census/replan; do not synthesize
v1 for live runs. Their frozen validator remains available only so an existing
canonical leased row can be inspected, preserved, inventoried, and closed
through exact owner cleanup without stranding its tab.

For Cursor, `interactive_pending` is a deliberate pre-launch state. The census
skips Cursor's auth/status command rather than triggering account or Keychain
access. It does not claim enrollment, and its zero process exit means only that
body-free evidence collection completed. Cursor remains blocked from ordinary
sends until the exact regular launch, Workspace Trust operation, and
operator-observed ready input all succeed. Login, account, or credential UI is
a human gate.

The binding census happens before plan creation. For Claude, choose `run-id`
before plan creation and pass the same `run-id` plus absent
`--claude-hook-root` through census; later row verification uses that lineage.
Each row repeats the current remote census from inside its new leased Herdr pane
after shell STATUS. Use
`harness_census.py --output <exact-task-file> --checkpoint-nonce <nonce>` so
the helper creates the output once, fsyncs it, and emits a strict STATUS only
after the JSON is complete. Wait for that exact beacon before copying out the
sanitized census artifact, then run `harness-census-verify`. Shell redirection
is not completion proof and can expose an empty-but-existing file.
Authentication stores, status bodies, environment
dumps, and raw output are never copied. A timestamp may advance; any bound
fact mismatch fails the row before launch.

For Claude, the hook marker root must be absent before census.
Before launch, register all eight task-owned marker files under that marker root:

- `session_start-0001.json`
- `user_prompt_submit-0001.json`
- `user_prompt_submit-0002.json`
- `stop-0001.json`
- `stop-0002.json`
- `stop_failure-0001.json`
- `stop_failure-0002.json`
- `overflow.json`

After launch, use `qualification-claude-receipt-command` to derive the exact
isolated observe command from the current lease. Its settings-embedded
bootstrap verifies the resolved running interpreter plus the bound interpreter
and helper bytes before executing the helper; the helper then verifies the
bound implementation bytes. Execute that generated command
without alteration over the exact leased SSH target, copy only its bounded
sanitized JSON to a caller-owned local file, and validate that file through
`qualification-claude-lifecycle-observe`. The exact route provides operational
provenance; receipt validation proves internal binding and sequence
consistency, not cryptographic remote origin.

Every form of `exec <harness>` is forbidden because replacing the leased shell
can remove foreground SSH identity. Generic direct launch through
`qualification-run` is also forbidden after shell readiness. The bound
dedicated launch is exactly once, at the next sequence, and unrestricted. AGY
alone carries the exact `--model gemini-3.7-flash-high` selector proven by its
help token and first TSV model cell. The launch uses `/usr/bin/env -i`, then supplies
only the census-bound `HOME`, deterministic system/Homebrew `PATH`, `LANG`,
`LC_ALL`, and `TERM`. `inherit_environment: false` is part of the hashed
launch vector, so controller, prior-agent, and Herdr variables cannot silently
select another profile or contaminate the qualifying process.

## Startup gates and instruction plane

Startup-gate handling is pre-readiness, sequence-bound, exact-worktree-bound,
single-use, and controller-attested by an operator. Cursor Workspace Trust
must have either its exact allowlisted acceptance or a recorded
`not_present` result before ordinary readiness. Codex and Claude trust,
security acknowledgement, or bypass confirmation may be handled only when the
operator sees that exact surface and the task-owned worktree and unrestricted
posture are already authorized. Only the bounded key vectors defined by the
controller may be sent. Login, enrollment, account selection, credentials,
and unrelated UI are never startup gates.

Strict checkpoint matching treats leading or trailing horizontal space, tabs,
and non-breaking spaces added by an interactive TUI as presentation padding.
After operator-verified harness readiness, Codex's native assistant line may
additionally carry exactly one leading U+2022 bullet followed by horizontal
separation. That exception is harness- and readiness-scoped; shell checkpoints,
other bullets, inline prose, or non-whitespace decoration remain non-matches.
After removing only the admitted presentation marker and edge padding, the
logical line must still be exactly `HERDR_PUPPET_<CLASS> <nonce>`. Matching is
deliberately line-local: surrounding lines neither strengthen nor invalidate an
otherwise canonical checkpoint line. Submitted prompts may not contain an
assembled checkpoint token.

Create the first message with `instruction-wrapper-create`. Its manifest binds
the universal, harness-specific, harness-selected model (AGY's explicit Gemini
3.7 layer or default-unresolved for other harnesses), and regular lifecycle
layers to the binding fingerprint, run ID, initial-message plane, and rendered
body hash. The first `qualification-send` must carry that manifest. The separate
steering turn uses a later lease sequence and an ordinary private text file with
no manifest. Before a non-Claude steering send, a
controller-observed STATUS beacon must bind to the initial send sequence.

## Claude native lifecycle proof

Claude rows use `qualification-claude-lifecycle-observe` instead of generic
checkpoint-only send proof. Each send phase must be observed in order:
`armed` after launch before the initial prompt, `initial` after initial prompt and
before steering, `steering` after steering prompt.

The lifecycle observation includes one `session_start`, up to two
`user_prompt_submit`, up to two `stop`, and up to two `stop_failure` markers.
An eighth `overflow.json` sentinel invalidates the receipt if any extra or
conflicting hook event appears. All marker paths are expected under the exact
run-bound hook root and are
registered before launch. The row validates the receipt locally from `--receipt-json`
against the leased `harness_binding`; only the expected sequence and count
transitions advance.

Receipt and helper policy intentionally rejects prompt retention. The
UserPromptSubmit hook reads its bounded hook JSON only in memory, hashes the
`prompt` field, and retains neither the raw input nor prompt. SessionStart,
Stop, and StopFailure leave hook stdin unread. The helper never opens the
transcript path, emits nothing for record operations, and reports
`stdin_read: true` only after at least one prompt fingerprint was recorded.
The helper and implementation are source-owned, while the interpreter identity
and derived settings are hash-bound. Native hook handlers use isolated Python
`-I -c`: the settings-embedded bootstrap checks the resolved running
interpreter path and hashes the bound interpreter and helper before compiling
the helper, and the helper opens and hashes the implementation before
compiling it. The same generated bootstrap route is mandatory for receipt
observation; direct execution of the worktree helper is not qualifying
evidence. The controller requires prompt fingerprints to equal the exact
sequenced send history.
`response_completed` means the native Stop hook fired for that phase. It does
not prove instruction compliance, the requested checkpoint, or task success;
the strict terminal beacon remains separate.
After terminal lifecycle proof and route completion, move the exact run-bound
marker root recoverably when cleanup is authorized, verify every registered
path is absent, and record that removal evidence through maintenance.

`qualification-reconcile-send` is unsupported for Claude lifecycle rows; when a
send outcome is uncertain, preserve the row and start a fresh bounded run.

Every interactive send is first recorded in the canonical lease as an exact
`pending_or_unknown` reservation while the lease lock is held and before Herdr
input. An acknowledged send is then promoted to the bounded
`interactive_sends` ledger and advances `next_seq`. A crash, timeout, or write
failure that leaves the reservation pending blocks replay. Reconciliation is
limited to the exact pending second steering send on a non-Claude row, after
one wrapped initial send, controller-observed initial consumption, and
independent proof that the steering text was applied. It performs no Herdr
mutation. Pending initial sends and all pending Claude sends require
preservation and a fresh row.

Shell run, harness launch, and startup-gate operations likewise carry one
`pending_sequence_operation` reservation before Herdr mutation. Finalization
clears it and advances the sequence. Any interruption or failed final write
leaves delivery unknown and blocks further qualification mutation; preserve
the row rather than replaying the command, launch, or key vector.

## Harness readiness

Treat a successful `qualification-send` receipt as pane transport acceptance
only, and a successful `qualification-run` receipt as Herdr CLI acceptance
only. Before the first interactive task, record the operator's observation of
the exact leased tab's ready input surface through
`qualification-harness-ready`. Bind the transition to the exact leased repo
and worktree, an explicit operator identity, bounded
`operator_observed_ready_input` evidence, and `--confirm-ready`. The command
requires shell readiness and rechecks structural identity before advancing
`harness_readiness` to `operator_verified`. `qualification-send` requires that
state even for sequence 1. A shell STATUS, product name, banner, fixed wait,
process count, SSH client, or missing receipt file does not prove harness
readiness. `qualification-run` never launches a harness; noninteractive AGY is
unsupported in this version.

If a launcher submission lands before the harness is ready, do not immediately
resubmit the task. Reconcile from independent operator or structural evidence,
then use the next sequence only when duplicate execution is ruled out. Journal
the lesson without copying the prompt or pane.

Plan status and lease status serve different lifecycle moments. Use
`status --plan-json` before `qualification-create-tab`. After a successful
create, the plan's owned label must exist, so plan status is expected to reject
reuse; use `status --lease-json` or `maintenance-checkpoint` for every
post-create structural check.

## Native view and detach/reattach

`qualification-view-begin` records the operator-observed native TUI and hashes
the exact leased session/workspace/tab/pane/terminal/SSH identity. The
controller must then detach and reattach a real task-owned Herdr client.
`qualification-view-complete` accepts the same nonce and operator only after
that real action and only when a fresh structural join yields the unchanged
identity hash. The record pair is not a substitute for the client action.

## Checkpoint and token waits

`qualification-beacon-wait` and `qualification-token-probe` are the only
transcript-aware operations in the initial skill. Both use Herdr's blocking
`wait output` primitive and must:

- require `--allow-live-qualification`;
- lock and reload the exact canonical lease before any pane read;
- reject a stale caller payload before reaching Herdr;
- operate on the exact leased pane;
- wait with bounded recent lines and a finite timeout;
- compare against one caller-provided nonce;
- emit only match state and hashes;
- never emit or persist surrounding pane text.

Herdr 0.7.3 returns the bounded matched window to the controller process; the
skill cannot make that native response transcript-blind. Qualification waits
therefore keep the window small, hold it only in memory, extract the strict
match, and discard the response without stdout or journal exposure.

The normal controller loop uses `qualification-beacon-wait`. Assign one unique
nonce per task and require exactly one terminal line with one of these shapes:

```text
HERDR_PUPPET_STATUS <nonce>
HERDR_PUPPET_ACTION_REQUIRED <nonce>
HERDR_PUPPET_DONE <nonce>
```
<nonce> is limited to safe identifier characters and a length of 8-24.
For harness input, give the nonce and the output composition rule separately;
never place the fully assembled token containing the real nonce in the submitted
prompt. `qualification-send` rejects such a token before pane mutation. This
prevents a TUI-rendered user prompt from satisfying the output watcher. The
shell `qualification-run` path may still emit an assembled line because its
quoted `printf` command does not render that line standalone before execution.

The waiter uses an anchored regular expression, validates the returned line
again, emits only the checkpoint class, and journals only that class, the
revision, and a nonce hash. `ACTION_REQUIRED` is a human gate. The lower-level
token probe is for transport diagnosis and reports only match/no-match. Both
waiters snapshot the complete disk lease revision under its exact sibling
lock, release the lock for the blocking wait, then reacquire and reject any
revision change before journaling or returning. The token probe consumes no
beacon attempt.

The controller subprocess timeout is a hard cap independent of Herdr's native
wait timeout. The standard long-running qualification watcher uses a 480000 ms
native wait and a 510 s controller cap. A native or controller timeout returns
`not_matched` and records only which timeout boundary fired.

`not_matched` is narrowly scoped evidence: no strict checkpoint line matched
inside the bounded wait. It does not mean input delivery failed, the remote
worker went offline, SSH exited, the harness stopped, or a human gate exists.
Do not convert it into any of those claims. One re-wait is allowed with the
same nonce only while the lease still identifies the same submission. The
second `not_matched` exhausts that nonce; a matched STATUS, DONE, or
ACTION_REQUIRED also makes it terminal. Cross-sequence reuse and a third wait
are rejected. Before each Herdr wait, the controller durably reserves the
attempt in the journal while holding the exact lease lock. Reservations, not
only completed results, consume the two-attempt allowance, so concurrent
waiters cannot all pass the cap and an interrupted wait fails closed. Final
processing requires the exact unique reservation. The journal is bound to the
plan proof root, so a caller cannot obtain another two attempts by copying the
same-run journal elsewhere. Recheck structural status and independent
source/proof artifacts without reading the transcript; never speculatively
resend the same prompt.

A validated terminal artifact may independently prove that the bounded task
completed. In that case, record the artifact verdict, run
`lease-preserve --reason milestone_complete`, and continue exact cleanup if it
was authorized. Do not report the beacon as matched, and do not synthesize a
`DONE` checkpoint that Herdr did not observe.

The native waiter scans existing recent content before subscribing to new
output, so every checkpoint nonce must be unique per submission. Matching is
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
- `repair`: fix a concrete failure before the next submission;
- `defer`: preserve a useful idea outside the current slice;
- `reject`: do not encode a one-off workaround;
- `human_gate`: stop for additional authority.

Do not treat an AGY response or a clean visual tab as sufficient proof. Join
behavior to the exact lease, sequence, nonce checkpoint, source commit, and
redacted run packet.

`qualification-create-tab` focuses only the exact tab it creates in the
plan-authorized workspace. Herdr 0.7.3 focus is server-owned, so the new
run-owned tab becomes the visible tab in that operator's isolated session.
This makes the run observable; it is not permission to navigate or adopt
pre-existing tabs.

At every terminal controller stop, run `maintenance-checkpoint`. If a remote
task file was registered, final maintenance must record its exact registered
path, explicit confirmation, and one bounded removal evidence class before tab
cleanup. Preservation is local and non-destructive: it keeps the Herdr tab
visible while making all later run, send, reconcile, probe, and beacon
operations fail closed.
Maintenance classifies exact leased resources and routes cleanup; it does not
perform it.

## Harness posture and tab lifecycle

Herdr transport qualification never implies broader YOLO or auto-approval
authority in the target harness. The caller must separately authorize the
bound unrestricted regular launch. The controller journal records transport
identity and submissions; it does not reinterpret that flag as push, merge,
deploy, secret, account, device, or cleanup authority.

Closing a completed, failed, or gated tab is also separate from
`lease-preserve`. When the operator authorizes closure, first preserve the
lease, then use `cleanup-preserved-tab` with the exact leased tab ID repeated
as confirmation. The command verifies exact tab and pane absence plus absence
of the leased foreground SSH PID. PID reuse blocks verification. It does not
claim independent proof for remote
harness descendants that were never recorded. Do not add generic close/reap
behavior to qualification, and do not target by label, process name, age, or
focus.
