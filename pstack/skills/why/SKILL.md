---
name: why
description: "Investigate the historical context, architectural rationale, and git commit history behind existing code or decisions."
---

# Why (Context & Commit Archeology)

Understand the reasoning, constraints, and historical trade-offs behind existing code before attempting changes.

## Protocol

1. **Git Archeology**:
   - Use `git log -S` or `git log -L` on the target code block.
   - Read the commit messages, PR descriptions, and linked issue numbers.
2. **Identify Invariants & Edge Cases**:
   - Was this written to work around a specific bug, race condition, or platform quirk?
   - Check if existing tests were written specifically to protect this behavior.
3. **Synthesize Findings**:
   - State why the code was designed this way originally.
   - Identify whether the original constraint still applies today.\n