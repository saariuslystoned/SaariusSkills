# Harness² experiment contract

Use this as the smallest handoff packet. Keep it sanitized and portable; do
not include private repository names, absolute local paths, host topology,
credentials, or raw transcripts.

## Experiment

- **Identity:** stable target, hypothesis, acceptance identity, and unique
  active/completed-record check.
- **Task:** one real task, exact repository and immutable source revision,
  product outcome, and exclusions.
- **Editable surfaces:** explicitly allow-listed harness surfaces only
  (system prompt, guardrails, memory, tool guidance, subagents, skills,
  scripts, or plugins). No installed edits or unrelated product files.
- **Budget:** sequential `k=1`; four solver executions total
  (reference plus three improvement stages), then reflection; state time,
  model, tool, cost, and retry limits.
- **Isolation:** candidate workspace and artifacts are separate from the
  original; one writer owns each conflicting target.
- **Checks:** hard repository checks, product acceptance criteria, tests,
  proof/review gates, permissions, and stop condition.
- **Evaluation boundary:** the optimizer and solver cannot access held-out
  judge answers, rubrics, or labels. Do not confuse upstream's automatic
  adoption of its sole composed candidate with improvement proof.

## Result

Record these independently:

- `status`: `keep`, `reject`, `inconclusive`, or `blocked`;
- `attempt`: first attempt or recovery attempt, with separate evidence;
- `source`: exact repository/branch/SHA and experiment identity;
- `artifacts`: candidate, logs or summaries, hard-check results, and sanitized
  anonymized fixed-protocol A/B evidence;
- `jev`: `decision_evaluate` result or `unavailable` provenance, with manual
  fallback explicitly labeled when used;
- `ownership`: current writer, cleanup owner, and next action.

Jev choices are only `original-better`, `candidate-better`, `equivalent`, or
`insufficient-evidence`. An unavailable Jev result is not a judgment. Jev
cannot override a hard failure or authorize an action. A result does not prove
transfer to another task.
