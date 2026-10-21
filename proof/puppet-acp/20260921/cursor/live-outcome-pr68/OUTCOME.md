# PR68 Cursor live-path outcome

This is evidence from the one parent-authorized session. It is not a live qualification pass.

- Exact source: `6a9140f81b1850a0b39935bb8cd3e58b9ca0f0e2`, tree `2c4a2142266a6f7eaa80873a609935d0e6736e38`.
- Session: `cursor-proof-v3-live-pr68-20260921-once`.
- Allocation: one session, one prompt, no retry. The live command was executed once.
- Official executable process started and was matched by exact worker identity. Worker lifecycle termination was proven; no fence was created; replacement remained unblocked.
- Selected and current model metadata matched `grok-4.6[effort=high,fast=true]`; route identity was `cursor-agent-acp`.
- First-turn event types were observed: `status`, `text_delta`, `tool_call`. No second turn was requested.
- Fixture result: `normalize-lines.mjs` changed; protected test remained unchanged; post-task tests passed 3/3. Baseline was 2/3.
- Receipt fields: `ok=true`, `live=false`, `live_claimed=false`, `live_cursor_acp_claimed=false`, `mode=live_path_substitute`, `used_kind=qualified_archive`, `ordinary_launch=unavailable`.
- Cleanup fields: `backend_discard=unsupported`, `worker_termination=proven`, `cleanup_uncertain=false`, `replacement_blocked=false`, `finish_error=null`.

## Blocker

The official route process launched, but ordinary live launch was unavailable, so the driver used its qualified archive substitute and correctly withheld a live qualification claim. The allocation is consumed. No retry, provider fallback, or second prompt is authorized by this evidence.

## Evidence hashes

- `live-receipt.json`: `8b19acc25d0f604154059a3fa95e19900a1fb3579d443258109ebdc68c5c27a9`
- `live-driver-output.log`: `473b7c9d5ba73e2940395f16fcb07485eeea8a4ec6ed838d243113783affa3d6`
- After implementation: `2e303480de7689072f5fe708e75a09155ff57b83904e7ed0b648db65499eb38c`
- Protected test: `bf063a0bdbf43dbe3fcda4e4d297af1aebcc2d7d1766efb6582f38e84710742e`
