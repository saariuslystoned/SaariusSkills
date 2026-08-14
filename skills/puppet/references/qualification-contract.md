# Qualification contract

This contract governs census, probes, pairing, activation transactions,
startup gates, and promotion only; nothing here authorizes an ordinary
launch. Every generated capability is doctor-only until a real conformance
probe qualifies the exact executable, adapter, platform, and protocol
fingerprints.

## Census and qualification core

Run `adapter_lab.py census` without launching an agent. Treat every
generated capability as doctor-only until a real conformance probe
qualifies the exact executable, adapter, platform, and protocol
fingerprints. Enable it only with `adapter_lab.py qualify` and the
accepted receipt from that probe. A probe also requires the separately
supplied campaign ID, canonical goal repository root, and exact
repository/commit/path/SHA-256 goal tuple. Regular probes require the
exact authenticated Puppet-owned private profile and bind its closed
launch environment; they never borrow an operator-global harness home.

Codex is stricter: one accepted worktree receipt can never qualify a
public manifest. A bounded Codex candidate additionally requires a
distinct ordinary-control run linked to that positive receipt and
supplied with its own clean linked-worktree descriptor from the same Git
common repository and exact head, the same exact private subscription
profile, the same current-default launch vector with no model or effort
selector while resolved model and effort remain unavailable, distinct
non-overlapping workspace/process/tmux/lease identities, one real
read-only native-view attach/detach observation, and exact terminal
halts. `adapter_lab.py pair-codex` writes that body-free evidence
create-only and controller-attests it; `verify-codex-pair` independently
rebuilds it. Both commands report `paired_evidence_only`, and the pair
itself never authorizes launch. `adapter_lab.py qualify` must
independently rebuild that exact terminal pair against the current
doctor manifest before it can write a qualified runtime manifest. Public
doctor and launch then reverify the pair and require the same exact
private subscription-profile binding.

`--goal-repo` names the canonical local Git root. `--goal-repository`,
`--goal-commit`, `--goal-path`, and `--goal-sha256` must exactly match
the submitted authorization; they are independent expected values, not
inferred from the authorization file.

## Unqualified plans are doctor-only

A doctor-only, unqualified Codex manifest yields a
`target_gate.state=waiting_for_human` packet for the exact
`codex_regular_pass_b` identity. It names the expected source-only
evidence kinds but reports preserved evidence kinds as empty because
planning supplies and validates no such artifacts. It proposes `doctor`,
but marks launch, status, waits, attach, open-view, and halt unsupported.
Its `profile-init` command is a human-gated proposal: the human must
choose either the named process-local broker route or a human-present
login into the lane-owned home before any account action. The plan
carries route names only, never values or credential selectors.

A doctor-only, unqualified Claude manifest yields a body-free
`target_gate.state=waiting_for_human` packet for `claude_regular_pass_b`.
It names the expected `zero_agent_claude_matched_control_blocker`
observation kind but reports preserved evidence kinds as empty because
planning receives no observation artifact. Only `doctor` remains
proposed; launch, status, waits, attach, open-view, and halt are
unsupported. Private-profile initialization remains a human-gated
proposal under `human_approve_authenticated_claude_matched_control_pair`;
the plan neither authenticates nor runs either member of that pair.

A doctor-only, unqualified Cursor manifest yields a body-free
`qualification_required` boundary for `cursor_regular_pass_b`. The exact
private file-store route is available through `profile-init` and
`profile-status`; neither command performs login. Cursor promotion then
requires two fresh regular Pass B runs against that exact profile: one
qualification-only, create-once namespaced workspace rule and one
separate ordinary control. The activated run must also carry a
structurally observed read-only native-view attach/detach. `cursor-pair`
joins only those exact accepted runs after both exact halts and
activated-rule rollback. A source-only binding, a standalone activation
receipt, or an ordinary receipt cannot qualify the manifest.

## Codex entry plans and root-run qualification

