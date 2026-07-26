# Cursor Agent regular-session qualification harness (v0.1)

## Scope and lane contract

- File purpose: exact-version design and public operating record for Cursor
  Agent regular-session qualification under `codex-goal-regular-qualification.md`.
- Current source baseline: integration head
  `94b303fb9411c8de79a9d24367c916a2f1e465ae`.
- Objective: qualify the sole viable workspace plane without granting authority
  to source-only plans or one-sided activation evidence.

## Current public qualification path (2026-07-26)

The controller now has a public, qualification-only Cursor path. This source
change did not launch Cursor or inspect the enrolled private profile; fresh real
evidence is still required before any manifest becomes promotable.

1. Run a fresh Cursor census and scaffold at the current controller source.
2. Create a body-free request:

   ```bash
   python3 skills/puppet/scripts/adapter_lab.py cursor-request \
     --manifest <fresh-cursor-doctor-manifest> \
     --out <private-proof-root>/cursor-qualification-request.json
   ```

3. Run an activated regular Pass B with that request, the fresh manifest and
   mapping, and `<exact-enrolled-cursor-profile>`. Pass B compiles the effective
   contract, derives
   `.cursor/rules/puppet-<effective-contract-sha256>.mdc`, requires the
   workspace `.cursor` root to be absent, creates the rule and directories
   create-only, and composes exactly one absolute `--workspace` selector with
   `cursor-agent --yolo --sandbox disabled`.
4. While the activated probe is live, run:

   ```bash
   python3 skills/puppet/scripts/adapter_lab.py cursor-native-view \
     --run-root <activated-run-root>
   ```

   The command prints the exact read-only attach command, observes exactly one
   read-only tmux client attach and detach structurally, and never reads pane
   content.
5. Run a distinct ordinary regular Pass B without a plane descriptor, using the
   same controller, campaign, goal, executable, compiler policy, unresolved
   default-model selection, and exact private profile, but another workspace.
6. After both accepted exact halts and activated-rule rollback, join them:

   ```bash
   python3 skills/puppet/scripts/adapter_lab.py cursor-pair \
     --activated-receipt <activated-run-root>/receipt.json \
     --ordinary-receipt <ordinary-run-root>/receipt.json \
     --native-view <activated-run-root>/cursor-native-view.json \
     --out <private-proof-root>/cursor-terminal-qualification.json
   python3 skills/puppet/scripts/adapter_lab.py qualify \
     --manifest <fresh-cursor-doctor-manifest> \
     --mapping <fresh-cursor-mapping> \
     --receipt <private-proof-root>/cursor-terminal-qualification.json \
     --out <qualified-cursor-manifest>
   ```

`cursor-pair` re-verifies both Pass B receipts, exact profile identity,
distinct/unchanged workspaces, native-view identity, activation rollback, and
ordinary-control absence before fixed-controller attestation. The unresolved
current default is intentionally represented as requested `default`, observed
`unavailable`, with no explicit model selector. Source-only records,
qualification requests, descriptors, activation-only receipts, and ordinary
receipts are non-promotable.

Interrupted activation never relaunches and never guesses cleanup. Recovery
fences and preserves the exact transaction for controller adjudication. Rollback
occurs only after accepted exact registered-PID halt and refuses to remove
anything when the receipted artifact changed or either created directory gained
foreign content.

### Live-forced workspace-trust reducer

At source head `3e5fddd1394d28d2701cb7aba9783e556bf575fb`, a fresh
subscription-backed activation reached the exact registered Cursor process and
private tmux pane but produced no handoff for 300 seconds. A second, explicitly
rejected diagnostic captured only the bounded synthetic startup screen in
memory. It identified the exact blocker as Cursor's two-option
`Workspace Trust Required` dialog for the exact Puppet fixture. Literal
lowercase `a`, the displayed `Trust this workspace` shortcut, released the
already-admitted fixed positional trigger; the ready and sequenced follow-up
handoffs then passed and PID `42205` was halted without changing the five
protected operator Cursor identities. No screen bytes, screenshot, prompt, or
transcript were retained.

