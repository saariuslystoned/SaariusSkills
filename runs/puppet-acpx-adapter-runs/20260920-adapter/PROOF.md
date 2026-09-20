# Puppet acpx adapter proof

## Boundary

Disabled synthetic-only Puppet adapter for one named local Cursor transport
(`cursor-acp`). Puppet authority identity is preserved; ordinary leases are
not admitted. One isolated state root; exact workspace/model/session
identity; transcript-blind durable evidence; controller acceptance distinct
from worker completion; independently observed halt. Duplicate ownership
rejected. Ordinary launch remains unavailable.

## Worktree

- worktree: `/Users/bobbybones/.codex/worktrees/1b4d/SaariusSkills`
- branch: `codex/puppet-acpx-adapter-20260920`
- draft PR pending publication

## Dependency

- Upstream draft PR: https://github.com/openclaw/acpx/pull/648
- Exact head: `2b7627a6b91b4c94c8a83ad0cc4863f72e8f14de`
- Integrity: `cad05ead9a4cae01e0cc612e43a16ea647323a69d14c172700c790c333e4b0fd`
- Artifact status: reviewed draft only; synthetic development evidence; not
  merged, released, or production qualification evidence.

## Implementation

Public-runtime allowlist only (`cwd`, `sessionStore`, `agentRegistry`,
`fs=false`, `terminal=false`). Approve-all and MCP broker policy are
rejected. Adapter lives at `skills/puppet/scripts/cursor_acpx.py` so
`adapter_implementation_fingerprint()` is unchanged. Bridge disabled surface
is `bridge/cursor-acp/puppet-adapter.mjs`; `broker.mjs` / `server.mjs` are
untouched.

## Checks

| Check | Result |
| --- | --- |
| `python3 -m unittest tests/test_puppet_cursor_acpx.py -v` | 10 passed |
| `npm run check` in `bridge/cursor-acp` | 23 passed; syntax checks passed |
| `python3 -m unittest discover -s tests -q` | 1281 tests; one unrelated existing `test_doctor_output_cap_timeout_and_source_drift_fail_closed` failure |
| isolated rerun of that unrelated test | same failure in 3/3 attempts |
| repository changes touching the failed test path | none |
| repo-local autoreview | unavailable; no repo-local surface exists |

The full-suite failure is in unchanged `tests/test_puppet_codex_launch.py` /
`skills/puppet/scripts/puppet_lib/codex_launch.py`: the test expects a child
PID file after a 250ms process-group timeout, but the file is absent. It is
not in the changed-file set and the adapter-focused suites pass. No live
Cursor, provider, or qualification action occurred.
