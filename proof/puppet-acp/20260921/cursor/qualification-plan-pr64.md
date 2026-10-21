# Cursor qualification plan on accepted PR64

Status: plan persisted before launch; no provider turn is represented by this file.

## Exact inputs

- Owner task: `01a0c01d-9ac8-7552-a0f7-aea711f1cb3d`
- Qualification checkout: `/Users/bobbybones/Developer/worktrees/puppet-cursor-qualification-pr64-20260921`
- Qualification branch: `codex/puppet-cursor-qualification-pr64-20260921`
- Source head/tree: `84a6dad7110ed97722b35ff1d7c102671312ec80` / `c923dfc6fc698d14d2e5c3fcdfdce3f156226b39`
- Accepted source PR: [PR #64](https://github.com/saariuslystoned/SaariusSkills/pull/64), unmerged; no merge is required or permitted for this run.
- Reviewed driver SHA-256: `2292f0f39220b214fa561ff413d162e812b668a8ccdc86013ed1b645c0cb682f`
- Reviewed tests SHA-256: `4e3440bd04e7b3fc9b957faba8656614889d5b785a0c0db9da88d8f953724b56`
- Cursor route: `/Users/bobbybones/.local/bin/cursor-agent acp`
- Selector/current model: `cursor-grok-4.6-high` / `grok-4.6[effort=high,fast=true]`
- ACPx source: `2e05de525dd1ab62e9e74bf02d91e3638920fcf3`; archive SHA-256 `5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614`; runtime/chunk hashes independently verified.

## Allocation and command

- Fresh session: `cursor-proof-v3-live-pr64-20260921`
- One qualification session, one useful prompt, at most `300000ms`; no retry, substitution, paid fallback, second session, or shared install.
- Use the reviewed v3 driver with `--no-continue` so exactly one task prompt is attempted; owner-mediated finish remains required.
- Parent allocation is new for this assignment and is distinct from the consumed historical PR62 session.

## Preflight proof

- Focused driver tests: 10/10 pass in the PR64 checkout.
- `verify_existing_runtime()` passed the archive and all imported runtime/chunk digests; lifecycle scripts remain disabled.
- Official executable exists and is executable; source/product status is clean within tracked product paths.
- Session workspace/state/fence paths are absent and exclusive before launch.
- Existing PR62 failure evidence remains immutable and is not reused as a live result.

## Acceptance and failure handling

Accept only if the actual candidate controller establishes the same-session selected/current model, useful fixture output is independently tested, protected tests remain unchanged, ownership/session mapping is real, and owner-mediated cleanup proves the matched backend incarnation terminated. Do not infer success from helper exit or readiness alone; unavailable controls remain unavailable and ordinary production admission remains false.

On any failure or uncertainty, retain workspace/state/fence/evidence, write a sanitized receipt, and stop. No retry or replacement session is authorized.
