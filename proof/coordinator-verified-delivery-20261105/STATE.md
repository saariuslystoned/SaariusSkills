# Task state

- Assignment: `coordinator-verified-delivery-20261105`.
- Writer and review-wait owner: assigned Pi lead; closer and user-channel
  delivery owner: coordinator. No delegated writers.
- Branch: `ridge/coordinator-verified-delivery-20261105`.
- Base: `42eaec2d62fa15bda220ae46a4feaf788380205e`.
- Skill head: `a27fe4be2b80eedbf89c24d6f102c3c56451b79d`.
- State at this checkpoint: local checks pass; preparing proof-only commit,
  non-force push, PR and exact-head external review requests.
- Required evidence: current-head CI and comprehensive review; native route
  unavailable (repository not enrolled). Do not infer a per-PR exception from
  earlier PRs. No merge or deployment authority.
- Next observation: exact CI run and comprehensive request reach terminal
  result, actionable failure, or bounded review wait deadline. Inspect and
  disposition findings; repair only this skill/proof slice. Keep immutable
  source tuples and historical results if the head changes.
- Continuation: latest PR closeout is the external review status/readback
  pointer. Turn exit does not relinquish lifecycle ownership; resume the same
  assignment for scoped repairs or route resolution, not a new worker.
- Stop: reviewed PR awaiting human merge, or an exact unresolved dependency
  returned to coordinator with this same owner retained. Never self-merge.
