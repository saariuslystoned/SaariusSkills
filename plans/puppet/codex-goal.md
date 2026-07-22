# Goal Packet: Build and Dogfood Puppet Autonomously

Use this entire document as the goal prompt for one Codex orchestration
campaign after the Puppet GrillTrack is cleanly closed. Submitting it as the
goal is the single bounded campaign authorization described below. This file by
itself does not authorize or launch anything.

## Objective

Build a public, portable `puppet` Agent Skill and companion Python CLI in a
fresh isolated worktree of the current SaariusSkills repository. Use the
public provenance map plus any separately authorized operator-local evidence as
design input, then dogfood Puppet by using real AGY, Cursor, Claude, Codex, and
Grok CLI harnesses one at a time to help finish, review, repair, and prove
Puppet.

Complete the campaign without routine questions or per-rung promotion
approvals. Finish with either:

1. a clean, locally committed, fully tested and evidence-backed Puppet skill
   and CLI, with every required real-harness probe complete; or
2. one precise blocker packet that identifies the failed gate, preserves all
   state and evidence, and names the next safe action.

Do not merge, push, deploy, globally install, delete, archive, spend, send
customer or non-test messages, change accounts or security, inspect or change
secrets, or perform any other external human-gated action.

## Campaign authorization and warning

Repository text grants no standing execution authority. When an operator
deliberately submits this packet as a Codex goal, supplies a campaign ID,
operator identity, and isolated worktree root, and records the local
acknowledgement below, that operator authorizes this one campaign to launch the
locally installed AGY, Cursor, Claude, Codex, and Grok harnesses in each
harness's current-version unrestricted, always-approve, YOLO, dangerous, or
equivalent mode, with the harness sandbox disabled wherever the installed CLI
exposes that control. The authorization covers only the bounded Puppet work and
conformance prompts in this packet.

Puppet is intentionally YOLO-only. Prompted or sandboxed target modes are not a
supported fallback. A disposable fixture bounds the assigned task and makes
drift detectable; it is not an operating-system security boundary. The target
has the access available to the submitting operator account.

Before the first live launch, record a non-secret local campaign
acknowledgement containing this scope and the campaign ID. The submitted goal
is the operator acknowledgement; do not ask for each harness or internal
promotion again within that exact campaign envelope.

The authorization includes the ordinary model-provider traffic caused by
these five explicitly named CLI harnesses and internal Puppet prompt/steering
messages. It does not authorize email, SMS/RCS, social posts, customer contact,
PR comments, issue comments, or any other external send. It also does not
authorize:

- merge, push, pull-request creation, release, deployment, publication, or
  global installation;
- purchases, paid resource changes, or spending beyond already configured
  model use;
- deletion, cleanup, archive operations, force pushes, or history rewriting;
- account, permission, security, token, credential, device, or service changes;
- reading, printing, copying, summarizing, diffing, or preserving `.env`
  contents, tokens, cookies, keychains, wallets, private keys, auth logs,
  credential stores, or auth-bearing shell history;
- interference with an existing harness, tmux session, worker, or operator
  process that was not created by this campaign.

Stop with a blocker rather than seeking broader authority during the unattended
run.

## Source of truth

Read applicable repository instructions before acting. Within the product
design, use this priority:

1. the curated GrillTrack decision record at `plans/puppet/DECISIONS.md` and
   closeout proof at `plans/puppet/PROOF.md`;
2. the reconciled implementation seed at
   `plans/puppet/implementation-seed.md`;
3. the curated provenance-and-delta map at
   `plans/puppet/prior-proof-provenance.md`;
4. current `SaariusSkills` repository instructions and tests;
5. separately authorized, exact, attributable operator-local evidence;
6. fresh controller-observed behavior from the installed CLIs.

If the seed conflicts with the curated decision record, the decision record
wins. Do not
revive superseded fake-harness qualification or per-promotion user approval.
Automatic model routing remains deferred; preserve explicit harness and model
selection while collecting neutral run evidence for a possible later feature.

