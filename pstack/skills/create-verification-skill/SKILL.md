---
name: create-verification-skill
description: "Scaffold project-local verification scripts and automated test harnesses (e.g. in bin/verify-* or local skills) to prove system behavior."
---

# Create Verification Skill

Build deterministic, executable verification scripts so agents can prove application behavior repeatedly.

## Protocol

1. **Identify the Surface**: Determine if the surface is a CLI, HTTP API, DB state, or background daemon.
2. **Write an Owned Script**:
   - Place executable verification in `bin/` or repo-local `tools/` (e.g. `bin/verify-<feature>`).
   - The script must return exit code `0` on success and non-zero with diagnostic output on failure.
   - Ensure the script runs non-interactively and fast.
3. **Document in a Local Skill**:
   - Create a corresponding `SKILL.md` in `skills/<feature>-verification/SKILL.md` documenting usage, flags, and expected output.
4. **Smoke Test**: Run the verification script once to prove it works as intended.\n