# SaariusSkills

Public, experimental Agent Skills maintained by
[Saariusly Stoned](https://github.com/saariuslystoned).

The same skillpack ships as a [Codex plugin](.codex-plugin/plugin.json), a
[Cursor plugin](.cursor-plugin/plugin.json), and a
[Claude Code plugin](.claude-plugin/plugin.json). Pick the install path for your
harness in [Install](#install).

## Archived: Puppet and Herdr-Puppet

The `puppet` and `herdr-puppet` skills are archived. The local Cursor ACP and
Antigravity ACP delegation lanes below replace them, and no plugin manifest
installs them any more. Their final source, tests, and fixtures are preserved at
the [`puppet-archive-20260925`](https://github.com/saariuslystoned/SaariusSkills/tree/puppet-archive-20260925)
tag. The historical [Puppet design packet](plans/puppet/README.md) and dated
proof and run records remain in `plans/`, `proof/`, and `runs/`.

## Local Cursor ACP

The repository also carries an additive, experimental [Cursor ACP delegation
skill](skills/cursor-acp-delegation/SKILL.md) and stdio MCP bridge. It routes
one bounded implementation slice through pinned `acpx@0.19.1` to Bobby's
explicit local `/Users/bobbybones/.local/bin/cursor-agent acp` executable,
resolves the requested Cursor Grok 4.6 selector against the live ACP model
catalog, and exposes readiness, delegation, status/result, and
cancellation tools. Job state and compact proof live outside the mutating
workspace.

This local experiment does not claim Puppet's transport-neutral controller,
OpenClaw gateway, remote-host support, or issues #35/#37 complete. See the
[local setup and rollback guide](docs/cursor-acp-delegation.md).

## Local Antigravity ACP

A second experimental stdio MCP bridge, named `antigravity-acp`, routes one
bounded implementation slice through pinned `acpx@0.19.1` to Google's official
`antigravity-acp` 1.1.1 runtime. It stays separate from the Cursor lane and
from native `agy --print` / Puppet qualification. Omitting `model` uses the
plugin default exact id `gemini-3.8-flash-high` when advertised; otherwise an
exact advertised model ID is required. Personal OAuth lives under an explicit
`GEMINI_HOME` profile; fixed-choice questions fail closed. See the
[local Antigravity setup and reload guide](docs/antigravity-acp-delegation.md).

Both local MCP bridges use a shared per-user persistent dependency store outside
the Codex and Claude Code plugin caches. After installing or updating the plugin,
prepare the bridges explicitly from the installed plugin root:

```bash
node "$SAARIUS_PLUGIN_ROOT/bridge/acp-runtime/prepare.mjs" --bridge cursor-acp
node "$SAARIUS_PLUGIN_ROOT/bridge/acp-runtime/prepare.mjs" --bridge antigravity-acp
```

The launchers reuse compatible prepared trees and keep MCP stdout reserved for
protocol frames. They never perform a network install during MCP initialization.
An optional parent-only `SAARIUS_ACP_HOP_ARGV` hops that same launcher onto
another machine; ACpx stays a local child there. See the hop section in the
[Antigravity setup guide](docs/antigravity-acp-delegation.md).

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

Use **Codex**, **Cursor**, or **Claude Code** when you want the packaged skills
and bundled ACP MCP servers. Use **Google Antigravity (AGY)** when you want a path-based
install from a checkout.

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

For the optional local Cursor ACP bridge used by some skills, see
[docs/cursor-acp-delegation.md](docs/cursor-acp-delegation.md).

### Claude Code

Add this repository as a Claude Code plugin marketplace, then install its
plugin:

```bash
claude plugin marketplace add saariuslystoned/SaariusSkills
claude plugin install saarius-skills@saarius-skills
```

Inside a session, `/plugin marketplace add saariuslystoned/SaariusSkills` and
`/plugin install saarius-skills@saarius-skills` do the same. The
[Claude Code manifest](.claude-plugin/plugin.json) registers the `cursor-acp`
(Cursor Grok) and `antigravity-acp` delegation servers through
`${CLAUDE_PLUGIN_ROOT}`, with no machine-specific paths; each bridge keeps its own
defaults for the Cursor executable and `GEMINI_HOME`. Prepare both bridge
runtimes once per plugin version, as described in
[Local Antigravity ACP](#local-antigravity-acp). If a server fails to start, its
stderr names the exact `prepare.mjs` command for the installed copy. Then start a
fresh session and confirm with `/mcp`. Puppet and Herdr-Puppet are archived and
not installed.

For a checkout-based trial without installing:

```bash
claude --plugin-dir /path/to/SaariusSkills
```

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
- [`skills/phone-proof/SKILL.md`](skills/phone-proof/SKILL.md): the
  build-install-look-fix-look mobile UI workflow.
- `skills/phone-proof/scripts/phone_proof.py`: a standard-library Android
  display inventory and structurally validated screenshot helper.
- `skills/phone-proof/references/`: display-ID and visual-proof contracts.
- [`skills/antigravity-acp-delegation/SKILL.md`](skills/antigravity-acp-delegation/SKILL.md):
  the official Antigravity ACP MCP lane, separate from Cursor ACP and native AGY.

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
python3 skills/phone-proof/scripts/phone_proof.py --help
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes.
