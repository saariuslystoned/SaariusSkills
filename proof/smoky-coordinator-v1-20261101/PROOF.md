# smoky-coordinator v1 proof

## Decision

- `smoky-coordinator` is the canonical public skill.
- `smoky-codex-coordinator` is a thin, non-recursive forwarding alias for one
  migration cycle.
- One parent conversation owns decisions, acceptance, evidence, and the next
  action; no new scheduler, queue, or status store is introduced.
- ACP is preferred for substantial work through the existing
  `acp-delegation` contract. This implementation used the authorized direct
  fallback because native ACP tools were unavailable in the active session.

## Source and scope

- Canonical source: `skills/smoky-coordinator/`
- Compatibility source: `skills/smoky-codex-coordinator/`
- Packaging surfaces: Codex, Claude, Cursor, and AGY manifests already discover
  the shared `skills/` root.
- No sibling lane, private binding, credential, generated log, or runtime
  integration was changed.

## Commands

```text
python3 -m unittest tests.test_packaging tests.test_portable_skills
python3 -m unittest discover -s tests
python3 skills/smoky-skill-cleaner/scripts/audit-skills --root skills --json
```

## Limits

This proof establishes source-level packaging, alias, discovery, privacy, and
test behavior. It does not claim runtime ACP execution, external reviewer
approval, merge, deployment, or a provider/model availability measurement.
