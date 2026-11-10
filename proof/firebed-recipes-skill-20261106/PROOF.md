# Coordinator evidence and environment-recovery guidance

Branch: `ridge/firebed-recipes-skill-20261106`.
Base: `820a8397b559a8ae865bf2531fb6b420812562f1`.

Small documentation-only update to `skills/smoky-coordinator/SKILL.md`:
complete transcript vs bounded window vs digest; missing history unknown;
shared research not authority; non-disruptive observation; trusted explicit
check/setup/check with bounded proof, not a preflight bypass.
No runtime, packaging, installed skill or deployment change is claimed.
Concrete operator mechanics remain outside the public core.

`python3 -m unittest discover -s tests -q`: PASS, 229 tests.
Skill-creator `quick_validate.py skills/smoky-coordinator`: PASS using a task-local
test interpreter with PyYAML 6.0.3; default interpreter lacked PyYAML. This checks
syntax/structure, not runtime or model behavior.

Manual source-fidelity walkthrough (not an independent model evaluation): a short
history tail cannot establish absence of earlier work; an observation request
must not interrupt the writer; a shared recipe without trust/authorization cannot
authorize setup. These follow the added distinctions without adding tools or
changing installed behavior. PR CI/review status is recorded by the PR surface.
Manual scope/privacy review: public generic guidance only; no private repository
paths/revisions, host details, source logs, account data or inherited history.
No merges or automatic rollouts; maintainer review remains required.
