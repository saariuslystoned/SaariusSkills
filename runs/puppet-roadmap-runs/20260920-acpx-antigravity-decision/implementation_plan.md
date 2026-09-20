# ACP candidate contract implementation plan

## Boundary

`puppet_lib.antigravity_acp` owns the source-level contract for a future
Google Antigravity ACP target. It does not launch a runtime, authenticate,
register a Puppet transport, qualify a runtime, persist transcripts, or change
the native `agy-print` route.

## Pinned identity

- ACP registry revision: `81bf71b55e15f630c4fb8a86d20d3088071d2071`
- Google runtime id/version: `antigravity-acp` / `1.1.1`
- acpx source/release: `50a47ad10a75431cbc276ec9b555d11fe1f69c84` / `0.17.1`
- Platform commands and matching `localharness_external` helper are exact
  contract data; no installer or updater is included.

## Interfaces

- `candidate_contract() -> Mapping`: returns the immutable, non-qualifying
  route contract and platform launch metadata.
- `validate_candidate_contract(value) -> dict`: rejects drift, generic ACP,
  qualification claims, fallback auth, and incomplete platform metadata.
- `validate_candidate_observation(value) -> dict`: accepts only bounded,
  body-free runtime metadata and requires non-qualifying state.
- `validate_auth_observation(value) -> dict`: requires explicit personal OAuth
  state and rejects API-key, Cloud, alternate-account, interactive-login, and
  overage ambiguity.
- `validate_model_observation(value) -> dict`: requires exact advertised and
  observed model identity; native effort is unsupported until separately
  proved.
- `validate_question_observation(value) -> dict`: requires cancellation and
  human-required state for fixed-choice interaction questions; no answer text,
  options, or automatic selection may enter metadata.

## Invariants

1. `available` is false and `qualification` is `non_qualifying`.
2. `transport` is exactly `antigravity-acp`; `acp` is rejected.
3. No body-bearing key (`prompt`, `output`, `content`, `text`, `transcript`,
   `title`, or `options`) is accepted in observation data.
4. Personal OAuth must be explicitly observed; API/cloud/alternate-account or
   interactive-login paths fail closed.
5. Requested model must be an exact advertised id and equal the observed id;
   effort selection is rejected until an ACP-specific proof contract exists.
6. `interaction_*` questions can only produce `cancelled` + `human_required`;
   answer selection is never represented or inferred.

## Review before implementation

The module is intentionally not imported by transport dispatch or census. A
future live adapter must add its own process-birth, owned-tree halt,
checkpoint/review/acceptance, and account-quota proof before changing that
boundary.
