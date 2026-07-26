# Grok Build regular-session qualification harness (v0.1)

Status: paired-runtime qualification substrate implemented; no live Grok pair
is qualified until both subscription-backed runs and their native views are
independently verified.

## Scope and lane contract

- Current source-only target: Grok Build 0.2.111 regular TUI with its current
  default model.
- Historical 0.2.106 parser-evidence source head inspected:
  `b8cce94bf2a4a62f974207a95abcfe1668412b90`.
- Source-only launch-authority implementation base:
  `e18dc4509644eaf069f3e9ce41ab3db081f01dbd`.
- The parser-evidence lane used bounded parser/model/config probes only. It did
  not launch a model session, read live config/auth/session contents, or modify
  any file. This follow-up changes source and tests only; it performs no live
  Grok or credential-bearing operation.
- `/goal`, `/loop`, native agent profiles, automatic routing, explicit model
  selection, and non-Puppet session adoption remain out of scope.

## 1) Exact executable and parser evidence

The current PATH winner is an operator-local symlink chain to the final Mach-O
binary:

```text
~/.local/bin/grok -> ~/.grok/bin/grok ->
~/.grok/downloads/grok-0.2.111-macos-aarch64
```

- Isolated-home version: `grok 0.2.111 (94172f2aa4e5)`.
- Final binary SHA-256:
  `e1fafdfffe14f339460befaf194360e8f90bfd02efe8a4f24cfa1c7aea657ffe`.
- Isolated-home version-output SHA-256:
  `580e7f325a2b1c0807e2eca5ad4bceac313dee481c3e66c06af08013ef89430d`.
- Ordinary-home channel-labeled output:
  `grok 0.2.111 (94172f2aa4e5) [stable]`, SHA-256
  `056584a715a3f6cdb882797e20c49495c1dc8874d83eb4c62d474a1fb188f15d`.
  It is the safe-field version identity in the doctor manifest consumed by the
  source planner, not private-profile launch authority. The isolated-home hash
  above is parser-probe evidence and must not be substituted for that census
  identity.
- Main-help SHA-256:
  `d11f1815c770a69d87a05f394c6f7759562738c7de4e29a043f9f06c0aeba1c1`.
- `help agent` SHA-256:
  `80eca1cc827e677c5d4310fe60ccaa941627cc688189405742e69e4f4ec734d3`.

The canonical machine-readable prior-evidence admission input remains the dated
0.2.106 packet `grok-build-0.2.106-pass-a-evidence.json`, with record SHA-256
`219f5e5b20a7ea4de65b35c098eeb2a31f287a6e44d8c389857863554b1f6ef4`.
`puppet_lib/grok_evidence.py` rederives every admitted field from source-owned
historical constants independently of the current 0.2.111 launch tuple, and
rejects altered hashes, parser classifications, limitations, or authority
bits. It distinguishes the parser lane's observation-source revision
`b8cce94bf2a4a62f974207a95abcfe1668412b90` from evidence-artifact revision
`c711c6b11ef529e1ff7860bef4232ad03c83e6ef`, which first records the detailed
facts. The packet also binds both dates, lane owner, artifact blob and SHA-256,
proof strength, mechanism/version scope, portability/operator assumptions, MIT
attribution, reuse decision, deterministic tests, and remaining live delta for
each claim. It is not a complete current Pass-A census and is not consumed by
launch, session, probe, adapter, qualification, or promotion code.

An alternate PATH candidate is a shell `exec` wrapper. If selected, the
fingerprinted launcher and live runtime process differ. Puppet must bind or
reject the complete launcher chain instead of assuming argv executable equals
kernel process executable.

Relevant parser-visible flags include `--agent`, `--rules`,
`--system-prompt-override`, `--prompt-file`, `--cwd`, `--worktree`,
`--session-id`, `--resume`, `--continue`, `--leader-socket`, `--model`,
`--reasoning-effort`, `--always-approve`, and `--sandbox`.

The 0.2.111 help re-census still exposes those candidates. Help presence is
parser evidence only and does not prove live semantics.

Closed-root `--version` parser probes on 2026-07-23 produced:

