# Visual dogfood proof contract

Keep one compact record per build-install-look iteration:

```json
{
  "iteration": 1,
  "source_revision": "<commit>",
  "artifact_sha256": "<digest>",
  "target": {
    "kind": "registered_test_device",
    "model": "<model-without-serial>",
    "package": "<test-package>",
    "posture": "<flat|folded|unfolded|unknown>"
  },
  "capture": {
    "image": "<proof-relative-path>",
    "physical_display_id": "<observed-id>",
    "logical_input_display_id": 0,
    "width": 1080,
    "height": 2400,
    "bytes": 123456,
    "sha256": "<digest>",
    "human_mirror": "Vysor"
  },
  "visible_contract": {
    "legible": "pass",
    "controls_reachable": "pass",
    "expected_content_present": "pass",
    "empty_or_black_regions": "pass"
  },
  "finding": null,
  "result": "pass"
}
```

Use `pass`, `fail`, `blocked`, or `out_of_scope` for visible checks. Keep the
raw screenshot authoritative.

For each failure, preserve the failed image and record:

- what a human can see;
- the smallest violated clause;
- whether display mismatch, screen-off state, stale install, or app rendering
  is the likely class;
- the repair commit;
- the next capture that proves or rejects the repair.

Close with:

- exact source revision and build artifact digest;
- install/relaunch command summary;
- final screenshot and helper manifest;
- human mirror/display alignment result;
- anti-cheat probe results;
- restore action and final state;
- remaining gates or out-of-scope claims.

Never include device serials, account names, messages, notifications, tokens,
private app content, or unrelated desktop material.
