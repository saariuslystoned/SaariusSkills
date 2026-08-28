---
name: blast-radius
description: "Analyze downstream callers, consumers, imports, and system dependencies to prove what could break before making a change."
---

# Blast Radius Analysis

Determine the full ripple effect of an interface, schema, or implementation change before editing source code.

## Protocol

1. **Symbol & Route Identification**: Identify the exact symbol(s), type signatures, route handlers, or configuration keys being modified.
2. **Exhaustive Dependency Search**:
   - Use `grep_search` to find all direct and indirect references across the entire repository/workspace.
   - Check internal callers, unit/integration test suites, configuration files, and documentation references.
   - Identify cross-process contracts (e.g. IPC, HTTP endpoints, message queues, SQLite schemas).
3. **Classify Risk Matrix**:
   - **Low**: Pure internal helper function with full unit test coverage.
   - **Medium**: Exported module function or shared type used across multiple local packages.
   - **High**: Public API, database migration, external network protocol, security/auth gate, or cross-machine interface.
4. **Verification Plan**:
   - Identify which existing tests will cover the change.
   - If callers lack test coverage, design test cases *before* altering the implementation.
5. **Report**:
   - Explicitly list affected files, caller count, downstream risk, and required regression proofs.\n