| Probe | Exit | Bounded output SHA-256 |
|---|---:|---|
| `--append-system-prompt <sentinel>` | 0 | `580e7f325a2b1c0807e2eca5ad4bceac313dee481c3e66c06af08013ef89430d` |
| `--append-system-prompt-file /dev/null` | 2 | `bbeae0499314fa15011986eda0bd674a765c47df9a58aee6b4055445acc174ee` |
| `--rules-file /dev/null` | 2 | `97d14caf487b18ca0fb0a6013efb50d1eaae46565c2f38d5bae2f71c349ca673` |
| `--system-prompt <sentinel>` | 0 | `580e7f325a2b1c0807e2eca5ad4bceac313dee481c3e66c06af08013ef89430d` |
| `--prompt-file /dev/null` | 0 | `580e7f325a2b1c0807e2eca5ad4bceac313dee481c3e66c06af08013ef89430d` |
| `--agent <sentinel>` | 0 | `580e7f325a2b1c0807e2eca5ad4bceac313dee481c3e66c06af08013ef89430d` |
| `--always-approve --sandbox off --cwd ... --leader-socket ...` | 0 | `580e7f325a2b1c0807e2eca5ad4bceac313dee481c3e66c06af08013ef89430d` |

These were zero-agent parser probes. They neither prove alias semantics beyond
parser acceptance nor authorize launch.

An isolated 0.2.111 `inspect --json` fixture with its own Git root discovered
both exact create-only candidates:

- `.grok/rules/puppet-<64-hex>.md`; and
- compatibility `.claude/rules/puppet-<64-hex>.md`.

The bounded inspection output was not retained; its SHA-256 was
`fca38ce36511ff04bf3d5dc5f9d4eae570d2a84adc48735ade1e11f866ae9d14`.
The native `.grok/rules` candidate remains the source-only workspace
descriptor. Discovery proves a current surface, not precedence, activation,
no-bleed, instruction consumption, or qualification.

Parser-only controls prove:

- `--append-system-prompt` is only an alias of literal `--rules <RULES>`;
- `--append-system-prompt-file` and `--rules-file` are rejected;
- `--system-prompt` aliases replacement `--system-prompt-override`;
- `--prompt-file` is single-turn task input, not a system addendum; and
- top-level `--agent <name|definition-file>` selects a whole agent profile,
  including prompt/tool behavior, rather than an additive instruction file.

`--always-approve --sandbox off --no-leader --trust --cwd /var/empty --leader-socket <path>
--version` parses successfully. Runtime semantics remain live-unqualified.

## 2) Instruction-plane map

`session_profile=regular` is the active unprefixed lifecycle selection, not an
instruction plane.

### Plane 1: lane-owned harness-global addendum (factual, blocked)

Exact-version embedded documentation names `$GROK_HOME/AGENTS.md` and
`$GROK_HOME/rules/*.md`. The safe candidate is a create-only namespaced rule
under a unique lane `GROK_HOME`. Named agents remain disabled until default
prompt/tool inheritance is proved.

This plane cannot be live-tested yet: `GROK_HOME` owns config, authentication,
sessions, skills, plugins, and logs. A clean lane root is unauthenticated.
Puppet must never copy, link, inspect, hash, or persist the operator's live
auth/session store to manufacture isolation.

This is a first-enrollment limitation, not a per-run authentication contract.
Current xAI documentation classifies browser OIDC and device-code sessions as
refreshable, and Grok reuses cached credentials. Puppet therefore keeps one
stable private Grok profile across runs, checks its native status silently
before launch, and asks for a human login only when that profile has never been
enrolled or Grok reports it invalidated. Safe adoption of an already-authorized
operator subscription remains the preferred but unqualified route because
inheriting the complete ordinary `GROK_HOME` would also inherit unrelated
configuration, instructions, plugins, sessions, and logs.

#### No-copy adoption candidates

The installed 0.2.111 binary exposes a more promising native boundary than
copying `auth.json` or inheriting the operator's whole `GROK_HOME`:

- `grok agent leader` runs a shared leader process;
- `grok agent --leader` connects a client to a shared leader; and
- `--leader-socket` selects the exact Unix socket.

