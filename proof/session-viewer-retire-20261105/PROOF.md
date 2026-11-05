# Standalone session viewer retirement

## Scope and source

Owner-approved source maintenance: retire `smoky-session-viewer`, not installed
copies or transcript data. Branch: `ridge/session-viewer-retire-20261105`.
Base: `19a31ea47001323ff39dea9d6dfd621f4d9c68f0`.

Removed exact source paths under `skills/smoky-session-viewer/`:
`SKILL.md`, `agents/openai.yaml`, `references/session-policy.md`,
`scripts/render-session`, and `LICENSE`. Also remove its explicit Cursor entry,
portable skill listing and obsolete synthetic renderer tests. Codex/Claude use
skill-root discovery; AGY/path installation uses the skills directory, so no
manifest identity, version or root change is needed.

## Consumer decision and preservation

Tracked-source search for `smoky-session-viewer`, `render-session`, session-viewer
variants and transcript HTML found no runtime helper import/caller. The public
renderer tests and a downstream synthetic installer fixture were its only
executable consumers. The downstream workflow recommendation is being removed
in its owning source; executable-bit installation coverage uses an unrelated
synthetic helper fixture, not a relocated transcript renderer. No helper needs
a retained source location. The downstream discovery/composition change can
land before this public retirement, retaining immutable source references.

Existing remote session-view documentation describes a separately owned
surface; no equivalence or replacement claim is made. Independent skills do
not require transcript rendering. Historical proof, receipts, upstream snapshots
and Git history remain unchanged. No real transcripts, installed files,
archives, credentials or unrelated skill bodies were inspected or changed.
Validation uses only synthetic fixtures.

## Validation

- `python3 -m unittest discover -s tests -q`: PASS, 206 tests, 96.039 seconds.
- Packaging discovery asserts retired directory absence across Cursor and
  Codex/Claude roots; existing packaging suite checks exact Cursor/source set.
- Remaining portable metadata/license/reference/privacy checks and read-only
  audit fixture pass; no renderer remains to execute.
- `git diff --check`: PASS.

Prepared/tested source only, not deployed or installed. External CI and review
are separate exact-head gates. No merge or installed-file cleanup authorized.
