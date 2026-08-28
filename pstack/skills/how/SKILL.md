---
name: how
description: "Trace and explain runtime execution paths, data flow, and control logic through a codebase without modifying code."
---

# How (Execution Tracing)

Read-only code investigation that maps the mechanics of how a feature, subsystem, or workflow actually runs.

## Protocol

1. **Entrypoint Resolution**: Locate the initial trigger (CLI flag, HTTP handler, event listener, cron job).
2. **Follow Control Flow Step-by-Step**:
   - Trace each function call in sequence.
   - Note argument transformations, state mutations, and external I/O.
   - Identify where validation, auth checks, and error handling occur.
3. **Map Data Shapes**: Record the input, intermediate representation, and output data structures.
4. **Summary**: Provide a concise, step-by-step trace with exact `[file:line]` markdown links.\n