# SaariusSkills

Public, experimental Agent Skills maintained by
[Saariusly Stoned](https://github.com/saariuslystoned).

## Puppet design bundle

The repository now carries the closed pre-implementation design packet for
[Puppet](plans/puppet/README.md), a proposed skill and CLI for supervising real
agent harnesses through durable, transcript-blind checkpoints.

> Puppet uses agents like puppets to build Puppet—the skill that uses agents
> like puppets.

Puppet itself is not implemented or runtime-proved yet. The bundle includes the future
Codex orchestration goal, complete implementation seed, curated prior-proof
provenance, full public decision record, and closeout proof. Its proposed live
runtime is deliberately YOLO-only and prominently preserves separate human
gates for delivery, external effects, accounts, security, and secrets.

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
classification. Ordinary status never reads pane text. Parent-session mutation,
pre-existing-tab adoption, generic transcript capture, halt, and recovery remain
disabled.

The first live dogfood lane uses one newly owned, persistently visible AGY pane
on a remote worker. Its machine-local controller journal is deliberately not a
public transcript or promotion claim; curated public proof will follow only
after the behavior and redaction boundaries survive review.

## GrillTrack

GrillTrack helps a user and an agent build a complicated thing without
pretending every important decision is visible at the beginning. It runs one
focused decision cycle at a time:

```text
grill -> confirm shared understanding -> implement -> verify -> inspect -> repeat or close
```

Accepted choices stay present while later choices are judged, so the product
converges as a whole rather than becoming a pile of disconnected preferences.
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
implement, verify, inspect, and repeat.

The pinned upstream influences are:

- [Matt Pocock’s grilling skill](https://github.com/mattpocock/skills/blob/9603c1cc8118d08bc1b3bf34cf714f62178dea3b/skills/productivity/grilling/SKILL.md)
- [Matt Pocock’s batch-grill-me skill](https://github.com/mattpocock/skills/blob/9603c1cc8118d08bc1b3bf34cf714f62178dea3b/skills/in-progress/batch-grill-me/SKILL.md)
- [Matt Pocock’s grill-with-docs skill](https://github.com/mattpocock/skills/blob/9603c1cc8118d08bc1b3bf34cf714f62178dea3b/skills/engineering/grill-with-docs/SKILL.md)
- [Matt Pocock’s domain-modeling skill](https://github.com/mattpocock/skills/blob/9603c1cc8118d08bc1b3bf34cf714f62178dea3b/skills/engineering/domain-modeling/SKILL.md)
- [Will Ness’s grilling-frontend-prototyping skill](https://github.com/will-ness-ai/skills/blob/131c397a7731b6b0ce398a5b3bb8db8768136bc5/skills/engineering/grilling-frontend-prototyping/SKILL.md)
- [Agent Skills specification](https://agentskills.io/specification)

These projects and their authors do not endorse GrillTrack. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for provenance and license
details.

## Install

### Codex

Add this repository as a Codex plugin marketplace, then install its plugin:

```bash
codex plugin marketplace add saariuslystoned/SaariusSkills
codex plugin add saarius-skills@saarius-skills
```

Restart Codex if the newly installed skill does not appear. The commands follow
the current [Codex plugin marketplace documentation](https://learn.chatgpt.com/docs/build-plugins#add-a-marketplace-from-the-cli).

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
  validated, resumable, non-destructive project ledgers.
- `skills/grilltrack/scripts/validate_picker.py`: a validator for the
  exactly-five frontend picker contract.
- `skills/grilltrack/references/`: progressively loaded protocol, ledger,
  proof, closeout, and frontend guidance.
- `fixtures/`: small public evaluation inputs.
- `tests/`: protocol, state, packaging, and safety regression tests.
- [`skills/herdr-puppet/SKILL.md`](skills/herdr-puppet/SKILL.md): the
  exact-identity Herdr transport and dogfood workflow.
- `skills/herdr-puppet/scripts/herdr_puppet.py`: a standard-library controller
  for doctor, plan, status, journals, and gated qualification operations.
- `skills/herdr-puppet/references/`: authority, transport, qualification, and
  versioned JSON-schema contracts.

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
python3 skills/herdr-puppet/scripts/herdr_puppet.py --help
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing changes.