Puppet therefore prefers a future process-local shared-leader broker: an
attended operator-owned process keeps the ordinary native authentication, while
a private Puppet client connects only through a controller-bound socket. This
now has a source-only admission and client-halt plan, not launch authority.
The exact human handoff is:

```text
grok agent leader --no-exit-on-disconnect --relay-on-demand \
  --no-auto-update --leader-socket <controller-owned-private-socket>
```

Puppet may compile and validate that vector but may not execute or signal it.
The plan requires an empty same-target baseline, binds the closed private
client vector, and models client completion only when the exact client tree
stops while the attended leader tree and socket remain unchanged. Qualification
must still prove that the socket belongs to the bound leader, the TUI actually
attaches without consulting local auth, and
operator instructions, configuration, plugins, sessions, logs, and tools do
not bleed across the leader/client boundary; bind exact socket ownership and
process lifecycle; and show that stopping the Puppet client never stops or
mutates unrelated operator sessions.

The documented `auth_provider_command` is not an automatic bridge for an
already-authorized consumer subscription. It requires a separately provisioned
command that can already emit a token, so using it without such a provider
would merely move credential enrollment and storage elsewhere. Puppet will not
extract, copy, link, or print the native cached session to manufacture that
provider.

Zero-agent hashes for the exact installed surface:

- `grok agent --help`:
  `80eca1cc827e677c5d4310fe60ccaa941627cc688189405742e69e4f4ec734d3`
- `grok agent leader --help`:
  `5d0199eb0b874a66a899c34e305719e3f52eb816d3799f9b3510301fdf0455d7`

### Plane 2: workspace addendum (implemented qualification candidate)

The positive Pass-B run creates a deepest-scope
`<candidate-worktree>/.grok/rules/puppet-<contract-sha>.md` artifact with
`write_mode=create_only`, then launches from that exact worktree with
`--no-leader`, `--trust`, explicit `--cwd`, a new socket namespace below the
enrolled private profile, and a canonical new UUIDv4. The externally prepared
request is body-free. After the randomized
fixture contract is compiled, the controller derives and persists the exact
hash-named entry descriptor before process launch. Only the positive run
receives the opaque native trigger; the ordinary control receives the regular
compiled task directly and must contain zero namespaced Puppet rules before
and after execution.

Promotion requires both real receipts, distinct workspaces/processes/tmux
identities/sockets/UUIDs/checkpoints/viewers, the same exact authenticated
profile and reported `grok-4.5` default, one sequenced steering turn per run,
two structural read-only native views, two exact standalone tree halts, equal
protected before/after baselines, and positive hash-guarded rollback.
Filesystem absence by itself remains explicitly non-promotable.

### Plane 3: invocation-scoped additive file (unsupported)

`--rules` and its `--append-system-prompt` alias put instruction content in
argv. File variants are rejected. Replacement system-prompt flags are
forbidden, and `--agent <file>` is a whole-agent definition. No native
invocation-scoped additive file plane exists for this tuple.

Current first-party surface references:
`https://docs.x.ai/build/cli/reference`,
`https://docs.x.ai/build/settings`,
`https://docs.x.ai/build/features/skills-plugins-marketplaces`, and
`https://docs.x.ai/build/features/permissions`.

## 3) Default-model observation

An isolated `env -i HOME=/var/empty GROK_HOME=/var/empty` model probe reported:

```text
You are not authenticated.
Default model: grok-4.5
Available models:
  * grok-4.5 (default)
```

- Output SHA-256:
  `5c7ad803cc612bd198e2f200f4fac1340800382a0e321c9b69e2082085af18b8`.
- This proves clean-root catalog observability only. Authenticated runtime
  model and effort remain `unavailable`.
- Omit `--model` and `--reasoning-effort`; do not pin a replacement when the
  default cannot yet be observed in the live isolated tuple.

## 4) Source-only qualification launch candidate

`puppet_lib/grok_launch.py` now builds a typed, body-free candidate only from a
schema-valid doctor manifest bound to the current adapter/protocol source and
the exact 0.2.111 binary, version-output, and main-help hashes. It rechecks the
manifest's current execution-file identity, then binds the following exact
values without granting launch authority:

