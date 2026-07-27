---
name: puppet
description: "Control transcript-blind YOLO harness sessions through census, exact real probes, recovery, qualification, checkpoints, and controller-only acceptance."
---

# Puppet

> **Warning:** Puppet live execution is YOLO-only. It requires the target's
> current unrestricted or always-approve mode and disables the harness sandbox
> wherever that control exists. The target receives the operator account's
> machine access. Prompted, sandboxed, or partly automatic launches are not a
> fallback.

Use Puppet as a small lifecycle and acceptance controller, not as a generic
launcher or transcript reader. Keep delivery, external effects, accounts,
security, secrets, spending, and destructive actions separately gated.

## Before a live session

1. Compile a source-only operator plan before running profile, doctor, launch,
   or lifecycle commands. From inside the target repository, `plan` resolves
   the current Git root. From a cockpit or another repository, pass `--repo`
   with the exact target Git root. The body-free result binds the repository,
   branch, commit, tree, controller fingerprints, input artifact hashes,
   private roots, blockers, and exact command arrays, but always reports
   `launch_authorized: false`; it neither checks login state nor creates a
   profile, tmux server, session, or harness process.
   A doctor-only, unqualified Codex manifest also yields a
   `target_gate.state=waiting_for_human` packet for the exact
   `codex_regular_pass_b` identity. It names the expected source-only evidence
   kinds but reports preserved evidence kinds as empty because planning
   supplies and validates no such artifacts. It proposes `doctor`, but marks
   launch, status, waits, attach, open-view, and halt unsupported. Its
   `profile-init` command is a human-gated proposal: the human must choose
   either the named process-local broker route or a human-present login into
   the lane-owned home before any account action. The plan carries route names
   only, never values or credential selectors.
   A doctor-only, unqualified Claude manifest yields a body-free
   `target_gate.state=waiting_for_human` packet for
   `claude_regular_pass_b`. It names the expected
   `zero_agent_claude_matched_control_blocker` observation kind but reports
   preserved evidence kinds as empty because planning receives no observation
   artifact. Only `doctor` remains proposed; launch, status, waits, attach,
   open-view, and halt are unsupported. Private-profile initialization remains
   a human-gated proposal under
   `human_approve_authenticated_claude_matched_control_pair`; the plan neither
   authenticates nor runs either member of that pair.
   A doctor-only, unqualified Cursor manifest yields a body-free
   `qualification_required` boundary for `cursor_regular_pass_b`. The exact
   private file-store route is available through `profile-init` and
   `profile-status`; neither command performs login. Cursor promotion then
   requires two fresh regular Pass B runs against that exact profile: one
   qualification-only, create-once namespaced workspace rule and one separate
   ordinary control. The activated run must also carry a structurally observed
   read-only native-view attach/detach. `cursor-pair` joins only those exact
   accepted runs after both exact halts and activated-rule rollback. A
   source-only binding, a standalone activation receipt, or an ordinary receipt
   cannot qualify the manifest.
2. Resolve the target repository explicitly. From a cockpit or another repo,
   require an explicit target path. From inside the target, use its Git root
   unless the user overrides it. Give every mutating target a fresh worktree;
   keep the immutable controller, state, and proof outside that worktree.
3. Read the target repository instructions and the task contract.
4. Read [yolo-contract.md](references/yolo-contract.md) and require a local,
   uncommitted acknowledgement for this exact campaign.
5. Run `adapter_lab.py census` without launching an agent. Treat every generated
   capability as doctor-only until a real conformance probe qualifies the exact
   executable, adapter, platform, and protocol fingerprints. Enable it only
   with `adapter_lab.py qualify` and the accepted receipt from that probe. A
   probe also requires the separately supplied campaign ID, canonical goal
   repository root, and exact repository/commit/path/SHA-256 goal tuple.
   Regular probes require the exact authenticated Puppet-owned private profile
   and bind its closed launch environment; they never borrow an operator-global
   harness home.
   Codex is stricter: one accepted worktree receipt can never qualify a public
   manifest. A bounded Codex candidate additionally requires a distinct
   ordinary-control run linked to that positive receipt and supplied with its
   own clean linked-worktree descriptor from the same Git common repository and
   exact head, the same exact private subscription profile, the same
   current-default launch vector with no model or effort selector while
   resolved model and effort remain unavailable,
   distinct non-overlapping workspace/process/tmux/lease identities, one real
   read-only native-view attach/detach observation, and exact terminal halts.
   `adapter_lab.py pair-codex` writes that body-free evidence create-only and
   controller-attests it; `verify-codex-pair` independently rebuilds it.
   Both commands report `paired_evidence_only`, and the pair itself never
   authorizes launch. `adapter_lab.py qualify` must independently rebuild that
   exact terminal pair against the current doctor manifest before it can write
   a qualified runtime manifest. Public doctor and launch then reverify the
   pair and require the same exact private subscription-profile binding.
