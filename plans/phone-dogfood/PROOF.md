# Phone Dogfood initial proof

Issue: [#12](https://github.com/saariuslystoned/SaariusSkills/issues/12)

## Verdict

The first `phone-dogfood` capture loop is dogfoodable on a registered Android
test device. The helper inventories physical and logical displays, excludes a
Vysor-created virtual stdout display, captures a structurally valid PNG,
produces a compact manifest without a device serial, and gives the agent an
image it can actually inspect.

This run validates the display/capture/human-mirror slice. It does not claim a
full app build and APK reinstall loop; that remains the next product-app case.

## Bound revision

- Source revision: `8800824867cba8f72048ba22ef94ca09c22a9fe7`
- Device class: registered Pixel 10 Pro XL test device
- Device serial: intentionally omitted
- Physical display ID: observed at runtime; public proof keeps only SHA-256
  `53df27464be8b05a27759d30014369324f0e81affe821be56a472556f3bea73f`
- Logical input display ID: `0`
- Human mirror: Vysor 5.0.7

## Live checks

1. `inventory` reported one active physical display and ignored one virtual
   stdout display. It mapped the physical display to logical input display
   `0`.
2. A safe Calculator surface was launched on the test device.
3. `capture` produced
   [pixel-calculator-adb.png](artifacts/pixel-calculator-adb.png):
   1080×2404, 152,521 bytes, valid PNG, SHA-256
   `32012761f1ba01aed2ba16d01ab22f63f5699160419e31b7bc0324b9312acbb8`.
4. Visual inspection found the Calculator controls legible and reachable, with
   no unintended empty panel or black frame.
5. A window-scoped Vysor capture,
   [pixel-calculator-vysor.png](artifacts/pixel-calculator-vysor.png), showed
   the same Calculator state. It is 395×965, 144,385 bytes, SHA-256
   `580e26cf4016739622a829f744f422cbc6ffd3b3c8d3c691c032139aecd7fa59`.
6. The ADB accessibility tree independently reported only
   `com.google.android.calculator`, 49 nodes, and the visible numeric controls.
7. HOME restoration completed; the final accessibility packages were the
   standard Pixel launcher surfaces.

## Regression and anti-cheat checks

- A warning-prefixed PNG is rejected before file creation.
- Two physical displays without explicit selection fail closed.
- Physical capture IDs and logical input IDs remain separate fields.
- A fake explicit serial is accepted for targeting but absent from stdout and
  error details.
- The full repository suite passed: 66 tests.
- Skill Creator `quick_validate.py` reported `Skill is valid!`.

## Gates honored

No account, message, purchase, permission, security, radio, DND, notification,
or non-test-device action was performed. The public images contain no device
serial, account identity, notification content, or unrelated desktop surface.
