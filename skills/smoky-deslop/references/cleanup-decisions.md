# Cleanup decisions, not deletion rules

| Candidate | Evidence needed before changing it | Preserve when |
| --- | --- | --- |
| Obvious narration | The comment only repeats the adjacent operation | It explains a boundary, unusual choice, external constraint, license or tool directive |
| Defensive/null guard | All relevant callers and parsing contracts establish the same guarantee | It protects untrusted input, permissions, stale state or another entry point |
| Broad catch | Error propagation, cleanup and callers remain equivalent | It preserves rollback, resource release, error translation or user-facing diagnostics |
| Type cast/escape | Existing types or narrowing prove the replacement without widening an API | The cast bridges a verified external contract; uncertainty needs investigation, not deletion |
| Wrapper/abstraction | Callers, binding, stack/trace use and evaluation order remain equivalent | It supplies lazy execution, instrumentation, compatibility or a stable interface |
| Duplicate logging | Consumers and operational policy show no unique signal is lost | It supports incidents, audits, metrics or deliberate tracing |

A style mismatch is not proof of redundancy. Read relevant tests and nearby code; targeted checks should exercise error paths as well as success. Do not introduce logic changes merely to eliminate a cast or shorten a function.

## Security example

A changed handler checks `can_read(actor, record)` before returning a record. Its caller currently checks too, but the handler is also an external entry point. Retain the guard and its permission-denied behavior. A comment that says only “return the record” may be removed; a comment explaining the independent entry-point boundary is useful.

Verify both authorized and unauthorized calls directly to the handler. A successful caller-only test cannot establish equivalence of the guard's removal.

## Uncertain example

A retry looks excessive beside nearby one-shot calls. If its dependency's transient-failure contract or operational consumer is unknown, leave it. Report the uncertainty rather than replacing resilience with stylistic consistency.
