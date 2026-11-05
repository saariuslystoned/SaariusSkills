# Bounded maintenance assessment

## Evidence within the selection

Follow the selected repository or repositories to their trusted instructions, current work and relevant proof. Record source revision and observation date when they affect the conclusion. A stale index or export is a context gap, not current authority or evidence of an urgent defect. Keep unknowns visible; do not claim a live condition from source alone.

For onboarding, summarize purpose, owner, source/dirty state, active work, relevant dependency/release constraints, required checks and decision gates. Recommend a small first deliverable consistent with existing priorities, without starting it. Preserve unrelated work; assessment does not authorize checkout cleanup or synchronization mutations.

Inspect evidence proportionately. A named failing check may need its exact run and relevant source, not an inventory of every repository. If a dependency outside the selection blocks the recommendation, identify the dependency, evidence available, missing check and responsible owner. Propose a separate follow-up if necessary; do not expand scope automatically.

## Priority reasoning

Compare plausible next steps in plain language:

- **Goal fit and impact:** whose stated outcome improves, and what evidence supports that benefit?
- **Urgency:** is there an observed failure, verified exposure or relevant deadline? Age alone does not answer this.
- **Dependencies:** what does this unblock, and what must happen first? Distinguish a real prerequisite from a convenient cleanup.
- **Effort and risk:** what is known, what is uncertain, and what committed work would be displaced?

Recommend an order with its main tradeoff; avoid made-up scores, speculative precision and automatic dependency-first ranking. With no new goal, use documented commitments to recommend a focus. If evidence is insufficient, make a conditional recommendation or identify the smallest missing check rather than inventing a priority or asking an avoidable broad question.

## Authority is separate from priority

Classify each actionable proposal as needed; a short answer need not enumerate every category:

- `already_authorized`: applicable authorization covers this bounded maintenance, such as an existing assignment, explicit approval or standing repository policy. Cite its source and scope; this is eligibility for an execution handoff, not execution by this skill.
- `needs_owner`: applicable authorization is missing for the proposed action or a material choice remains unresolved. This includes routine unassigned fixes when no approval or standing policy covers them; small effort alone is not authority. State exactly what the owner must decide, with options and a recommendation. Do not ask again for authorization that already covers the action.
- `blocked`: a required dependency or evidence source is unavailable. Name the missing prerequisite, responsible owner and resume condition; do not assume every blocker needs human permission.
- `defer`: valid work that should wait under the established goal, commitments or capacity. State why and what would change that choice.
- `reject`: duplicate, obsolete or contradicted by evidence. Cite the reason rather than treating low priority as invalid.

Priority and authority can differ: the most valuable item may be blocked or need an owner, while an already-authorized item may still merit deferral. Note both when applicable.

An owner brief states what changes, who benefits, why now, evidence completed/missing, alternatives, tradeoffs, recommended choice and exact pending action. Complete relevant assessment research first; do not interpret 'safe reversible preparation' as permission to implement a fix.

## Stop at the recommendation

Return the assessment in the current authorized conversation. Use an existing task or PR record for a durable handoff only when persistence is needed and authorization covers that destination and audience; assessment alone does not authorize publishing owner details or other sensitive information. Include only information appropriate for that audience. If destination authority is missing, describe the proposed handoff without posting it. Identify the source and proof limits, proposed owner/workflow, authorization/gates, completion check and stop condition. Execution follows a separate assignment through the coordinator or configured harness workflow. No new worker, ledger, timer or mandatory service follows from this assessment.

If nothing justifies new work, say so and explain why. Idle capacity is valid; do not refill it with speculative maintenance or repeatedly poll for activity.
