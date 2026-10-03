# PR113 artifact redaction

Accepted official comprehensive Spark P3 on request req-20261002T024648Z-327928717642, epoch 2. The finding is disclosure in committed run artifacts: an internal SSH host and account, plus physical home and local-state paths. Parent accepts this as required artifact hygiene. It is not a source defect. The accepted P2 model and High-effort repair is unchanged.

Source head `14c840c079dce5f4d32b41851071f9ddd8af0f8e`. Base `f04b0568424fba1c62db436081a037f1a0c8963d`.

## Substitutions

Tracked files introduced by this PR under `runs/grok-effort-repair-runs/20261001` and `runs/grok-model-selection-runs/20261001` were sanitized in place.

- Operator home prefixes became `<USER_HOME>`.
- The review-host home prefix was absent from this tracked scope, so no `<REVIEW_HOME>` substitution was required.
- The SSH account field, probe account transcript, and account prose became `<REVIEW_ACCOUNT>`.
- The operator origin host became `<USER_HOST>`.
- The concrete LAN host became the existing alias `spark-2`.
- Alias `spark-2`, port, identitiesonly, identity-file count, probe exit code, model selections, High effort, deadlines, test results, commit IDs, recorded hashes, and failure results stayed in place.
- Skill and tool names were not rewritten.

## Semantic preservation

Each modified public file differs from its private original only by those substitutions. Affected JSON documents parse: 12. Embedded JSON documents parse: 1. Keys, numbers, booleans, and unsubstituted strings are unchanged, including nested JSON. Hex tokens of 7–64 digits and failure wording are unchanged. The route proof still records alias `spark-2`, target `Spark-2`, port 22, identitiesonly `no`, one identity file, and probe exit code 0.

## Local private raw

Byte-for-byte originals, before/after sha256, and head blob identity are untracked at `runs/grok-effort-repair-runs/20261003/private-raw/` plus `runs/grok-effort-repair-runs/20261003/redaction-manifest.json`. The SSH preflight account and host remain only in that local raw copy. Those files must stay untracked. Untracked files already present under `runs/grok-effort-repair-runs/20261001` were not edited; do not stage them.

## Verification

Bounded scan of 108 tracked files in the two run directories found no concrete internal IP, account, physical home prefix, or operator origin host. All 594 tracked files outside this run scope are hash-equal to head `14c840c079dce5f4d32b41851071f9ddd8af0f8e`, including product source (56), tests (66), and docs (135). No source, test, plugin, provider, commit, or merge action was taken.

## Files

- `runs/grok-effort-repair-runs/20261001/PROOF.md`
- `runs/grok-effort-repair-runs/20261001/STATE.md`
- `runs/grok-effort-repair-runs/20261001/coherent-implementation-result.json`
- `runs/grok-effort-repair-runs/20261001/events.jsonl`
- `runs/grok-effort-repair-runs/20261001/green-all-grok-coherent/cwd.txt`
- `runs/grok-effort-repair-runs/20261001/green-all-grok/argv.json`
- `runs/grok-effort-repair-runs/20261001/green-all-grok/cwd.txt`
- `runs/grok-effort-repair-runs/20261001/green-regressions-coherent/cwd.txt`
- `runs/grok-effort-repair-runs/20261001/green-regressions/cwd.txt`
- `runs/grok-effort-repair-runs/20261001/implementation-receipt.json`
- `runs/grok-effort-repair-runs/20261001/implementation-result.json`
- `runs/grok-effort-repair-runs/20261001/node_modules-symlink-target.txt`
- `runs/grok-effort-repair-runs/20261001/old-head-review-status.json`
- `runs/grok-effort-repair-runs/20261001/parent-model-invariant-red.stdout.txt`
- `runs/grok-effort-repair-runs/20261001/parent-post-main-shared-deps.json`
- `runs/grok-effort-repair-runs/20261001/parent-post-main-shared-deps.stdout.txt`
- `runs/grok-effort-repair-runs/20261001/parent-post-main-shared.stdout.txt`
- `runs/grok-effort-repair-runs/20261001/parent-review-route.json`
- `runs/grok-effort-repair-runs/20261001/readiness.json`
- `runs/grok-effort-repair-runs/20261001/red-f929a25/cwd.txt`
- `runs/grok-effort-repair-runs/20261001/red-f929a25/stdout.txt`
- `runs/grok-effort-repair-runs/20261001/regressions-tmpdir-import-fail/cwd.txt`
- `runs/grok-effort-repair-runs/20261001/regressions-tmpdir-import-fail/stdout.txt`
- `runs/grok-model-selection-runs/20261001/PROOF.md`
- `runs/grok-model-selection-runs/20261001/STATE.md`
- `runs/grok-model-selection-runs/20261001/grok-tests.log`
- `runs/grok-model-selection-runs/20261001/implementation-receipt.json`
- `runs/grok-model-selection-runs/20261001/implementation-result.json`
- `runs/grok-model-selection-runs/20261001/packaging-tests.log`
- `runs/grok-model-selection-runs/20261001/parent-test-summary.json`

## Encoded payload follow-up

One remaining `session.runtimeSessionName` `acpx:v2` payload still decoded to a physical home `cwd` after the accepted plaintext redaction. That encoded `cwd` was rewritten to `<USER_HOME>` so it matches adjacent `session.cwd`. Native IDs and other decoded fields are unchanged. No other tracked scoped `acpx:v2` string decoded to a physical home prefix.
