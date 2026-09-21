# Proof — host-owned VM ACP wrapper plan

## Scope

Research and documentation only in the isolated SaariusSkills worktree. No
source implementation, remote VM/SSH call, installation, credential delivery,
browser/desktop control, account change, provider job, merge, or upstream
publication was performed.

## Repository checks

- Worktree: `/Users/bobbybones/.codex/worktrees/ee24/SaariusSkills`.
- Branch: `codex/puppet-vm-wrapper-plan-20260921`.
- Fresh `origin/main`: `49a4640` (no divergence at branch creation).
- No repository-local `AGENTS.md` or `REPO_HYGIENE.md`; provided global swarm
  constraints were applied.
- Existing issue/PR search found roadmap issue #11 and open PRs #62–#64; no
  duplicate VM tracker was opened.

## Evidence read

- Parent `STATE.md`, `MORNING_HANDOFF.md`, and `upstream692-adjudication.json`
  under the parent-owned overnight run. Parent records upstream #692 merged at
  `c1bdc539` and keeps the current candidate pin frozen.
- Historical VM recipe and authorization notes under
  `runs/puppet-upstream-plan-20260920/`.
- Existing Parallels owner task `01a0c06b-de79-7a03-887b-a1ec04887911` and its
  value-free blocked receipt at
  `.../runs/parallels-coding-agent-proof-runs/20260920T200509Z-4717/`.
- Primary maintainer comment on acpx #637:
  <https://github.com/openclaw/acpx/issues/637#issuecomment-5751590763>.
- Current official acpx source/docs at `c1bdc539`; current Crabbox main at
  `46fb70e`; official OpenClaw main at `fbef0ba`; Cua main at `9bbfa7d`.

## Acceptance result

`PLAN_READY`: the authored plan names ownership boundaries, admission order,
one-VM proof identities, reconnect/cancel/timeout/artifact failure handling,
non-secret credential architecture, reusable primitives, and host-specific
work. It distinguishes observed VM transport/readiness evidence from proposed
future proof and does not claim VM qualification or subscription entitlement.

Follow-up portability repair: removed the owner checkout path from the public
plan while retaining exact machine-specific selectors only in this private run
packet. `python3 -m unittest tests.test_puppet_packaging -v` passed all 9 tests,
including `test_public_puppet_plans_do_not_publish_absolute_macos_home_paths`.
