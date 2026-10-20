---
name: smoky-skill-cleaner
description: Audit explicit skill directories for metadata, duplicate names, missing references and oversized instructions. Use for skill maintenance and consolidation; default to read-only inspection.
---

# Skill Auditor

Read the current request and trusted repository instructions first. If they name an optional binding for this skill, read it for local targets, tools and policy. Without a binding, use the portable workflow below. A binding does not grant authority to act.

Read `references/audit-policy.md` for the checks and their limits. Run the repository's existing validator when available, then run this helper against an explicit skill root:

```sh
python3 skills/smoky-skill-cleaner/scripts/audit-skills --root skills --json
```

Inspect metadata, body size, duplicate names and missing references. Distinguish advisory size thresholds from broken packaging. Missing optional UI metadata is not a universal validity error. A duplicate name is a candidate for comparison, not proof that either copy is disposable.

Report counts, affected paths, evidence and recommendations. Do not infer that a skill is unused because no usage record was found. Suggest a smaller body or a reference split when it reduces routine context without hiding essential instructions.

Keep this task read-only unless edits are requested. Do not scan session transcripts, authentication logs, shell history or arbitrary home directories. Before recommending removal, identify the canonical retained source and its callers. Use the repository's own cleanup policy for any eventual deletion.
