# SaariusSkills issue #15 Phase 5B corrected Pixel-use comparison

schema: smoky.swarm.route_terminal_proof.v1
result: completed
route_id: route_20260726_024224_71847_saariusskills-custom-agent-pixel-use-ab-corrected
repo: saariuslystoned/SaariusSkills
base_sha: 23f3b0c8062c7cffaadabee3154477285ccac0f3
source_head_sha: f68771eb63c44db9b21af9cfc95a27da32ec363e
run_id: saariusskills-issue15-phase5b-pixel-use-ab-20260726

## Result

The corrected comparison is valid and complete:

| Arm | Complete exact | Policy exact | Friction exact | Mean duration | Declared sessions |
| --- | ---: | ---: | ---: | ---: | ---: |
| single | 1/2 | 2/2 | 1/2 | 10.0935s | 2 |
| custom width two | 1/2 | 2/2 | 1/2 | 16.4135s | 6 |

Comparative accuracy is tied. Both B rounds made the same exact friction
mistake: they set beta `target_missing`'s `human_intervention_count` to `0`
instead of `1`, then ranked alpha before beta. All other policy and friction
values were exact.

The custom arm demonstrated reliable mechanics:

- exact parent discovery `1` in both rounds;
- four exact child artifacts before profile quarantine;
- both joins stayed empty until OS-gate release;
- both joins were written after release;
- join-to-child values and hidden identity-marker pairs were exact `2 / 2`;
- both processes exited `0` without timeout;
- both exact scoped postflights passed.

Those mechanics did not improve product answer quality. Custom used three
times the declared sessions, took `1.626x` total wall time, and was slower in
both paired rounds.

## Correction integrity

The predecessor attempt remains committed at
`4f823d794ada77173b1e16c6a9206a46021317f6`. This replay changed only the
missing policy-envelope wording and its contract/tests/docs:

- corrected policy packet SHA-256:
  `30eb87e927875b4a606a76a882b8fca070b9bfa883c84972a738004ab08cf79e`;
- unchanged canonical policy answer SHA-256:
  `4ac5522583c2e6047c21acb6618dde2d8ee81b8fd5fbc3c68fe049c2453a7551`;
- unchanged friction packet SHA-256:
  `185354a5c64ae236b9d8deaab82f3a3320ac821609bcead3b0a2b252f36ae0ba`;
- unchanged canonical friction answer SHA-256:
  `c4b3eb0f4c387c97775df27807214816ef315e1343574e9723c905abcff17148`.

No answer was exposed, normalized, or repaired after launch.

## Product and packaging disposition

- ordinary exact-count guarded primary selection: keep as qualified;
- ordinary width-two functional fan-out/join: keep as qualified reference;
- Pixel-use-specific custom-agent skill: reject;
- reusable custom-agent orchestration plugin: reject;
- width-four joining: remains failed;
- Teamwork Preview dependency: not required;
- Puppet/Herdr: keep independent as an optional future transport replay, not
  capability ownership.

The product clauses B3/B4 failed because neither arm reached `2 / 2`.
Completing the comparison does not qualify product packaging.

## Scope boundary

Pixel-use remained clean at
`6474159cc15eafbd2abe602e13017a2754768ce9`; no source, device, account, or
runtime state was touched. Teamwork Preview, Puppet, Herdr, browser/device
surfaces, and PR #6 were untouched.

## Evidence

- `capability-fingerprint.json`
- `behavior-report.json`
- `comparison-summary.json`
- `runtime-summary.json`
- `cleanup.json`
- `STATE.md`
- `events.jsonl`

The executed corrected `product_probe_harness.py` SHA-256 was
`ae07e075ad85252425492b211f21e7d5362af540ad92d1fe5e590a7b2cbc34de`.
It is the exact copy committed at source head
`f68771eb63c44db9b21af9cfc95a27da32ec363e`.

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

Five exact remote roots were inventoried as `19` files, `26` directories,
`0` symlinks, `0` special files, and `140716` bytes. The two exact custom
`.issue15` parent directories were restored from their intentional read-only
postflight mode, then all five disposable roots were removed and verified
absent.

The deletion is not recoverable; committed summaries and result hashes retain
the bounded evidence.
