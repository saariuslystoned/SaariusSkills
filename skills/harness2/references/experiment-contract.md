# Harness² experiment contract

Use this as the smallest handoff packet. Separate the authorized PRIVATE
execution packet from hosted evaluation and public proof. The PRIVATE packet
may contain the exact repository, branch, immutable revision, and workspace
routing needed for delegation. Minimize or redact those identifiers before
hosted evaluation or public proof. The PRIVATE packet may include minimal
authorized routing IDs and sanitized excerpts actually needed for execution.
Never include secret values, credentials, or unfiltered transcripts;
public/hosted evidence should minimize private identifiers.

## Experiment

- **Identity:** stable target, hypothesis, acceptance identity, and unique
  active/completed-record check.
- **Task:** one real task, exact repository and immutable source revision in
  the PRIVATE packet, product outcome, and exclusions.
- **Editable surfaces:** explicitly allow-listed harness surfaces only
  (system prompt, guardrails, memory, tool guidance, subagents, skills,
  scripts, or plugins). Preserve immutable sections and do not modify or
  override them. Keep mandatory repository policy, safety or authority rules,
  acceptance criteria, and installed-file boundaries in the frozen packet and
  authoritative sources. No unrelated product files.
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
- **Jev input:** provide sanitized, anonymized A/B evidence only. Ask Jev to
  choose `A-better`, `B-better`, `equivalent`, or `insufficient-evidence`
  against neutral, evidence-based criteria. Keep the mapping of A/B to
  original/candidate outside the judge input; translate the result only in the
  PRIVATE record.

## Result

Record these independently:

- `status`: `keep`, `reject`, `inconclusive`, or `blocked`;
- `attempt`: first attempt or recovery attempt, with separate evidence;
- `source`: exact repository/branch/SHA and experiment identity in the PRIVATE
  record; a minimized or redacted source reference for hosted/public artifacts;
- `artifacts`: candidate, logs or summaries, hard-check results, and sanitized
  anonymized fixed-protocol A/B evidence;
- `jev`: `decision_evaluate` result or `unavailable` provenance, with an
  independent manual fallback explicitly labeled when used. Jev is not a new
  delivery gate; without comparative evidence, the result is inconclusive;
- `ownership`: current writer, cleanup owner, and next action.

Jev input choices are only `A-better`, `B-better`, `equivalent`, or
`insufficient-evidence`; the PRIVATE record may map the first two to
`original-better` or `candidate-better`. An unavailable Jev result is not a
judgment; the same fixed criteria may instead be applied by an explicitly
labeled independent manual evaluation. Jev cannot override a hard failure or
authorize an action. A result does not prove transfer to another task.
