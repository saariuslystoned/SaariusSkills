# Qualification reuse and AGY selector implementation plan

## Boundary

`puppet_lib.qualification_scope` owns reusable harness-compatibility identity.
It does not authorize a task, select a repository, or approve a live probe.
Campaign/goal authorization, controller ownership, exact leases, protected
process checks, and terminal acceptance remain owned by the existing probe and
authority paths.

## Versioned contracts

- `puppet.qualification-scope/v1`: executable, execution bundle, version,
  platform, protocol, target-scoped adapter behavior, instruction policy, and
  model/effort selector semantics.
- `requested_model` and `requested_effort` remain per-task contract values and
  are copied into fresh real-harness qualification evidence. A qualified
  manifest may be reused only when the requested pair matches that evidence.
- Existing receipts without the scope envelope remain legacy evidence: they may
  be verified only by the existing exact campaign/goal/global identity rules;
  they cannot be promoted into the new scope or broaden authority.

## Invalidation matrix

| Change | Reusable scope | Task authorization |
| --- | --- | --- |
| selected executable bytes, vnode, runtime bundle, or version/help surface | invalidate selected target | invalidate |
| selected adapter policy or shared probe/launch/authority behavior | invalidate selected target | invalidate |
| unrelated harness-only policy | preserve selected target | preserve |
| platform or protocol semantics | invalidate selected target | invalidate |
| relevant shipped instruction layer or instruction compiler | invalidate selected target | invalidate |
| requested model/effort pair or selector flags | invalidate selected pair | invalidate |
| campaign id, goal content, repo, branch, or task contract | preserve reusable scope | invalidate only that task |
| stale, tampered, or legacy receipt/catalog | never promote | block |

The scoped source list is explicit and target-aware. Shared behavior remains in
the shared list; per-target adapter policy and mapping semantics are in the
selected target list. A target-only source change does not alter another
target's scope digest.

## CLI shape

`adapter_lab.py requalify --target TARGET ...` performs a read-only plan by
default. It reports the selected target, scope comparison, blockers, and the
exact next bounded probe/qualify commands. `--execute --ack-live-qualification`
is required to run one selected target's existing Pass B/proof/promotion path;
it never expands to a campaign.

## AGY selector contract

The exact manifest mapping must declare `--model` and `--effort` before a
requested value can enter the regular argv. The deterministic order is the
proved regular tail followed by model then effort. The selected pair is bound
in the probe controller contract, instruction wrapper, evidence, receipt, and
qualified manifest. Unspecified values preserve the existing default path.

