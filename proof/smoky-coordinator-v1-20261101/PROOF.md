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
skill-creator quick_validate.py skills/smoky-coordinator  # exit 0; isolated uv + PyYAML environment (parent validation)
```

## Limits

This proof establishes source-level packaging, canonical discovery, privacy,
and test behavior. An independent Muse scenario exercise on the core succeeded
on all six policy cases, but that is not full live runtime proof. This proof
does not claim external reviewer approval, merge, deployment, or a
provider/model availability measurement.

## Attribution preservation

The previous coordinator third-party acknowledgement and MIT notice are preserved byte-for-byte at `skills/smoky-coordinator/THIRD_PARTY_NOTICES.md`; the obsolete skill directory remains absent. This is an attribution move, with no second discoverable skill.

Parent verification after the attribution move: packaging/portable suite exit 0 (32 tests); `git diff --check` exit 0. Original attribution file compared byte-for-byte with the source-base copy.
