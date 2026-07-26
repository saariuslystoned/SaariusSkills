# Custom-agent qualification

This directory owns the product-independent proof contract for
[issue #15](https://github.com/saariuslystoned/SaariusSkills/issues/15).

PR #6 remains historical research at
`baea84b2bb0d21ff749ce65d077a76cc76f2e1de`. Nothing here imports its Puppet
package or treats token relay as current qualification.

The first admitted slice was Phase 0/1 only:

1. freeze one exact capability fingerprint and route packet;
2. materialize workspace-local custom-agent fixtures into disposable
   workspaces;
3. prove discovery and exact identity selection with source-blind,
   transcript-free evidence;
4. exercise negative selection and removal behavior;
5. commit the behavior report and stop before 2x2 fan-out.

Attempt 01 is preserved at
`proof/custom-agents/agy-1.1.7-aiworker01-phase1-20260726/`. It proved
explicit-workspace discovery and one bounded identity artifact, then failed
closed because a naked workspace `.agents/hooks.json` produced no events.

Phase 1B is a new contract, not a reinterpretation of that result. It packages
the observer as the CLI's documented plugin shape under the disposable
workspace, uses an absolute environment-provided harness path, and assigns new
v2 agent identities. Plugin discovery must pass before another model session.

Files:

- `ROUTE_PHASE_0_1.md` — ownership, host, launcher, proof path, budget, gates,
  and stop condition;
- `BEHAVIOR_CONTRACT.md` — source-blind observable clauses and anti-cheat
  probes;
- `BEHAVIOR_CONTRACT_PHASE1B.md` — CLI workspace-plugin observer correction;
- `ROUTE_PHASE_1B.md` — bounded retry route and remaining budget;
- `capability-fingerprint.schema.json` — exact runtime tuple contract;
- `behavior-report.schema.json` — machine-readable verdict contract;
- `scripts/phase1_harness.py` — create-only fixture materializer, privacy-safe
  hook observer, inventory filter, CLI-log filter, and bounded result verifier.

The committed fixture source is
`fixtures/custom-agents/phase1/`. It is inert in this repository. Runtime
materialization creates `.agents/agents/...` only inside an exact disposable
workspace; global custom-agent directories are never written.
