# Synthetic guidance sanity cases

Manual scenario walkthrough, 2026-11-05. These are stipulated inputs/observations used to check the revised instructions' decisions, not live executions, independent model evaluations, or proof that any product or harness behaves this way. No implementation source would be available to the validator in these cases. Authoring inspection of this skill is a separate activity.

| Case / assigned criterion | Stipulated observation or dependency | Guidance outcome |
| --- | --- | --- |
| Standalone CLI: `--help` exits zero and lists `export` | Exact release/command, stdout and exit captured; both expectations met | `pass` for this narrow clause; short inline reproduction and limits, no coordinator, packet, or claim that export works. |
| CLI dry run must leave a named fixture unchanged | Exit zero and a success message, but the externally observed fixture changes | `fail`; cite the dry-run criterion, command and before/after state, not implementation. |
| Web preference must survive reopening | Save banner appears; reopening on the same test identity shows old preference | `fail`; the screenshot/banner alone does not establish persistence. |
| API must create a retrievable test item | HTTP 201 and subsequent authorized GET returns the specified item on the identified test deployment | `pass` for creation/retrieval, not unrelated API behavior. |
| API empty-name edge probe has no published expected outcome | Response is 400; neither task nor published spec states this case | Record observation and expectation gap, not an invented failure/pass; block a requested verdict on this case until clarified, continue independent clauses. |
| Registered-device interaction | Assigned test device unavailable; a personal phone happens to be connected | `blocked`; identify missing exact target, do not substitute or enroll a device. |
| Artifact export must include two named columns | Correctly identified synthetic file opens in a suitable consumer, but one required column is absent | `fail`; existence or successful generation alone is insufficient. |
| Source-only explanation offered for a failing action | Developer provides a diff/internal test to explain why it should pass | Do not inspect it as validation evidence; obtain external observations. If already exposed, disclose contamination and hand independent validation to a clean source-blind context. If source is required, `blocked_source_required`. |
| A live journey is requested, but only a mock is available | Mock check succeeds | Do not claim a live pass; label mock evidence explicitly and block the live clause for missing target access. |
| Customer send explicitly excluded | A send control is reachable | `out_of_scope`, not a pass; do not send. Missing permission on an otherwise in-scope action is instead `blocked`. |
| Mixed clauses | One observed violation, one access blocker, one pass, one exclusion | Preserve all four clause results; overall `violates_contract` with blocker and limits, never blanket satisfaction. If all clauses are excluded, no satisfaction claim. |
| Repair handed back on new identified build | Separate source-aware owner reports a repair | Rerun affected observable clauses plus proportionate adjacent probes against the new target. The edit/report is not proof of the repaired behavior. |

## Copilot repair walkthroughs

Additional manual synthetic guidance cases, 2026-11-05; not live product behavior or independent harness proof. The same verdict rules apply without a JSON report.

| Case / assigned criterion | Stipulated observation or dependency | Guidance outcome |
| --- | --- | --- |
| Inline report, one pass and one blocked clause | First criterion observed; second lacks required evidence | Preserve both results; overall `blocked`, not satisfaction. |
| Inline report, all clauses excluded | No in-scope criterion remains | Explicitly report no in-scope clauses, no satisfaction claim. |
| Inline report, fail plus missing evidence | One observed violation and another undecidable clause | Overall `violates_contract`; keep the other clause `blocked` and its next observation. |
| Web display-only criterion | Click displays the promised banner; action/result captured on exact target | `pass`; do not demand persistence or other unpromised work. |
| API status-only criterion | Exact authorized endpoint returns the specified HTTP 200 | `pass`; do not demand response content or state changes not in the contract. |
| API additionally promises retrievable item | HTTP 201 observed, but retrieval observation unavailable | Creation/retrieval clause `blocked` for missing evidence; fetch authorized external state next. No product failure inferred from the gap. |
| Promised artifact content, inconclusive observation | Identified file is accessible, but captured view does not establish whether the required column exists | `blocked`; name the unresolved content check and reopen in a suitable consumer, not pass or fail by inference. |

## Source-contamination precedence walkthroughs

Additional manual synthetic cases for the distinct follow-up finding; not actual product runs, independent model evaluations or executable prose assertions. Here the affected in-scope clauses are the entire assignment unless otherwise stated.

| Case / assigned criterion | Stipulated observation or dependency | Guidance outcome |
| --- | --- | --- |
| Apparent violation in a contaminated context | After seeing implementation details, validator observes the old preference after a promised save/reopen | Clause and overall `blocked`; retain the apparent violation as provisional with a clean source-blind verification handoff, not a product failure verdict. |
| Apparent success in a contaminated context | Implementation is already in context; HTTP status appears to meet the contract | Clause and overall `blocked`; apparent success cannot bypass independence either. |
| Clean verification confirms violation | New source-blind context receives only acceptance, authorized fixtures and target identity, independently repeats save/reopen and observes old preference | `fail`, overall `violates_contract`, supported by the clean context's own observations, not the contaminated report. |
| Clean verification contradicts provisional violation | Clean context independently repeats the exact contracted action on the identified target and observes all required results | `pass`, overall `satisfies_contract`; the provisional observation does not override fresh clean evidence. |
| Clean context still lacks evidence | Fresh context has not observed the required reopen result | Remains `blocked`; a new context alone is not verification. No pass or fail inferred. |
| Clean observed violation plus a separate missing observation | Clean context observes a criterion violation, but another in-scope clause remains inconclusive | Preserve `fail` and `blocked`; overall `violates_contract`. The independence fix does not suppress genuine clean failures or erase other blockers. |

## Existence-only artifact follow-up

Copilot's subsequent current-head review raised a distinct, previously missed requirement mismatch. Manual synthetic case: the acceptance criterion promises only that a named artifact exists at the authorized path; exact target identity and file-existence evidence are available, but no viewer is available or authorized. Outcome: `pass` for existence alone, no content claim, viewer installation or extra permission required. In contrast, the original missing-column and inconclusive-content cases still require content evidence: existence alone cannot satisfy them. This is a guidance walkthrough, not actual filesystem/product validation.

Walkthrough result: decisions above are expressible without implementation evidence, domain-specific checkout rules, runtime dependencies or fixed prose assertions. This is an author judgment of guidance consistency only; actual source-blind product validation and installed-harness execution remain unproved.
