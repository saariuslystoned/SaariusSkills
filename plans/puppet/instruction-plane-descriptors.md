# Puppet native instruction-plane descriptors

Status: active design/evidence record; no plane is qualified by this document.

The deterministic `initial_message_wrapper` composes Puppet's universal,
harness, unresolved-default-model, regular-lifecycle, runtime-contract, and task
layers for safe delivery through the existing tmux transport. It is a fallback
composition/transport contract. It is **not** any of the three harness-native
instruction planes and cannot by itself make a harness row `qualified`.

## Descriptor contract

Each native plane is an immutable, content-addressed descriptor bound to one
exact harness/version/adapter tuple:

```yaml
schema: puppet.instruction-plane/v1
descriptor_id: <stable Puppet name>
target:
  harness: <agy|codex|claude|cursor|grok>
  version: <exact version>
  adapter_manifest_sha256: <sha256>
  requested_model: default
  observed_model: <exact value|unavailable>
  config_fingerprint: <sha256|unavailable>
plane: <harness_global|workspace_addendum|per_run_additive>
status:
  surface: <factual|hypothesis|unsupported>
  activation: <qualification_only|disabled>
materialize:
  - artifact_id: <stable id>
    root_ref: <config_root|workspace_root|ephemeral_root>
    relative_path: <contained relative path>
    content_ref: effective_contract
    write_mode: <create_only|patch_if_base_sha256>
launch_delta:
  cwd_ref: <workspace_root|null>
  env: [{name: <allowlisted name>, value_ref: <non-secret lane binding>}]
  argv: [{literal: <allowlisted flag>} | {path_ref: <artifact>} | {name_ref: <closed name>} | {root_ref: <typed root>}]
rollback:
  owned_artifacts: [<artifact refs>]
  preimage_sha256: [<required for patched artifacts>]
  retain_hash_only_proof: true
assertions: [<closed assertion ids>]
blockers: [<closed blocker ids>]
```

Instruction bodies never appear in a descriptor, argv, environment, registry,
journal, receipt, or committed proof. `content_ref` is symbolic. Paths resolve
only beneath lane-owned roots. `hypothesis` and `unsupported` descriptors are
non-activatable; factual but unqualified descriptors can run only in isolated
qualification mode.

Activation uses four bounded operations:

```text
render_plane -> plan_activation -> activate_qualification -> verify_and_rollback
```

The compiler manifest remains immutable. A separate
`puppet.plane-binding/v1` envelope binds its SHA-256, effective-contract SHA-256,
plane-descriptor SHA-256, and exact adapter-manifest SHA-256. The activation
receipt then adds rendered-artifact and launch-plan hashes. This avoids circular
hashes while making drift fail closed.

The descriptor is intentionally not promotion authority. Version 1 has no
`qualified` descriptor state: `qualification_only` means the exact closed tuple
may be staged inside an isolated qualification lane, while a separate
controller-attested plane binding and receipt own any later qualified verdict.
Historical descriptors therefore remain structurally parseable when a new
harness version is censused; exact version support is checked by the activation
and evidence registry, not changed retroactively in this parser.

The first activation grammar is deliberately partial: Claude's additive file
surface uses one fixed `effective_contract_file` at
`ephemeral_root/puppet-instructions.md`, a lane `CLAUDE_CONFIG_DIR`, disabled
auto-memory, and the closed `--append-system-prompt-file <artifact>` vector.
Other matrix rows remain disabled records until their exact namespaced path,
technical-settings/template renderers, isolation bindings, and rollback
transactions are implemented. A structurally valid descriptor is never by
itself launch authority.

Materialization list order is part of descriptor identity because future
multi-artifact transactions execute and roll back in a declared order. Lists
that are semantically sets—assertions, blockers, ownership, preimages, and
environment bindings—are normalized before fingerprinting.

## Current exact-version discovery matrix

`candidate` means a native surface was found but is not live-qualified.

| Harness | Harness-global | Workspace | Per-run additive |
|---|---|---|---|
| AGY 1.1.5 | documented custom-agent candidate via `--agent`; blocked because no isolated config-root or positive sandbox-off control is proved | exact source-owned, activation-disabled `.agents/agents/puppet-<rendered-sha>/agent.md` + planned `--agent puppet-<rendered-sha>` descriptor; a source-only body-free binding rejoins compiler bytes, strict workspace inode identity, current doctor/adapter/protocol/execution, and the immutable regular verdict while all lifecycle authority stays false | unsupported; no additive file/stdin system-instruction surface found |
| Codex CLI 0.145.0 | lane-owned `CODEX_HOME` named profile with additive `developer_instructions`; factual candidate blocked on isolated auth | nested/scoped `AGENTS.md` candidate; unqualified and still blocked on isolated auth | unsupported for the regular TUI because `-c developer_instructions=...` exposes the body in argv |
| Claude Code 2.1.215 | namespaced custom output style under lane `CLAUDE_CONFIG_DIR`, selected by lane settings; unqualified | create-only namespaced `.claude/rules/*.md` candidate; unqualified | exact parser accepts `--append-system-prompt-file`; strongest first candidate, unqualified |
| Cursor Agent 2026.07.17-3e2a980 | unsupported: no session-specific User Rules/config-root selector | namespaced `.cursor/rules/*.mdc` or scoped `AGENTS.md`, selected by absolute `--workspace`; sole viable candidate, unqualified | unsupported; no public additive file transport found |
| Grok Build 0.2.106 | exact `$GROK_HOME/rules/*.md` additive surface; factual candidate blocked because the isolated root also owns auth/session state | deepest-scope `.grok/rules/*.md` plus explicit `--cwd`; strongest first candidate, unqualified | unsupported: append alias is literal `--rules`, file variants are rejected, replacement flags forbidden |

## Qualification and no-bleed evidence

Every viable descriptor must prove both direct-repository and cockpit entry,
using the current default model and a Puppet-owned session/worktree/config root.
Required evidence is structural and source-blind:

- exact executable, adapter, protocol, compiler, effective-contract, plane, and
  requested/observed model identities;
- an opaque target-only marker in the expected checkpoint and its absence from
  an ordinary control;
- vendor tools, built-ins, safety, and repository authority retained;
- target/control config metadata and protected process populations unchanged;
- simultaneous lane isolation and exact process/session ownership;
- create-only or preimage-guarded materialization plus exact rollback; and
- hashes only in durable proof, with no instruction/task body, transcript,
  scrollback, config content, credential, or auth material.

An unsupported plane is a valid independent result. It does not authorize a
fallback wrapper to impersonate that plane. A harness baseline can be promoted
only according to the campaign acceptance rules at one exact pushed head.

## Deferred command and automode map

Keep a versioned discovery matrix for useful long-running commands, but do not
activate them automatically. Current future tuples include AGY regular/goal/
teamwork-preview, Codex regular/goal, Claude regular/goal/loop, and regular
sessions for Cursor and Grok. Each command needs its own activation,
continuation, steering, resume, and termination proof. Default/alternative model
selection is a separate dimension. Automatic harness/model/command routing stays
deferred until this evidence exists. Pi-specific RPC, child-session, and
observation-lease evidence is recorded separately in
`plans/puppet/deferred-pi-adapter.md`; it does not add Pi to the current matrix
or authorize an upstream dependency.
