# Puppet main-cleanup successor lane — 2026-08-14

Lane: `saariusskills-puppet-5-successor`. Contract: x-api
`plans/operator-space-durable-product-20260814.md` Track A (x-api PR #539,
treated as source while unmerged) and issue #11 Phase 3. Mission: get tmux
Puppet mergeable as a cleaned successor of PR #5 without re-qualification and
without merging #5 as-is.

## Exact heads

| ref | commit |
| --- | --- |
| `origin/main` (successor base) | `255f95e4305180d88fcf9a7eebf35592ddca9fed` |
| successor branch | `codex/puppet-v01-main-cleanup-20260814` |
| PR #5 campaign head | `410fcf5b17c2e69903a3f8ca40ee06ad230c87fd` |
| campaign implementation head | `544a347` (five-harness closeout binding) |
| merge base | `23f3b0c8062c7cffaadabee3154477285ccac0f3` |
| PR #18 head (OPEN, not touched) | `e9792ee26cc9cbd836078f192d81d933a22ecfe8` |

Divergence: `origin/main` is 39 commits ahead of the merge base (the hardened
`herdr-puppet` vertical plus the #9 and #17 merges); the campaign branch is
241 commits ahead of it. GitHub's stale #5 comparison against `23f3b0c` is not
merge authority.

## Inventory — additive conflicts

Campaign side changes 159 files. Only two overlap textually with the main
side; the rest are path-disjoint additions.

| file | state | resolution |
| --- | --- | --- |
| `plugin.json` | campaign-side only since merge base | take campaign version (already describes both skills); pre-applied on this branch |
| `.codex-plugin/plugin.json` | campaign-side only (0.1.0 → 0.2.0, keywords, prompts) | take campaign version; pre-applied on this branch |
| `tests/test_packaging.py` | both sides + #18 | campaign contributes exactly 3 hunks (description string, version `0.2.0`, cache-dir excludes in the placeholder scan); pre-applied here. Main/#18 herdr hunks live in other regions and merge cleanly |
| `README.md` | both sides, adjacent sections | union at replay: keep main's Herdr-Puppet sections, take campaign's Puppet section, "What ships" entries, and verification commands; not pre-applied because it must describe the tree it sits in |
| `.github/workflows/tests.yml` | campaign-side add; `main` has no `.github` at all | hermetic-split version pre-applied on this branch (see below) |
| `tests/__init__.py` | campaign-side add | clean add at replay |
| `skills/puppet/**` (128 files) | campaign-side add | disjoint from `skills/herdr-puppet/**`; `SKILL.md` add/add resolves to this branch's rewrite |
| PR #18 files | herdr-puppet scripts/schemas/tests/plans | fully disjoint from `skills/puppet/**`; only `tests/test_packaging.py` is shared, in non-overlapping regions |

## Inventory — test-failure classification

- Deterministic failures: none today. `origin/main` runs 235 tests OK and the
  campaign head runs 883 tests OK on the same host (Python 3.14.6, tmux 3.6b,
  macOS) and historically on GitHub-hosted Ubuntu 24.04 and macOS 26. The
  only deterministic rebase risk is `tests/test_packaging.py` asserting the
  plugin manifest identity, resolved by taking the three campaign hunks
  together with the campaign manifests (pre-applied here as one unit).
- Live-host census blockers: none inside the unit suite. tmux-dependent tests
  skip when tmux is unavailable; nothing in `tests/` launches a harness,
  authenticates, or probes a subscription. Live census and subscription
  probes are operator-run CLI flows (`adapter_lab.py census|probe`,
  `puppet.py onboard`), now documented as explicitly opt-in and banned from
  default CI in the workflow header.
- Python-version-sensitive JSON-depth assertion
  (`test_parse_rejects_excessive_json_depth_before_shape_validation`):
  already repaired mid-campaign. `parse_instruction_plane_descriptor` guards
  depth twice — a `RecursionError` catch around the JSON parse (fires on
  interpreters with lower C-recursion limits) and
  `validate_bounded_json(max_depth=8)` on every parsed shape (fires when the
  parser survives). Both raise a `ValidationError` matching the test's
  "nesting exceeds" regex, so the outcome is version-independent; only the
  message source varies. No further gate is required; optional hardening
  (an explicit pre-decode bracket-depth scan) is noted as a non-blocking
  follow-up.

## Prepared on this branch (#18 still open — no replay yet)

PR #18 (`herdr-agy-autoready`) was OPEN at preparation time, so per the lane
contract the 241-commit replay is deferred and this branch carries only work
that applies cleanly after that rebase:

1. `skills/puppet/SKILL.md` — full rewrite. The ordinary operator loop
   (`plan → doctor → launch → send → status → halt`) is the front door; the
   concurrent fast path follows; qualification, matched-control, activation
   transactions, startup gates, subscription onboarding, and campaign
   recovery moved to references. All content markers pinned by the campaign's
   `tests/test_puppet_packaging.py` are preserved verbatim, so that test
   passes unchanged against the rewrite at replay. Well under the 500-line
   packaging cap.
2. New references receiving the moved liturgy verbatim:
   `skills/puppet/references/qualification-contract.md`,
   `subscription-profiles.md`, `campaign-recovery.md`. The campaign's six
   existing references arrive unchanged at replay; links resolve then.
3. `.github/workflows/tests.yml` — the campaign workflow plus an explicit
   hermetic contract header: default CI is unit/packaging/compileall/help
   smokes only; live census and subscription probes are operator-run opt-in
   and must never join default CI.
4. Conflict pre-resolution: campaign `plugin.json`,
   `.codex-plugin/plugin.json`, and the three campaign hunks in
   `tests/test_packaging.py`, applied together so the manifest-identity test
   stays green on this branch now and at replay.

Not prepared here, by design: `README.md` union (must describe the replayed
tree), `tests/__init__.py`, and every `skills/puppet` script, template,
fixture, plan, and live-proof artifact — those replay from `410fcf5`
unchanged. The five-harness closeout and live-proof JSON under
`plans/puppet/` are immutable evidence and are not re-run; re-running the
five-way live campaign is not a merge tax.

## Replay recipe (run after #18 merges)

1. Fetch and verify the new `origin/main` tip; rebase this branch onto it
   (expected: no conflicts — prepared files are disjoint from #18).
2. Import the campaign tree:
   `git merge --no-ff origin/codex/puppet-v01-campaign-20260721` (or an
   equivalent squashed replay onto this branch), resolving:
   - `skills/puppet/SKILL.md`: keep this branch's rewrite;
   - `.github/workflows/tests.yml`: keep this branch's hermetic version;
   - `plugin.json`, `.codex-plugin/plugin.json`, `tests/test_packaging.py`:
     already identical to the campaign side modulo main/#18 hunks — take the
     union git proposes;
   - `README.md`: union as described above.
3. Confirm `skills/puppet/references/` contains the six campaign files plus
   the three added here; confirm no `skills/puppet/README.md` exists.
4. Validate: full `python -m unittest discover -s tests`, plugin manifest
   parse, both skill packaging suites, compileall, and the CLI `--help`
   smokes from the workflow.
5. Open the successor PR against `main`. Independent review covers the
   rebase and cleanup delta only — not a third reading of 241 commits.
   Transport extraction (`--transport herdr`) stays out of scope (issue #11
   Phases 4–6). Merge remains Bobby's gate.

## Stop reason

Replay blocked on #18 merge. #18 was OPEN when this lane ran; the campaign
replay happens once, on top of a main that already contains it. No live
harness was launched, no qualification re-run, and no existing PR branch was
mutated.
