---
name: reflect
description: "Post-task retrospective analyzer that inspects session transcripts to extract lessons and persist durable repo rules."
---

# Reflect (Post-Task Retrospective)

Inspect session execution history to learn from friction, failures, and operator corrections.

## Protocol

1. **Analyze Transcript**:
   - Read the conversation's `transcript.jsonl` from `<appDataDir>/brain/<conversation-id>/.system_generated/logs/`.
   - Look for:
     - Commands that failed and had to be retried.
     - User corrections or redirects.
     - Ambiguities that wasted tool calls.
2. **Extract Root Cause**:
   - What assumption was wrong?
   - What missing context caused the mistake?
3. **Persist Durable Rules**:
   - If the lesson is repo-specific, propose an addition to `AGENTS.md`, `CLAUDE.md`, or a local skill.
   - If the lesson is operator-specific, update `bobby-mode` or global guidelines.\n