```yaml
env:
  HOME: <unique-lane-home>
  GROK_HOME: <unique-lane-grok-home>
  GROK_DISABLE_AUTOUPDATER: "true"
  PATH: /usr/bin:/bin
  LANG: C
  LC_ALL: C
argv:
  - --always-approve
  - --sandbox
  - off
  - --cwd
  - <absolute-fixture-cwd>
  - --leader-socket
  - <unique-lane-socket>
  - --session-id
  - <controller-owned-new-uuid>
```

The admitted lane root, `HOME`, `GROK_HOME`, and leader-socket parent must be
current-UID-owned mode-`0700` directories. `HOME` and `GROK_HOME` are distinct,
non-overlapping children of the lane root; the workspace is a separate admitted
root; the leader socket is a new contained non-symlink path; and the Grok
session id is a canonical UUIDv4. Ambient operator `HOME`, `GROK_HOME`, and
updater values cannot become this candidate's bindings. The planner does not
accept an ambient environment source: its fixed baseline is the lane `HOME`,
`PATH=/usr/bin:/bin`, and `C` locale above. Every PATH component is an existing
absolute directory, and `git` plus `sh` must resolve against that exact PATH.
`SSH_AUTH_SOCK`, operator PATH additions, user/shell/tmp identity, dynamic
loader settings, cloud/API credentials, and all other ambient values are
absent.

The older `grok_launch.py` binding remains planning authority only. The
paired-runtime path composes the same canonical vector from the body-free
private-profile binding inside Pass B and revalidates it immediately before
start. A doctor-only manifest remains fenced. A qualified manifest can clear
the normal-session fence only when it references the independently rebuilt
terminal pair; a positive member, ordinary member, filesystem-only absence
record, or edited ready bit cannot clear it. No live Grok session was launched
or qualified by this source change.

The task remains in the tmux-buffer transport. The wrapper is not native-plane
proof. Literal/replacement prompt flags, saved/latest sessions, `--continue`,
Grok-managed worktrees, and inherited operator homes are forbidden.

`HOME` matters separately from `GROK_HOME`: enabled compatibility scanners may
consult it. Qualification needs a lane-owned `HOME` or an exact complete
scanner-disable contract. The current pair uses a standalone private socket for
each member and retains complete descendant ancestry until exact halt. The
attended shared-leader design remains deferred evidence and is not silently
substituted into this qualification.

Normal-session preflight now retains every current-UID `grok`,
`grok-macos-aarch64`, or `grok-0.2.111-macos-aarch64` candidate found by the
repository-native argv-free census. The versioned name and exact 0.2.111
doctor/workspace tuple remain source-only and do not admit live launch or
parser semantics. Execution selectors cannot broaden those fixed candidate
basenames, so a declared transient such as `bash` does not become a Grok
candidate. A same-name launcher/transient vnode is retained as a candidate but
cannot match: only the validated final-runtime selector carries matching
authority.
An exact current-manifest population still requires the existing exact V2
parallel override. A same-name different-vnode candidate is a hard blocker and
cannot be hidden by that override. Doctor-only and source-only launch remain
fenced; a terminal paired manifest still performs the pre-start population
recheck before its standalone private-socket runtime starts.

## 5) Required proof and rollback

- `inspect --json` identifies exactly the candidate rule plus pre-existing
  repository instructions in expected order, without reading bodies.
- An opaque marker occurs only in the Puppet-owned positive checkpoint; matched
  ordinary and sibling controls remain unchanged.
- Built-ins, tools, agents, safety behavior, and repository authority remain
  active.
- Unique `HOME`, `GROK_HOME`, cwd, leader socket, session UUID, tmux/process
  ancestry, artifact hashes, and default-model observation are bound.
- Direct-repository and cockpit entry resolve to the same workspace identity.
- Halt targets only the exact Puppet-owned process tree and returns the
  protected population to baseline.
- Rollback removes only exact hash-matching create-only artifacts. Durable proof
  retains hashes and sanitized metadata, never prompt bodies, transcripts,
  scrollback, config contents, or credentials.

## 6) Source status and remaining deltas

