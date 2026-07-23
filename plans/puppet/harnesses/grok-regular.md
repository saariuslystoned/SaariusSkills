# Grok Build regular-session qualification harness (v0.1)

Status: exact-version mapping only; no live Grok session is qualified.

## Scope and lane contract

- Target: Grok Build 0.2.106 regular TUI with its current default model.
- Parser-evidence source head inspected:
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

The PATH winner is an operator-local symlink chain to the final Mach-O binary:

```text
~/.local/bin/grok -> ~/.grok/bin/grok -> ~/.grok/downloads/grok-macos-aarch64
```

- Version: `grok 0.2.106 (bde89716f679)`.
- Final binary SHA-256:
  `7229f5e2a69b05832c86db82bebda541e92b5c24958fbfacf5c8f463394d3027`.
- Version-output SHA-256:
  `9bd542d793801415b20fcd8165e714196c3d7ae6f927782a2b41c6a0e939118e`.
- Main-help SHA-256:
  `17211afac01a2f089f47a0c6f0e9ec0ff38c0bc86a977c2da713e16c63e25fe2`.
- `help agent` SHA-256:
  `80eca1cc827e677c5d4310fe60ccaa941627cc688189405742e69e4f4ec734d3`.

The canonical machine-readable prior-evidence admission input for Pass A is
`grok-build-0.2.106-pass-a-evidence.json`, with record SHA-256
`219f5e5b20a7ea4de65b35c098eeb2a31f287a6e44d8c389857863554b1f6ef4`.
`puppet_lib/grok_evidence.py` rederives every admitted field from source-owned
constants and rejects altered hashes, parser classifications, limitations, or
authority bits. It distinguishes the parser lane's observation-source revision
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

Parser-only controls prove:

- `--append-system-prompt` is only an alias of literal `--rules <RULES>`;
- `--append-system-prompt-file` and `--rules-file` are rejected;
- `--system-prompt` aliases replacement `--system-prompt-override`;
- `--prompt-file` is single-turn task input, not a system addendum; and
- top-level `--agent <name|definition-file>` selects a whole agent profile,
  including prompt/tool behavior, rather than an additive instruction file.

`--always-approve --sandbox off --cwd /var/empty --leader-socket <path>
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

### Plane 2: workspace addendum (strongest candidate, unqualified)

Create a unique deepest-scope
`<fixture-cwd>/.grok/rules/puppet-<contract-sha>.md` artifact with
`write_mode=create_only`, then launch with explicit
`--cwd <absolute-fixture-cwd>`. Preserve every existing repository instruction.
Prove discovery order, built-in/tool retention, repository authority, and exact
hash-guarded rollback before promotion.

### Plane 3: invocation-scoped additive file (unsupported)

`--rules` and its `--append-system-prompt` alias put instruction content in
argv. File variants are rejected. Replacement system-prompt flags are
forbidden, and `--agent <file>` is a whole-agent definition. No native
invocation-scoped additive file plane exists for this tuple.

Official surface references: `https://docs.x.ai/build/features/project-rules`,
`https://docs.x.ai/build/cli/reference`, and
`https://docs.x.ai/build/settings/reference`.

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
the exact 0.2.106 binary, version-output, and main-help hashes. It rechecks the
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

This is planning authority only. The candidate records
`launch_authorized=false` with blockers for authentication isolation, the
native instruction plane, and leader/child halt authority. Normal-session
doctor also keeps Grok blocked even if a synthetic manifest claims readiness.
No live Grok session was launched or qualified by this change.

The task remains in the tmux-buffer transport. The wrapper is not native-plane
proof. Literal/replacement prompt flags, saved/latest sessions, `--continue`,
Grok-managed worktrees, and inherited operator homes are forbidden.

`HOME` matters separately from `GROK_HOME`: enabled compatibility scanners may
consult it. Qualification needs a lane-owned `HOME` or an exact complete
scanner-disable contract. Bind any leader process/socket and spawned children;
the current single pane-process identity is insufficient for a shared leader.

Normal-session preflight now retains every current-UID `grok`,
`grok-macos-aarch64`, or `grok-0.2.111-macos-aarch64` candidate found by the
repository-native argv-free census. The versioned name is detection-only and
does not admit 0.2.111 launch or parser semantics. Execution selectors cannot
broaden those fixed candidate basenames, so a declared transient such as `bash`
does not become a Grok candidate. A same-name launcher/transient vnode is
retained as a candidate but cannot match: only the validated final-runtime
selector carries matching authority.
An exact current-manifest population still requires the existing exact V2
parallel override. A same-name different-vnode candidate is a hard blocker and
cannot be hidden by that override. Because all live Grok launch remains fenced,
the eventual pre-start population recheck belongs with the future leader-tree
authority rather than an unreachable launch hook.

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

- Implemented source-only: the exact 0.2.106 workspace-addendum descriptor and
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
- Implemented source-only: a canonical schema-v1 prior-evidence admission input
  for Pass A binds exact executable/version/help/catalog hashes, parser
  classifications, model/effort/session control candidates, unavailable status
  and authenticated-effort facts, public provenance, three claim-level
  decisions/deltas, and eleven remaining live limitations. Every runtime and
  promotion authority bit is false, and no runtime module consumes the packet.
- Implemented source-only: for the doctor-only/unqualified tuple, the operator
  plan now rederives the expected Pass-A source schema/state/record identity and
  all eleven limitations without loading or claiming to preserve an evidence
  artifact. It keeps only `doctor` as a runnable diagnostic; launch, status,
  waits, attach, open-view, and halt are unsupported. Private-profile setup
  remains a human-gated proposal, and the blocked target gate names leader/child
  halt modeling as the next safe source-only action. A schema-valid qualified
  manifest is not labeled doctor-only/unqualified.
- Intentionally unchanged: census remains `doctor_only` and its incomplete
  mapping does not promote help/parser facts into live sandbox or isolation
  claims.
- Remaining `census.py` / `adapter_manifest.py`: bind proved live semantics for
  explicit `--sandbox off`, parser facts, and clean-root model evidence.
- Remaining plane lifecycle: controller-attested materialization, launch-time
  revalidation, matched no-bleed proof, and exact rollback are still absent.
- `session.py` / `tmux.py`: consume the typed plan only after qualification and
  recheck the exact candidate population immediately before target start.
- `registry.py` / `probe.py`: bind leader/child identities, lane homes, artifact
  hash, model/auth observation, no-bleed control, and exact rollback.
- Tests: alias/file/replacement classification, explicit sandbox-off mapping,
  launcher/runtime separation, path containment, no live-home fallback,
  distinct lane sockets/UUIDs, leader identity, default-model parsing, and
  rejection of wrapper-only plane claims.

## 7) Blockers and stop condition

- No approved authentication-preserving isolated `HOME`/`GROK_HOME` route.
- No invocation-scoped additive file plane.
- Sandbox-off and always-approve semantics are parser-proved but not live-
  observed in the isolated authenticated tuple.
- The direct launcher/runtime vnode is censused, but possible leader/child
  process identity and exact tree halt authority are not modeled.
- No direct/cockpit lifecycle, control, no-bleed, or rollback proof exists.

Keep Grok at `doctor_only/mapping`. Do not start live Pass B until these gates
are implemented and a clean exact pushed controller head is available.
