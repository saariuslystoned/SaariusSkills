# Behavior report

The verdict rules below apply to every report, inline or structured. For a small check, an inline contract, target/version/environment and observation time, action/result, clause status, reproducible steps and limits suffice. Link larger evidence only when useful. This JSON is an optional example, not a required packet or measured confidence score.

```json
{
  "overall_behavior": "satisfies_contract",
  "overall_confidence": 0.9,
  "target": {"type": "CLI", "access": "<authorized command>", "version": "<exact version>"},
  "observed_at": "<timestamp>",
  "contract": {"path": "behavior-contract.md", "version": "<revision>"},
  "checks": [{
    "contract_clause": "Task 1",
    "status": "pass",
    "severity": null,
    "evidence": "<artifact or command/result>",
    "reproduction_steps": ["<authorized action>"],
    "confidence": 0.9,
    "remaining_uncertainty": "<none or explicit limit>"
  }],
  "anti_cheat_probes": [{"probe": "<input variation>", "result": "<observed result>"}],
  "blockers": []
}
```

Each clause is `pass`, `fail`, `blocked` or `out_of_scope`:

- `pass`: observed evidence supports the stated criterion on the identified target.
- `fail`: an observed result violates that criterion. Missing or inconclusive observations alone are not proof of a product defect.
- `blocked`: the clause cannot be decided because required evidence is missing or inconclusive, required expectations, authorization, access, fixtures or tools are missing, or source-blind independence cannot be established. Reject an unsupported claimed pass as `blocked` unless an observed violation establishes `fail`. Name the evidence gap or dependency and next action; use `blocked_source_required` as a blocker reason when applicable.
- `out_of_scope`: explicitly excluded or outside the assignment; give the scope reason, not a passing verdict.

Overall behavior is `violates_contract` if any in-scope clause fails, otherwise `blocked` if any in-scope clause is blocked, otherwise `satisfies_contract` only when all in-scope clauses pass. If none is in scope, report that explicitly instead of claiming satisfaction (omit the overall field in structured output). Preserve mixed clause results and blockers even when a failure determines the overall value.

`anti_cheat_probes` holds the relevant edge checks actually run; it can be empty. Unspecified exploratory outcomes are observations/gaps, not new requirements. Identify live versus synthetic/mock targets explicitly. Confidence fields are optional estimates, not measured accuracy; record remaining uncertainty instead of inventing precision. Never embed credentials, private user data, authentication links or unrelated log contents.
