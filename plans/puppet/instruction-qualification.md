# Puppet instruction and regular-session qualification amendment

Status: active operator-confirmed design amendment, 2026-07-22

This document preserves the decisions from the post-implementation grilling
session without rewriting the hash-bound historical GrillTrack packet. For new
Puppet work it supersedes conflicting serial, session-profile, native-envelope,
and campaign-completion language in `DECISIONS.md`, `codex-goal.md`, and
`implementation-seed.md`. Their unchanged safety, proof, transcript-blindness,
controller-authority, exact-identity, and external-action gates remain active.

## Decision index

- `baseline-001`: qualify regular sessions only for the five current harnesses.
- `lifecycle-001`: native commands require separate lifecycle-state proof.
- `instruction-001`: compose one fingerprinted effective contract from shipped
  layers plus a task packet and optional user addendum.
- `instruction-plane-001`: test all three native planes and prefer a safe
  session-selected harness-global profile only when evidence wins.
- `instruction-safety-001`: live global activation is explicit setup; isolated
  config roots are mandatory during this campaign.
- `ownership-001`: Puppet controls only sessions it created.
- `workspace-001`: support both cockpit and direct-repository entry with
  isolated worktrees for mutation.
- `qualification-001`: graduate harnesses independently without a blind
  Cartesian product; overall completion still requires all five.
- `concurrency-001`: independent harness lanes may run concurrently after
  per-harness leases exist; shared mutation and integration remain serialized.
- `model-001`: use and fingerprint the current default first; alternative
  models qualify separately.
- `routing-003`: automatic routing remains deferred while neutral outcome
  evidence accumulates.

## Baseline decision

Puppet v0.1 qualifies one ordinary unrestricted session for each of these five
harnesses:

| Harness | v0.1 live profile | Independent result |
|---|---|---|
| AGY | regular | `qualified`, `experimental`, or `unsupported` for the exact version |
| Codex CLI | regular | `qualified`, `experimental`, or `unsupported` for the exact version |
| Claude Code | regular | `qualified`, `experimental`, or `unsupported` for the exact version |
| Cursor Agent | regular | `qualified`, `experimental`, or `unsupported` for the exact version |
| Grok Build | regular | `qualified`, `experimental`, or `unsupported` for the exact version |

Overall campaign acceptance still requires all five regular baselines to be
qualified. One harness's failure does not invalidate another harness's proof,
but it does prevent a claim that the five-harness campaign is complete.

Pi remains a mapped, deferred harness because it is a multi-provider surface,
not one of the current subscription-provider targets. Do not run a live Pi
qualification in this campaign.

Existing `/goal`, `/loop`, and `/teamwork-preview` implementation and evidence
must be preserved, not treated as accepted baseline behavior. After the regular
baseline is stable, run a read-only command sweep and record promising native
commands in a dedicated/versioned reference. A command enters the product only
after its own lifecycle qualification.

## Native commands are lifecycle state machines

A native command is not a static prefix attached to every message. Qualify each
harness/version/command as a state machine with at least:

- activation envelope;
- follow-up envelope;
- resume behavior;
- steering behavior while already active;
- termination or cancellation behavior; and
- observable evidence that the requested mode actually occurred.

Current observations are evidence, not universal rules. `/goal` commonly
activates a durable goal once and then accepts ordinary steering. Claude
`/loop` has separate repeat semantics. Live AGY field work found repeated
`/teamwork-preview` prefixes reliable, while the one-prefix-only hypothesis was
not qualified. Selecting teamwork and actually observing helper decomposition
are separate capabilities. Record `initial_envelope`, `followup_envelope`,
`turn_2_consumed`, helper use/integration when observable, and exact executable,
adapter, and protocol fingerprints.

## Effective instruction contract

Every Puppet-owned run materializes one bounded effective contract:

```text
universal Puppet orchestration contract
+ harness overlay
+ model-family overlay
+ lifecycle/command overlay
+ task packet
= fingerprinted effective contract
```

