# Herdr-Puppet named-destination and Gemini 3.7 proof

Observed: 2026-08-14

## Scope and verdict

This packet binds the review-ready controller source that adds explicit named
machine/workspace selection, a deterministic fresh-tab ordinal, and exact AGY
`gemini-3.7-flash-high` model authority to Herdr-Puppet.

The exact source head is
`f985ad7ef20ef5ea998b4c95d4b85ba71ed787aa`, stacked on draft PR #9 head
`f73caf237a961f77904389a53427572e36e4b4bd`. Its source lineage is:

- `809758206d708edb844d2ab1fef00e1a62b4ed82` — named destination, fresh-tab,
  sanitized receipt, and exact AGY model binding;
- `d17082d43be70b2e1a2305f2b0c6a3b9be29b1f3` — full selected-authority
  fingerprinting, plan/lease version separation, and journal binding; and
- `f985ad7ef20ef5ea998b4c95d4b85ba71ed787aa` — mandatory active-journal
  enforcement and census producer/schema hardening.

No live Herdr tab, SSH connection, remote worker, AGY process, account,
credential, or network mutation was used to earn this proof.

## Product behavior

- `plan --machine` resolves exactly one caller-owned destination profile, one
  status-reported workspace label, and one fresh-tab ordinal. Named and legacy
  selectors are mutually exclusive; no existing-tab adoption path exists.
- The private mode-`0600` plan retains the exact SSH/catalog authority while
  the public receipt emits only the selected machine, workspace label,
  fresh-tab ordinal, and create-only requirement.
- Missing, malformed, duplicate, symlinked, drifted, or mismatched catalog and
  workspace evidence fails before a plan is emitted.
- AGY must advertise the exact `--model` token and a bounded TSV census must
  contain exactly one byte-exact first cell `gemini-3.7-flash-high`.
- The frozen launch vector is the absolute AGY executable followed by
  `--model gemini-3.7-flash-high --dangerously-skip-permissions`
  `--sandbox=false --new-project --log-file /dev/null`.
- Plan, initialized journal, lease, state, and events bind one canonical
  selected-authority fingerprint across run, harness, destination, fresh-tab,
  SSH, source, proof root, full harness binding, and model.
- All seven active post-lease operations require the exact initialized journal
  before lease or fake-client mutation. Only the bounded historical/local
  preservation path retains optional-journal compatibility.
- Active plan/lease records are v2 and fresh bindings are v3. Frozen plan/lease
  v1 and binding v1/v2 readers remain bounded to status, preservation,
  maintenance, exact cleanup, and explicit migration; they cannot authorize a
  fresh tab or qualification transition.

The real two-machine destination catalog remains caller-owned and outside this
repository. This branch does not publish SSH targets, workspace IDs, catalog
paths, raw model listings, or ordinary terminal transcripts.

## Verification

Run from the repository root:

```bash
python3 -m unittest tests.test_herdr_puppet
python3 -m unittest tests.test_packaging
python3 -m unittest discover -s tests -v
python3 -m py_compile skills/herdr-puppet/scripts/harness_census.py skills/herdr-puppet/scripts/herdr_puppet_lib/*.py tests/test_herdr_puppet.py tests/test_packaging.py
git diff --check f73caf237a961f77904389a53427572e36e4b4bd...f985ad7ef20ef5ea998b4c95d4b85ba71ed787aa
```

Observed results:

- Herdr-Puppet: 202/202 passed;
- packaging: 10/10 passed;
- full discovery: 235/235 passed;
- all 21 tracked JSON files parsed;
- Python compile and diff checks passed;
- `SKILL.md` remained within the package cap at 498 lines; and
- the frozen historical plan/lease/binding schemas remained unchanged by the
  final repair.

## Independent review and behavior proof

The terminal exact-source audit inspected `f73caf2..f985ad7` and found no
P0/P1/P2 blocker. Mutants proved that all seven active operations reject an
explicit missing journal root before changing lease bytes or calling the fake
client; successful census records validate before serialization; unsafe host
and failed-enrollment paths emit no active v3 artifact; and version guidance is
consistent.

The independent source-blind validator returned `satisfies_contract` with
confidence `0.99` at exact source head `f985ad7`. All eight behavior clauses
passed, including 202/202 public behavior tests, exact model/argv probes,
cross-authority rejection, historical compatibility, and two identical repeat
runs. It did not inspect implementation source, test source, the private
catalog, credentials, or ordinary transcripts.

## Finding adjudication

One P3 operator-guidance debt is deferred. Historical-binding initialization
correctly writes a maintenance-only/recensus next action, while a later
`journal-refresh` rewrites `STATE.md` without any next-action line. Refresh does
not recommend a forbidden action, the reported record state remains accurate,
the skill still states the historical boundary, and every fresh runtime
transition fails closed. A follow-up may share one binding-aware next-action
renderer between initialization and refresh. This omission is review debt, not
an authority or promotion blocker, and is not being expanded into a third
review-triggered repair cycle.

## Remaining external gate

This proof does not claim live two-machine behavior. Fresh Herdr-Puppet-owned
AGY tabs on the two worker Macs remain blocked by the separately human-gated
CP-1 admission service installation/activation boundary. The controller must
not bypass that boundary, adopt arbitrary tabs, infer a default model, inspect
credentials, or weaken account/security controls. After that gate is approved
and safely installed, the next proof is one fresh named tab per worker with the
exact Gemini 3.7 binding and sanitized controller receipts.