- Implemented paired qualification substrate: `grok_workspace_plane.py`
  binds create-only `.grok/rules/puppet-<hash>.md` materialization, direct-
  repository and cockpit entry join, hash-guarded rollback, exact regular argv
  without model/effort selectors, and mapping-closure helpers. Ordinary-control
  filesystem absence is only a structural precheck
  (`no_bleed_verified=false`, `proof_strength=filesystem_absence_only_nonpromotable`)
  and cannot build terminal isolation or clear launch.
  `grok_qualification.py` now verifies the stronger subscription-backed
  positive/ordinary runtime pair, two native views, exact independent halt
  trees, equal protected baselines, positive rollback, exact profile/default
  model, and immutable ordinary-to-positive linkage.
- Implemented source-only: the exact 0.2.111 workspace-addendum descriptor and
  a deterministic body-free `binding_only` join rederived from its validated
  instruction manifest, effective contract, current adapter/doctor manifest,
  and current filesystem sources. The binder rebuilds the Grok launch context;
  it never accepts one from a caller. Controller-owned expected contract, run,
  lane, `HOME`, workspace, and config identities reject candidate-context
  forgery, replay, and same-path root replacement. Saved bindings perform the
  same full reconstruction on every record read. The join does not materialize
  `.grok/rules`, activate the plane, launch Grok, or authorize qualification.
- Implemented source-only: exact doctor-manifest/source/executable tuple,
  body-free argv/environment planning, private root and socket containment,
  UUID shape, a closed source-owned PATH/locale baseline with no ambient
  credential channels, and an admitted value-private launch-plan identity.
- Implemented source-only: normal-session census retains exact and mismatched
  Grok candidates, requires the existing exact override for a matching active
  population, and fails closed on different executable identity.
- Implemented source-only:
  `skills/puppet/scripts/puppet_lib/grok_shared_leader.py` compiles the exact
  attended leader handoff and private client join from the current launch
  context. It requires an empty same-target baseline, records no operator
  environment values, starts and signals no process, and grants no launch or
  qualification authority. Its structural binders admit only an exact leader
  tree plus private socket, then an exact client tree. Client completion
  requires the client tree gone while the protected leader tree and socket
  remain byte-for-byte identity-stable. Socket ownership, attach semantics,
  no-bleed, and live halt remain explicitly false.
- Implemented source-only: `target_population.py` now owns the shared
  protected/root/descendant admission policy previously embedded in the probe.
  `grok_halt.py` binds a pre-launch protected population, the exact expected
  Grok runtime selector and private leader-socket path, then admits only a
  retained exact root plus birth-bound same-runtime descendant chains. Its
  completion verifier accepts only the unchanged protected population after
  the exact root and all bound descendants stop and the leader socket is gone.
  It authorizes only an exact root `SIGINT`; broad signals and force-kill are
  structurally impossible. These records remain source-only and grant neither
  launch nor qualification authority.
- Implemented source-only: a canonical schema-v1 prior-evidence admission input
  for historical 0.2.106 Pass A binds exact executable/version/help/catalog
  hashes, parser
  classifications, model/effort/session control candidates, unavailable status
  and authenticated-effort facts, public provenance, three claim-level
  decisions/deltas, and eleven remaining live limitations. Its constants are
  intentionally decoupled from the current 0.2.111 launch tuple. Every runtime
  and promotion authority bit is false, and no runtime module consumes the
  packet.
- Implemented source-only: for the doctor-only/unqualified tuple, the operator
  plan now rederives the expected Pass-A source schema/state/record identity and
  all eleven limitations without loading or claiming to preserve an evidence
  artifact. It keeps only `doctor` as a runnable diagnostic; launch, status,
  waits, attach, open-view, and halt are unsupported. Private-profile setup
  remains a human-gated proposal, and the waiting target gate records the
  leader/child halt model as current source and advances the next safe action
  to the human-gated, lane-owned private-profile login required for live
  topology and halt proof. A schema-valid qualified manifest is not labeled
  doctor-only/unqualified.
- Intentionally unchanged: zero-agent census remains `doctor_only` with
  incomplete `project_isolation_declared` until a terminal workspace-isolation
  receipt closes the mapping. Help/parser facts alone never complete the mapping.
- Public qualification and launch remain fenced for doctor-only manifests.
  They clear only after `pair-grok`, `verify-grok-pair`, and `qualify`
  independently rebuild a terminal receipt from both real members.