6. Run `puppet.py doctor --profile-root <private-profile>`. Stop on a missing,
   invalid, unauthenticated, or adapter-mismatched private profile; an active
   target/store lock; ambiguous executable identity; incomplete unrestricted
   mapping; missing sandbox-off control; prompt-in-argv transport; dirty or
   overlapping worktree; or missing proof-root writability.
7. Run at most one live lane per harness target and one mutation owner per
   source slice. Different harness targets may proceed independently only with
   their own leases, isolated worktrees, state, sessions, and proof roots.

`--goal-repo` names the canonical local Git root. `--goal-repository`,
`--goal-commit`, `--goal-path`, and `--goal-sha256` must exactly match the
submitted authorization; they are independent expected values, not inferred
from the authorization file.

Never kill, rename, attach to, reuse, or repurpose a pre-existing process or
tmux session. Never inspect `.env`, credentials, auth logs, session stores,
conversation stores, terminal scrollback, or transcripts. The only
ordinary-operation exceptions to this terminal-capture ban are the narrow
Claude and Cursor startup-screen reducers described under *Operate a session*.
Each reads only a bounded owned pane before ordinary prompt delivery, classifies
a fixed harness-specific allowlist, retains only
gate/selection/workspace-match/size/hash/timing metadata, and discards the raw
bytes. Cursor may send literal `a` once only for its exact two-option
`Workspace Trust Required` screen when the displayed path equals the
Puppet-owned workspace; an MCP-expanded, login, terms, permission, unknown, or
ambiguous screen fails closed.

Puppet ships editable baseline layers under `templates/instructions/`. Prefer a
bounded per-run user addendum for customization; changing a shipped layer or
template root creates a new instruction-policy fingerprint and requires fresh
qualification. The initial-message wrapper is a safe composition transport,
not proof that a harness-native global, workspace, or additive plane works.

Subscription authentication is isolation-scoped and durable across Puppet
runs. For harnesses with a private-home selector, use one stable Puppet-owned
mode-0700 home/config root per user, harness, and account selection; never put
it inside a disposable run, proof, or campaign root. `profile-init` creates
that root once and idempotently rejoins it on later runs. It may atomically
refresh the profile's non-secret, exact launcher authority after a compatible
harness or Puppet update without replacing the profile directories or their
authentication state. Rejoining or refreshing a profile is not a request to
log in. Puppet silently checks native status before each launch and reuses a
logged-in profile without a human prompt. A human login handoff is allowed only
for initial enrollment or after the provider reports that the session was
invalidated, revoked, or logged out. Puppet does not copy an existing
credential or perform login itself. For Claude specifically, an enrolled,
stable Puppet-owned profile may present the ready startup screen immediately on
later runs, so the startup-screen reducer reaches ready without navigating
intermediate gates; a fresh, un-enrolled profile instead shows the logged-out
screen, which the reducer treats as a fail-closed forbidden gate, so Puppet
neither copies auth into it nor runs an unattended login and only presents the
one-time human enrollment handoff. A harness-native operating-system keyring
may instead be reused only when its non-secret configuration and session state
remain separately isolated and the exact adapter proves that boundary.

