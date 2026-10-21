# Behavior report

```json
{
  "overall_behavior": "satisfies_contract",
  "overall_confidence": 0.9,
  "target": {"type": "CLI", "access": "<authorized command>", "version": "<exact version>"},
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

Overall behavior is `satisfies_contract`, `violates_contract` or `blocked`. Each clause is `pass`, `fail`, `blocked` or `out_of_scope`. Use fail for an observed violation or inadequate evidence for a claimed pass; use blocked for missing access, fixtures or tools. Confidence fields are optional estimates, not measured accuracy; record the remaining uncertainty instead of inventing precision. Never embed credentials, private user data, authentication links or unrelated log contents.
