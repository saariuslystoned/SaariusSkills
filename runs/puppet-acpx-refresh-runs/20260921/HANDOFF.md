# acpx refresh handoff

One bounded candidate-only adoption slice is implemented and owner-verified in commit `4a560197607197a45abfeb537f5f841457a73db2`. Source is frozen at SaariusSkills main `faa332ca8b3eb7da6662f127d6e3a55056f3db9d`; upstream acpx is frozen at merged main `ce8c3689fe830fd5c6199a8a683dc979d180af1d`. The task-local artifact and loaded runtime import closure are recorded in `ARTIFACT_PREP.md`.

PR #60 exists. This follow-up repairs the one bounded P2: discarded-event
`observed_types` is now a fixed-bound unique-type summary plus an honest
count, so metadata retention no longer grows with event volume. Unknown
types are retained as `unknown`. The default consume path still drains
through completion; only an explicit `limit` ends the iterator, and that
path still calls `return()`.

Repair implementation job: `80c22421-0e7a-488e-bf0f-53a5eabb55c3` using the
exact Cursor ACP Grok route. Worker proof:
`/Users/bobbybones/.local/state/saarius-skills/cursor-acp-delegation/runs/80c22421-0e7a-488e-bf0f-53a5eabb55c3/PROOF.md`.

Owner checks after this repair: Python 23/23 and bridge 65/65, including
the 100000-event bounded-metadata regression. The candidate pin, task-local
artifact/runtime root, actual-runtime isolation, static-catalog reconnect,
and result-only event tests remain in the local branch. This repair is a
provider job. No LIVE CANDIDATE qualification,
ordinary broker/plugin pin change, live provider turn, release, or merge
has been performed. Reconnect remains static-catalog only; it does not
claim `#675` or `#666`. Draft PR: https://github.com/saariuslystoned/SaariusSkills/pull/60.
