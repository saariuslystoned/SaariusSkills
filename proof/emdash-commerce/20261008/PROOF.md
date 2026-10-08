# EmDash Commerce skill packaging proof

Prepared against SaariusSkills main `1c914f7` on branch
`codex/emdash-commerce-skill` in an isolated worktree. This packages separately
authored portable guidance, not an upstream EmDash skill or Commerce product
implementation. Only public-safe skill files and curated packaging evidence
are included; no private decision packets, operator paths or ledger state.

## Validation

- Bundled skill-creator `quick_validate.py`: valid skill.
- `python3 -m unittest discover -s tests -p 'test_packaging.py' -q`:
  16 tests passed, including skill discovery, Cursor registration and complete
  Commerce metadata/reference packaging.
- `python3 -m unittest discover -s tests -p 'test*emdash*.py' -q`:
  25 tests passed.
- `python3 -m unittest discover -s tests -q`: 172 tests passed.
  Expected rejection diagnostics from negative fixtures are not suite failures.
- `python3 scripts/sync-emdash-skills --check`: pinned vendor mirror and four
  packaged upstream skills clean.
- GrillTrack ledger `--help`, picker fixture validation and phone-proof `--help`:
  exit 0; picker reported `valid`.
- `git diff --check`: clean.

The packaged three-file skill matches the previously validated local artifact
byte for byte. Existing Codex, Claude and path-install surfaces discover the
skills directory; Cursor's explicit list now includes `emdash-commerce`.
This verifies packaging, not a live installation or ecommerce integration.

## Behavioral review

Author walkthroughs checked a new agent-facing catalog/cart API decision
(activate focused official-source comparison), a misspelled admin label
(skip competitor research), and implementation of an existing lock
(preserve the lock, do not restart comparison without material new evidence).
These are manual routing/workflow checks, not independent model evaluations.

The skill preserves current decisions and unresolved choices, separates platform
facts from recommendations, and reports unavailable source coverage. It does
not impose today's product-model proposal or universally prohibit bundles.
Research recommendations remain separate from GrillTrack state transitions
and implementation/delivery authorization.

Author packaging review found no required fixes. Upstream license checks apply
only to the four pinned upstream skills; the new maintained skill is not
misrepresented as vendored upstream work. No release, runtime provider/protocol
support, deployment or merge is claimed.

## Skill content identity

| File | SHA-256 |
| --- | --- |
| `skills/emdash-commerce/SKILL.md` | `7bc568b9fa546793d87193dc6340036560260e6bd2c2d52edc91c501cda76d13` |
| `skills/emdash-commerce/agents/openai.yaml` | `82cbc45ee717d907f306d32578b9d7b0da4f02fb0922fff1726a29b46f2cd28f` |
| `skills/emdash-commerce/references/source-map.md` | `d762e50e417372a3e5bf47efa9b850fa55418e354fb27612c079b9443a07d754` |
