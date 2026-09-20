## Summary

- add a disabled, synthetic-only Puppet adapter for the named `cursor-acp` transport
- bind only the public `acpx/runtime` / `createAcpRuntime` shape from openclaw/acpx draft PR #648 at repaired exact head `02c03c7abeee0324a71e2114e6b1b4cf7b0785ff`
- keep the ordinary `acpx@0.16.0` broker route and native launch defaults unchanged

## Safety boundary

- `available()` and ordinary launch remain false; no lease is admitted
- filesystem and terminal callbacks are disabled and rejected without local side effects
- approve-all, MCP broker policy, and private runtime fields are rejected
- exact workspace/model/session/conversation identity is required on bind/reconnect
- completion is distinct from controller acceptance; cancellation is distinct from observed halt
- unsupported questions require human input and cancel without invented answers
- durable evidence is body-free; cleanup uncertainty blocks replacement

The repaired upstream head is a test-only hardening delta: reconnect/load-session
coverage, absolute fixture paths, enabled/disabled control reconnect cases, and
probe path assertions. No upstream runtime implementation file changed in
that delta.

## Verification

- `python3 -m unittest tests/test_puppet_cursor_acpx.py -v` — 10 passed
- `npm run check` in `bridge/cursor-acp` — 23 passed
- full repository suite — 1,281 tests ran; one unrelated existing doctor-child timing test fails consistently, documented in the proof packet
- refreshed repaired dependency pin — Python and JS identity checks both produce integrity `9f5d189cf0adf8151109b36814b39293a5f8b82bee38668724635f6fed652b66`

No live Cursor ACP, provider prompt, or qualification action was performed.
