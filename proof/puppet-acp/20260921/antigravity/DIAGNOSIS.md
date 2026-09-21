# v3 live-attempt diagnosis

Status: `FAILED_NO_USEFUL_EDIT`; no qualification PASS. This is a read-only
diagnosis of the retained evidence after the one released v3 attempt. No
provider rerun or source change was made.

## Direct evidence

- The exact parent-selected v3 command exited `2` with the body-free error
  `fixture after tests did not pass independently`.
- The fresh workspace `agy-proof-v3-live` retained only the baseline fixture:
  `package.json`, `src/normalize-lines.mjs`, and the protected test. There was
  no `bin/normalize-lines.mjs`; protected SHA-256 values matched baseline and
  `git status` had no changed paths.
- Retained `ownership.json` records the owned official controller session
  `agy-proof-v3-live`, conversation `conv-agy-proof-v3-live`, transport
  `antigravity-acp`, adapter `antigravity-acpx`, `cleanup=owned`, and
  `qualification=non_qualifying`. Its only event is `ownership_claimed`.
- No retained body-free receipt contains an exact request ID, stop reason,
  advertised/current model, second-turn continuation, matched backend
  incarnation, or post-finish termination result. No cleanup fence file was
  emitted. A post-run process-name search found no matching task process, but
  that is not matched-incarnation cleanup proof.

## Source-backed execution path

- The v3 driver selected the official resolver for `live=True`, passed exact
  `TASK_TEXT`, `gemini-3.8-flash-high`, `catalog=None`, and the owned fixture
  into `_antigravity_acp_structured_launch` (`v3/driver/...py:1157-1193,
  1322-1338`). Live mode never calls the known-answer implementation.
- Structured launch resolves the official route, constructs the candidate
  runner with `prompt` and the expected workspace, then calls
  `controller.require_observation` and `caller_result`
  (`skills/puppet/scripts/puppet_lib/session.py:1057-1104`).
- The runner binds the task text, calls `ensure_session`, maps the runtime
  model through status/setModel/status, and sends the text plus request ID in
  `start_turn` (`skills/puppet/scripts/puppet_lib/antigravity_acp.py:1621-1672`).
- The driver then requests the same-owner `owner.next_turn` and calls
  `owner.finish` before running the live fixture-after assertion
  (`v3/driver/...py:1393-1424`). Since the observed error is the later
  fixture-after error, it is reasonable control-flow evidence that those
  stages returned; it is not a persisted runtime receipt.

## Evidence versus inference

The direct cause established by the run is that the provider path did not
leave the required implementation in the owned workspace. The smallest
truthful explanation is “expected file absent”; the retained evidence does
not distinguish provider non-action, an unavailable native edit capability, or
an earlier task-level failure. `fs=false`/`terminal=false` is a client callback
policy and does not prove native backend tools were unavailable.

The source path proves how `TASK_TEXT` was bound and sent, but the retained
failure path does not prove exact observed model, stop reason, or matched
backend termination. Do not promote those inferred stages to live acceptance.

## Smallest justified repair / proof recommendation

Do not spend another provider session under this packet. If a future rescope
authorizes one, first add a body-free failure receipt at the driver boundary
that persists: official route identity, requested/observed model, first-turn
request/stop reason, same-owner continuation request/stop reason, owner.finish
result, and the captured backend incarnation plus matched post-finish
termination. Preserve the workspace/state and write a durable fence whenever
cleanup is uncertain. This is a proof-observability repair, not evidence that
the backend lacks edit tools.
