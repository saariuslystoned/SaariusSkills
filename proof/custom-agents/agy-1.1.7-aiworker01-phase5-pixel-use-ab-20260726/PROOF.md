# SaariusSkills issue #15 Phase 5 Pixel-use comparison

schema: smoky.swarm.route_terminal_proof.v1
result: failed
route_id: route_20260726_023232_69381_saariusskills-custom-agent-pixel-use-ab
repo: saariuslystoned/SaariusSkills
base_sha: 23f3b0c8062c7cffaadabee3154477285ccac0f3
source_head_sha: 16a8543bd773a15e4e9f32a8f3072295c2b01e0e
run_id: saariusskills-issue15-phase5-pixel-use-ab-20260726

## Result

The first Pixel-use comparison is preserved as inconclusive because its exact
policy oracle required an undisclosed output envelope.

All four sessions passed their execution boundaries:

- exact custom-agent discovery count `1`;
- fresh disposable workspaces and byte-identical profiles within each arm;
- single results written after profile quarantine;
- custom branch results written before quarantine;
- custom joins empty until OS-gate release, then written afterward;
- both custom joins exactly preserved child values and identity-marker pairs;
- process exit `0`, no timeout, exact scoped postflight, and no foreign state;
- discovery and raw stdout/stderr/log content digested then unlinked unread.

Every round also produced all six correct policy decisions. The policy packet
said to return every id in order with `decision` and `receipt_type`, but did
not say that the outer object had to be named `cases`. The verifier silently
required that key. Models used three semantically equivalent forms:
`items`, `decisions`, and an id-keyed object.

No post-hoc normalization was applied and no score was repaired. P1/P2 fail,
so complete-result rates cannot fairly choose a winning arm.

## Valid product subset

The friction contract did specify its exact outer keys and remains usable:

- single: `1 / 2` exact rounds;
- custom width two: `0 / 2` exact rounds;
- custom join fidelity: `2 / 2`;
- mean runtime: single `11.4345s`, custom `19.329s`;
- declared sessions: single `2`, custom at most `6`.

This small valid subset does not show a product-quality benefit from
decomposition. It is evidence against immediate product-specific packaging,
not a universal rejection of the already-qualified width-two primitive.

## Scope boundary

Pixel-use remained clean at
`6474159cc15eafbd2abe602e13017a2754768ce9`; no source, device, account, or
runtime state was touched. Teamwork Preview, Puppet, and Herdr were not used.
PR #6 remains historical research at
`baea84b2bb0d21ff749ce65d077a76cc76f2e1de`.

This attempt cannot repair Phase 3's failed width-four join. It also cannot
admit a reusable plugin or product-specific skill.

## Evidence

- `capability-fingerprint.json`
- `behavior-report.json`
- `comparison-summary.json`
- `runtime-summary.json`
- `cleanup.json`
- `STATE.md`
- `events.jsonl`

The executed `product_probe_harness.py` SHA-256 was
`b313e798ba00fc0bc30657fb980c702532c9668a57724eb7fa6f4b8f900c4146`.
It is the exact copy committed at source head
`16a8543bd773a15e4e9f32a8f3072295c2b01e0e`.

## Verification and budget

The frozen source passed:

```text
python3 -m py_compile plans/custom-agents/scripts/product_probe_harness.py
python3 -m unittest tests.test_custom_agent_product_probe_harness -v
python3 -m unittest discover -s tests -v
```

Result: `82` repository tests passed.

- top-level CLI processes: `4 / 4`;
- declared nested child branches: `4 / 4`;
- total declared sessions: `8 / 8`;
- unexpected timeouts: `0`;
- raw content retained: `false`;
- foreign state touched: `false`.

## Cleanup

Five exact remote roots were inventoried as `21` files, `27` directories,
`0` symlinks, `0` special files, and `236171` bytes. The initial removal
deleted the controller and both single roots, then met the intentional
read-only parent-directory fence in the two custom roots. Only those two exact
owned `.issue15` directories were restored to owner-write mode; both residual
roots were then removed. All five roots were verified absent.

The deletion is not recoverable; committed summaries and result hashes retain
the bounded evidence.

## Disposition

Preserve this attempt as an oracle-design counterexample. A corrected replay
is warranted only under a new frozen source and separate route that explicitly
specifies `policy: {"cases": [...]}` without exposing answer values. Until
then, the product comparison is inconclusive and packaging remains rejected.