For an unqualified Codex regular plan, do not execute that proposal
until its `human_choose_private_codex_auth_route` gate is explicitly
resolved. When a root-run Codex qualification is separately authorized,
supply the operator plan to the positive probe with `--codex-entry-plan`
before launch. The controller recompiles its exact schema and full field
set, persists its source binding before target start, and includes that
binding in the accepted positive receipt and controller attestation.
Recovery requires that same exact persisted plan. Pairing accepts no new
entry-plan argument. Its hash-verified `entry_mode` is the only accepted
claim for direct repository (`direct_git_root`) versus explicit cockpit
(`cockpit_explicit`) entry, and it must name the exact positive worktree
branch and head. Static repository file absence, target self-report,
mocked launch, post-hoc plan synthesis, or doctor-only output is never
entry or promotion evidence.

Observe a native viewer only through structural tmux client/process
identity: never retain pane body, prompt, transcript, scrollback, or
authentication or configuration content. Keep target process, tmux
server, viewer client/process, and controller lease identities separate
in every proof.

## Claude matched-control pairing

For an unqualified Claude regular plan, profile initialization is only
preparation for the separately approved authenticated matched-control
pair; it is not launch or matched-control authority.

Claude matched-control probe reservations are one-use. Never retry or
relaunch the same run after reservation; use exact `adapter_lab.py
recover`. Stop and preserve the run when its attestation, reservation,
ready checkpoint, or hash-only signal observation is missing or drifted.
Also stop on a non-source, ambiguous, or post-observation recreated
signal leaf; do not manually delete or recreate it. An accepted
activation lifecycle remains non-qualifying until a separate ordinary
control and paired no-bleed proof are accepted. Its terminal receipt
must retain both matched-control artifacts as exact proof references;
standalone verification rejoins them to the source-owned ready request
and controller journals before returning the still-non-promotable
lifecycle result. For the separately approved live Claude pair, run the
ordinary control with `adapter_lab.py probe --paired-activation-receipt
ACTIVATION_RECEIPT` and no plane descriptor. While each member is live,
attach exactly one read-only controller-produced tmux view and record
its structural identity with `adapter_lab.py observe-claude-view
--proof-root ROOT --run-id RUN`. After both terminal receipts exist,
`adapter_lab.py pair-claude --manifest MANIFEST --mapping MAPPING
--activation-receipt ACTIVATION_RECEIPT --control-receipt
CONTROL_RECEIPT` writes a fixed create-only paired receipt beside the
control. Only that controller-attested pair may close Claude's
incomplete mapping; activation-only and unpaired control receipts remain
non-promotable. Repeat the same `--paired-activation-receipt` on
linked-control recovery. These commands retain structural hashes only
and never read or store pane, instruction, configuration,
authentication, prompt, or reply bodies.

## Cursor workspace qualification

Cursor workspace qualification also uses a one-use activation
transaction. Build a body-free request from the fresh doctor manifest;
the activated Pass B compiles the effective contract, derives the exact
hash-named qualification-only descriptor, and runs it with
`--plane-descriptor`:

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

The request contains no instruction body and grants no materialization,
launch, or qualification authority outside that exact Pass B. While the
activated probe is active, run:

```bash
python3 <skill-root>/scripts/adapter_lab.py cursor-native-view \
  --run-root <proof-root>/probes/<activated-run>
```

The command prints the exact human read-only tmux attach command to
stderr, observes one read-only client attach and detach structurally,
and writes no pane content. Run a separate ordinary Cursor Pass B
without a descriptor; Pass B still composes the exact dynamic absolute
`--workspace` selector for its distinct control fixture. Then join and
promote:

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
controller, campaign, goal, executable, adapter, protocol, compiler
policy, and unresolved default-model selection, but must use distinct
workspaces and run identities. The activated instruction is a temporary
root `AGENTS.md` with a deterministic Puppet qualification envelope; the
descriptor, activation plan, and receipt bind the wrapper hash and
underlying effective-contract hash separately. Activation adds one
fixed, non-secret opaque positional trigger as the final launch argument
so Cursor starts the contract already materialized in `AGENTS.md`; one
allowlisted descriptor symbol resolves to that exact literal, whose
SHA-256 is plan and launch authority. Never put the compiled contract,
task body, or an operator-supplied prompt in argv. The ordinary control
and every post-qualification regular launch remain positional-prompt-free
and use transcript-blind post-launch transport. Require `AGENTS.md` to
be absent, create it mode 0600 with no-follow `O_EXCL`, and remove it
only after exact registered-PID halt. Never overwrite, append to, or
follow a repository-owned `AGENTS.md`. A failed or timed-out activation
rolls it back only after the controller proves the exact target stopped
and the protected same-target population returned to baseline. Halt,
population, artifact, or rollback ambiguity leaves the activation fenced
for controller adjudication; recovery never relaunches or guesses at
cleanup. The prior `.cursor/rules/*.mdc` and root-`AGENTS.md`
post-launch-trigger activation evidence remains non-promotable legacy
proof and cannot satisfy this descriptor version.

