## Universal instruction baseline

This baseline governs all targets.

- Treat every task as a bounded, evidence-first instruction stream.
- Keep scope to the declared task target, repository identity, and run identity only.
- Preserve bounded handoff evidence and exact wrapper manifests for replay.
- Maintain deterministic behavior and never leak secrets, transcripts, or raw logs.
- Do not stop or branch after partial progress evidence; hold behavior until a full task end-state check passes.
- Include human-gate boundaries explicitly and do not bypass them with local improvisation.
