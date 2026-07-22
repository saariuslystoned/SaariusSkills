# Grok Build regular-session qualification harness (v0.1)

Status: exact-version mapping only; no live Grok session is qualified.

## Scope and lane contract

- Target: Grok Build 0.2.106 regular TUI with its current default model.
- Source head inspected: `b8cce94bf2a4a62f974207a95abcfe1668412b90`.
- This lane used bounded parser/model/config probes only. It did not launch a
  model session, read live config/auth/session contents, or modify any file.
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

## 4) Recommended qualification launch delta

After auth/config isolation is approved and implemented, the workspace-plane
candidate should bind:

```yaml
env:
  HOME: <unique-lane-home>
  GROK_HOME: <unique-lane-grok-home>
  GROK_DISABLE_AUTOUPDATER: "1"
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

The task remains in the tmux-buffer transport. The wrapper is not native-plane
proof. Literal/replacement prompt flags, saved/latest sessions, `--continue`,
Grok-managed worktrees, and inherited operator homes are forbidden.

`HOME` matters separately from `GROK_HOME`: enabled compatibility scanners may
consult it. Qualification needs a lane-owned `HOME` or an exact complete
scanner-disable contract. Bind any leader process/socket and spawned children;
the current single pane-process identity is insufficient for a shared leader.

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

## 6) Required Puppet source deltas

- `census.py` / `adapter_manifest.py`: bind or reject launcher chains; record
  explicit `--sandbox off`, parser facts, and clean-root model evidence.
- `instructions.py`: bind a native-plane descriptor digest separately from the
  fallback wrapper.
- `adapters.py` / `session.py` / `tmux.py`: support allowlisted per-launch
  environment, exact cwd, leader socket, and session UUID without a shell
  wrapper or body in argv/env/proof.
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
- Launcher/runtime and possible leader-process identities are not yet modeled.
- No direct/cockpit lifecycle, control, no-bleed, or rollback proof exists.

Keep Grok at `doctor_only/mapping`. Do not start live Pass B until these gates
are implemented and a clean exact pushed controller head is available.
