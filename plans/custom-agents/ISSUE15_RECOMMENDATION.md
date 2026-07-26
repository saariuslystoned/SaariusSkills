# Issue #15 decision brief

Date: 2026-07-26

## Recommendation

Choose `reference_only`.

Retain the contracts, fixtures, harnesses, and committed counterexamples as
research material. Do not ship a Pixel-use-specific custom-agent skill, a
generic custom-agent orchestration skill/plugin, or a Puppet adapter from this
evidence.

Ordinary guarded custom agents are real and useful as a bounded primitive.
They have not earned a product package.

## Evidence

### Qualified within an exact scope

- Workspace-local primary selection passed for four distinct agents on AGY
  `1.1.7`, including `subagent: false`.
- An exact-count discovery guard rejected absent and duplicate names before
  model launch and admitted one exact name.
- Two fresh width-two rounds produced two grounded child artifacts and one
  OS-gated, source-faithful join per round.
- Width-four denial, malformed-child, and watchdog controls were externally
  observed and contained.

### Rejected or unqualified

- Raw unknown-name selection is not fail-closed when another valid profile is
  present.
- Exact internal actor count, scheduler concurrency, tool-call count, retry
  count, and token/credit cost remain unobserved because the retained proof is
  intentionally transcript- and tool-trace-blind.
- The first width-four success round produced four correct child artifacts but
  a parent join that invented all four child markers. Width-four semantic
  joining is rejected under the tested fingerprint.
- The corrected Pixel-use comparison tied complete exact accuracy:
  single `1 / 2`, custom width two `1 / 2`. Both arms independently made the
  same B-round friction error.
- Custom used three times the declared sessions and `1.626x` total wall time;
  it was slower in both paired rounds.
- Neither product arm met the two-of-two exact reliability clause.

## Alternatives

### `reject`

Not chosen. Guarded primary selection and width-two functional joining are
repeatable enough to preserve as a research/reference primitive.

### `product_skill`

Rejected. The Pixel-use probe showed no correctness or coverage improvement
and added coordination cost. No OKF or LLM-Wiki product claim was needed after
the first admitted product probe failed to show benefit.

### `reusable_skill_or_plugin`

Rejected. The tracker required the same stable contract to improve at least
two materially different product probes. It improved none, and width-four
joining failed.

### `puppet_adapter_later`

Not selected by this tracker. Puppet/Herdr should remain independently owned.
A future Puppet transport replay may use a frozen reference experiment only
if a product capability later becomes worth transporting; Puppet does not own
custom-agent semantics.

## Teamwork Preview and PR #6

Teamwork Preview is not required for any qualified result. All passing
identity, guard, width-two, containment, and product-comparison mechanics used
ordinary workspace custom agents.

Issue #11 correctly removes Teamwork Preview and PR #6 from Puppet convergence.
PR #6 remains unchanged historical research at
`baea84b2bb0d21ff749ce65d077a76cc76f2e1de`.

## Residual risk and future admission

Do not continue generic fan-out campaigns by default. A new route is justified
only when a materially different product has:

1. independent work that should benefit from decomposition;
2. controller-known ground truth and an explicit output schema;
3. a single-agent baseline;
4. a reason to expect the additional sessions and join cost to pay for
   correctness, coverage, latency, or operator burden;
5. its own bounded budget, owner, proof root, and stop condition.

Such a route would be new research, not continuation debt for issue #15.

## Owner and review

- recommendation owner: Bobby;
- evidence branch:
  `codex/custom-agent-qualification-issue15-20260726`;
- review path: issue #15 plus committed behavior reports and proof packets;
- remaining human gate: accept `reference_only` and close or retain the
  tracker;
- no merge, deploy, release, install, account, device, or customer action is
  implied.

## Proof index

- Phase 1D identity/negative controls:
  `b2e7dbab204408b7933dcc66df9e74cefedd9063`
- Phase 1E exact-count guard:
  `d01fb5c5ce4a01e9acbb19ceb40ac48ccc32a1d2`
- Phase 2 width-two proof:
  `c71206a3e6a2fad71119ee8d53d06651aee1cbc5`
- Phase 3 width-four counterexample:
  `6be2a699fa7cb96f81fe9679ae867b6273834960`
- Phase 4 containment:
  `8cea286fca4fdcc55852f136ef0b3dd5acd2604a`
- Phase 5 oracle-design counterexample:
  `4f823d794ada77173b1e16c6a9206a46021317f6`
- Phase 5B corrected product comparison:
  `2c1a07b7ab2c355918413eb7fd25806c117bdba8`
