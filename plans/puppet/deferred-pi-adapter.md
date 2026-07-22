# Deferred Pi adapter and automode evidence

Status: deferred design evidence; not part of the five-harness v0.1 campaign

Pi is a useful future Puppet harness because its native RPC/JSONL mode provides
an outer supervision boundary. `pi-unified-exec` is also a useful reference for
long-running shell children inside a Pi session. Neither component is approved
as Puppet authority or as a current dependency.

```text
Puppet -- Pi RPC/JSONL --> Pi agent
                              |
                              +-- unified-exec --> shell/PTY children
```

## Reusable evidence

The following `pi-unified-exec` patterns should inform a future Pi adapter and
the separately deferred automode design:

- persistent `exec_command` / `write_stdin`-style child sessions;
- bounded polling and explicit interactive control bytes;
- exactly-once `on_exit: wake` delivery guarded by observation leases;
- explicit kill-failure reporting and shutdown cleanup;
- bounded ownership through LRU eviction and completion tombstones; and
- cross-platform behavioral tests.

These are design inputs, not qualifications. Autonomous wake must default off
until Puppet can prove ownership, bounded observation, replay, and
controller-only continuation decisions.

## Why upstream cannot be Puppet authority unchanged

- Session identifiers are numeric and memory-only. They are not bound to an
  exact Puppet lease, PID birth identity, executable identity, or durable run.
- Every stdout/stderr byte is persisted under `/tmp` without automatic
  removal. Puppet prohibits transcript and instruction-body persistence.
- Commands are shell strings with inherited environment rather than closed
  argv plus an explicitly admitted environment.
- Children terminate with Pi and have no durable restart/recovery contract.
- The package is not a permission or operating-system sandbox boundary.
- Upstream community maintenance has stopped and the maintainer recommends a
  fork rather than new reliance on the package.
- The optional PTY dependency downloads native prebuilds whose bytes are not
  covered by the package digest alone.

## Future adoption gates

A future Pi lane may use Pi's native RPC mode for Puppet-to-Pi supervision and
may evaluate a project-local fork of `pi-unified-exec` for Pi-to-child process
control only after all of these gates pass:

1. Remove unconditional `/tmp` transcript logging. Keep only bounded,
   body-free controller evidence.
2. Bind every session to exact Puppet run/lease, PID birth, executable/runtime,
   argv, cwd, and environment identities.
3. Replace shell command strings and inherited environment with closed argv
   and a typed allowlisted environment.
4. Add durable restart recovery, replay protection, and completion tombstones.
5. Keep wake/continuation disabled by default and require an admitted policy
   plus exactly-once observation lease before enabling it.
6. Install only project-locally in an isolated Pi lane; never modify a global
   Pi installation as incidental Puppet setup.
7. Pin, hash, and independently verify every native PTY artifact in addition
   to the JavaScript package.
8. Qualify normal launch, follow-up, resume/rejoin, exact halt, no-bleed, and
   rollback against the exact Pi and provider/model tuple.

## Current boundary

Do not add Pi to the AGY, Codex CLI, Claude Code, Cursor Agent, and Grok Build
regular-session matrix. Do not take a direct dependency on upstream
`pi-unified-exec`. Do not enable Pi routing, wake behavior, or command profiles
from this record. Revisit it only in a separately admitted Pi/automode lane.

Primary references:

- Pi RPC mode: <https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md>
- `pi-unified-exec` overview: <https://github.com/iamwrm/pi-unified-exec/blob/main/README.md>
- session store: <https://github.com/iamwrm/pi-unified-exec/blob/main/src/session-store.ts>
- session implementation: <https://github.com/iamwrm/pi-unified-exec/blob/main/src/session.ts>