Prefer safe adoption of an already-authorized operator subscription when the
harness exposes a qualified auth-only selector or broker. Do not adopt an
operator-global home merely because it is logged in: that can also import
unrelated instructions, configuration, plugins, sessions, and logs. When safe
adoption is unavailable, group the one-time profile enrollments into first-use
Puppet onboarding instead of interrupting later runs with repeated prompts.
For Grok 0.2.111, qualify the current standalone private-profile pair first. The
attended shared-leader/exact-socket surface remains a deferred no-copy
operator-subscription candidate. Its external auth provider is not a cached
session export or generic consumer bridge without a provisioned token provider.
Use `grok_shared_leader.py` only to compile the exact source plan and bind
structural observations. Require an empty same-target baseline before the
attended leader starts. Puppet must not start or signal that leader: present
the exact `human_start_attended_operator_grok_leader` handoff, then bind its
private socket and process identity. Client halt authority targets only the
exact client root and must preserve the leader tree and socket unchanged.
Socket ownership, TUI attach semantics, configuration no-bleed, and live halt
remain blockers until independently observed.
Do not mix the deferred shared-leader topology into the promotable standalone
pair: every current Grok member gets its own new socket and UUID below the same
exact enrolled private profile.
Use `onboard` with the current adapter manifest for every selected harness and
one durable mode-0700 profile shelf. It prepares or rejoins supported profiles,
runs body-free native status checks, silently marks logged-in profiles ready,
and emits a login handoff only for a profile reported logged out. It never runs
that handoff, launches a model, or changes an account. A status failure remains
local to that harness so the other selected subscriptions still classify. AGY
reports `native_reuse_candidate`: its vendor route silently reuses a valid
operating-system keyring profile, but Puppet does not probe the current account
or emit a login action while AGY's separate configuration/no-bleed boundary is
unqualified. Cursor uses an exact private HOME/config/data root and file-backed
credential selector. Its native status probe runs with browser opening
disabled, retains only the allowlisted login classification, and emits the
one-time login handoff only when that isolated profile reports logged out.
This qualifies authentication isolation, not Cursor's remaining workspace,
default-model, process-population, or lifecycle behavior.
For an unqualified Codex regular plan, do not execute that proposal until its
`human_choose_private_codex_auth_route` gate is explicitly resolved.
When a root-run Codex qualification is separately authorized, supply the
operator plan to the positive probe with `--codex-entry-plan` before launch.
The controller recompiles its exact schema and full field set, persists its
source binding before target start, and includes that binding in the accepted
positive receipt and controller attestation. Recovery requires that same exact
persisted plan. Pairing accepts no new entry-plan argument. Its hash-verified
`entry_mode` is the only
accepted claim for direct repository (`direct_git_root`) versus explicit
cockpit (`cockpit_explicit`) entry, and it must name the exact positive
worktree branch and head. Static repository file absence, target self-report,
mocked launch, post-hoc plan synthesis, or doctor-only output is never entry or
promotion evidence.
Observe a native viewer only through structural tmux client/process identity:
never retain pane body, prompt, transcript, scrollback, or authentication or
configuration content. Keep target process, tmux server, viewer client/process,
and controller lease identities separate in every proof.
For an unqualified Claude regular plan, profile initialization is only
preparation for the separately approved authenticated matched-control pair; it
is not launch or matched-control authority.
After the operator completes that account action, use `profile-status` to retain
only an allowlisted login state. Codex, Claude, Cursor, and Grok have public
private-profile recipes. Cursor's recipe fixes
`AGENT_CLI_CREDENTIAL_STORE=file`, isolates HOME/config/data, and keeps
`NO_OPEN_BROWSER=1` on status and login-handoff preparation; Puppet itself
never runs the handoff. AGY does not need credential copying or a second
Puppet-owned login profile: its installed CLI can reuse the operator's native
keyring. It remains non-launchable until Puppet can isolate AGY's global
configuration, instructions, plugins, sessions, and logs independently of that
keyring.
`doctor` and `launch` require the selected profile explicitly. `launch` passes
only that profile's closed home/config environment to the exact target and
revalidates its manifest, executable, directory identities, login state, and
environment fingerprint immediately before target start. It never falls back
to an operator-global harness home.

## Operate a session

Invoke the skill-local CLI:

```bash
python3 <skill-root>/scripts/puppet.py <command> ...
```

Compile the first operator packet with:

```bash
python3 <skill-root>/scripts/puppet.py plan \
  --contract <contract.json> \
  --manifest <manifest.json> \
  --authorization <authorization.json> \
  --profile-root <private-profile> \
  --prompt-file <launch-prompt.txt> \
  --session <session-id> \
  --run-root <private-run-root> \
  [--repo <exact-target-git-root>]
```

Omit `--repo` only when the current directory is inside the target Git tree.
Redirect the JSON result if a durable packet is needed; `plan` itself does not
write an output file. Treat every listed command as proposed operator work, not
as authority to run it. Resolve the reported blockers and make a separate human
choice before any live launch.

Use this sequence:

