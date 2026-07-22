# Goal Packet: Qualify Puppet regular sessions and instruction planes

Status: active autonomous campaign packet, 2026-07-22

Submitting this document as a Codex goal authorizes the bounded internal
campaign below. Read `instruction-qualification.md` first. The historical
`codex-goal.md`, `implementation-seed.md`, `DECISIONS.md`, and `PROOF.md` remain
applicable wherever this packet does not supersede them.

Live targets run in their harness's proved unrestricted/always-approve mode.
That is cooperative YOLO execution with the operator account's available
access, not an operating-system containment boundary and not authorization for
the excluded external actions below.

## Objective

Finish Puppet's portable regular-session baseline for AGY, Codex CLI, Claude
Code, Cursor Agent, and Grok Build. Build and prove the instruction-composition
system, qualify the safest native instruction plane for each installed exact
harness/version using its current default model, and prove the complete
transcript-blind lifecycle through real harnesses.

Run independent per-harness lanes concurrently where safe. The controller owns
shared integration, review adjudication, acceptance, and promotion. Continue
without routine questions until all five regular baselines qualify. A genuine
hard-gate blocker must be preserved precisely and must not be mislabeled as
five-harness completion.

## Active scope

In scope:

- regular unrestricted sessions for AGY, Codex, Claude, Cursor, and Grok;
- a shipped baseline template catalog and deterministic effective-contract
  compiler;
- universal, harness, model-family, lifecycle, task, and user-addendum layers;
- harness-global/profile, workspace/repository, and additive per-run plane
  census and isolated proof;
- direct-repository and cockpit-to-explicit-repository entry;
- per-harness lane leases, isolated config roots, worktrees, sessions, state,
  and proof;
- setup planning plus test-only install/upgrade/rollback/uninstall in isolated
  config roots;
- a read-only versioned native-command sweep after the regular baseline;
- outcome telemetry that can inform a later automode; and
- bounded implementation, tests, local commits, independent review, repair,
  controller acceptance, and already-authorized updates to draft PR #5.

Out of scope:

- enabling `/goal`, `/loop`, `/teamwork-preview`, or another native command as
  accepted baseline behavior;
- automatic harness/model routing;
- live Pi qualification;
- replacement of vendor system prompts;
- modification of the operator's live harness-global files;
- adoption, monitoring, steering, signaling, or cleanup of a session Puppet did
  not create;
- merge, deployment, release/publication, destructive cleanup, external sends,
  account/security changes, spending changes, or secret/auth-store access.

Keep PR #5 draft and unmerged.

## Entry and controller invariants

1. Fetch the exact remote PR head and work only in isolated SaariusSkills
   worktrees. Preserve the dirty primary checkout and unrelated worktrees.
2. Read applicable repository and skill-creator contracts before source edits.
3. Bind the controller to an immutable exact Puppet release. No live candidate
   may supervise itself.
4. Inventory existing Puppet-owned sessions and leases read-only. Never infer
   authority from a tmux name or executable alone; exact campaign/session
   identity is required.
5. Create or resume one campaign root with current `STATE.md`, `events.jsonl`,
   `heartbeat`, and `PROOF.md`. Give every harness lane a separate proof root.
6. Re-census every executable/version/help surface without reading config
   contents, transcripts, credentials, auth logs, cookies, or session stores.
7. Confirm exact unrestricted/always-approve behavior and sandbox treatment for
   the installed version. Prompted or partially approved live mode is not a
   silent fallback.
8. Upgrade Puppet's single-target lease design before concurrent live launches.
   Until that gate passes, concurrency is limited to read-only mapping, fixture
   design, and isolated code/test work.

## Harness-lane assignment

Assign each harness to a named sub-agent/worker lane. Because controller runtime
capacity may be lower than five simultaneous workers, start as many independent
lanes as slots allow and reuse a completed slot for the remaining harnesses.
Each assignment must name:

- harness and exact executable/version;
- owner and allowed task/mutation mode;
- source base, branch, worktree, and proof root;
- isolated config/home root and profile namespace;
- controller release and protocol fingerprint;
- tests, real-probe acceptance clauses, hard gates, and stop condition; and
- exact handoff format for controller integration.

Workers are not alone in the repository. They must preserve other lanes, avoid
shared-file edits unless explicitly assigned, make additive commits, and never
self-merge or self-accept. Shared core/profile-registry edits belong to one
serialized integration owner.

## Work sequence

### Phase 1: reconcile the current branch

- Treat existing implementation and machine-private dogfood as evidence, not
  automatically accepted proof.
- Address known contract/profile correctness findings before trusting new
  fingerprints, including canonicalization of an omitted default
  `session_profile` if the current source still fingerprints only raw input.
- Preserve the current native-command code and evidence behind disabled or
  experimental capability states; do not delete it merely because v0.1 narrows
  to regular sessions.
- Add deterministic tests for the new baseline and every changed authority or
  fingerprint rule.

### Phase 2: implement instruction composition

- Store editable baseline templates inside `skills/puppet/`, outside
  `SKILL.md` when detail would bloat the skill.
- Compose universal + harness + model-family + lifecycle + task + optional user
  addendum into one canonical, bounded, fingerprinted contract.
