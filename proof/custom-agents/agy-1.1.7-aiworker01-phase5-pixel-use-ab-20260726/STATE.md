# Issue #15 Phase 5 Pixel-use comparison state

- status: `failed-inconclusive`
- route id:
  `route_20260726_023232_69381_saariusskills-custom-agent-pixel-use-ab`
- frozen source head:
  `16a8543bd773a15e4e9f32a8f3072295c2b01e0e`
- Pixel-use source head:
  `6474159cc15eafbd2abe602e13017a2754768ce9`
- host: `aiworker-01`
- heartbeat: `2026-07-26T06:36:39Z`
- top-level processes: `4 / 4`
- declared nested child branches: `4 / 4`
- total declared sessions: `8 / 8`
- unexpected timeouts: `0`
- raw process/catalog artifacts retained: `false`
- foreign sessions or processes touched: `false`
- exact-owned remote roots: `clean; all five verified absent`

All four runtime and postflight boundaries passed. Both custom joins exactly
preserved their child values and identities. The comparison is inconclusive
because the controller required a `policy.cases` envelope that the prompt
never disclosed; semantically correct alternative envelopes were therefore
scored as exact failures. No post-hoc normalization or rerun was applied.

The still-valid friction subset was exact in one of two single-agent rounds
and zero of two custom-agent rounds. This attempt does not justify a
product-specific or reusable plugin.