1. Run first-use or recovery onboarding for the selected harnesses:

   ```bash
   python3 <skill-root>/scripts/puppet.py onboard \
     --profile-shelf <durable-private-shelf> \
     --manifest agy=<current-agy-manifest> \
     --manifest codex=<current-codex-manifest> \
     --manifest claude=<current-claude-manifest> \
     --manifest grok=<current-grok-manifest> \
     --manifest cursor=<current-cursor-manifest>
   ```

   Reuse every `ready` profile without prompting. Present `login_command` only
   for an `enrollment_required` profile, then rerun `onboard` to verify it.
   `status_unknown`, `status_unavailable`, `native_reuse_candidate`, and
   `unsupported` are blockers, not reasons to guess or log in blindly.
   `native_reuse_candidate` specifically means the subscription reuse mechanism
   is known but the remaining runtime isolation is not qualified. The login
   handoff is an explicit account action and never runs unattended.
   `profile-init` and `profile-status` remain the low-level single-target
   equivalents.
2. `doctor` validates the current executable, YOLO mapping, repository,
   authorization, tmux, proof root, and collision state.
3. `launch` creates one deterministic user-private tmux socket/session from a
   controller-verified manifest, waits through the adapter's bounded structural
   startup settle, rechecks process/pane identity, and then delivers the initial
   prompt through a protected file or literal tmux buffer, never as a process
   argument. The settle reduces startup races; only a validated handoff proves
   the harness consumed the prompt. Claude is the single exception to the
   terminal-capture ban and does not use the plain structural settle: before the
   initial prompt it runs a narrow internal startup-screen reducer over the
   bounded owned pane of the exact registered Claude process. The reducer
   classifies the pane against a fixed allowlist — the security notice, an
   exact-workspace trust prompt, the bypass warning, or the ready screen —
   requires the displayed workspace path to equal the contract worktree exactly,
   reconstructing only bounded hard-wrap boundaries between the unique
   `Accessing workspace:` label and one line beginning with the exact
   `Quick safety check:` marker, excluding that boundary line's narrative tail,
   and selects and recaptures the exact authorized `yes` choice before pressing
   Enter. It
   retains only gate/selection/size/hash/timing metadata and discards
   raw bytes, and a login, account, terms, subscription, unknown, ambiguous,
   oversize, or non-UTF-8 screen fails closed with no retry. It is bounded by the
   Claude startup-settle and transition deadlines, and immediately before
   delivery re-verifies process, pane, and executable identity and that the pane
   is still the ready screen. This is the only ordinary-operation terminal read
   Puppet performs.
4. Give the human the exact command from `attach-command`. When the operator
   opts in and the local surface supports visible macOS terminal launch, use
   `open-view` to open that command in a separate iTerm or Terminal window. It
   uses a short-lived one-use ticket and reports success only after a new
   read-only tmux client is structurally observed; an app-launch return code is
   not viewer proof. Request a fresh command after expiry or any failed check. It
   must open the harness's native, unfiltered live TUI on the exact Puppet-owned
   private socket/session in read-only mode: no capture, transcript, log mirror,
   renderer, summary, or controller mediation. The human may attach and detach
   without changing the target. Tmux's owner-execute bit is only an
   attached-client state marker and is excluded from socket identity; device,
   inode, owner, every other mode bit, group/other access, socket type, and
   server/pane/process identities remain exact. Do not have the controller
   attach or read the pane.
5. Use `status` and bounded `wait` calls for structural state and validated
   checkpoints. Do not use `capture-pane`, `pipe-pane`, or terminal text, except
   for Claude's bounded pre-prompt startup-screen reducer above; after the ready
   handoff, never capture or read pane text for any target.
6. Pin one adapter-qualified `session_profile` in the contract. Puppet applies
   that profile's native command only to the initial launch message; later
   `send` calls are ordinary steering messages. For AGY, Puppet also rejects
   `/btw`, `/side`, and caller-supplied profile prefixes.
7. Import handoffs with `checkpoint`, inspect the bounded referenced artifact,
   and record controller findings with `review`.
8. Use `accept` only after independently verifying the exact checkpoint and
   terminal criteria. A target cannot review or accept itself.
9. Use `halt` only for the exact registered target. Preserve tmux and proof.
   `reconcile-grok-dead-lease` is the sole exceptional controller-only path for
   an explicitly named Grok registry record that remains `BLOCKED` with a
   proven-dead `launch_incomplete` target and preserved dead pane. It strictly
   revalidates the recorded process, private tmux topology, and canonical fixed
   Grok lease generation and its exact backed legacy compatibility fence. Under
   the target lock and then the existing legacy lock, it changes only the exact
   `halting` target generation and matching fence to `halted`. It never signals,
   attaches, updates the registry or proof journal, creates or repairs authority
   evidence, or relaxes the immutable supervisor checks used by ordinary
   `status` and `halt`.

