# GrillTrack summary output proof

## Acceptance-to-proof table

| Acceptance | Expected proof from synthetic inputs | Evidence |
| --- | --- | --- |
| Independent synthetic inputs yield expected receipt fields and bounded output despite large history | A summary receipt has `command`, active `track.id/status`, the affected decision `id/status` where applicable, `updated_at`, and absolute durable `ledger/events` paths; it contains no choice, rationale, history, or decision list, and remains bounded as history grows. | Focused test and command transcript below |
| Default output remains full and parseable | Without `--output`, stdout is formatted JSON containing the persisted ledger, including decisions and current-focus user content. | Focused test |
| Equivalent full/summary operations preserve identical durable ledger/event semantics | Two disposable projects run the same deterministic command sequence; after normalizing only timestamps and generated event IDs, ledgers and event action/data records are equal. | Focused test |
| Invalid transitions retain stderr/exit2 and no writes | Locking a nonexistent synthetic decision returns exit 2 with the existing error on stderr and leaves both durable files byte-identical. | Focused test |
| Existing `--summary` input, read commands, and reconcile remain compatible | `focus --summary` persists its input; `show` remains a full read; `validate` remains `valid`; lifecycle parser coverage accepts `--output summary` for all 16 supported transitions. Reconciliation code and parser are unchanged. | Focused tests and source diff |

## Verification

All fixtures use disposable temporary projects. No operator ledger, provider,
credential, or external service was accessed.

Commands and results:

```text
python3 -m unittest tests.test_ledger
PASS (26 tests)

python3 -m unittest discover
OK (176 tests discovered; 175 passed, 1 skipped because Node was absent from PATH)

# With Node 24.22.0 on PATH:
python3 -m unittest tests.test_plugin_corrections tests.test_packaging -q
PASS (24 tests, including the previously skipped Node-backed check)
```

The implementation worker reported 26 focused tests and 176 discovered tests
passing with Python 3.12.9. The coordinator independently ran full discovery
with the result shown above, then ran the skipped check and packaging checks
with Node 24.22.0 available.

The focused large-history fixture used 24 verified decisions. Its successful
`focus` operation produced 54,419 bytes of full output versus 347 bytes for
the summary receipt (99.36% smaller). The summary receipt still named the actual
absolute paths:

```json
{
  "command": "propose",
  "decision": {"id": "summary-001", "status": "proposed"},
  "track": {"id": "summary-track", "status": "active"},
  "updated_at": "<fixture clock value>",
  "durable_paths": {
    "ledger": "<temporary project>/.grilltrack/ledger.json",
    "events": "<temporary project>/.grilltrack/events.jsonl"
  }
}
```

The displayed clock and temporary-root values are redacted in this curated
proof; tests assert the generated values and preserve the durable files.

## Independent CLI acceptance

A separate reader inspected only public CLI help and usage documentation, then
executed synthetic operations against implementation commit
`06b523f3003c9effab8a5a8731ee5317b23442ab` with Python 3.12.9. It did not read
implementation or test source. The later documentation changes do not alter
that implementation.

| Check | Observed result |
| --- | --- |
| Lifecycle commands | All 16 advertised and successfully executed with `--output summary`. |
| Default and explicit full output | Parsed output matched the persisted ledger. |
| Receipt contents | Current command, track/decision status, timestamp and real durable paths; no rationale or history payload. |
| Existing content input | `focus`, `confirm` and `close` preserved the existing `--summary` input. |
| Read interfaces | `show` matched durable state and `validate` printed `valid`; `show`, `validate` and `reconcile` rejected the output selector with exit 2. |
| Invalid transition | Resuming an active track returned exit 2, empty stdout and useful stderr; durable file hashes were unchanged. |
| Rollover | `new` archived byte-identical copies of the closed ledger and events. |

Across 107 successful summary transitions, receipts were 410–503 bytes, under
the independent 2,000-byte ceiling. Forty `propose`/`defer` pairs grew full
`show` output from 12,467 to 84,827 bytes and events from 4,957 to 17,597 bytes.
The first and last `defer` receipts were both 467 bytes. These sizes come from
different fixtures than the 24-decision unit test above. Only owned disposable
fixtures were removed; their removal was verified.

## Limits

This proves deterministic local CLI behavior only. It does not claim Harness²
savings, interruption metrics, provider behavior, or reconciliation changes.
Cross-mode persistence parity is a unit-suite result, not an independent
black-box claim. The independent exercise did not run a reconciliation
transaction. Byte reductions are measured output, not measured token, latency,
or end-to-end productivity gains.
