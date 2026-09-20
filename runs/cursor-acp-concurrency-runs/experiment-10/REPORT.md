# Cursor ACP ten-job experiment

Date: 2026-09-20

## Result

All ten bounded Cursor ACP jobs were accepted and completed successfully. Each returned its own marker (`ACK-01` through `ACK-10`), with zero tool calls and no cross-wiring.

The ten delegate calls were issued together by the orchestrator, but native delegate acceptance was staggered from `15:16:57.430Z` through `15:17:11.647Z`—a 14.217s submission window. The exact component enforcing that observed serialization is not proven from this run. Canonical job lifecycles show up to five jobs in `running` state at once, while `prompt_started` intervals overlapped by up to three at once. This is a ten-job smoke result, not proof of ten simultaneous provider/model turns or unlimited capacity.

## Per-job evidence

| Job | Job ID | Running interval | Prompt interval | Backend session | Result |
|---|---|---|---|---|---|
| 01 | `99108517-a4e0-4f9d-b4f4-b426efcd1161` | 15:16:57.434–15:17:04.650Z | 15:17:00.340–15:17:04.650Z | `e4cae727-6b1e-4680-97ec-c3224c39e407` | `ACK-01` |
| 02 | `6c79dec0-e163-406d-bcf4-143a1cdf803c` | 15:16:58.968–15:17:06.827Z | 15:17:01.952–15:17:06.827Z | `6d672119-b256-48a5-be90-2db6db9079ef` | `ACK-02` |
| 03 | `35e03429-2659-4987-8307-25ceab195684` | 15:17:00.469–15:17:07.531Z | 15:17:03.494–15:17:07.531Z | `db0e2f10-03cf-47d4-bbfa-5dcd9f1d0666` | `ACK-03` |
| 04 | `00877c5f-8f90-4240-96ca-f4a2d9356342` | 15:17:02.010–15:17:08.854Z | 15:17:05.266–15:17:08.854Z | `0b1abb1d-0284-4d98-b760-60e0cfcd55c2` | `ACK-04` |
| 05 | `3f18906c-341f-4cc3-97c2-32d31b56de19` | 15:17:03.919–15:17:10.450Z | 15:17:07.065–15:17:10.450Z | `f10125e1-b439-4d18-9126-9432174a7093` | `ACK-05` |
| 06 | `8058db58-8e2e-48b2-8ae5-ddc0c7a5d416` | 15:17:05.654–15:17:12.073Z | 15:17:08.525–15:17:12.073Z | `9dda6811-05f8-45a3-8dd8-cba5eb5f2801` | `ACK-06` |
| 07 | `c7e9c484-bee1-4158-8981-8be6f3b88adb` | 15:17:07.284–15:17:13.439Z | 15:17:10.088–15:17:13.439Z | `3489dffa-1b3b-4592-b89d-e757b6b224a8` | `ACK-07` |
| 08 | `1d64c5bd-4316-4f02-a4c2-b55a3f87062e` | 15:17:08.665–15:17:14.591Z | 15:17:11.408–15:17:14.591Z | `14689f45-d53d-4bb5-beaf-23cbd831e4e4` | `ACK-08` |
| 09 | `755bfd46-2774-42a4-b4f2-6fba5580503b` | 15:17:10.071–15:17:16.213Z | 15:17:13.056–15:17:16.213Z | `c6206cfc-2afd-4027-be29-b92d9d171968` | `ACK-09` |
| 10 | `059d392a-3978-4c68-9125-47b1e0a9f9ac` | 15:17:11.655–15:17:18.803Z | 15:17:14.733–15:17:18.803Z | `dcb8eb9a-7d9d-4a7f-9877-a65e1544bb2a` | `ACK-10` |

All jobs used distinct empty scratch directories under this run root, and no scratch files were created. A targeted post-run process check found zero matching `/Users/bobbybones/.local/bin/cursor-agent acp` processes. No auth, permission, rate-limit, needs-input, timeout, or cancellation outcome occurred.

## Interpretation

- Bridge/runtime admission: no failure at ten submissions; the bridge did not expose a hard ten-job cap.
- Observed activity: five concurrent `running` jobs at peak; three overlapping ACP prompt lifecycles at peak.
- Submission path: acceptance was serialized over 14.217s despite concurrent orchestration calls. This may be MCP/tool dispatch serialization; the run cannot attribute it confidently to the bridge, server process, Cursor process, or provider.
- Provider/account: concurrency ceiling, throttling behavior beyond this sample, exact token usage, and billing remain unknown. No billing or usage metadata was exposed, so cost is not inferred as zero.

Recommendation remains a caller-side default cap of two for normal work. Ten succeeded as a small smoke wave, but ten should not become an automatic fan-out default without a separately approved usage/rate-limit study.

No source, plugin, issue, PR, commit, push, account, plan, billing, or quota state was changed.