## Grok qualification and the deferred shared leader

For Grok 0.2.112, qualify the current standalone private-profile pair
first. The attended shared-leader/exact-socket surface remains a
deferred no-copy operator-subscription candidate. Its external auth
provider is not a cached session export or generic consumer bridge
without a provisioned token provider. Use `grok_shared_leader.py` only
to compile the exact source plan and bind structural observations.
Require an empty same-target baseline before the attended leader starts.
Puppet must not start or signal that leader: present the exact
`human_start_attended_operator_grok_leader` handoff, then bind its
private socket and process identity. Client halt authority targets only
the exact client root and must preserve the leader tree and socket
unchanged. Socket ownership, TUI attach semantics, configuration
no-bleed, and live halt remain blockers until independently observed.

Do not mix the deferred shared-leader topology into the promotable
standalone pair: every current Grok member gets its own new socket and
UUID below the same exact enrolled private profile.

Grok qualification uses `grok-request`, one positive Pass B, one linked
ordinary control, `observe-grok-view` for each real read-only TUI,
`pair-grok`, `verify-grok-pair`, and only then `qualify`. The positive
request is compiled before launch, derives a hash-named rule, sends only
an opaque trigger, and rolls back after exact halt. Both members must
bind the same logged-in private profile and `grok-4.5` default while
using distinct workspaces, process/tmux identities, sockets, UUIDs,
checkpoints, and viewers. Both exact tree halts must restore the same
protected baseline. One member, synthetic or filesystem-only absence, or
an edited manifest cannot promote or launch. The exact CLI forms and
receipt joins live in [adapter-contract.md](adapter-contract.md).

## Startup-screen gates

Claude is the single exception to the terminal-capture ban and does not
use the plain structural settle: before the initial prompt it runs a
narrow internal startup-screen reducer over the bounded owned pane of
the exact registered Claude process. The reducer classifies the pane
against a fixed allowlist — the security notice, an exact-workspace
trust prompt, the bypass warning, or the ready screen — requires the
displayed workspace path to equal the contract worktree exactly,
reconstructing only bounded hard-wrap boundaries between the unique
`Accessing workspace:` label and one line beginning with the exact
`Quick safety check:` marker, excluding that boundary line's narrative
tail, and selects and recaptures the exact authorized `yes` choice
before pressing Enter. It retains only gate/selection/size/hash/timing
metadata and discards raw bytes, and a login, account, terms,
subscription, unknown, ambiguous, oversize, or non-UTF-8 screen fails
closed with no retry. It is bounded by the Claude startup-settle and
transition deadlines, and immediately before delivery re-verifies
process, pane, and executable identity and that the pane is still the
ready screen. This is the only ordinary-operation terminal read Puppet
performs.

The only ordinary-operation exceptions to the transcript ban are the
narrow Claude and Cursor startup-screen reducers in this section. Each reads
only a bounded owned pane before ordinary prompt delivery, classifies a
fixed harness-specific allowlist, retains only
gate/selection/workspace-match/size/hash/timing metadata, and discards
the raw bytes. Cursor may send literal `a` once only for its exact
two-option `Workspace Trust Required` screen when the displayed path
equals the Puppet-owned workspace; an MCP-expanded, login, terms,
permission, unknown, or ambiguous screen fails closed.

## Shared authority root for probes

Pass B probes and normal live sessions share one fixed,
checkout-independent authority root with one lock, projection, and
durable lease history per target. Different harness targets may run
independently; a caller-selected proof or state root cannot create a
second lane for the same target. A lossy legacy global projection keeps
older controllers fenced while any per-target lane is active.

Interrupted probes recover under
[campaign-recovery.md](campaign-recovery.md).
