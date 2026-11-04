# Coordinator core rewrite — 2026-11-04

The public core now routes substantial work through the configured execution
runtime with one lead assignment. It keeps quick checks conversational and
permits bounded specialists below the lead. Host, transport, model, and local
runtime policy remain outside the public core.

## Source identity

- Repository: `saariuslystoned/SaariusSkills`.
- Assigned Ridge mount: `SaariusSkills/`.
- Branch: `ridge/coordinator-rewrite-20261104`.
- Base: `origin/main`, `88eaac168fcf140915570fdfe8b2d1126bee4877`.
- Reviewed source commit: `1d7892be96a3ef3b5ea38caeb677f5428ab38f96`.
- Scope: `skills/smoky-coordinator/SKILL.md`, its existing UI metadata, and
  the coordinator row in `docs/portable-skills.md`.
- The subsequent proof commit changes only this proof directory. Its immutable
  head is available from the PR or `git log -1` on this branch.

All 15 open PRs were checked for exact changed-file overlap before edits;
none touched these three source files. Packaging manifests, other skills,
runtime code, and installed skill copies were not changed.

## Validation

- Skill Creator `quick_validate.py skills/smoky-coordinator`: PASS using system
  Python with PyYAML. The default Python lacked PyYAML; no package was installed.
- `python3 -m unittest tests.test_packaging tests.test_portable_skills -q`:
  PASS, 34 tests. See `packaging-tests.txt`.
- `python3 -m unittest discover -s tests -q`: PASS, 187 tests in 95.347s.
  See `all-tests.txt`; expected negative-fixture diagnostics precede `OK`.
- `git diff --check`: PASS.
- Existing license and third-party attribution preserved. No private operator
  names, infrastructure, model preferences, or checkout paths added to the core.

## Manual scenario walkthrough

This is a static reading exercise, not live harness execution or an independent
behavioral pass. An optional external judge was unavailable under the worker's
approval policy; no judge result is claimed.

| Request or condition | Resulting action from the revised core |
| --- | --- |
| Quick aside during coding | Answer inline; preserve the original objective and active assignment. |
| Substantial coding request | Check overlap, select workspace/loadout, hand off one durable lead assignment through the configured runtime. |
| Follow-up on that coding request | Steer or queue on the existing assignment; do not create a competing writer. |
| Worker reaches a human gate | Surface the exact ask and evidence; preserve ownership and do not redo blocked work. |
| Harness/model fails after partial work | Recover the same assignment, preserving explicit model choices and partial work; prove old/conflicting writers stopped before replacement. |
| ACP child cancellation is unproved | Disclose the limitation; keep children supervised or read-only rather than assume parent cancellation covers them. |
| Worker needs another repository | Return scope/workspace expansion to the coordinator before writing. |

Repository review and human merge gates remain required. This packet claims
source and packaging checks only, not installation, deployment, or runtime
lifecycle qualification.

## Conversation-separation follow-up

The same assignment now also distinguishes conversation containers from execution
ownership and preserves explicitly assigned sidebar sessions. See
[follow-up proof](FOLLOWUP.md) for its source checkpoint and validation. The
source/proof commits and test results above describe the initial rewrite.
