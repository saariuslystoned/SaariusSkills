---
name: smoky-skill-cleaner
description: Audit user-selected skills for packaging health and practical usefulness. Use to assess metadata, references, discoverability, context cost, unclear triggers, overlapping roles or stale workflows; return evidence-backed keep/update/consolidate/retire recommendations, not automatic cleanup.
---

# Skill cleaner: packaging and usefulness

Read the request and trusted repository instructions first. Check them and available skill metadata for a configured profile-specific variant or optional binding; read it first unless already loaded. Do not invent a binding, search unrelated files or bypass a configured profile. A binding supplies local choices, not permission. Without one, use this portable core; no service, fleet or specific harness is required.

## Select the audit boundary

Confirm the user-selected skill directories or skill roots, the question being answered and where to return findings. Inspect only that selection plus explicitly supplied source/caller evidence. Do not auto-discover home directories, installed/global skills, sibling repositories, transcripts, shell history or authentication logs. Missing usage telemetry means **unknown**, not unused; do not add a collector to fill that gap.

Read the selected canonical `SKILL.md`, its relevant references and scripts, applicable authoring contracts and actual consumers such as scoped manifests, invocation tests, named caller docs or user-supplied examples. Distinguish source, packaged copy and observed loaded inventory: one does not prove the others. If canonical ownership, caller coverage or selection is unclear, state the gap and ask only for the missing input; do not widen the scan.

## Part 1 — packaging and context cost

Use the repository's existing validator when available and safe. The bundled standard-library helper supplies a bounded structural report, **not** the usefulness assessment. From a checkout containing this skill, pass an explicitly selected shelf or one or more skill directories:

```sh
python3 skills/smoky-skill-cleaner/scripts/audit-skills --root ./selected-skills --json
python3 skills/smoky-skill-cleaner/scripts/audit-skills --skill ./selected-skills/example --json
```

Replace example paths with the user's selection; do not run against a larger shelf for convenience. For an installed copy, locate the helper relative to this skill rather than assuming a checkout path.

Check metadata, referenced assets, duplicate names and discoverability in the **scoped** caller surface. Confirm helper candidates against source and native rules. Separate broken packaging from advisory description/body size and optional UI metadata. Long instructions can be justified; a short body can be complete. Counts are not token measurements, a universal budget or proof of what any harness loads. Compare duplicate bodies, references, policy and caller routing before proposing consolidation; equal names alone do not establish equivalence.

## Part 2 — usefulness and role fit

Read [audit policy](references/audit-policy.md) for the evidence rubric and report fields. Assess whether triggers express a concrete task, match actual callers and distinguish adjacent roles. Identify overbroad/unclear triggers, overlapping responsibilities, obsolete command/runtime assumptions and instructions that add effort or context without helping the task. Preserve essential safety and owner policy even when rarely invoked.

Tie each judgment to a source location and a concrete caller example, test, contract or supplied observation; separate fact from inference and mark missing evidence. Propose a narrower trigger, reference split, workflow update or canonical consolidation only when the evidence supports it. A structurally clean skill may still be unhelpful; a useful skill may still need a reference fix. Do not turn helper flags into usefulness scores or fabricate usage/frequency.

## Return recommendations, not mutations

Report coverage, both audit parts, evidence/confidence and ranked **keep / update / consolidate / retire** recommendations using the policy's compact schema. For retirement, identify canonical ownership, known callers and migration, replacement (or explicit none), retention needs and unresolved owner gates. Without that evidence, keep retirement unqualified/pending, not a recommended deletion.

This audit does not edit skill sources, delete/disable packages, install/refresh copies or change callers. If remediation is requested, hand off a separately scoped change through the repository's existing workflow and authorization gates. Report inline by default; use an existing task/proof location only when retention is requested or required.

## Design references

Adapted guidance from Peter Steinberger's skill-cleaner and Vincent Koc's technical-skill-finder informs duplicate comparison, trigger preservation and evidence-based reuse recommendations. See [pinned sources and notices](THIRD_PARTY_NOTICES.md). Their personal tools, log-mining defaults, runtime inventory/budget assumptions and scoring thresholds are not part of this skill.
