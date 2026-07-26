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

Phase 1B also failed its pre-model gate: AGY 1.1.7 discovered all four v2
agents but did not list the workspace observer plugin. Its zero-model proof is
preserved at
`proof/custom-agents/agy-1.1.7-aiworker01-phase1b-20260726/`.

Phase 1C removes hooks from the identity oracle. It uses one-time runtime agent
names and role markers, stdin print mode, immediate profile quarantine,
write-only agent tools, a disposable sandbox, complete scoped filesystem
postflight, process exit, and digest-then-unlink raw-output handling.

Phase 1C's boundary passed its launch calibration, but AGY rejected a bare
`--print` flag before model use. Phase 1D preserves the oracle and changes only
the bounded prompt transport to the officially documented
`-p "<challenge-only prompt>"` value.

Phase 1D proved four of four exact primary identities after profile quarantine,
including a profile with `subagent: false`. Its strict unknown-name control
failed when a catalog containing one unrelated profile produced a structured
but nonqualifying result for an absent requested name. An empty-catalog
companion stayed unchanged. Phase 2 therefore remains gated on a
discovery-first exact-count selection guard; the CLI fallback is preserved as
an upstream compatibility finding rather than normalized away.

Phase 1E qualified that guard as a distinct controller surface. Live absent and
duplicate controls were rejected before model launch; exactly one
`subagent: false` profile was admitted and passed the unchanged identity
oracle. This admits a separately bounded 2x2 route while leaving raw direct
unknown-name selection unqualified.

Files:

- `ROUTE_PHASE_0_1.md` — ownership, host, launcher, proof path, budget, gates,
  and stop condition;
- `BEHAVIOR_CONTRACT.md` — source-blind observable clauses and anti-cheat
  probes;
- `BEHAVIOR_CONTRACT_PHASE1B.md` — CLI workspace-plugin observer correction;
- `ROUTE_PHASE_1B.md` — bounded retry route and remaining budget;
- `BEHAVIOR_CONTRACT_PHASE1C.md` — external filesystem identity oracle;
- `ROUTE_PHASE_1C.md` — bounded C1–C8 route without hook dependence;
- `BEHAVIOR_CONTRACT_PHASE1D.md` — documented print-argument correction;
- `ROUTE_PHASE_1D.md` — C1–C8 execution route on the corrected transport;
- `BEHAVIOR_CONTRACT_PHASE1E.md` — exact-count pre-model selection guard;
- `ROUTE_PHASE_1E.md` — bounded no-model negatives and one positive guard
  route;
- `capability-fingerprint.schema.json` — exact runtime tuple contract;
- `behavior-report.schema.json` — machine-readable verdict contract;
- `scripts/phase1_harness.py` — create-only fixture materializer, privacy-safe
  hook observer, inventory filter, CLI-log filter, and bounded result verifier.

The committed fixture source is
`fixtures/custom-agents/phase1/`. It is inert in this repository. Runtime
materialization creates `.agents/agents/...` only inside an exact disposable
workspace; global custom-agent directories are never written.