The exact installed `2026.07.17-3e2a980` bundled source confirms that the dialog
dispatches lowercased option keys: `a` trusts, `q` quits, and an additional `w`
appears only when workspace MCP servers are present. Puppet therefore uses a
Cursor-only bounded reducer. It requires the exact title, safety wording,
question, hard-wrap-reconstructed absolute workspace, `a`/`q` options, footer,
manifest, launch argv, pane PID, cwd, and process lease before sending `a`
once. An MCP-expanded (`w`), login, account, terms, permission, unknown,
duplicate, non-UTF-8, oversize, or path-mismatched screen fails closed. After
the key, the reducer requires Cursor's `Auto` / `Run Everything` footer and the
exact workspace, then revalidates the process, pane, executable, and cwd.
Only gate/workspace-match/byte-count/SHA-256/timing metadata survives; raw
screen bytes are discarded.

## 1) Exact-version discovery: facts vs hypotheses

### Facts observed

- Executable discovery by command census:
  - `cursor-agent` resolves through an operator-local symlink to a 1,074-byte
    versioned shell launcher. That launcher `exec`s a bundled Node binary plus
    `index.js`; launcher and runtime process identity are distinct.
- Version / help hashes:
  - `cursor-agent --version` -> `2026.07.17-3e2a980`
  - executable SHA-256: `eed61c5224668c9236334c4c68936a16aecc37374b592f59e31eb50433817831`
  - bundled Node SHA-256:
    `336b5b3ebc5deb86df842102b20b6e4761605b7a667823e68dda7761b91a161b`
  - bundled `index.js` SHA-256:
    `f45ce0860ce8c282110c2f8cfc04e0e8d8b3bc6a83ad01fcded0b5916e1e3a6e`
  - version text SHA-256: `ff67fa8c4d173904e13f0da944d7f763f5399ec48052b81c1ae3c7d87f118f4a`
  - `cursor-agent --help` SHA-256: `bb2aed29e46b3c80635858d2181c140985dbf9f6a96d788f1b6a8adbb0d725af`
- Historical `census_target('cursor', adapter_implementation_fingerprint())`
  snapshot (historical protocol fingerprint
  `a09805b247b6dcdaad8a7d45e8c29c2c4742c8dcce65283f853953c679590aab`),
  recorded before the current controller source changes:
  - `permission_flags`: `["--yolo"]`
  - `project_isolation_flags`: `[]`; the current `all([])` result is a vacuous
    truth and not isolation proof. A typed absolute `--workspace` selector is
    required before live launch.
  - `sandbox_disable_declared`: `true` (`--sandbox disabled`)
  - `model_flag`: `--model`
  - `session_profiles`: `{"regular": ""}`
  - `startup_settle_seconds`: `8.0`
  - `submit_settle_seconds`: `1.0`
  - `launch_argv`: shell launcher plus `--yolo --sandbox disabled`; this is not
    launch-ready because it omits the absolute workspace selector and the live
    process becomes bundled Node after `exec`.
  - capabilities declared: `launch/send/status/wait/checkpoint/resume/halt` = `declared`
  - manifest state: `doctor_only = true` until qualified
  - adapter fingerprint at the recorded census snapshot (any Puppet source
    change, including this substrate, requires a fresh doctor manifest):
    `dff76b92ab1ecea857a67118424fc9109b5ff2f7066e50f9595bc6c086076d6b`
  - this snapshot is not a current doctor manifest and grants no launch or
    qualification authority.
- Pure source identity at controller head
  `b2f443bc941567830f6a5b7d2c141b2b1a651a81`, computed without invoking
  Cursor or reading operator state:
  - adapter fingerprint: `db3b4391007e46105f53a802d9bec80e732237f8878b44c6a165c5aca7cf78a9`
  - protocol fingerprint: `a4e220c27ecfd4b3a28245e4849bad4b9296f192155a2d8b865ca1109d3e1ce9`
  - a fresh exact-version census remains required before any live lane.
- `cursor-agent --help` confirms:
  - command format is `agent [options] [command] [prompt...]`
  - notable supported features for this lane: `--yolo`, `--model`, `--resume`, `--continue`,
    `--workspace`, `--add-dir`, `-w/--worktree`, `--worktree-base`, `--list-models`, `generate-rule|rule`
