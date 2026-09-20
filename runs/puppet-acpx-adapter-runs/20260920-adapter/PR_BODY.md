## Summary

- add a disabled, synthetic-only Puppet adapter for the named `cursor-acp` transport
- bind only the public `acpx/runtime` / `createAcpRuntime` shape from openclaw/acpx draft PR #648 at exact head `2b7627a6b91b4c94c8a83ad0cc4863f72e8f14de`
- keep the ordinary `acpx@0.16.0` broker route and native launch defaults unchanged

## Safety boundary

- `available()` and ordinary launch remain false; no lease is admitted
- filesystem and terminal callbacks are disabled and rejected without local side effects
- approve-all, MCP broker policy, and private runtime fields are rejected
- exact workspace/model/session/conversation identity is required on bind/reconnect
- completion is distinct from controller acceptance; cancellation is distinct from observed halt
- unsupported questions require human input and cancel without invented answers
- durable evidence is body-free; cleanup uncertainty blocks replacement

## Verification

- `python3 -m unittest tests/test_puppet_cursor_acpx.py -v` — 10 passed
- `npm run check` in `bridge/cursor-acp` — 23 passed
- full repository suite — 1,281 tests ran; one unrelated existing doctor-child timing test fails consistently, documented in the proof packet

No live Cursor ACP, provider prompt, or qualification action was performed.
