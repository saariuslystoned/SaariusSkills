# SaariusSkills issue #15 Phase 1D proof

schema: smoky.swarm.route_terminal_proof.v1
result: failed
route_id: route_20260726_010611_46254_saariusskills-custom-agent-qualification
repo: saariuslystoned/SaariusSkills
base_sha: 23f3b0c8062c7cffaadabee3154477285ccac0f3
source_head_sha: 3ed1313841227216129df0c41e2beb9d4c9341a9
run_id: saariusskills-issue15-phase1d-20260726

## Result

Phase 1D proved the ordinary custom-agent happy path and then failed its
strict unknown-name control:

- all four random workspace-local profiles passed filtered discovery;
- all four produced their exact controller-held identity after the complete
  profile tree had been quarantined outside the workspace;
- every positive AGY process exited `0`, without timeout;
- every positive postflight found only the one result and one unchanged
  quarantined profile;
- the proof role had `subagent: false` and still passed primary discovery and
  exact primary execution;
- malformed frontmatter and `mainAgent: false` were excluded before model use;
- duplicate declarations were repeatably listed twice and therefore rejected
  as ambiguous;
- renaming the definition directory preserved the declared frontmatter name;
- a quarantined/removed profile disappeared from workspace discovery.

C4 failed under the frozen strict contract. An unknown name was absent from
filtered discovery, but when one unrelated profile existed in the catalog the
bounded AGY process wrote a structured result after quarantine. Exact
verification showed that it matched neither the requested identity nor the
decoy identity. An empty-catalog companion control left the result at zero
bytes. This is not evidence of identity confusion, but it is a nonqualifying
fallback rather than the required fail-closed rejection.

Phase 2 was not admitted.

## What this proves about Teamwork Preview

Ordinary custom-agent discovery and exact primary selection do not require
Teamwork Preview. The strongest direct control is `pos-proof-04`: the selected
profile explicitly set `subagent: false`, yet it was discovered and executed
as the primary agent with a hidden role marker and exact post-quarantine
identity result.

This does not yet prove nested fan-out, joins, retries, or 2x2/4x4 reliability.
Those remain gated behind a safe exact-selection guard.

## Evidence

- `capability-fingerprint.json`
- `positive-identities.json`
- `unknown-controls.json`
- `negative-discovery-controls.json`
- `behavior-report.json`

The capability fingerprint binds:

- AGY `1.1.7`;
- binary SHA-256
  `48e37ce7ef2db0e8972b6fed36ce866d4b094c587d377029ba7223565f49aed8`;
- `aiworker-01`, Darwin arm64;
- `gemini-3.6-flash-low`, effort `low`;
- sandboxed `accept-edits`, no permission bypass;
- absolute `--add-dir`, fresh `--print` processes;
- exact harness SHA-256
  `fedacac1e1d8dc5c4a0297466f77cb4b453c2654e5cc03a847160c352572e5cd`.

## Commands and boundaries

- create-only runtime fixture builds: exit `0`;
- exact-name filtered positive discovery: four of four exit `0`;
- four positive bounded print runs: four of four exit `0`;
- four exact positive result verifiers: four of four exit `0`;
- positive scoped postflights: four of four exit `0`;
- malformed primary discovery: exit `2`, expected absent;
- duplicate discovery: two stable exit-`0` runs, two declared-name
  occurrences;
- renamed-path discovery: two stable exit-`0` runs;
- `mainAgent: false` primary discovery: exit `2`, expected absent;
- `subagent: false` primary selection: exit `0`, exact identity passed;
- post-removal discovery: exit `2`, expected absent;
- unknown-with-decoy discovery: exit `2`, then bounded AGY exit `0` with a
  nonqualifying result;
- unknown-with-empty-catalog discovery: exit `2`, then bounded AGY exit `0`
  with an unchanged zero-byte result.

No raw stdout, stderr, CLI log, transcript, pane, credential, auth state, or
foreign session was read or retained. Raw process artifacts were hashed for
byte-level accountability and unlinked. No global custom agent/plugin,
settings, permissions, product source, device, deployment, merge, release, or
customer state was changed.

After this packet was committed locally, the exact Phase 1D controller and
workspace roots were removed from `aiworker-01` and both exact paths were
verified absent. The cleanup covered 22 controlled files totaling 96 KiB. No
prior-run root or foreign state was touched.

PR #6 remains unchanged historical research at
`baea84b2bb0d21ff749ce65d077a76cc76f2e1de`.

## Budget

- Phase 1D fresh AGY sessions: `6 / 7`;
- issue-level fresh model sessions: `7 / 8`, including Attempt 01;
- Phase 1D timeouts: `0`;
- no malformed, duplicate, rename, flag, or removal model session was needed.

## Next route

Prove a discovery-gated exact-selection guard that requires exactly one
workspace-local declaration before starting AGY and rejects absent or duplicate
names without model use. Keep the CLI fallback finding as an upstream
compatibility fact. Only after that guard passes may a fresh exact fingerprint
admit the 2x2 campaign.