- `cursor-agent models` output first lines:
  - default/current selector is `auto - Auto (current, default)`; resolved
    provider/model and effort remain `unavailable`.
  - model-list SHA-256:
    `7160694a310c168cee2cc97747d08d19683a9529515a9252c8bae7e611541d3f`
  - output includes `gpt-5.6-sol-*`, `claude-*`, `gemini-*`, plus many Cursor/Opus/Sonnet model variants.
- Authentication-isolation probe at controller head
  `9fe12552aae516a727573ffe88cd929d68492ad8`:
  - exact executable version `2026.07.17-3e2a980` ran only native
    `status --format json` in a fresh current-UID mode-0700 profile;
  - the closed environment replaced HOME and fixed private config/data roots,
    `AGENT_CLI_CREDENTIAL_STORE=file`, and `NO_OPEN_BROWSER=1`;
  - the allowlisted result was `logged_out` / `private_file_store`, exit 0;
    raw output was discarded and no browser, login, account change, model, or
    interaction with the pre-existing Cursor process occurred;
  - this closes `cursor_auth_isolation_unproved` for the exact private-profile
    mechanism. It does not authenticate that profile or qualify workspace,
    trust, default-model, process, or session lifecycle behavior.

### Hypotheses requiring proof

- Default effective model and effort when `--model` is omitted are not proven by static census.
- Exact absolute `--workspace` behavior and workspace trust remain unproved.
  Saved workspace names, `--add-dir`, and Cursor-managed `--worktree` are not
  baseline candidates.
- Puppet currently lacks a process-generation resume contract. Bare resume,
  `--continue`, and latest-session selection could adopt an operator session and
  are forbidden; only a future exact Puppet-created chat ID can be considered.
- Any additive per-run instruction-plane (`--append-system-prompt` equivalent) remains unsupported from current
  help surface and requires live proof.

## 2) Instruction planes for this version

The lane maps three candidate planes to minimize prompt-in-argv risk:

`session_profile=regular` is the active unprefixed lifecycle selection, not an
instruction plane.

- **Plane 1: session-selected harness-global Puppet addendum**
  - Cursor User Rules are the supported all-project surface, but the current CLI
    exposes no public per-run User Rules profile or config-root selector.
  - Keep this candidate unsupported until an isolated, reversible activation
    path is proved. Never mutate live User Rules during launch.

- **Plane 2: workspace/repository addendum candidate (hypothesis, disabled)**
  - Candidate surfaces are `.cursor/rules/*.mdc`, `AGENTS.md`, and documented
    compatibility rules. Workspace/worktree flags choose scope but are not
    themselves instruction injection.
  - Select scope only through `--workspace <absolute-lane-path>`. Prove
    precedence and preserve existing repo rules in the isolated worktree.
  - The source-only binding chooses a deterministic
    `.cursor/rules/puppet-<effective-contract-sha256>.mdc` artifact rather than `AGENTS.md`. The
    stored CLI/help and official-surface notes identify `.cursor/rules/*.mdc`
    as the Cursor-native workspace candidate, while `AGENTS.md` is a broader
    compatibility surface. This is not activation proof: the substrate records
    the surface as `hypothesis`, activation as `disabled`, and launch as not
    authorized.

- **Plane 3: additive per-run system-instruction plane**
  - No supported public primary-agent system-prompt append/file flag was found.
    The installed internal-only flag is not a product contract.
  - Keep this plane unsupported; `generate-rule` is an authoring command, not a
    run-scoped instruction transport.

Official surface references: `https://docs.cursor.com/context/rules-for-ai`
and `https://docs.cursor.com/en/cli/using`.

## 3) Default-model observation plan

1. Run isolated fixture with `cursor-agent --list-models` and `cursor-agent models` in bounded env.
2. Launch regular profile with no explicit `--model` and record whether ready-state reveals an explicit resolved
   default.
3. If resolution remains opaque, record selector `auto`, catalog hash, and
   resolved identity/effort as `unavailable`. Do not pin an explicit model as a
   substitute for the default tuple.

## 4) Regular launch / resume / steer / halt / no-bleed matrix