## Entry conditions

Prove every entry condition before editing source or launching a harness:

- The curated GrillTrack decision record and proof are closed, contain no
  unresolved `needs_reverification` decision, and cover the current kernel,
  evidence, probe, trust, review, diagnostics, and promotion locks.
- Resolve the canonical checkout and remote from the active repository. Fetch
  the remote default and bind the base to its exact fresh commit.
- Create a new task branch and fresh isolated worktree using the active
  repository's branch and worktree policy. Do not edit any dirty primary
  checkout or unrelated worktree.
- Record the exact source repo, base commit, branch, worktree, campaign owner,
  campaign ID, proof root, and stop condition.
- Read the system skill-creator instructions completely and follow current
  SaariusSkills packaging, license, provenance, and test contracts.
- Use the active repository's safe-worktree workflow and an available worktree
  skill when applicable; do not improvise a main-checkout mutation.
- Confirm Python 3 and tmux are available. Run a zero-agent executable census
  for `agy`, `cursor-agent` and/or `cursor agent`, `claude`, `codex`, and `grok`.
- Confirm no conflicting process-store lock, target session, tmux identity, or
  worktree mutation owner exists. Never kill, rename, attach to, or repurpose a
  conflicting session. A conflict is a blocker unless it disappears through a
  bounded read-only recheck.
- Confirm the campaign root can atomically write its state and proof files.
- Confirm the current exact CLI versions expose a provable unrestricted-mode
  mapping and a prompt transport that keeps prompt bodies out of process
  arguments. A stale flag assumption or ambiguous mapping blocks that adapter.

If an entry condition fails, do not improvise around it. Produce the blocker
packet described below.

## Worktree and ownership contract

The main Codex orchestration session is the campaign controller and sole final
acceptance authority. It owns the campaign ledger, integration decisions,
promotion pointer, final branch, and final report.

Use one target and one mutation owner at a time. For every self-hosting rung:

- invoke controller commands only from a fixed, controller-owned Puppet
  release whose root, commit, tree hash, executable path, and executable hash
  were recorded before launch;
- give the target a different candidate worktree and branch based on the exact
  currently stable head;
- reject overlapping supervisor and candidate roots;
- never load controller code from the target-mutated candidate while that
  target session is live;
- preserve candidate worktrees and prior stable releases; do not clean them up
  during this campaign;
- allow a target to end useful work only in a bounded commit, structured
  checkpoint, review finding, proof artifact, or explicit blocker.

The supervisor is immutable for the full lifetime of each target session. A
mutable candidate worktree may never supervise anything. After its mutation
session ends, the controller may materialize its exact head as a separate,
read-only, fingerprinted qualification release and use that sealed release only
for bounded tests and real-harness conformance. It becomes the stable supervisor
only after those qualification sessions end and the promotion gate passes.

## Durable campaign state

Create one dedicated campaign run root in the isolated task area, following any
stricter repository hygiene contract. Keep these files current from preflight
through final report:

```text
STATE.md
events.jsonl
heartbeat
PROOF.md
```

Also preserve, as applicable:

```text
contract.json
state.json
evidence-admission.json
promotions.jsonl
adapter-census/
run-observations/
handoffs/
verdicts/
review-qualifications/
probes/
```

`STATE.md` must always name the current stable Puppet identity, active rung,
target, candidate head, last completed gate, current blocker, and next safe
action. `events.jsonl` and `promotions.jsonl` are append-only. State writes are
atomic. Refresh `heartbeat` throughout long work. `PROOF.md` indexes commands,
results, commits, evidence artifacts, verdicts, deferred risks, and stop reason.