The universal and overlay templates ship inside `skills/puppet/` as the source
of truth. A setup or run compiler produces the harness-native representation
and records its source hashes, normalized composition, output hash, selected
plane, harness/version, model observation, and cleanup identity.

The Puppet layer is orchestration-only: persistence, ownership, checkpoints,
beacons, handoffs, stop conditions, and controller acceptance. Repository
instructions own architecture, code, tests, safety, and definition of done.
Controller hard gates remain highest. Conflicts fail closed; Puppet never
silently overrides a target repository's work or safety contract.

Ship baseline templates and make customization easy. Normal customization is a
separate user addendum composed after the shipped baseline. Full replacement is
an advanced fork. Any changed composition receives a new fingerprint and must
requalify before it can regain trusted, promotion, or future automode status.

## Three instruction planes to prove

Test all three planes with the real harness and its currently selected default
model:

1. a session-selected harness-global Puppet profile or addendum;
2. a workspace/repository instruction addendum; and
3. an additive per-run system instruction or the closest supported native
   equivalent.

The preferred tie-breaker is the session-selected harness-global plane when it
passes every hard gate and performs at least as well as the alternatives. It is
not an unconditional default. A harness without a safe supported form may
select another plane or be marked unsupported.

Never replace a vendor system prompt. Never permanently activate Puppet policy
for ordinary sessions. The global form is a Puppet-namespaced catalog/profile
selected only for a Puppet-owned launch, not an always-on edit to a user's
normal CLI behavior.

Installing or updating a real user-global profile is explicit setup, never an
incidental launch. It requires an exact proposed diff, Puppet namespace,
unrelated-content preservation, before/after hashes, backup and rollback,
auditable upgrade/uninstall, and human approval. This campaign tests global
semantics only through isolated Puppet-owned configuration roots or equivalent
throwaway homes. It must not edit the operator's live global files.

## Instruction-plane hard gates

A plane can qualify only when controller proof shows:

- zero activation or bleed into an ordinary non-Puppet session;
- vendor built-ins, tools, skills, and safety behavior remain available;
- target repository instructions retain their authority;
- exact effective-contract and harness/version identity are recoverable;
- simultaneous Puppet lanes cannot consume each other's profile or state;
- setup, launch, upgrade, rollback, and uninstall are bounded and reversible;
- prompt bodies and secrets do not enter argv, state, logs, or committed proof;
- harness or model-default drift invalidates the affected qualification; and
- only the exact Puppet-owned process/session can be resumed, steered, halted,
  or inspected.

Puppet may never attach to, adopt, infer lifecycle for, signal, or otherwise
intervene in a non-Puppet session. A future explicit adoption feature requires
its own design and operator action.

## Dated instruction-surface discovery

This is a discovery map, not qualification. Re-census the installed executable
and authoritative documentation before implementing a plane.

- Claude Code 2.1.215 exposes namespaced output styles, project rules, and an
  exact-parser-accepted additive `--append-system-prompt-file`. Replacement
  `--system-prompt`, `--system-prompt-file`, and main `--agent` are forbidden.
  A unique `CLAUDE_CONFIG_DIR` plus explicit setting sources is the candidate
  isolation boundary; `.claude/settings.local.json` is not worktree-isolated.
- Cursor IDE 3.12.17 / Cursor Agent 2026.07.17-3e2a980 exposes User Rules,
  project `.cursor/rules`, `AGENTS.md`, and compatibility rule files. No public
  supported per-run primary system-prompt flag was found; an internal flag is
  not a product contract.
- Grok Build 0.2.106 exposes home/project rule layers and named agent/profile
  surfaces. Exact help does not expose `--append-system-prompt`; literal
  `--rules` places content in argv and cannot qualify Puppet's per-run plane.
  Prompt-replacement flags are forbidden.
- AGY 1.1.5 and Codex CLI 0.145.0 have exact-version static censuses, but their
  native planes remain unqualified. AGY lacks a proved isolated config root and
  positive sandbox-off override; Codex's isolated `CODEX_HOME` is coupled to
  authentication and cannot be manufactured by copying credentials.

