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

Walkthrough result: decisions above are expressible without implementation evidence, domain-specific checkout rules, runtime dependencies or fixed prose assertions. This is an author judgment of guidance consistency only; actual source-blind product validation and installed-harness execution remain unproved.