Write one bounded `run-observations/<run-id>.json` for every zero-agent or live
run. It records requested and controller-observed harness, model, version, and
effort; task type/profile; latency; native turn/tool counts when safely exposed
or the literal state `unavailable`; checkpoint quality; repair-cycle count;
proof integrity; and controller verdict. Never infer missing native metrics
from a transcript, target claim, or brand stereotype.

Do not put prompts, transcripts, raw pane output, credentials, auth logs, source
copies, or arbitrary CLI logs into these files. Curate only bounded,
non-secret evidence. Keep machine-private run state out of the public commit;
commit a sanitized proof packet that preserves enough detail to reproduce and
audit every claim.

## Admit prior evidence before rebuilding

Do not treat Puppet as a greenfield wrapper. Before implementation, build an
explicit provenance-and-delta admission matrix. For each candidate source,
record:

- public source identity or, for separately authorized local evidence, a
  machine-private exact source identity, revision, date, and owner;
- invariant or behavior claimed;
- proof artifact and proof strength;
- whether the mechanism and relevant version still match;
- portability and operator-specific assumptions;
- license and attribution path;
- decision: `reuse_contract`, `extract_with_attribution`, `reimplement`,
  `design_input_only`, or `fresh_live_proof`;
- deterministic tests to rerun and the remaining live-proof delta.

At minimum, thoroughly inventory the public map and any separately authorized
operator-local evidence for:

- AGY/teamwork launch, steering, locks, checkpoints, and sanitized lifecycle
  metadata;
- Codex and Claude launch/worker lanes;
- current and historical Grok PTY/tmux buffer isolation, lane identity,
  checkpoint/commit protocol, interrupted synchronization, and any still-open
  local implementation branches;
- session-control proofs for one current runner, replacement fencing, viewer
  separation, exact input routing, output/event fanout, and explicit completion;
- generational one-live-session, attach, provenance, fencing, rollback, and
  exact-session lifecycle proofs;
- current `teamwork-preview` mechanics and its sanitized bridge hook;
- process identity, tmux session collision, exact halt, worktree isolation,
  proof packet, review, and exact-head acceptance patterns;
- Cursor's current installed CLI surface, recognizing that no admitted Cursor
  lane existed at GrillTrack time and its adapter therefore needs fresh proof.

Start with `plans/puppet/prior-proof-provenance.md`. If the submitting operator
separately provides private evidence roots, inspect them read-only and keep
their exact paths, revisions, topology, and raw proof machine-private. Do not
copy private or branch-only code merely because it exists. Stale, uncommitted,
branch-only, terminal-derived, operator-specific, or license-uncleared work
remains design input until its exact delta is revalidated. Commit only the
bounded public invariant, limitation, reuse decision, and proof delta.

Reuse proven contracts and tests where attribution and portability are clean.
Rerun deterministic tests against every extracted or reimplemented Puppet
component. Freshly prove every changed mechanism and the complete Puppet
composition. Prior proof accelerates the ladder; it does not let a current
adapter skip its real-harness probe.

## Required public deliverable

Build the canonical package under `skills/puppet/` using the repository's
current skill-creator conventions. The minimum Puppet N CLI surface is:

```text
doctor
launch
send
status
wait
checkpoint
review
accept
attach-command
halt
```

Puppet N must make `promote`, `close`, controller-side source-editing or
delivery commands, and unproved adapter behavior explicitly unsupported. Its
existing `launch` command may supervise a target contract that permits
`mutate` and `local_commit` only after the read-only AGY and independent-review
bootstrap gates pass, and only in the target's distinct candidate worktree.
Promotion during the self-hosting campaign is controller-owned campaign
machinery until a later proved Puppet command graduates.

The public package must include:

- a concise controller-neutral `SKILL.md`;
- the generated `agents/openai.yaml` metadata required by the repository;
- a standard-library Python CLI and small testable modules;
- references for the operating, adapter, checkpoint/handoff, trust, and prompt
  contracts without duplicating them throughout the skill;