Pass B probes and normal live sessions share one fixed, checkout-independent
authority root with one lock, projection, and durable lease history per target.
Different harness targets may run independently; a caller-selected proof or
state root cannot create a second lane for the same target. A lossy legacy
global projection keeps older controllers fenced while any per-target lane is
active. If a probe is interrupted, use `adapter_lab.py recover` with the same
target, run ID, controller, campaign, goal, manifest, mapping, authorization,
and proof root. Recovery reconciles the persisted exact identities and may halt
that exact target; it never relaunches.

Claude matched-control probe reservations are one-use. Never retry or relaunch
the same run after reservation; use exact `adapter_lab.py recover`. Stop and
preserve the run when its attestation, reservation, ready checkpoint, or
hash-only signal observation is missing or drifted. Also stop on a non-source,
ambiguous, or post-observation recreated signal leaf; do not manually delete or
recreate it. An accepted activation lifecycle remains non-qualifying until a
separate ordinary control and paired no-bleed proof are accepted. Its terminal
receipt must retain both matched-control artifacts as exact proof references;
standalone verification rejoins them to the source-owned ready request and
controller journals before returning the still-non-promotable lifecycle result.
For the separately approved live Claude pair, run the ordinary control with
`adapter_lab.py probe --paired-activation-receipt ACTIVATION_RECEIPT` and no
plane descriptor. While each member is live, attach exactly one read-only
controller-produced tmux view and record its structural identity with
`adapter_lab.py observe-claude-view --proof-root ROOT --run-id RUN`. After both
terminal receipts exist, `adapter_lab.py pair-claude --manifest MANIFEST
--mapping MAPPING --activation-receipt ACTIVATION_RECEIPT --control-receipt
CONTROL_RECEIPT` writes a fixed create-only paired receipt beside the control.
Only that controller-attested pair may close Claude's incomplete mapping;
activation-only and unpaired control receipts remain non-promotable. Repeat the
same `--paired-activation-receipt` on linked-control recovery. These commands
retain structural hashes only and never read or store pane, instruction,
configuration, authentication, prompt, or reply bodies.

Cursor workspace qualification also uses a one-use activation transaction.
Build a body-free request from the fresh doctor manifest; the activated Pass B
compiles the effective contract, derives the exact hash-named
qualification-only descriptor, and runs it with `--plane-descriptor`:

```bash
python3 <skill-root>/scripts/adapter_lab.py cursor-request \
  --manifest <fresh-cursor-doctor-manifest> \
  --out <private-proof-root>/cursor-qualification-request.json
python3 <skill-root>/scripts/adapter_lab.py probe \
  --target cursor --profile source-free-pass-b-v2 --session-profile regular \
  --manifest <fresh-cursor-doctor-manifest> \
  --mapping <fresh-cursor-mapping> \
  --subscription-profile-root <exact-enrolled-cursor-profile> \
  --plane-descriptor <private-proof-root>/cursor-qualification-request.json \
  <campaign-goal-and-proof-options>
```

The request contains no instruction body and grants no materialization, launch,
or qualification authority outside that exact Pass B. While the activated
probe is active, run:

```bash
python3 <skill-root>/scripts/adapter_lab.py cursor-native-view \
  --run-root <proof-root>/probes/<activated-run>
```

The command prints the exact human read-only tmux attach command to stderr,
observes one read-only client attach and detach structurally, and writes no pane
content. Run a separate ordinary Cursor Pass B without a descriptor; Pass B
still composes the exact dynamic absolute `--workspace` selector for its
distinct control fixture. Then join and promote:

```bash
python3 <skill-root>/scripts/adapter_lab.py cursor-pair \
  --activated-receipt <activated-run>/receipt.json \
  --ordinary-receipt <ordinary-run>/receipt.json \
  --native-view <activated-run>/cursor-native-view.json \
  --out <private-proof-root>/cursor-terminal-qualification.json
python3 <skill-root>/scripts/adapter_lab.py qualify \
  --manifest <fresh-cursor-doctor-manifest> \
  --mapping <fresh-cursor-mapping> \
  --receipt <private-proof-root>/cursor-terminal-qualification.json \
  --out <qualified-cursor-manifest>
```

