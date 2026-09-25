# SaariusSkills

Public, experimental Agent Skills maintained by
[Saariusly Stoned](https://github.com/saariuslystoned).

The same skillpack ships as a [Codex plugin](.codex-plugin/plugin.json) and a
[Cursor plugin](.cursor-plugin/plugin.json). Host either, then delegate over
ACP to Cursor or Antigravity. Published install is this plugin, not a
hand-written `~/.cursor/mcp.json`. Pick the install path for your harness in
[Install](#install).

## Puppet

The repository carries the historical [Puppet design packet](plans/puppet/README.md)
and the bootstrap [`puppet` skill](skills/puppet/SKILL.md), a standard-library
Python lifecycle controller for supervising real agent harnesses through
durable, transcript-blind checkpoints.

> Puppet uses agents like puppets to build Puppet—the skill that uses agents
> like puppets.

> **Mandatory warning:** Puppet live execution is YOLO-only. It requires the
> target harness's unrestricted/always-approve mode and disables its sandbox
> wherever that control exists. Prompted or sandboxed live launches are
> unsupported. Delivery, external effects, accounts, security, secrets,
> spending, and destructive actions remain separately gated.

The bootstrap source implements the bounded CLI, strict contracts, atomic and
append-only state, doctor-only adapter census, source and conformance handoffs,
controller-only verdicts, immutable-supervisor checks, sanitized status, and
exact-target transport boundaries. Enabled manifests additionally require a
goal-bound, current-identity-checked real-harness receipt included in a fixed,
checkout-independent controller ledger. This remains cooperative same-UID
coordination, not hostile-code containment; see the
[`YOLO contract`](skills/puppet/references/yolo-contract.md). It is not yet fully
runtime-qualified: every live
adapter remains hard-disabled until its exact current CLI passes the shared
real-harness conformance probe, and no self-hosting promotion is claimed.

## Herdr-Puppet

Herdr-Puppet is the experimental transport skill growing beside Puppet. It
binds an explicit operator capability to one newly created Herdr tab, exact
tab/pane/terminal/SSH identity, a sequence-checked lease, and a transcript-blind
controller journal.

Ordinary AGY turns use plain messages. `/teamwork-preview` is reserved for an
explicitly requested, separately qualified 4-20-helper fan-out; it is not the
default steering prefix.

The scaffold implements Herdr 0.7.3 doctor, source-only plan, structural status,
append-only dogfood journals, gated qualification tab creation,
sequence-checked input, partial-send reconciliation, and a bounded exact-nonce
wait with strict `STATUS` / `ACTION_REQUIRED` / `DONE` checkpoint
classification. Pane input receipts explicitly do not claim harness readiness
or task submission. Waits have an independent controller hard timeout,
terminal checkpoints preserve the lease automatically, and
`maintenance-checkpoint` inventories exact run-owned structure without closing
anything. Separately authorized `cleanup-preserved-tab` closes only an exact
confirmed preserved tab and verifies tab, pane, and foreground-SSH-PID absence.
Ordinary status never reads pane text.
Parent-session mutation, pre-existing-tab adoption, generic transcript capture,
halt, and recovery remain disabled.

Current status is tracked by a five-row, transcript-blind qualification bundle at
implementation head `8ee87d8ed9882043762ca1877e54cb844072d685` in
`plans/puppet/herdr-puppet-proof.md`:

- AGY: PASS
- Cursor: BLOCKED_LOGIN_ENROLLMENT
- Grok: PASS
- Claude Code: FAIL
- Codex CLI: FAIL

The run remains experimental, and these outcomes are not a universal PASS claim
for all harnesses.

## ACP delegation

SaariusSkills is the host policy for one local ACP contract. ACpx is the
local client. ACP is the wire. Host the plugin in **Codex** or **Cursor**,
then delegate one bounded slice to a **Cursor** or **Antigravity** worker.
The Cursor plugin starts `antigravity-acp`. The Codex plugin starts both
`antigravity-acp` and `cursor-acp`.

The same six tools (`readiness`, `delegate`, `status`, `result`, `steer`,
`cancel`) run in three proven placements. **Gateway** (was A2) — a
SaariusSkills process that owns phone or browser chat and spawns ACP —
stays off. Do not build it.

Former aliases: Local was L; Always-on was A1; Hop was B.

| Product | Parent | Worker | Proven |
| --- | --- | --- | --- |
| **Local** | Same machine | Same machine | MacBook desktop Agent chat: readiness plus `proof/l-live-dogfood/hello.mjs` (job `38a1c9e7`). Later #80 default fail-closed write/exec that would prompt (job `a8c3cbbf`). |
| **Always-on** | Always-on box | Same box | Same local contract on CP-1: readiness plus `proof/a1-live-dogfood/hello.mjs` (job `9028cc7a`). First live job fail-closed on `approve-reads`. |
| **Hop** | Carry laptop | Another machine | Parent hops stdio with `SAARIUS_ACP_HOP_ARGV`; ACpx stays a local child on the worker. MacBook → CP-1 job `69b134e9` wrote `proof/b-live-dogfood/hello.mjs` after [#83](https://github.com/saariuslystoned/SaariusSkills/pull/83). |

Those hello.mjs jobs used the Antigravity worker. The Cursor worker lane is
source-landed (Codex → local `cursor-agent acp`) and is not those jobs.

Host policy on `main` ([#80](https://github.com/saariuslystoned/SaariusSkills/pull/80),
[#82](https://github.com/saariuslystoned/SaariusSkills/pull/82)): readiness
gates `delegate`; everyday permission is `approve-reads` plus fail on
write/exec that would prompt; `SAARIUS_ACP_PERMISSION_MODE=approve-all` is
break-glass on the attach, not a tool argument; one parent conversation
owns one worker (cwd is not exclusive).

This plugin does not claim Google AI Ultra, Gateway (was A2), Parallels,
`acpx --agent ssh`, or that a cloud Cursor Project chat can call
`antigravity_acp_*`. Hop argv is parent-attach config, not a hostname in
the published manifests. Bare `ssh` as the laptop login user is not the
proven hop identity.

### Cursor worker (`cursor-acp`)

The [Cursor ACP delegation skill](skills/cursor-acp-delegation/SKILL.md)
and stdio MCP bridge route one bounded slice through pinned `acpx@0.19.1`
to Bobby's explicit local `/Users/bobbybones/.local/bin/cursor-agent acp`
executable, resolve the requested Cursor Grok 4.6 selector against the
live ACP model catalog, and expose the six tools. Job state and compact
proof live outside the mutating workspace.

This lane does not claim Puppet's transport-neutral controller, an
OpenClaw gateway, or issues #35/#37 complete. Shared hop is documented
with the Antigravity lane. See the
[Cursor setup and rollback guide](docs/cursor-acp-delegation.md).

### Antigravity worker (`antigravity-acp`)

The `antigravity-acp` bridge routes one bounded slice through pinned
`acpx@0.19.1` to Google's official `antigravity-acp` 1.1.1 runtime. It
stays separate from the Cursor worker lane and from native `agy --print`
/ Puppet qualification. Omitting `model` uses the plugin default exact id
`gemini-3.8-flash-high` when advertised; otherwise an exact advertised
model ID is required. Personal OAuth lives under an explicit `GEMINI_HOME`
profile; fixed-choice questions fail closed. See the
[Antigravity setup and hop guide](docs/antigravity-acp-delegation.md).

Both bridges use a shared per-user persistent dependency store outside
the Codex plugin cache. After installing or updating the plugin, prepare
the bridges explicitly from the installed plugin root:

```bash
node "$SAARIUS_PLUGIN_ROOT/bridge/acp-runtime/prepare.mjs" --bridge cursor-acp
node "$SAARIUS_PLUGIN_ROOT/bridge/acp-runtime/prepare.mjs" --bridge antigravity-acp
```

The launchers reuse compatible prepared trees and keep MCP stdout reserved
for protocol frames. They never perform a network install during MCP
initialization. Unset `SAARIUS_ACP_HOP_ARGV` is Local or Always-on. Set
hop is Hop.

## PhoneProof

PhoneProof closes the gap between a green mobile build and the UI a human
actually sees. It runs a build-install-capture-inspect-fix-capture loop,
distinguishes physical screenshot IDs from logical input display IDs, rejects
warning-corrupted PNG streams, flags suspiciously small black-screen captures,
keeps Vysor or scrcpy aligned with headless ADB proof, and extracts
accessibility-tree text with a delimiter-safe parser instead of a hand-rolled
regex that silently misses quote-containing values. It is intentionally
bounded to registered test devices and reversible, route-approved actions.
The [initial Pixel 10 Pro XL proof](plans/phone-proof/PROOF.md) exercises the
capture and human-mirror alignment slice.

## GrillTrack

GrillTrack helps a user and an agent build a complicated thing without
pretending every important decision is visible at the beginning. It runs one
focused decision cycle at a time:

```text
grill -> confirm -> implement -> verify -> exact-source review -> inspect -> repeat or close
```

Accepted choices stay present while later choices are judged, so the product
converges as a whole rather than becoming a pile of disconnected preferences.
Each phase now crosses a typed artifact edge in the durable ledger. Large or
foggy destinations route through a source-linked decision map instead of being
flattened into one oversized grill, and context switches carry explicit
artifact refs plus a next safe action instead of relying on chat memory.

Project-changing cycles review two axes separately: repository standards and
confirmed source intent. Review is bound to a full commit SHA or content hash;
accepted fixes return to implementation and re-verification. Human-only setup
steps use resumable, secret-safe guided gates without turning attended work into
delivery authority.

The first domain pack supports frontend work with exactly five live variants
inside the accepted layout. For greenfield whole-product frontend builds,
verified design choices also accumulate in a canonical `design.md` contract so
future cycles inherit the real design language rather than reconstructing it
from screenshots or chat history.

The frontend pack includes a complete font-system grill: compare five role-based
systems on the accepted product canvas, then verify the winner's real weights,
delivery path, responsive fit, and motion behavior before promoting it into
`design.md`.

> **Experimental:** the portable skill, durable ledger tools, frontend
> reference pack, packaging checks, and unit tests are available. Real-project
> rehearsals and public case-study proof remain planned. The repository does
> not claim stable cross-host support or a completed production proof ladder.

## Origins

GrillTrack began when an ordinary grilling session worked exactly as intended:
it clarified a website well enough to build. The implemented site then exposed
decisions the initial interview could not usefully settle—imagery, icons,
mobile usability, copy, and motion. Each became a focused new grill using five
live variants inside the previously accepted layout. Locked choices stayed
visible, implementation made them real, and that new reality revealed the next
grill.

Matt Pocock’s grilling skill supplied the interview foundation. Will Ness’s
frontend-prototyping variant introduced five live visual alternatives.
GrillTrack adds the durable, cumulative loop across focused grills: grill,
implement, verify, review, inspect, and repeat.

The original foundation pins are:

- [Matt Pocock’s grilling skill](https://github.com/mattpocock/skills/blob/9603c1cc8118d08bc1b3bf34cf714f62178dea3b/skills/productivity/grilling/SKILL.md)
- [Matt Pocock’s batch-grill-me skill](https://github.com/mattpocock/skills/blob/9603c1cc8118d08bc1b3bf34cf714f62178dea3b/skills/in-progress/batch-grill-me/SKILL.md)
- [Matt Pocock’s grill-with-docs skill](https://github.com/mattpocock/skills/blob/9603c1cc8118d08bc1b3bf34cf714f62178dea3b/skills/engineering/grill-with-docs/SKILL.md)
- [Matt Pocock’s domain-modeling skill](https://github.com/mattpocock/skills/blob/9603c1cc8118d08bc1b3bf34cf714f62178dea3b/skills/engineering/domain-modeling/SKILL.md)
- [Will Ness’s grilling-frontend-prototyping skill](https://github.com/will-ness-ai/skills/blob/131c397a7731b6b0ce398a5b3bb8db8768136bc5/skills/engineering/grilling-frontend-prototyping/SKILL.md)
- [Agent Skills specification](https://agentskills.io/specification)

The 2026 workflow refresh also compared GrillTrack against Matt's current
engineering graph at commit
[`5b15a47f2d7150f545fbcacbfe381787fc0230dc`](https://github.com/mattpocock/skills/tree/5b15a47f2d7150f545fbcacbfe381787fc0230dc/skills/engineering),
especially `grill-with-docs`, `implement`, `tdd`, `code-review`, `to-spec`,
`to-tickets`, `wayfinder`, and `wizard`. GrillTrack remains a clean-room,
domain-neutral implementation rather than a bundled copy of that suite.

These projects and their authors do not endorse GrillTrack. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for provenance and license
details.

## Install

Use **Codex** or **Cursor** when you want the packaged skills and the ACP
bridges. Published install is this plugin. Do not treat a hand-written
`~/.cursor/mcp.json` as the product install. Use **Google Antigravity
(AGY)** when you want a path-based install from a checkout.

### Codex

Add this repository as a Codex plugin marketplace, then install its plugin:

```bash
codex plugin marketplace add saariuslystoned/SaariusSkills
codex plugin add saarius-skills@saarius-skills
```

Restart Codex if the newly installed skill does not appear. The commands follow
the current [Codex plugin marketplace documentation](https://learn.chatgpt.com/docs/build-plugins#add-a-marketplace-from-the-cli).

### Cursor

SaariusSkills is not listed in the [official Cursor Marketplace](https://cursor.com/marketplace)
yet. Install it as a **local Cursor plugin** from a real directory under
`~/.cursor/plugins/local` (Cursor skips symlinks whose target lives outside that
folder):

```bash
mkdir -p ~/.cursor/plugins/local
git clone https://github.com/saariuslystoned/SaariusSkills.git \
  ~/.cursor/plugins/local/saarius-skills
```

Run **Developer: Reload Window**, then open **Customize** and confirm the
`saarius-skills` skills (and MCP servers, if enabled) appear. This follows
[Cursor's local plugin development flow](https://cursor.com/docs/plugins#test-plugins-locally).

To update an existing local install:

```bash
git -C ~/.cursor/plugins/local/saarius-skills pull --ff-only
```

The Cursor plugin MCP entry is hop-free and ships no machine paths. Hop,
when used, is `SAARIUS_ACP_HOP_ARGV` on the parent attach. For the
optional Codex → Cursor worker bridge, see
[docs/cursor-acp-delegation.md](docs/cursor-acp-delegation.md).

### Google Antigravity (AGY)

Install this skillpack with the AGY CLI:

```bash
agy plugin install /path/to/SaariusSkills
```

AGY loads the pack from the provided path and reads the root `plugin.json`
manifest.

Then start a track naturally:

```text
Help me decide and implement the next high-leverage product slice with GrillTrack.
```

Natural requests such as “continue to the next grill” or “reopen the layout
decision” work too. `$grilltrack` remains available as a concise explicit
invocation, but it is never required when the user's intent is already clear.

## What ships

- [`skills/puppet/SKILL.md`](skills/puppet/SKILL.md): the YOLO-only,
  transcript-blind cross-harness operating workflow.
- `skills/puppet/scripts/puppet.py`: the bootstrap lifecycle and acceptance CLI.
- `skills/puppet/scripts/puppet_launch.py`: one-request warm catalog, campaign
  preparation, single-owner mutation routing, explicit concurrent checkpoint
  collection, and lifecycle entrypoint for any one-to-five-target mix.
- `skills/puppet/scripts/puppet_fanout.py`: concurrent launch, status, native
  view, and exact halt for any operator-selected one-to-five-harness mix.
- `skills/puppet/scripts/adapter_lab.py`: zero-agent census, real-harness
  probe/recovery, receipt verification, and qualification tooling.
- `skills/puppet/references/`: operating, adapter, prompt, provenance, trust,
  qualification, subscription-profile, and campaign-recovery contracts.
- [`skills/grilltrack/SKILL.md`](skills/grilltrack/SKILL.md): the portable,
  intent-aware core workflow.
- `skills/grilltrack/scripts/grilltrack_ledger.py`: a standard-library CLI for
  validated, resumable, non-destructive project ledgers, exact-source review
  adjudication, and context-boundary pause records.
- `skills/grilltrack/scripts/validate_picker.py`: a validator for the
  exactly-five frontend picker contract.
- `skills/grilltrack/references/`: progressively loaded workflow authority,
  artifact-graph, human-gate, protocol, ledger, proof, closeout, and frontend
  guidance.
- `fixtures/`: small public evaluation inputs.
- `tests/`: protocol, state, packaging, and safety regression tests.
- [`skills/herdr-puppet/SKILL.md`](skills/herdr-puppet/SKILL.md): the
  exact-identity Herdr transport and dogfood workflow.
- `skills/herdr-puppet/scripts/herdr_puppet.py`: a standard-library controller
  for doctor, plan, status, journals, and gated qualification operations.
- `skills/herdr-puppet/references/`: authority, transport, qualification,
  desktop-observation fallback, and versioned JSON-schema contracts.
- [`skills/phone-proof/SKILL.md`](skills/phone-proof/SKILL.md): the
  build-install-look-fix-look mobile UI workflow.
- `skills/phone-proof/scripts/phone_proof.py`: a standard-library Android
  display inventory and structurally validated screenshot helper.
- `skills/phone-proof/references/`: display-ID and visual-proof contracts.
- [`skills/antigravity-acp-delegation/SKILL.md`](skills/antigravity-acp-delegation/SKILL.md):
  the official Antigravity ACP MCP lane (proven Local / Always-on / Hop), separate from
  Cursor ACP and native AGY.

GrillTrack never treats a decision lock as permission to commit, push, open or
merge a pull request, deploy, spend, or change an account. Those actions require
their own explicit authorization and remain subject to the active repository’s
rules.

## Development

Run the complete local verification:

```bash
python3 -m unittest discover -s tests -v
python3 skills/grilltrack/scripts/grilltrack_ledger.py --help
python3 skills/grilltrack/scripts/validate_picker.py fixtures/frontend-picker/manifest.json
python3 skills/puppet/scripts/puppet.py --help
python3 skills/puppet/scripts/puppet_launch.py --help
python3 skills/puppet/scripts/puppet_fanout.py --help
python3 skills/puppet/scripts/adapter_lab.py --help
python3 skills/herdr-puppet/scripts/herdr_puppet.py --help
python3 skills/phone-proof/scripts/phone_proof.py --help
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes.
