---
name: automate-me
description: "Mines recent conversation transcripts to extract operator preferences, habits, and rules, generating or updating bobby-mode/SKILL.md."
---

# Automate Me (Operator Profiler)

Inspect recent Antigravity conversation logs to synthesize operator preferences and generate a personalized `bobby-mode` skill.

## Protocol

1. **Read Transcripts**:
   - Access `<appDataDir>/brain/<conversation-id>/.system_generated/logs/transcript.jsonl` across recent sessions.
   - Filter for `USER_INPUT` steps and explicit operator corrections.
2. **Extract Key Dimensions**:
   - **Voice & Brevity**: Tone rules, brevity requirements, voice-to-text formatting quirks.
   - **Workflow Preferences**: TDD, worktree isolation, required verification commands, git branching rules.
   - **Decision Gates**: Actions pre-approved for autonomy vs actions requiring explicit human approval.
3. **Emit / Update `bobby-mode`**:
   - Write or update `~/.gemini/config/plugins/saarius-skills/skills/bobby-mode/SKILL.md`.
   - Maintain a concise, actionable, bulleted summary of operator invariants.
4. **Output Summary**:
   - Report newly captured rules or updated preferences to the operator for confirmation.\n