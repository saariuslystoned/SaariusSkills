# Issue #15 Phase 5B corrected Pixel-use comparison state

- status: `complete-product-contract-failed`
- route id:
  `route_20260726_024224_71847_saariusskills-custom-agent-pixel-use-ab-corrected`
- frozen source head:
  `f68771eb63c44db9b21af9cfc95a27da32ec363e`
- Pixel-use source head:
  `6474159cc15eafbd2abe602e13017a2754768ce9`
- host: `aiworker-01`
- heartbeat: `2026-07-26T06:46:02Z`
- top-level processes: `4 / 4`
- declared nested child branches: `4 / 4`
- total declared sessions: `8 / 8`
- unexpected timeouts: `0`
- raw process/catalog artifacts retained: `false`
- foreign sessions or processes touched: `false`
- exact-owned remote roots: `clean; all five verified absent`

Both arms achieved `1 / 2` complete exact rounds and `2 / 2` exact policy
rounds. Both made the same B-round friction error. Custom join fidelity was
`2 / 2`, but custom used three times the declared sessions and `1.626x` total
wall duration.

The comparison is valid and complete, but B3/B4 product reliability failed.
Disposition: keep the ordinary guarded width-two pattern as a reference,
reject a Pixel-use-specific skill and reusable orchestration plugin, and keep
Puppet/Herdr independent as an optional later transport replay.