- deterministic tests for state transitions, atomic/append-only state,
  identity binding, literal prompt transport, locks, checkpoint validation,
  controller-only verdicts, exact-head invalidation, supervisor/candidate
  separation, halt targeting, promotion records, and non-terminal diagnostic
  advisories that cannot independently produce a stop verdict;
- adapter manifests and implementation for AGY, Cursor, Claude, Codex, and
  Grok, initially hard-disabled beyond `doctor` until their real probe passes;
- a prominent YOLO-only warning in `SKILL.md`, the root README summary, doctor
  output, and relevant install guidance;
- provenance and third-party notices for admitted material;
- sanitized, committed proof for this campaign.

Do not add a duplicate README inside `skills/puppet/`. Do not bake an
operator's paths, standing authorization, accounts, model preferences, or
private proof into public defaults. Local policy may bind the submitting
operator's campaign authorization; the portable package must require every
operator to acknowledge YOLO mode for themselves.

The root README must keep the promised tongue twister:

> Puppet uses agents like puppets to build Puppet—the skill that uses agents
> like puppets.

It may follow with the plainer explanation: “Puppet uses supervised agents to
build the system that supervises agents.”

## Two-pass adapter factory

Implement one reusable adapter factory, not five unrelated wrappers.

### Pass A: zero-agent census

Pass A must not launch or resume an agent. For each allowlisted executable:

1. Resolve the exact command, real path, file identity/hash, version, help
   surface, platform, and prior-evidence references.
2. Discover current model/effort controls, prompt-file/stdin or interactive
   transport, session/resume identity, status surface, and exact unrestricted
   mode flags without reading credentials or transcript stores.
3. Determine how to disable tool prompts and the harness sandbox. Do not infer
   a mapping from another version or another harness.
4. Generate a fingerprinted capability manifest and a hard-disabled
   doctor-only adapter.
5. Mark every behavioral capability unproved until Pass B observes it against
   this exact executable, adapter implementation, and probe-protocol
   fingerprint.

Static help text, prior evidence, and a target's own claims may populate
candidate capabilities. They may not enable `launch`, `send`, `status`,
`wait`, `checkpoint`, resume, or `halt`.

Build a version-scoped diagnostic taxonomy into the manifest. Keep structural
process/transport liveness, controller-validated protocol progress, target
checkpoint claims, harness advisories, provider execution errors, and terminal
failures separate. Do not halt, diagnose, or declare a blocker from a banner or
badge alone. A dated, untrusted operator fixture records that AGY's display
`Gemini 3.6 Flash · high · AI: Out of credits` referred to AI overage credits,
not subscription exhaustion or task failure, in the observed local setup. Do
not stop from it alone. Freshly validate the interpretation against the current
executable/provider surface before normalizing it as
`agy_ai_overage_credits_exhausted`, and require separate controller-observed
failure evidence for any terminal verdict. Never scrape terminal content to
detect it. Treat future harness quirks the same way:
source them explicitly, scope them to an executable fingerprint, and
revalidate rather than generalize.

### Pass B: real-harness conformance

Run the same bounded behavioral contract against the real installed CLI. Fake
harnesses, mocked targets, or model self-reports do not qualify an adapter or
count as product proof. Pure kernel logic may use deterministic unit tests,
property tests, and controlled fault injection, but all adapter and end-to-end
claims require the real harness.

Run only one real harness at a time. AGY must be first. Every one of AGY,
Cursor, Claude, Codex, and Grok must pass before campaign acceptance; the order
after AGY may change only to establish an independent proved review rail. Never
skip a harness because its prior proof looks strong.

Every Pass B launch must:

- use the exact Pass A fingerprint and proved YOLO mapping;
- run in a fresh disposable fixture with no protected source mutation;
- use a unique controller-created run ID, nonce, and strict schema;
- deliver prompts through stdin, a protected prompt file, or literal tmux
  buffer input, never as a process argument;