| Surface | Planned action | Expected evidence | Stop criteria |
| --- | --- | --- | --- |
| Launch | `session_profile=regular` only, YOLO-on + sandbox-off mapping | single launch artifact with deterministic startup settle and active process identity | blocked if process identity drifts vs manifest launch_argv |
| Steer | second `send` on same session, initial=False | exact unprefixed follow-up transport, checkpoint progression | blocked if slash-prefix enforcement breaks or no checkpoint delta |
| Resume | future exact Puppet-created chat ID only | a new process generation bound to exact prior session identity | unsupported until that contract exists; bare/latest/continue are forbidden |
| Halt | exact halt action | one targeted stop and clean process exit; no collateral mutation | blocked if lingering process remains or collateral stop observed |
| No-bleed control | ordinary and fixture targets parallel | ordinary sessions unchanged outside lane-owned fixture artifacts | blocked if any ordinary process or config outside fixture mutates |

## 5) Isolated fixture strategy

- Use a lane-owned fixture run root under
  `runs/puppet-v01-regular-qualification-20260722/lanes/cursor/` with dedicated
  temporary directories for workspace/worktree experiments.
- Keep all evidence under lane-owned fixture and run roots.
- Do not read or modify live Cursor User Rules or config contents. The installed
  executable may be fingerprinted read-only; configuration proof stays inside
  lane-owned fixture/worktree surfaces.
- Official config paths are fixed at user `~/.cursor/cli-config.json` and
  workspace `.cursor/cli.json`; no command-line config-root selector was found.
  The exact installed launcher does honor Puppet's closed private HOME,
  config/data, and file-credential-store environment, and the body-free native
  status probe proved that route without borrowing operator state. Workspace
  trust remains a separate gate, and `--api-key` in argv is forbidden.
- Re-run all cursors probes when executable, manifest hash, or help hash changes.

## 6) Puppet source surfaces for this lane

### Preserved source-only substrate

- `skills/puppet/scripts/puppet_lib/cursor_workspace_plane.py` is deliberately
  standalone from the shared probe and launch lifecycle. It performs no
  subprocess, executable census, tmux, network, Cursor config/auth, process, or
  filesystem mutation operation. It calls only the source-hashing
  `adapter_implementation_fingerprint()` helper from `census.py`.
- Planning accepts only exact version `2026.07.17-3e2a980` and its recorded
  launcher, bundled Node, `index.js`, version-output, and help hashes. It joins
  those facts to the canonical doctor-manifest hash, current
  `adapter_implementation_fingerprint()`, current `PROTOCOL_FINGERPRINT`, and
  runtime execution fingerprint. Planning and revalidation call
  `manifest.verify_execution_files()` so a stale, synthetic, or drifted
  executable identity cannot qualify as current merely because its hashes are
  caller-self-consistent. Neither API accepts a caller-provided current-authority
  override. The manifest must remain doctor-only with declared-only capabilities
  and the exact incomplete base argv `cursor-agent --yolo --sandbox disabled`.
- The caller supplies an existing current-UID `0700` admitted lane and an empty
  current-UID `0700` workspace beneath that lane. Read-only traversal is
  descriptor-relative with no-follow opens, and the workspace must remain an
  empty Puppet-owned nested scope.
- The original planner record remains body-free and contains paths, typed root
  identities, sizes, and hashes. A separate source-only binding now joins it to
  the exact shipped compiler manifest, effective-contract hash, source-owned
  descriptor, contract/run/workspace identities, and current
  adapter/protocol/execution tuple. The bound deterministic future candidate is
  `.cursor/rules/puppet-<effective-contract-sha256>.mdc` with exact dynamic argv
  delta `--workspace <absolute-workspace-root>`. The binding hard-codes
  `activation_authorized=false`, `launch_authorized=false`, and
  `qualification_authorized=false`; the underlying plan keeps
  `materialization_supported=false`, `rollback_supported=false`, and
  `recovery_supported=false`.
- The same source-only join now derives the exact complete disabled vector
  `cursor-agent --yolo --sandbox disabled --workspace <absolute-bound-root>`
  from the exact manifest base plus the workspace delta and stores only its
  SHA-256. Missing, duplicate, saved-name, worktree, added-directory, auth,
  model, profile, config, and prompt selectors fail closed. This is reusable
  argv provenance, not launch authority or shared-adapter wiring.
