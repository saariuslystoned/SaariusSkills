---
name: maintain-verification-skill
description: "Upkeep and update existing verification scripts, schemas, and test harnesses when the codebase drifts."
---

# Maintain Verification Skill

Keep repo-local verification scripts and feature maps in sync with code evolutions.

## Protocol

1. **Detect Drift**: Run existing verification scripts in `bin/` or `skills/` to identify broken assumptions, changed CLI flags, or schema updates.
2. **Update Harnesses**:
   - Update parameters, mocks, fixture data, and assertions to match the current codebase contract.
   - Remove obsolete assertions; add coverage for newly added variants.
3. **Verify Integrity**: Re-run the updated verification script and confirm clean exit status.\n