- bind the exact executable, process start identity, tmux server/session/pane,
  controller, adapter, and protocol fingerprints;
- expose only sanitized process/lifecycle metadata to Puppet;
- preserve a read-only human attach command without having Codex attach;
- finish with an exact graceful halt of only the registered target while
  preserving the tmux evidence session.

## Shared real-harness prompt contract

The behavioral contract and checkpoint schema must be semantically identical
across the five harnesses. Only the adapter's launch/transport commands, exact
YOLO flags, controller-selected harness/model values, and a required native
envelope such as AGY's single `/teamwork-preview` prefix may differ. The native
envelope must not change the contract's authority or expected checkpoint bytes.

The fixture contains `contract.json`, a writable `handoffs/` directory, and no
Puppet source. The initial prompt tells the target to:

1. read `./contract.json` and verify its schema, run ID, nonce, and allowed
   fixture root;
2. make no source, repository, account, network-send, or system changes;
3. atomically write one bounded `handoffs/ready.json` matching the strict
   schema and acknowledging the exact run ID and nonce;
4. remain available for exactly one sequenced follow-up instead of exiting or
   claiming completion.

After the controller independently validates `ready.json`, Puppet sends one
follow-up containing a unique message ID and the next sequence number. The
follow-up tells the target to:

1. verify the same run ID and nonce plus the new message ID and sequence;
2. atomically write one bounded `handoffs/followup.json` acknowledging those
   exact values and referencing the ready checkpoint;
3. make no other changes; and
4. remain waiting for Puppet to halt it.

The strict checkpoint schema must contain bounded typed fields for protocol
version, run ID, nonce, phase, sequence, message ID when applicable, prior
checkpoint hash when applicable, timestamp, claims, evidence references,
limitations, and requested controller decisions. Reject unknown, oversized,
out-of-root, transcript-bearing, log-bearing, or secret-shaped content.

The controller, not the target, must verify:

- exact executable, process, session, pane, adapter, and protocol identity;
- unrestricted launch mode and absence of prompt bodies from process arguments;
- legal lifecycle transitions and atomic, append-only state behavior;
- exactly one ready checkpoint and exactly one follow-up acknowledgement;
- the follow-up's exact sequence, message ID, nonce, and prior-checkpoint hash;
- bounded and sanitized artifacts;
- zero protected-source drift;
- continued target availability between checkpoints; and
- an exact graceful halt that stops only the registered target and preserves
  the tmux evidence session.

Harness/model descriptions, capability claims, and declarations of success are
self-reports only. They never graduate an adapter or accept a checkpoint.

## First live AGY stop condition

The first live launch in the campaign is the AGY Pass B conformance run. It is
a read-only control-loop proof, not a build rung.

That AGY session may only perform the shared prompt contract. It must not edit
Puppet, create a candidate commit, review a promotion, or modify any protected
source. The rung stops only after the controller has independently verified:

- doctor and the exact AGY executable/version/YOLO mapping;
- launch and initial prompt transport outside argv;
- the nonce-bound ready checkpoint;
- one exact sequenced follow-up and acknowledgement;
- status/wait/checkpoint behavior without pane or transcript reading;
- legal controller review/accept recording for the conformance checkpoint;
- no protected-source drift; and
- exact graceful halt of AGY with its tmux evidence session preserved.

Record the exact verdict and proof. Then gracefully halt only the registered
AGY target process/conversation while preserving its tmux evidence session; do
not invoke Puppet `close`. Do not mutate or promote anything from this first
run. Once it passes, the same unattended campaign may proceed to a separate
second rung without asking the operator.

## Transcript-blind learning contract

Codex may learn substantive information from only:

- exact target commits in the assigned candidate worktree;
- validated structured checkpoints and handoffs;
- controller-run tests and bounded evidence artifacts;
- independent exact-head reviews and controller verdicts.

