# Visual dogfood proof contract

Keep one compact record per build-install-look iteration:

```json
{
  "iteration": 1,
  "source_revision": "<commit>",
  "artifact_sha256": "<digest>",
  "target": {
    "kind": "<registered_test_device|android_emulator>",
    "device_class": "<physical|emulator>",
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
    "human_mirror": "<Vysor|Android Studio|scrcpy|null>"
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

## Installed artifact identity

When installing an Android build for proof, record the exact build task,
variant, package, output artifact(s), and expected SHA-256 digest(s). After
installation, resolve that package's installed APK paths on the selected
device (for example, `adb -s <serial> shell pm path <package>`) and hash the
installed files through the authorized device tooling. Compare them with the
artifacts actually selected for installation, not only a local build output.
Keep serials and raw device paths out of published receipts.

A single-APK install must match that APK. For split installs, verify the base
and every selected split against the expected device-specific install set;
do not compare a bundle's digest to `base.apk`, or silently check only the
first returned path. Missing or extra splits and digest mismatches fail the
identity check. If installed files cannot be inspected through the authorized
route, mark identity `blocked` rather than treating install success or a
version label as proof. Preserve the mismatch before rebuilding or reinstalling.

Record expected and observed digests, the selected split set when applicable,
and the comparison result alongside the iteration receipt. Inspection of an
already-installed app does not require a rebuild or install: record the
observed app version and leave unverified build identity explicit.

## Synthetic UI fixtures

Use synthetic fixtures only when they help prove the requested presentation
states. Label them as synthetic and keep them inert: no live credentials,
network clients, or callbacks that send or mutate real data. Reuse production
presentation where practical, but do not infer backend or integration success
from a fixture's rendered text.

For an in-app debug fixture, inspect the corresponding release package to
prove the fixture component and entry point are absent; a debug-only source
directory alone is insufficient. Record that packaging check and the debug
component actually launched. If the release check is unavailable, keep
release isolation `blocked`. Do not export a production activity or weaken
production permissions merely to make a proof fixture launchable.

## Emulator and physical-device claims

Classify only the claims needed for the task. An emulator and a physical test
device remain equally valid route-approved targets; this matrix does not
require an emulator-first workflow or an extra device admission gate.

| Claim | Emulator evidence can establish | Physical or live evidence still needed |
| --- | --- | --- |
| Copy, state presentation, scrolling, and layout | Visible behavior at the tested viewport and configuration | Only any claimed hardware-specific differences |
| Fold layouts and posture round trips | Simulated posture/layout behavior and activity survival | Real hinge/sensor behavior, cutouts, and device-specific input when claimed |
| Installation and package identity | Installed artifact identity on that emulator | Physical USB/install/upgrade behavior when claimed |
| Backend or command behavior | Only the exercised real integration; an inert fixture proves none | An authorized live route for any unexercised integration claim |
| Radio, camera, biometrics, battery, thermal, and OEM behavior | Simulated responses, clearly labeled as such | The relevant physical-device observation |

Record each claim's target, evidence, result, and any remaining physical or
live check. Emulator success does not close a physical-only claim. A phone
pass can focus on those remaining claims without replaying unrelated UI proof.
When changing targets, reselect the exact authorized device and bind new
receipts to it; never reuse the old target's identity or screenshots as evidence.

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
