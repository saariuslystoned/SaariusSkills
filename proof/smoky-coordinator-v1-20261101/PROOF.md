# smoky-coordinator v1 proof

## Decision

- `smoky-coordinator` is the canonical public skill.
- One parent conversation owns decisions, acceptance, evidence, and the next
  action; no new scheduler, queue, or status store is introduced.
- ACP is preferred for substantial work through the existing
  `acp-delegation` contract. Implemented by an ACP-dispatched worker; no
  nested delegation was needed.

## Source and scope

- Canonical source: `skills/smoky-coordinator/`
- Packaging discovery is host-specific: Codex and Claude manifests declare the
  `./skills/` and `./vendor/pstack/skills/` roots; Cursor uses an explicit
  skill-path list; the AGY root manifest relies on its host discovery shape and
  has no `skills` array.
- No sibling lane, private binding, credential, generated log, or runtime
  integration was changed.

## Commands

```text
python3 -m unittest tests.test_packaging tests.test_portable_skills  # exit 0; 32 tests
python3 -m unittest discover -s tests  # exit 0; 185 tests
python3 skills/smoky-skill-cleaner/scripts/audit-skills --root skills --json  # exit 0; 29 skills, 0 duplicates, 30 reported hygiene findings
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/smoky-coordinator  # not run: PyYAML unavailable (no install)
```

## Limits

This proof establishes source-level packaging, canonical discovery, privacy,
and test behavior. An independent Muse scenario exercise on the core succeeded
on all six policy cases, but that is not full live runtime proof. This proof
does not claim external reviewer approval, merge, deployment, or a
provider/model availability measurement.
