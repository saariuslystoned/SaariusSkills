---
name: phone-proof
description: Build, install, visually inspect, drive, and re-verify phone or emulator UI changes with device screenshots and compact proof. Use for Android, iOS Simulator, foldable, emulator, APK, app-layout, Vysor, scrcpy, Android Studio, Running Devices, AVD, ADB screenshot, black-frame, wrong-display, unreachable-control, or rendered-regression work where build logs alone cannot prove the human-visible result.
---

# PhoneProof

Treat pixels as part of the acceptance test. A successful build or install is
not a visual verdict. The loop verifies device UI with or without a build: a
registered physical test phone and a route-approved Android Studio emulator
(AVD) are both first-class proof targets. The install step applies only when
there is an artifact to install; a running emulator or phone can be
inspected on its own.

## Load the contracts

- Read [references/android-displays.md](references/android-displays.md) before
  Android capture or coordinate input, especially on foldables.
- Read [references/proof-contract.md](references/proof-contract.md) before
  creating a durable proof packet.

## Pixel Use interoperability

Use AGY Pixel Use as the phone-control backend for interoperability slices.

- Start in AGY with `/pixel-use`.
- Resolve target phones using `pixel_devices` and use the returned opaque handle.
- Observe with `pixel_observe`.
- Prefer controls in this order:
  1) named controls,
  2) app-semantic controls,
  3) general controls.

Use `scripts/phone_proof.py` and Vysor for display alignment, capture, and
troubleshooting only; do not let them replace Pixel Use as the control backend.

Transient-overlay rubric:

1. Capture and log the failure image/state.
2. If appropriate, issue exactly one reversible BACK action.
3. Capture two stable `pixel_observe` snapshots.
4. Re-verify full target, content, and consequence against both snapshots.
5. If stability or content proof fails, stop and report unsent.

Keep this control-plane guidance separate from the PhoneProof visual/proof
doctrine. Do not add a device admission gate.

Use `scripts/phone_proof.py` for Android device inventory and screenshots.
Do not hand-compose a display capture when the helper owns it.

## Run the loop

1. Read the target repo's `AGENTS.md` and device route. Confirm the exact
   registered test device, package, build artifact, allowed actions, restore
   condition, and proof root. A mirror window or familiar label is not target
   authority.
2. Write a short visible behavior contract: what should be legible, reachable,
   populated, and unchanged. Include the screen and posture the human watches.
3. Build with the repo-owned command. Record the artifact path and digest.
   Do not infer UI success from compilation.
4. Inventory Android displays:

   ```bash
   python3 scripts/phone_proof.py inventory
   ```

   With more than one authorized device, supply `--serial` before the
   subcommand. Never copy the serial into public proof.
5. Install only the reviewed debug/test artifact using the repo's owned
   installer or bounded `adb install -r <exact-apk>`. Force-stop and relaunch
   the exact test package so hot reload cannot masquerade as a native install.
6. Capture the physical display:

   ```bash
   python3 scripts/phone_proof.py capture \
     --physical-display-id <id-from-inventory> \
     --output <proof-root>/after-install.png \
     --manifest <proof-root>/after-install.json
   ```

   Omit `--physical-display-id` only when inventory reports exactly one
   physical display. The helper rejects warning-prefixed or malformed PNG data
   and flags unusually small captures as suspicious.
7. Actually inspect the image with the available image-viewing surface. Check
   real-size legibility, reachable controls, empty or black regions, clipping,
   stale content, and expected state. File size and a PNG signature are only
   anti-corruption checks.
8. Vysor and Android Studio's Running Devices (Device Mirroring) window are
   both acceptable human-view routes; scrcpy remains a fallback. The helper's
   ADB capture stays the canonical agent proof either way. If human and agent
   disagree, align the mirrored screen, physical capture ID, logical input
   display ID, posture, and foreground package before debugging the app.
9. Drive only the explicitly selected plugged-in test device and only
   reversible, route-approved actions.
   Use AGY Pixel Use (`/pixel-use` + `pixel_observe`) as the primary control
   path, preferring named → app-semantic → general controls. Fall back to
   Android input only when a control is not available through Pixel Use.
   Android input uses a logical display ID:

   ```bash
   adb shell input -d <logical-display-id> tap <x> <y>
   adb shell input -d <logical-display-id> swipe <x1> <y1> <x2> <y2> <ms>
   ```

   Never reuse a physical screenshot ID as a logical input ID. Capture after
   every meaningful action and every reinstall.
10. If the image violates the visible contract, record the finding, fix the
    smallest source slice, rebuild, reinstall, relaunch, and repeat from
    capture. Keep before/after images; do not replace failed evidence.
11. Close only when the final image has been inspected, anti-cheat probes pass,
    the requested state persists or resets as specified, and the device is
    restored.

## Android Studio route

Proof is executable inside Android Studio for both an emulator and a
USB/wireless real phone.

- Use the same `adb` binary Android Studio uses (SDK platform-tools) so
  device inventories match and the workflow does not fight a dueling `adb`
  server started from a different install.
- Emulators appear as `emulator-<port>` serials; the helper reports
  `device_class` (`"emulator"` or `"physical"`) so proof manifests
  self-describe the target without ever recording the serial.
- Android Studio's own screenshot button is a human convenience, never the
  agent's proof artifact. Captures still go through
  `scripts/phone_proof.py capture`.
- An emulator needs the same route approval as a physical device. The
  multiple-device guard still requires `--serial` when an emulator and a
  phone are both attached.

## Preserve the boundary

- Customer or non-test sends, accounts, purchases, credentials, permissions,
  security settings, radios, DND, notification state, non-test devices, and
  irreversible actions require their own explicit authority.
- Never publish device serials, account identifiers, notification content,
  private app data, or unrelated screen content.
- Treat an all-black or very small image as suspicious device/display state,
  not automatically as an app-rendering failure.
- Keep mirror tools observational for the human. Do not claim a mirror proves
  what the agent captured unless the display and foreground state agree.
- Do not expose generic shell or arbitrary ADB execution through this skill.
- iOS Simulator follows the same build-install-look-fix-look loop, but the
  bundled helper is Android-only; use the platform-owned simulator capture
  command and preserve the same proof contract.