- Generate only harness-native additive/profile forms; replacement prompt
  mechanisms stay unsupported unless a future explicit design changes this.
- Record source/output hashes, selected plane, exact harness/version, model
  observation, workspace/source identity, activation scope, and cleanup plan.
- Provide dry-run/audit output and deterministic isolated-root tests for setup,
  upgrade, rollback, uninstall, no unrelated overwrite, and customization
  invalidation.

### Phase 3: map and test the three planes

For each harness, statically map and then test:

1. session-selected harness-global Puppet profile/addendum;
2. repository/workspace addendum; and
3. additive per-run system instruction or closest supported native equivalent.

Use disposable fixtures, isolated config roots, and current default models.
Run an ordinary-session control proving zero Puppet activation/bleed. Verify
built-ins/tools/skills, repository instruction authority, profile isolation,
exact contract recovery, rollback, and concurrency. Select the harness-global
profile only when it clears every gate and performs at least as well as the
alternatives.

### Phase 4: qualify regular lifecycle per harness

Using each selected winning plane, prove against the real CLI:

- exact launch identity and unrestricted-mode mapping;
- prompt delivery outside argv;
- bounded ready checkpoint and one sequenced follow-up;
- continued parent availability;
- ordinary unprefixed steering;
- exact resume behavior where the harness exposes it;
- transcript-blind status/wait/checkpoint processing;
- direct and cockpit workspace entry;
- zero protected-source drift in conformance fixtures;
- exact halt of only the Puppet-owned target; and
- preserved bounded evidence plus no-bleed ordinary-session control.

Each harness independently receives `qualified`, `experimental`, or
`unsupported`, bound to executable, adapter, protocol, effective-contract,
model-observation, and workspace fingerprints. Do not substitute mocked targets,
pane scraping, target self-report, or another harness's result.

### Phase 5: integrate and review

- Workers deliver exact-head commits and structured proof handoffs.
- The controller serializes shared integration and reruns affected deterministic
  tests plus exact real probes.
- Independent review must distinguish `target_claimed_green`,
  `controller_gates_green`, and `independent_review_clean`.
- Classify findings as `required_fix`, `reject_false_positive`, `defer`, or
  `human_gate`; allow at most two review-triggered repair cycles per slice.
- A changed head invalidates bound probe, review, and acceptance proof.
- Push bounded checkpoints to the existing authorized draft PR when useful;
  never merge it.

### Phase 6: defer commands with evidence

After all regular baselines are stable, perform a read-only current-version
command sweep. Record candidate long-running commands and their activation,
continuation, resume, and termination hypotheses in a dedicated reference.
Preserve the known AGY `/teamwork-preview`, Codex `/goal`, and Claude `/goal`
and `/loop` evidence. Do not enable any command profile in this campaign.

## Required state and evidence

Maintain campaign and lane-local:

```text
STATE.md
events.jsonl
heartbeat
PROOF.md
```

Also preserve bounded capability manifests, effective-contract fingerprints,
instruction-plane observations, no-bleed controls, model/default observations,
worktree identities, handoffs, verdicts, reviews, and exact halt evidence. Raw
prompts, transcripts, panes, arbitrary logs, config contents, and secrets never
enter committed proof.

Refresh heartbeat during long work. Append meaningful events at lane start,
gate transitions, checkpoint, repair, integration, qualification, and blocker.

## Acceptance criteria

The goal is complete only when:

- all five regular harness rows are `qualified` at one exact integrated head;
- the effective instruction compiler and shipped baseline templates pass
  deterministic packaging, composition, customization, and fingerprint tests;
- each harness has a controller-observed plane winner and hard-gate proof;
- live operator globals and non-Puppet sessions were untouched;
- direct and cockpit entry paths pass for every harness;
- per-harness leases allow safe independent lanes while shared mutation remains
  serialized;
- real regular-session launch, checkpoint, follow-up, resume/steer, and exact
  halt proof exists for every current installed CLI;
- every claim binds exact harness, adapter, protocol, contract, workspace, and
  model/default observations and fails closed on relevant drift;
- controller-only verdict, independent review, and exact-head invalidation
  remain intact;
- automatic routing, Pi, and command enablement remain explicitly deferred;
- relevant repository tests and skill validation pass at the exact head;
- campaign/lane state, events, heartbeat, proof, commits, and PR #5 reconcile;
  and
- the final branch is clean, pushed to the existing draft PR, and not merged.

A single qualified harness is a valid lane result but not goal completion. If
one exact-version lane reaches an irreducible gate, keep working on independent
lanes, preserve the blocker packet, and use Codex goal blocked status only under
the goal system's repeated-blocker rules. Never weaken a hard gate to force a
green matrix.

## Final report

Report the exact PR head, integrated commits, clean/dirty status, tests, five-row
harness matrix, selected instruction plane and model observation per row,
direct/cockpit proof, no-bleed result, state/proof paths, review/adjudication,
deferred command-sweep artifact, residual risks, and confirmation that live
globals, non-Puppet sessions, merge/deploy/release, external sends, secrets,
accounts/security, spending, and destructive cleanup remained untouched.
