# acpx refresh handoff

One bounded candidate-only adoption slice is implemented and owner-verified in commit `4a560197607197a45abfeb537f5f841457a73db2`. Source is frozen at SaariusSkills main `faa332ca8b3eb7da6662f127d6e3a55056f3db9d`; upstream acpx is frozen at merged main `ce8c3689fe830fd5c6199a8a683dc979d180af1d`. The task-local artifact and loaded runtime import closure are recorded in `ARTIFACT_PREP.md`.

The candidate pin, task-local artifact/runtime root, actual-runtime isolation,
reconnect, and result-only event tests are in the local branch. Owner checks
pass: Python 23/23 and bridge 64/64. No ordinary broker/plugin pin, live
candidate qualification, provider turn, release, merge, or OpenClaw review
has been performed in this slice. Draft PR: https://github.com/saariuslystoned/SaariusSkills/pull/60.
