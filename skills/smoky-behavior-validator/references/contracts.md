# Observable behavior contracts

Begin with the assigned acceptance criteria and target-owned published interface specifications, not implementation details. If no contract exists, write a short inline one from those inputs before testing; a separate file is optional. Record missing/conflicting expectations as gaps and block only the affected verdicts pending clarification. Continue independent checks where possible; do not turn guesses into requirements.

```text
goal: <observable outcome>
target: <web app|CLI|API|device|artifact and exact version/environment>
access: <authorized URL, command, device or file>
fixtures: <allowed test inputs and approved credential mechanism; no values>
tasks: <concrete user actions>
expected: <observable result per acceptance clause; cite its source/revision>
gaps: <missing or conflicting expectations, if any>
probes: <relevant changed input, retry/reopen, invalid or boundary case>
evidence: <screenshots, response/exit summaries, artifact checks>
excluded: <actions and claims outside scope>
```

Select checks relevant to the claim, rather than applying every probe to every target:

- Web: perform the interaction and observe its result; refresh/reopen when persistence is promised. A button or success banner alone is insufficient.
- CLI: check relevant standard streams, exit codes, non-interactive behavior, output/state and any claimed dry-run boundary.
- API: check response semantics, relevant freshness and externally observable state changes using authorized fixtures; HTTP success alone is insufficient.
- Registered test device: bind the exact device/app/test identity; observe the action and visible result, then reopen when relevant. Missing registration or access is blocked, not permission to substitute a personal device.
- Artifact: identify the exact file/version (hash when useful), open it in an appropriate viewer or consumer and inspect the claimed content, not merely its existence.

Relevant edge cases can expose a violation of an existing criterion. If their expected outcome is unspecified, report the observation and expectation gap without declaring an invented product failure. Exclude aesthetic/code-quality preferences unless observable acceptance explicitly covers them.

Use only assigned test targets; state allowed mutations and communication before acting. Credential mechanisms may be named, never credential values. Capture only necessary redacted observations, not unrelated desktop, account or log content. Stop before an unapproved action and report the specific missing authority.

A successful edit, deploy/build or mock exercise is not proof of live target behavior. Keep implementation review/repair separate. Source access needed to proceed is `blocked_source_required`, not an invitation to inspect implementation. Record the tested target's exact release/build or artifact identity and observation time; obtain identity from authorized metadata, not source inspection. State when identity cannot be verified and limit the claim.

For the narrow upstream comparisons behind this revision, see [sources](sources.md).