Sources for the discovery record are the exact installed help/binaries and the
vendor documentation cited by the campaign evidence. Local config existence
may be recorded without reading its contents. Never inspect global instruction
contents, credentials, sessions, transcripts, or auth stores for this census.

## Workspace and ownership

Puppet must support both common entry patterns:

- cockpit entry: the controller starts elsewhere and receives an explicit
  source repository; and
- direct entry: the user starts inside the target repository and Puppet infers
  the Git root unless the user overrides it.

Every mutating target receives a fresh isolated worktree, one branch, one lane
owner, and one proof trail. Read-only observation may use the current checkout.
The immutable controller and proof root stay outside a candidate worktree. The
portable skill must not hard-code `x-api`, `~/Developer`, or this operator's
machine layout.

Puppet records exact source repo, remote/default base, commit, branch,
worktree, controller release, target process/session, profile namespace, and
proof root before launch.

## Qualification strategy

Avoid a blind Cartesian product. Qualify in stages:

1. statically map all three planes, precedence, activation, and cleanup;
2. run the regular-session fixture through each viable plane using the
   harness's current default model;
3. select the safe winner for that exact harness/version;
4. prove the winner through launch, checkpoint, follow-up, resume, steering,
   exact halt, rollback/cleanup, an ordinary-session no-bleed control, and a
   human-only read-only attach/detach of the exact native live TUI without any
   capture, mirror, renderer, summary, or controller pane access;
5. repeat both cockpit and direct repository entry paths; and
6. qualify alternative models and native commands only as separate tuples.

Record the requested `default` selection and the most specific
controller-observable resolved model identity/config fingerprint. Use the
literal `unavailable` when the harness cannot expose a field; never invent an
identity from branding. A changed default or relevant config fingerprint
invalidates the affected model-bound proof.

An explicitly selected but unqualified model may run only in an isolated
experimental lane. It may inspect, implement, test, and commit within its
packet, but cannot auto-accept, promote, or enter future automode decisions
until separately qualified.

## Concurrent harness lanes

Harnesses qualify independently and may run concurrently after the single-
target lease is upgraded to safe per-harness lane leases. Each lane needs its
own worker/sub-agent owner, worktree, branch, run state, proof root, tmux/process
identity, fixture, isolated config root, and Puppet profile namespace.

Serialize shared config-profile installation, shared core/capability-registry
changes, integration, review adjudication, and promotion. A harness worker may
produce a bounded commit and proof packet; it may not self-merge or mutate
another lane. The controller integrates accepted slices one at a time.

## Outcome evidence and deferred automode

Automatic harness/model routing remains deferred. Explicit user selection is
authoritative. Collect neutral evidence now so later routing can be built from
outcomes rather than brand stereotypes:

- harness, exact version, selected profile, model/effort observation;
- task class, wall time, repair cycles, verification depth;
- exact accepted head, checkpoint quality, proof integrity;
- `target_claimed_green`, `controller_gates_green`, and
  `independent_review_clean` as distinct states; and
- controller verdict, limitations, and unavailable metrics.

The real AGY/Gemini 3.6 Flash High field report on PR #5 reinforces this split:
the model completed deep mechanical verification and a clean bounded commit,
yet independent review still found a partial required payload assertion and
failure-path cleanup gap. Target green is not requirement proof or controller
acceptance.

## Campaign autonomy and terminal condition

Once the active Codex goal is deliberately set, no routine human checkpoints
are required for internal census, isolated plane tests, winner selection,
implementation, repair, retest, local commit, or controller adjudication.
Maintain `STATE.md`, `events.jsonl`, `heartbeat`, and `PROOF.md` for the campaign
and separate state/proof for each harness lane.

The campaign may continue autonomously until all five regular baselines are
qualified. If a genuine hard gate or irreducible exact-version blocker remains,
preserve evidence and report the exact blocked lane and next safe action; do not
weaken the gate, touch live globals, disturb non-Puppet sessions, enable
automatic routing, or call the five-harness goal complete.