Both runs must bind the same exact authenticated private Cursor profile,
controller, campaign, goal, executable, adapter, protocol, compiler policy, and
unresolved default-model selection, but must use distinct workspaces and run
identities. The activated instruction is a temporary root `AGENTS.md` with a
deterministic Puppet qualification envelope; the descriptor, activation plan,
and receipt bind the wrapper hash and underlying effective-contract hash
separately. Activation adds one fixed, non-secret opaque positional trigger as
the final launch argument so Cursor starts the contract already materialized in
`AGENTS.md`; one allowlisted descriptor symbol resolves to that exact literal,
whose SHA-256 is plan and launch authority. Never put the compiled contract,
task body, or an operator-supplied
prompt in argv. The ordinary control and every post-qualification regular
launch remain positional-prompt-free and use transcript-blind post-launch
transport. Require `AGENTS.md` to be absent, create it mode 0600 with
no-follow `O_EXCL`, and remove it only after exact registered-PID halt. Never
overwrite, append to, or follow a repository-owned `AGENTS.md`. A failed or timed-out
activation rolls it back only after the controller proves the exact target
stopped and the protected same-target population returned to baseline. Halt,
population, artifact, or rollback ambiguity leaves the activation fenced for
controller adjudication; recovery never relaunches or guesses at cleanup. The
prior `.cursor/rules/*.mdc` and root-`AGENTS.md` post-launch-trigger activation
evidence remains non-promotable legacy proof and cannot satisfy this descriptor
version.

Grok qualification uses `grok-request`, one positive Pass B, one linked
ordinary control, `observe-grok-view` for each real read-only TUI, `pair-grok`,
`verify-grok-pair`, and only then `qualify`. The positive request is compiled
before launch, derives a hash-named rule, sends only an opaque trigger, and
rolls back after exact halt. Both members must bind the same logged-in private
profile and `grok-4.5` default while using distinct workspaces, process/tmux
identities, sockets, UUIDs, checkpoints, and viewers. Both exact tree halts
must restore the same protected baseline. One member, synthetic or
filesystem-only absence, or an edited manifest cannot promote or launch. The
exact CLI forms and receipt joins live in
[adapter-contract.md](references/adapter-contract.md).

Read [operating-contract.md](references/operating-contract.md) for lifecycle and
ownership rules, [adapter-contract.md](references/adapter-contract.md) before
changing adapters, and [prompt-patterns.md](references/prompt-patterns.md) when
building a contract or handoff.

## Checkpoint authority

Use source-free `conformance` handoffs for the shared real-harness probe. They
bind run, nonce, phase, sequence, executable, adapter, protocol, and artifact
fingerprints and must omit `candidate_commit`. Use `source` handoffs for
implementation work; they require a full exact commit. Any identity drift
invalidates the corresponding verdict.

Targets publish claims and evidence references. The controller alone records
`repair`, `conformance_accept`, `source_accept`, `block`, or `fail`, and alone
performs terminal acceptance. Learn only from exact commits, validated bounded
handoffs, controller-run tests, and independent reviews.

## Self-hosting boundary

Keep the supervising Puppet release immutable for a live session. Give the
target a separate candidate worktree. Never execute candidate code while that
candidate is mutating. Bootstrap Puppet returns `unsupported` for `promote` and
`close`; promotion enters a later accepted surface only after exact-head tests,
real conformance, independent review, controller acceptance, and rollback proof.

Read [proof-provenance.md](references/proof-provenance.md) before reusing prior
work. Historical, private, branch-only, uncommitted, terminal-derived, or
license-unclear evidence is design input until its exact delta is re-proved.

## Controller authority boundary

Qualification receipts require inclusion in Puppet's fixed per-account local
controller ledger and remain bound to the current executable, adapter,
platform, protocol, goal, terminal state, tmux server, and proof artifacts.
This prevents a caller-selected proof root from qualifying itself. It remains a
cooperative same-UID mechanism, not cryptographic containment against hostile
code already running as the operator; the YOLO warning still governs the trust
boundary.

## Stop conditions

Stop and preserve a precise blocker when identity is ambiguous, a lock belongs
to another owner, a mapping or transport is unproved, transcript reading would
be required, a checkpoint is malformed, exact halt is uncertain, review stays
required after two repairs, controller-ledger inclusion is missing, an active
lease belongs to another run, exact recovery is required, or an external human gate appears. Never weaken a
guardrail or substitute a fake harness for real conformance.