Do not read or summarize target panes, terminal scrollback, raw stdout/stderr
transcripts, conversation/session stores, TUI logs, or chat histories. Do not
use pane text to infer status, readiness, completion, failure, or intelligence.
Process and transport code may observe only the minimum sanitized metadata
needed to verify identity, liveness, acknowledgements, and halt behavior.

If an adapter cannot provide transcript-blind status and checkpoint control,
leave it unqualified and stop with a blocker. Do not add scraping as a
fallback.

## Autonomous ratchet loop

After entry conditions and proof admission, run this loop without routine user
interaction:

1. **Scaffold Puppet N manually.** Build the minimum trusted kernel and AGY
   adapter from admitted contracts. Run deterministic kernel tests. Keep all
   non-AGY adapters doctor-only.
2. **Prove first AGY.** Execute the read-only first-live-run contract above,
   halt it exactly, preserve evidence, and record the controller verdict.
3. **Qualify the independent review rail.** Before any Puppet mutation, prove a
   reviewer materially different from the intended implementation target. For
   the first AGY implementation rung, the fixed Codex campaign controller may
   qualify by reviewing a controller-created committed fixture with known
   required and rejected findings. Bind exact controller/harness/model/version/
   effort identity where exposed, exact base/head, review protocol and result
   hashes, read-only no-edit proof, bounded finding classifications, and
   deterministic stale-head invalidation. This qualifies only the Codex
   controller review rail, not the Codex target adapter. If exact materially
   different identity or review behavior cannot be proved, qualify another
   distinct review rail through an already-proved real adapter, serially, or
   stop before mutation.
4. **Run the first self-hosting rung.** Use stable Puppet N to supervise real
   AGY implementing one bounded candidate N+1 slice, preferably promotion
   machinery or the next doctor-only adapter. The immutable Codex campaign
   controller independently reviews the exact AGY commit and evidence only if
   its step 3 qualification remains current; AGY may not review or accept its
   own work. After the mutation session ends, seal the exact candidate head as
   an immutable qualification release, run affected direct tests and real
   conformance through that sealed release, adjudicate as controller, and
   promote only if the full gate passes.
5. **Choose one bounded next slice.** Prefer one separable adapter, factory,
   safety, checkpoint, or proof feature. Name its acceptance tests and stop
   condition before launch.
6. **Create a separate candidate.** Start it from the exact stable head in a
   new candidate branch/worktree. Pin the current stable Puppet release as
   supervisor.
7. **Launch one proved target in YOLO mode.** Give it only the bounded task
   packet. Require additive commits and structured checkpoints. Do not read its
   terminal. Do not run another target concurrently.
8. **Inspect independently.** After the target checkpoint, halt or hold it as
   the contract requires. The Codex campaign controller checks the exact commit,
   tests, proof, scope, and source drift. Obtain an independent review from a
   different already-proved harness/model than the implementation target.
9. **Adjudicate.** Classify each finding as `required_fix`,
   `reject_false_positive`, `defer`, or `human_gate`. Record the controller-only
   verdict. The target cannot accept itself.
10. **Repair narrowly.** Send one bounded repair packet through Puppet and
   require an additive commit. Rebind all proof and review to the new exact
   head. Allow at most two review-triggered repair cycles for one candidate.
11. **Seal and qualify before promotion.** Once the mutation target is halted,
    materialize the exact candidate as an immutable controller-owned
    qualification release. Run its deterministic tests and required real
    probe without modifying it. A failed qualification returns to a new
    additive repair head; it never mutates the sealed release.
12. **Promote between sessions only.** When every gate below passes, append the
    promotion record, preserve the prior stable release and rollback pointer,
    and make the qualified candidate the fixed supervisor for the next
    session. Do not ask for per-rung approval.
13. **Advance one adapter at a time.** Run Pass A and Pass B for each real
    harness. After another target adapter is proved, use it for a later bounded
    Puppet slice so the skill is genuinely built by the agents it supervises.
    The main Codex controller remains the acceptance authority; when the target
    is Codex or reviewer independence is otherwise weak, obtain a separate
    review from a different already-proved harness/model.
