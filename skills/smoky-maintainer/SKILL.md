---
name: smoky-maintainer
description: Assess repository maintenance and onboarding, prepare evidence-backed priorities and owner decisions, and hand off bounded work. Use before selecting cross-repository execution.
---

# Portfolio Maintainer

Read the current request and trusted repository instructions first. Before applying this core, check those instructions and available skill metadata for a configured operator or repository profile. If they identify a profile-specific installed variant of this skill or an optional binding, read it first unless already loaded. Do not use an unbound core to bypass that profile, invent a binding, or search unrelated files. With no configured profile, use the portable workflow below. A profile or binding does not grant authority to act.

Use the user's approved repository set or a portfolio index named by repository instructions. Record the index/source revision and freshness. Do not infer priorities from directories found on disk or copy a private portfolio into this skill. If discovery is incomplete, report the bounded gap and next safe source check.

Read `references/portfolio-loop.md`. For each candidate, identify its owner contract, exact source state, current work, dependencies, proof, open decisions and blockers. Respect committed business work before proposing a diversion. A repository's existence is not an assignment to work on it.

Classify the proposal as `autonomous`, `needs_owner`, `blocked`, `defer` or `reject`. Explain the evidence and why it fits the approved scope. Prepare implementation/proof/review handoffs through existing tools; do not create a new portfolio ledger or become the execution worker by default.

Make owner decisions concrete: finish authorized reversible preparation, show the options and tradeoffs, and name the action awaiting authority. Keep technical readiness separate from permission to merge, release, deploy, spend or change an account.

Return portfolio scope, proposed priority, classification, evidence, recommended owner/route, proof and stop condition, pending gates and one next action. An idle repository may correctly receive no new task.

```text
portfolio:
current priority:
classification: <autonomous|needs_owner|blocked|defer|reject>
evidence:
recommended route: <owner, target, proof, stop condition>
owner decision:
gates:
next:
```