- Python/macOS pathname deletion has a check-then-remove race: a verified file
  or directory can be replaced before `unlink` or `rmdir`, causing an
  unreceipted vnode to be removed. The substrate therefore contains no create,
  unlink, rmdir, rename, rollback receipt, recovery receipt, or terminal-state
  mutation path. It also contains no function that can mint an `exact_halt`
  assertion. Canonical caller-shaped rollback JSON is not authority and is
  always rejected.
- The substrate has no call site in `probe.py`, `launch.py`, or an adapter. It
  cannot materialize, launch, clean up, recover, or qualify Cursor. It remains
  planner-only even though the separate qualification path below now exists.
- `skills/puppet/scripts/puppet_lib/operator_plan.py` and
  `skills/puppet/scripts/puppet.py` keep that boundary at the public front
  door:
  - a doctor-only, unqualified Cursor manifest emits a body-free
    `target_gate` with state `qualification_required`, failed invariant
    `cursor_regular_runtime_qualification_missing`,
    rung `cursor_regular_pass_b`, the exact manifest/executable/version/
    adapter/protocol identity, and every planner-only blocker;
  - the only preserved evidence kinds are
    `puppet.cursor-workspace-plane-plan/v2` and
    `puppet.cursor-workspace-plane-binding/v1`;
  - `doctor`, private `profile-init`, and body-free `profile-status` are
    proposed, while launch, session status, waits, attach, open-view, and halt
    remain unsupported with explicit source-only reasons; and
  - public onboarding may silently reuse an authenticated private Cursor
    profile or emit `human_run_one_time_login_handoff` only when native status
    reports logged out. Isolation detection is not human-gated and the handoff
    never runs unattended.

### Integrated qualification-only path

- `cursor_qualification.py` owns the exact installed tuple, body-free request,
  derived descriptor, create-only materialization, private-profile launch join,
  structural native-view observation, exact-halt rollback, mapping closure, and
  paired terminal receipt.
- `probe.py` accepts the request only for the exact fresh doctor manifest,
  derives the descriptor from the compiled contract, revalidates profile and
  launch authority immediately before start, emits the activation proof family,
  and leaves activation-only output non-promotable.
- `adapter_manifest.py` re-verifies both underlying Pass B receipts and the
  terminal join before closing only the dynamic absolute-workspace bit.
  `session.py` then composes that selector per normal repository and rejects
  explicit model/effort selection.
- `adapter_lab.py` exposes `cursor-request`, `cursor-native-view`, and
  `cursor-pair`. Request and output files are create-only.
- Unit coverage exercises create-only collisions, replacement and foreign-file
  refusal, exact halt, rollback, descriptor/body separation, mapping closure,
  native-view structure, paired no-bleed joins, and promotion rejection for
  nonterminal evidence.

## 7) Blockers and stop criteria

- Promotion blockers:
  - No fresh real activated/control pair has yet exercised this source at the
    current adapter/protocol fingerprints.
  - The enrolled private profile must report logged in through the body-free
    status contract immediately before each run; no operator-global fallback is
    allowed.
  - The activated run must prove the rule was consumed, one structural native
    view joined it, exact halt succeeded, and rollback completed. The ordinary
    run must prove absence and both workspaces must remain unchanged.
  - The current default remains unresolved. This path permits only requested
    `default`, observed `unavailable`, with no explicit selector; any claim of a
    resolved provider/model or effort requires separate evidence.
  - Resume remains unsupported and must not be inferred from regular
    launch/steer/halt qualification.
  - `--yolo` can still encounter product policy or approval denial. Any such
    result blocks rather than weakening the contract.
  - Any prompt-bearing value in argv, environment, request, descriptor, receipt,
    or durable proof is a terminal validation failure.
- Stop criteria:
  - Keep the doctor manifest unqualified until `cursor-pair` and `qualify`
    reverify one fresh accepted pair at the exact current identities.
  - Preserve and adjudicate any interrupted activation; do not relaunch or
    manually delete its rule.
  - Keep resume and alternate/default-model resolution claims unsupported until
    independently qualified.