14. **Repeat until acceptance.** Stop polishing when the acceptance criteria
    are satisfied. Do not add automatic routing, delivery, cloud control,
    migration, global installation, or unrelated features.

Update `STATE.md`, `events.jsonl`, `heartbeat`, and `PROOF.md` at every rung and
before any context compaction or bounded wait.

## Exact-head internal promotion gate

Internal promotion is authorized without further user input only when no
target session is live and all of these are true:

- the candidate worktree, branch, full commit SHA, tree hash, and expected
  executable fingerprint are exact and mutually consistent;
- the candidate was materialized after its mutation session as a distinct,
  controller-owned, read-only qualification release whose root and executable
  fingerprint match that exact head;
- the supervisor used during the candidate session still matches its recorded
  immutable root, commit, path, and hash;
- deterministic tests and current repository-wide packaging tests pass;
- every adapter or control-loop claim changed by the candidate has the required
  fresh real-harness conformance proof bound to the exact head and executable;
- an independent review from a different proved harness/model is bound to the
  exact candidate head, and the reviewer identity plus bounded review-
  qualification proof/fingerprint are bound to the promotion record;
- every `required_fix` is resolved, every rejected finding has written
  rationale, and every defer is compatible with the current acceptance scope;
- the controller has recorded an exact-head acceptance verdict;
- no protected source drift, history rewrite, secret exposure, or hard-gated
  action occurred;
- the previous stable release, its executable, proof references, and rollback
  pointer remain intact; and
- an append-only promotion record binds old stable, new stable, tests, probes,
  review, verdict, time, and rollback identity.

A changed head invalidates the review, probe, and verdict until rerun. Never
promote a live candidate, ambiguous identity, self-review, self-acceptance,
unproved adapter, or partially repaired head. Never supervise from the mutable
candidate worktree; only the sealed qualification release may execute before
promotion, and only for the bounded qualification sessions recorded here.

## Stop conditions

Stop the campaign and produce a blocker rather than guessing when any of these
occurs:

- a repository instruction or hard human gate requires an action outside this
  packet;
- source, branch, worktree, executable, process, session, pane, adapter,
  protocol, checkpoint, review, or proof identity is ambiguous or mismatched;
- a required CLI or tmux is unavailable, its current YOLO mapping cannot be
  proved, or its prompt transport necessarily exposes prompt bodies in argv;
- an existing harness/store lock, operator session, worker, or mutation owner
  conflicts with the planned target;
- a target touches protected source during the shared probe, escapes the
  assigned candidate scope, or attempts an external action;
- transcript or pane reading would be required to determine status or learn
  the result;
- checkpoint/handoff validation fails, acknowledgements are missing or
  duplicated, lifecycle transitions are illegal, atomic state cannot be
  trusted, or graceful halt cannot prove its exact target;
- prior evidence is contradictory, materially stale, license-unclear, or
  insufficient for a claimed reuse and the delta cannot be proved safely;
- independent review is unavailable, a changed head invalidates terminal
  review, or a required finding remains after two repair cycles;
- a test, probe, or review exposes a security, credential, account, spending,
  destructive, deployment, delivery, or external-send decision;
- the requested slice expands beyond Puppet's confirmed kernel/adapters/proof
  campaign or automatic routing becomes necessary;
- a target exits unexpectedly and bounded exact-identity recovery cannot
  re-establish trustworthy state; or
- completion would require merge, push, PR creation, deployment, publication,
  global installation, cleanup, deletion, account change, secret access, or
  any authority not explicitly granted here.

Do not kill broad process groups, delete worktrees, prune sessions, weaken a
guardrail, silently skip a harness, substitute a fake harness, or claim partial
proof as completion. Preserve state and evidence exactly where they are.

## Acceptance criteria

