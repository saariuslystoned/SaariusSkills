---
name: tdd
description: "Enforce strict Test-Driven Development: write a failing test first, observe failure proof, then write minimal code to pass."
---

# Test-Driven Development (TDD)

Build features and fixes by verifying failure before implementing solutions.

## The Red-Green-Refactor Loop

1. **Red (Failing Test First)**:
   - Write a unit or integration test that reproduces the bug or asserts the new requirement.
   - Execute the test runner via `run_command`.
   - **Requirement**: Observe and capture the exact failure output. If the test passes initially, the test is invalid.
2. **Green (Minimal Passing Code)**:
   - Write the smallest possible diff to make the failing test pass.
   - Do not add extraneous features, optimizations, or refactoring in this step.
   - Execute the test runner again and verify green exit code.
3. **Refactor**:
   - Clean up code structure, names, and duplication while keeping tests continuously green.
   - Ensure diff remains minimal and surgical.\n