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

PR_OPEN. Implementation and local validation complete. The owner approved one consolidated smoky-performance entrypoint replacing smoky-ci-performance. Its capture helper and measurement contracts are retained, including the existing persisted receipt schema. Both skills use portable repository-owned workflows. Upstream source at OpenClaw commit 85c39026a90f58164595249f69c311ed71b44df8 is MIT-licensed by the OpenClaw Foundation. The two source blobs match the earlier observation snapshots.

The full local suite passed with 227 tests. Packaging and capture tests passed, both skill metadata checks passed, and the complete source diff was inspected. The implementation is committed as 87146e2fd88abec030adf026eef40e374d6458ac. Subsequent changes in this packet record publication only.

The PR is https://github.com/saariuslystoned/SaariusSkills/pull/223. Current CI and external review status are tracked in its checks and conversation. The author lane returned source ownership to the parent. The next owner action is to review the PR with its current check results under the existing merge gate.

Focused owner review suggestions were applied to the instructions and migration documentation. Packaging tests and both validators passed again. No executable behavior changed in the follow-up. Review evidence for earlier heads remains historical, with the revised head tracked on the PR.

No application performance improvement has been measured by this skill-authoring task.
