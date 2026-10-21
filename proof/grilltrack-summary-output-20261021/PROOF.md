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
/Users/bobbybones/.local/share/mise/installs/python/3.12.9/bin/python -m unittest tests.test_ledger
PASS (26 tests)

/Users/bobbybones/.local/share/mise/installs/python/3.12.9/bin/python -m unittest discover
PASS
```

The focused large-history fixture used 24 verified decisions. Its successful
`focus` operation produced 54,419 bytes of full output versus 347 bytes for
the summary receipt (99.36% smaller). The full receipt still named the actual
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

## Limits

This proves deterministic local CLI behavior only. It does not claim Harness²
savings, interruption metrics, provider behavior, or reconciliation changes.
