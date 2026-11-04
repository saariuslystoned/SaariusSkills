# Conversation separation follow-up — 2026-11-04

The coordinator honors user-requested conversation separation on the active
surface while preserving the existing execution assignment and writable owner.
Distinct work still requires admission and overlap checks; a separate
conversation alone does not create a worker. Surface-specific details remain
outside the public core.

- Existing assignment, Ridge mount, branch and base are unchanged; see
  [original proof](PROOF.md#source-identity).
- Prior head: `391788b83f1ae3461c2991940f733952d93de083`.
- Follow-up source: `f5e9a31633beda1ee3d025807fc061617b64a384`.
- Changed source: `skills/smoky-coordinator/SKILL.md` only. Subsequent follow-up
  commit adds proof only. No new runtime, UI, package manifest or installation.
- Open-PR file lists were rechecked before editing; only this assignment's
  draft [PR213](https://github.com/saariuslystoned/SaariusSkills/pull/213)
  overlapped the source file.

## Validation

- Skill Creator `quick_validate.py skills/smoky-coordinator`: PASS with
  `/usr/bin/python3`; [output](followup-skill-validation.txt).
- `python3 -m unittest tests.test_packaging tests.test_portable_skills -q`:
  PASS, 34 tests; [output](followup-packaging-tests.txt).
- `git diff --check`: PASS.
- Public-source privacy inspection: PASS; no operator identities, private
  infrastructure, channel-specific mechanics or model preferences introduced.
- Prior full-suite result (187 tests) remains recorded as initial-rewrite
  evidence; the full suite was not rerun for this narrow prose follow-up.

## Static scenario walkthrough

| Request | Expected action from the revised core |
| --- | --- |
| Move the current task to a separate conversation | Check active-surface support/routing/authority, carry decisions and task/proof pointers, associate that conversation with the existing assignment. |
| Use an explicitly assigned sidebar session | Honor the supported destination without treating its UI identity as a new worker or writable owner. |
| Start distinct work | Admit a separate assignment only after scope and overlap checks; do not infer conversation isolation. |
| Separate conversations are unsupported on this surface | Explain the limitation without inventing a UI feature or duplicating the worker. |
| Follow-up or quick aside on existing work | Continue the existing assignment or answer inline; preserve the objective. |

These are manual source walkthroughs, not independent model trials or live
surface/runtime proof. Existing recovery, child lifecycle, exact-source review,
and human merge gates remain unchanged. The same draft PR is the handoff;
review must cover its updated head.
