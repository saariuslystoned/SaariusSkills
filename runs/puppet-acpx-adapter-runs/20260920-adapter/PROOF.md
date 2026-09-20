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
- draft PR: https://github.com/saariuslystoned/SaariusSkills/pull/56
- implementation commit: `23eb2fd3b3e53dafcc0cad2825ccb9ccf31ba37a`
- dependency refresh commit: `88d3ba63b7e4bcdc6a9db040e3829bac88ff97ee`

## Dependency

- Upstream draft PR: https://github.com/openclaw/acpx/pull/648
- Exact repaired head: `02c03c7abeee0324a71e2114e6b1b4cf7b0785ff`
- Integrity: `9f5d189cf0adf8151109b36814b39293a5f8b82bee38668724635f6fed652b66`
- Artifact status: reviewed repaired draft only; synthetic development
  evidence; not merged, released, or production qualification evidence.
- Exact upstream delta from the original pin: test-only hardening in
  `test/runtime-capabilities.test.ts` for reconnect/load-session support,
  absolute fixture paths, disabled/enabled control reconnect cases, and probe
  path assertions. No runtime implementation file changed in that delta.
- Historical pre-repair identity remains recorded in `events.jsonl`.

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
