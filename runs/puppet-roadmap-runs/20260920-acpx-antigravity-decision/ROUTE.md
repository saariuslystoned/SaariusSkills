# Antigravity route plan

## Ordered slices

### 0. Documentation correction — completed here

Record that the official ACP surface now exists, while preserving native
`agy-print` as the default and generic `acp` as unsupported for Antigravity.
The source change is limited to `skills/puppet/references/adapter-contract.md`.

### 1. Source-free ACP candidate contract — completed here

Add a distinct, non-qualifying `antigravity-acp` target schema/manifest with:

- pinned registry revision, runtime version, archive/helper identity, and
  platform argv;
- explicit `GEMINI_HOME`/personal-OAuth profile boundary;
- exact advertised model acknowledgement and an explicit effort policy;
- no API-key, Cloud-project, alternate-account, or credit fallback;
- fail-closed interaction-question handling;
- body-free metadata fields only.

Implemented in `skills/puppet/scripts/puppet_lib/antigravity_acp.py` with
focused fail-closed tests. It is not wired into the default route or generic
`acp`; `transport_capability_table()` remains unchanged.

### 2. macOS qualification probe, authorization-gated

Using a Bobby-approved isolated profile and the exact pinned runtime/helper,
prove initialize/session-new/model acknowledgement, one harmless prompt,
session resume/load, session cancel, and question cancellation. Capture only
bounded metadata; retain no raw ACP transcript. Do not run until account auth
and paid/overage boundaries are explicitly authorized.

### 3. Puppet lifecycle adapter

Implement a separate adapter around the ACP client that proves exact process
birth identity, owned descendant tree, escalation, and confirmed halt. Map ACP
session IDs to Puppet's checkpoint/review/acceptance records without storing
prompt/output bodies. Treat `session/cancel` as a request, not halt proof.

### 4. Ultra attribution gate

Run the smallest account-visible check defined in `DECISION.md`. A failure to
observe the Ultra baseline bucket is an unresolved acceptance blocker, not a
reason to try API keys or purchased credits.

### 5. Public qualification and comparison

Only after slices 1–4 pass, run a source-blind Puppet public lifecycle against
the ACP target: two-turn continuity, exact model/effort policy, verified tiny
task artifact, checkpoint/review/acceptance, question fail-closed behavior,
and owned-tree halt. Compare its receipt with the native `agy-print` receipt.

### 6. Default-route decision

Keep staged coexistence unless ACP passes every threshold. Graduate ACP to the
default only if it is at least as safe on process ownership, transcript
blindness, review gates, and account/quota attribution, and materially reduces
packaging or recovery burden. Otherwise retain native as default and keep ACP
experimental.

## Decision threshold

The threshold is conjunctive, not a score: exact runtime pin and observed
model; macOS provider/auth proof; Ultra baseline attribution with overages
off; body-free reducer; session recovery; question fail-closed behavior;
owned-tree halt; source-blind public Puppet acceptance; and no regression in
the native route. Any missing item keeps coexistence.
