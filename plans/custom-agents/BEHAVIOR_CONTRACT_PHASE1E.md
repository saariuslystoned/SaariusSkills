# Behavior contract: discovery-gated custom-agent selection

Version: `2026-07-26.phase1e`

## Purpose

Qualify a deterministic guard around ordinary AGY custom-agent selection
without weakening or reinterpreting the Phase 1D result.

Phase 1D remains authoritative:

- four of four exact primary identities passed after profile quarantine;
- primary selection with `subagent: false` passed;
- malformed, duplicate/rename, flag, and removal behavior was explicit;
- direct unknown-name selection with one unrelated catalog profile violated
  the strict fail-closed contract.

The raw `agy --agent <name>` surface therefore remains unqualified for
unvalidated names. This contract qualifies only the guarded controller surface.

## Guarded surface

The controller command is:

```text
phase1_harness.py guarded-run-print ...
```

Before any model launch, it must:

1. execute bounded read-only
   `agy --add-dir <workspace> agents`;
2. count exact token occurrences of the requested runtime name in discovery
   stdout;
3. retain only byte counts, line count, SHA-256 digests, process status,
   timing, and the exact-name count;
4. admit only process exit `0`, no timeout, and exactly one occurrence;
5. return exit `2`, `model_launch_started: false`, and no runtime record for
   zero or multiple occurrences.

The guard never prints or retains the raw catalog. An unrelated name,
diagnostic, profile, or account value must not appear in its output.

After admission, the controller uses the unchanged Phase 1D print runner:

- exact challenge-only `--print` argument;
- absolute `--add-dir`;
- fresh process;
- sandboxed `accept-edits`;
- profile exposing only `write_to_file`;
- whole-profile quarantine before a qualifying result mutation;
- exact result verification and scoped postflight;
- raw stdout, stderr, and CLI log digest-then-unlink.

## E1 — Absent name with unrelated profile

Create a disposable catalog containing one valid unrelated profile. Request a
fresh absent name through `guarded-run-print`.

Expected:

- discovery exit `0`;
- exact-name occurrence count `0`;
- gate reason `agent_absent`;
- guarded command exit `2`;
- `model_launch_started: false`;
- result remains zero bytes;
- the profile and workspace remain unchanged.

The underlying Phase 1D direct-launch fallback is not rerun and is not hidden.

## E2 — Duplicate declared name

Create two workspace paths containing byte-identical profiles with the same
declared name. Request that name through `guarded-run-print`.

Expected:

- discovery exit `0`;
- exact-name occurrence count `2`;
- gate reason `agent_ambiguous`;
- guarded command exit `2`;
- `model_launch_started: false`;
- result remains zero bytes;
- both profile hashes remain exact.

## E3 — Exactly one positive identity

Create one exact runtime profile with `mainAgent: true` and `subagent: false`.
Request it through `guarded-run-print` using the unchanged CLI/model tuple.

Expected:

- discovery exit `0`;
- exact-name occurrence count `1`;
- gate reason `exactly_one`;
- `model_launch_started: true`;
- the nested Phase 1D runtime report exits `0` without timeout;
- the result changes after quarantine and exactly matches the controller-held
  agent, challenge, marker, schema, and status;
- scoped postflight passes.

This is the only admitted Phase 1E model session.

## E4 — Evidence composition

The Phase 1E fingerprint must preserve the Phase 1D CLI binary, host, model,
effort, sandbox, prompt transport, four definition hashes, isolation, and
external-oracle tuple. It additionally binds:

- the new exact source head and harness SHA-256;
- `exact-name-occurrence-count-before-model`;
- `digest-in-memory-not-retained` discovery output handling;
- committed Phase 1D proof commit
  `b2e7dbab204408b7933dcc66df9e74cefedd9063`.

The one guarded positive proves the additive preflight delegates to the
unchanged runtime oracle. The prior four-role proof remains the evidence for
role diversity; it is not silently relabeled as a guarded run.

## Pass and gate

This guard contract passes only when E1 and E2 reject before model launch, E3
passes the complete external identity oracle, E4 binds the unchanged
capability tuple, all repository tests pass, all owned state is exact and
clean, and no foreign state is touched.

A pass qualifies guarded ordinary custom-agent selection and may admit a
separate 2x2 route. It does not qualify raw unknown-name selection, nested
fan-out, joins, retries, timeouts, 4x4 reliability, Puppet transport, or any
product-specific use case.

## Budget and safety

- remaining issue-level Phase 1 model sessions: `1`;
- Phase 1E model sessions: at most `1`;
- guarded model launches: at most `1`;
- discovery invocations: at most `8`;
- discovery timeout: `10 seconds`;
- model timeout: `90 seconds`;
- no merge, deploy, publish, global install, auth/settings/permission change,
  customer traffic, device action, transcript/pane read, or foreign
  session/process contact.

Stop on any rejected guard that starts a model, any admitted guard whose exact
identity fails, unexpected write, timeout, raw retention, cleanup ambiguity,
quota failure, or foreign contact.
