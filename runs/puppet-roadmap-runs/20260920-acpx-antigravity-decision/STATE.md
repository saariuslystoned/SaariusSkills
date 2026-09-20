# Antigravity route decision state

Status: candidate contract implemented and verified; ACP remains non-qualifying.

## Ownership

- Repository: `saariuslystoned/SaariusSkills`
- Worktree: `/Users/bobbybones/.codex/worktrees/d90a/SaariusSkills`
- Branch: `codex/acpx-antigravity-decision`
- Base: `origin/main` at `72934effc7db18be0c95a773cd841dbd7b52283e`
- Proof root: `/Users/bobbybones/.codex/worktrees/d90a/SaariusSkills/runs/puppet-roadmap-runs/20260920-acpx-antigravity-decision`

## Scope

Compare native `agy --print` stream-json with Google's official
`antigravity-acp` runtime as exposed by `acpx` v0.17.1. Produce a bounded
recommendation, route plan, and proof ledger. The pinned runtime was installed
only in a temporary isolated root after explicit authorization; no account,
billing, merge, issue mutation, remote comment, or broad transport change was
authorized.

## Current decision

Use staged coexistence: keep native `agy-print` as Puppet's current/default
Antigravity route; document and later qualify a distinct `antigravity-acp`
candidate. Do not alias the official ACP runtime to generic `acp` or replace
native AGY based on protocol standardization alone.

## Gates

- Cursor ACP readiness: route present, exact executable present, authentication
  required; setup check returned `MCP_READY`. No worker turn was sent.
- PR #49: verified open and unmerged at exact head
  `1e795546c29bf1eba3ed5b6b6e276c8b7c18c8cc`; Ubuntu/macOS checks green.
- AI Ultra attribution: undocumented for this separate ACP runtime and not
  claimed. A Bobby-authorized, account-visible check remains required.

## Implementation checkpoint

- Added `skills/puppet/scripts/puppet_lib/antigravity_acp.py` as a standalone
  source contract; transport dispatch and native `agy-print` are unchanged.
- Added `tests/test_puppet_antigravity_acp.py` with fail-closed auth/model/
  question/body-free metadata coverage.
- Focused verification: 52 tests passed; `py_compile` and `git diff --check`
  passed.
- Isolated ACP session created and one authorized smoke request completed with
  exit code 0 on `gemini-3.8-flash-high`; response body was discarded.
