# Skill audit policy

Inspect explicit skill roots and their metadata/references only. Do not scan logs, shell history, authentication stores, unrelated home folders or session transcripts as a side effect. Broader usage analysis requires its own scope and authorization.

Check names, descriptions, instruction length, optional UI metadata, reference existence and duplicate candidates. The helper uses simple single-line frontmatter parsing and a references/ path matcher; confirm findings when a package uses richer YAML or other link forms. Length thresholds and missing UI metadata are advisory.

Use these dispositions: keep; shorten-description; split-reference; script-candidate; duplicate-candidate; privacy-gated; delete-candidate. A deletion candidate must name the kept canonical copy and migration path. Lack of usage evidence is not evidence of disuse.

Report root, skill count, duplicate groups, body/description pressure, metadata/reference gaps, commands, privacy limits and ranked recommendations. Editing or deleting follows the user's scope and repository policy; the audit itself is read-only.
