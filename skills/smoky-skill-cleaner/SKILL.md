---
name: smoky-skill-cleaner
description: Audit explicit skill directories for metadata, duplicate names, missing references and oversized instructions. Use for skill maintenance and consolidation; default to read-only inspection.
---

# Skill Auditor

Read the current request and trusted repository instructions first. Before applying this core, check those instructions and available skill metadata for a configured operator or repository profile. If they identify a profile-specific installed variant of this skill or an optional binding, read it first unless already loaded. Do not use an unbound core to bypass that profile, invent a binding, or search unrelated files. With no configured profile, use the portable workflow below. A profile or binding does not grant authority to act.

Read `references/audit-policy.md` for the checks and their limits. Run the repository's existing validator when available, then run this helper against an explicit skill root:

```sh
python3 skills/smoky-skill-cleaner/scripts/audit-skills --root skills --json
```

Inspect metadata, body size, duplicate names and missing references. Distinguish advisory size thresholds from broken packaging. Missing optional UI metadata is not a universal validity error. A duplicate name is a candidate for comparison, not proof that either copy is disposable.

Report counts, affected paths, evidence and recommendations. Do not infer that a skill is unused because no usage record was found. Suggest a smaller body or a reference split when it reduces routine context without hiding essential instructions.

Keep this task read-only unless edits are requested. Do not scan session transcripts, authentication logs, shell history or arbitrary home directories. Before recommending removal, identify the canonical retained source and its callers. Use the repository's own cleanup policy for any eventual deletion.
