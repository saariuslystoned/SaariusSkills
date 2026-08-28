---
name: architect
description: "Design module boundaries, type signatures, interfaces, and state contracts before generating implementation code."
---

# Architect

Plan and lock down architecture, data shapes, and contracts prior to implementation to prevent premature or drifted code generation.

## Protocol

1. **Define Boundaries & Responsibilities**:
   - What does this component own?
   - What does this component explicitly *not* own?
   - What external dependencies does it rely on?
2. **Sketch Interfaces & Types**:
   - Define exact type definitions, schemas, function signatures, and error types.
   - Write these into the `implementation_plan.md` or design artifact first.
3. **State & Invariants**:
   - Document state lifecycles, concurrency guarantees, and invariant checks.
   - Ensure fail-closed defaults on error paths.
4. **Zero-Implementation Review**:
   - Review the type signatures and data flow *before* writing function bodies.
   - Confirm compatibility with callers and downstream consumers.\n