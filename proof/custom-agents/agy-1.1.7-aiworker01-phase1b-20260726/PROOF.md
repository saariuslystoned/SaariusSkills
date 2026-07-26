# SaariusSkills issue #15 Phase 1B proof

schema: smoky.swarm.route_terminal_proof.v1
result: failed
route_id: route_20260726_005308_42966_saariusskills-custom-agent-qualification
repo: saariuslystoned/SaariusSkills
base_sha: 23f3b0c8062c7cffaadabee3154477285ccac0f3
source_head_sha: c1f14445c51311309440490ea74ab29c6df42d4a
run_id: saariusskills-issue15-phase1b-20260726

## Result

- The corrected fixture set materialized seven exact files.
- All four v2 custom agents passed filtered discovery with the absolute
  workspace bound through `--add-dir`.
- `saarius-issue15-observer` did not appear in filtered
  `agy --add-dir <workspace> plugin list` output.
- The contract's pre-model gate stopped the route. Phase 1B spent zero model
  sessions and zero model invocations.
- Postflight hashes matched. Both exact-owned disposable Phase 1B roots were
  deleted; they are reproducible from the frozen fixture source. No foreign
  state was touched.

## Evidence

- `capability-fingerprint.json`
- `materialization.json`
- `agent-discovery.json`
- `plugin-discovery.json`
- `fixture-postflight.json`
- `behavior-report.json`

## Commands

- create-only Phase 1B materialization: exit `0`
- filtered `agy --add-dir <workspace> agents`: exit `0`
- filtered `agy --add-dir <workspace> plugin list`: exit `2`
- exact-owned postflight and cleanup: exit `0`

## Finding

On this AGY 1.1.7 tuple, workspace-local custom agents are discoverable while
the workspace observer plugin is not visible through the CLI plugin listing.
Under the no-global-install/no-settings-mutation constraint, plugin hooks
cannot be the qualification oracle.

## Next route

Use an external OS/filesystem oracle with fresh runtime-only identity nonces,
read-only fixtures, an exact pre-created result target, full scoped
pre/post hashes, sandboxing, and no hook dependency. Preserve both hook
failures as compatibility findings. Phase 2 remains gated.

