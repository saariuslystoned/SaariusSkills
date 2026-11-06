# Smoky build skills

## Assignment

- Repository is saariuslystoned/SaariusSkills.
- Branch is codex/smoky-simplify-performance.
- Verified fresh base is cbe0738b611b75cdf1dc458efdeb6863da102597.
- Task is to add smoky-pr-simplify and consolidate application, service, test and CI performance in smoky-performance, including packaging and a reviewable PR.
- Author lane owns the new skills, Cursor skill list, packaging tests and catalog entries. The parent owns proof, publication and review coordination.
- Mode is mutate within the assigned source slice. Existing operator checkouts remain separate.
- Stop condition is a published PR with applicable validation and honest review status. Merge and distribution remain under their existing gates.

## Current state

Implementation and local validation complete. The owner approved one consolidated smoky-performance entrypoint replacing smoky-ci-performance. Its capture helper and measurement contracts are retained, including the existing persisted receipt schema. Both skills use portable repository-owned workflows. Upstream source at OpenClaw commit 85c39026a90f58164595249f69c311ed71b44df8 is MIT-licensed by the OpenClaw Foundation. The two source blobs match the earlier observation snapshots.

The full local suite passed with 227 tests. Packaging and capture tests passed, both skill metadata checks passed, and the complete source diff was inspected. Next action is PR publication, repository CI and the available review workflow. The author lane has returned source ownership to the parent.

No application performance improvement has been measured by this skill-authoring task.