The campaign is complete only when all of these are true:

- The final SaariusSkills task branch is clean and locally committed. Nothing
  was pushed, merged, deployed, published, or globally installed.
- `skills/puppet/` validates under current skill-creator and repository
  packaging rules, and the full relevant SaariusSkills test suite passes.
- Puppet N exposes exactly the required minimum commands. `promote`, `close`,
  controller-side source-editing or delivery commands, and unproved adapter
  behavior fail clearly rather than pretending to work.
- The CLI is the authoritative lifecycle and acceptance recorder. A target
  cannot accept itself or advance a controller verdict.
- All state changes are atomic or append-only as specified; exact identity,
  locks, supervisor/candidate separation, and halt targeting have deterministic
  tests.
- The public skill and root README disclose the mandatory YOLO operating model
  prominently, while preserving separate gates for external actions.
- The two-pass adapter factory generated fingerprinted Pass A manifests and
  controller-verified Pass B results for the current installed AGY, Cursor,
  Claude, Codex, and Grok CLIs.
- Each of those five real harnesses passed the identical shared prompt contract
  sequentially in its proved unrestricted mode. No fake harness, terminal
  transcript, target claim, or stale proof substituted for a live result.
- The first AGY run stopped at the read-only control-loop boundary with no
  candidate mutation or promotion.
- Before the first AGY mutation, a materially different review rail passed its
  bounded read-only exact-head fixture; that qualification is bound to later
  review records and did not qualify the Codex target adapter.
- Codex learned only from exact commits, validated checkpoints/handoffs,
  controller tests, evidence, and independent reviews.
- At least one later Puppet N to N+1 self-hosting promotion passed the exact-head
  gate without per-rung user input, preserved the previous stable release, and
  proved rollback identity.
- Every adapter capability is bound to exact executable, adapter, platform,
  and probe-protocol fingerprints and fails closed after relevant drift.
- The AGY AI-overage-credit advisory is version-scoped and non-terminal; a
  deterministic regression test proves that it cannot independently trigger
  failure, diagnosis, or campaign stop.
- The provenance matrix and notices distinguish reusable public material from
  operator-specific, stale, branch-only, uncommitted, terminal-derived, or
  license-uncleared evidence.
- `STATE.md`, `events.jsonl`, `heartbeat`, `PROOF.md`, handoffs, verdicts,
  probes, and promotion history reconcile with the final exact head.
- There are no unresolved required findings or undeclared actions. Deferred
  auto-routing and any other non-goal are named honestly.

## Required final report

Return one concise closeout report containing:

- outcome: `complete` or `blocked`;
- canonical repo, worktree(s), branch, exact final head, and clean/dirty status;
- final stable Puppet root, commit/tree/executable fingerprints, plus rollback
  identity;
- locally created commits and their bounded purpose;
- test commands and results;
- the prior-evidence admission matrix path and the most important reuse versus
  reprove decisions;
- a five-row real-probe matrix for AGY, Cursor, Claude, Codex, and Grok showing
  exact executable/version fingerprint, YOLO mapping, protocol fingerprint,
  result, proof reference, and preserved tmux evidence identity;
- first AGY stop proof;
- independent review, adjudication, repair-cycle, verdict, and promotion
  records bound to exact heads;
- the `run-observations/` path plus a per-run completeness summary for every
  routing-telemetry field, explicitly retaining `unavailable` values;
- campaign `STATE.md`, `events.jsonl`, `heartbeat`, and `PROOF.md` paths;
- prominent residual risks and explicitly deferred work, including auto mode;
- confirmation that no merge, push, PR, deploy, publication, global install,
  delete/archive, external send, spend, account/security change, or secret
  access occurred.

If blocked, additionally name the exact failed invariant, last trusted stable
identity, affected target/rung, evidence proving the blocker, what was
preserved, and the smallest next safe operator action. Do not describe a
generic failure when a precise one is available.