- Live-qualified at exact source head `f153f18cc9749ed1b40b1420d6b60f5da4b9a6d3`:
  one positive and one linked ordinary-control Grok 0.2.111 session used the
  authenticated private profile and provider-default `grok-4.5`, explicit
  `--always-approve`, `--sandbox off`, `--no-leader`, `--trust`, private
  socket/UUID/cwd bindings, two native read-only tmux/iTerm views, two
  sequenced steering checkpoints, exact dual tree halts, equal protected
  baselines, and positive-only parent-restoring rule rollback. The pair
  independently reverified and produced a qualified manifest with public
  launch authority. The curated transcript-free record is
  `plans/puppet/live-proof/grok-f153f18-20260726.json`.
- `session.py` derives a fresh canonical socket/UUID/explicit-cwd vector for
  every qualified Grok session and rebinds the exact enrolled profile status.
- Remaining for final campaign closeout: exercise the public regular-session
  launcher from the qualified manifest, rerun after the last source change,
  and include Grok in the five-harness concurrent lifecycle proof.
- Tests: alias/file/replacement classification, explicit sandbox-off mapping,
  launcher/runtime separation, path containment, no live-home fallback,
  distinct lane sockets/UUIDs/workspaces/processes/tmux/viewers, exact
  default-model binding, positive/control relinking, baseline drift, malformed
  ancestry, missing views, incomplete halts, rollback, and filesystem-only
  shortcut rejection.

### Exact controller sequence

```text
adapter_lab.py grok-request --manifest DOCTOR --workspace-root POSITIVE_WORKTREE \
  --cockpit-root COCKPIT --controller CONTROLLER --campaign-id CAMPAIGN \
  --goal-fingerprint GOAL --private-profile-root PROFILE --out REQUEST
adapter_lab.py probe ... --target grok --plane-descriptor REQUEST
adapter_lab.py observe-grok-view --run-root POSITIVE_RUN_ROOT
adapter_lab.py probe ... --target grok \
  --paired-grok-positive-receipt POSITIVE_RECEIPT
adapter_lab.py observe-grok-view --run-root ORDINARY_RUN_ROOT
adapter_lab.py pair-grok --positive-receipt POSITIVE_RECEIPT \
  --ordinary-control-receipt ORDINARY_RECEIPT \
  --positive-native-view POSITIVE_VIEW --ordinary-native-view ORDINARY_VIEW \
  --private-profile-root PROFILE --out TERMINAL_RECEIPT
adapter_lab.py verify-grok-pair --receipt TERMINAL_RECEIPT \
  --private-profile-root PROFILE
adapter_lab.py qualify --manifest DOCTOR --mapping MAPPING \
  --receipt TERMINAL_RECEIPT --out QUALIFIED
```

The positive request is body-free; Pass B derives and persists the exact
hash-named descriptor before launch. Repeat that request on positive recovery,
or the exact positive receipt on ordinary recovery. Recovery never relaunches.
No command above adopts, inspects, or mutates the operator-global Grok home.

## 7) Blockers and stop condition

- The no-copy attended shared-leader route is deferred. It has source admission
  but still
  requires the explicit human start action and live proof of socket ownership,
  TUI attach without local auth, and configuration no-bleed. The durable
  private-profile fallback still requires one-time enrollment.
- The 2026-07-23 CP-1 source census found two exact 0.2.111 Grok processes.
  Puppet must not reuse, attach to, or stop them; live shared-leader work waits
  for an empty same-target baseline.
- No invocation-scoped additive file plane.
- Sandbox-off and always-approve semantics are parser-proved but not live-
  observed in the isolated authenticated tuple.
- The direct launcher/runtime vnode and a fail-closed retained-root/descendant
  halt contract are modeled, but Grok's actual authenticated leader/child
  topology and exact completion behavior remain live-unproved.
- No live direct/cockpit paired lifecycle, control, no-bleed, or rollback proof
  exists yet.

Keep the census manifest at `doctor_only/mapping` until the exact live sequence
above succeeds at one clean controller head. The substrate is ready for that
campaign; this source-only slice does not claim its outcome.
