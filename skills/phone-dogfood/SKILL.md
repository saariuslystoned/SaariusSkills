---
name: phone-dogfood
description: Build, install, visually inspect, drive, and re-verify phone or emulator UI changes with device screenshots and compact proof. Use for Android, iOS Simulator, foldable, emulator, APK, app-layout, Vysor, scrcpy, ADB screenshot, black-frame, wrong-display, unreachable-control, or rendered-regression work where build logs alone cannot prove the human-visible result.
---

# Phone Dogfood

Treat pixels as part of the acceptance test. A successful build or install is
not a visual verdict.

## Load the contracts

- Read [references/android-displays.md](references/android-displays.md) before
  Android capture or coordinate input, especially on foldables.
- Read [references/proof-contract.md](references/proof-contract.md) before
  creating a durable proof packet.

Use `scripts/phone_dogfood.py` for Android device inventory and screenshots.
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
   python3 scripts/phone_dogfood.py inventory
   ```

   With more than one authorized device, supply `--serial` before the
   subcommand. Never copy the serial into public proof.
5. Install only the reviewed debug/test artifact using the repo's owned
   installer or bounded `adb install -r <exact-apk>`. Force-stop and relaunch
   the exact test package so hot reload cannot masquerade as a native install.
6. Capture the physical display:

   ```bash
   python3 scripts/phone_dogfood.py capture \
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
8. Use Vysor or scrcpy for the human's live view when useful, while retaining
   the ADB screenshot as the agent's headless artifact. If human and agent
   disagree, align the mirrored screen, physical capture ID, logical input
   display ID, posture, and foreground package before debugging the app.
9. Drive only a registered test device and only reversible, route-approved
   actions. Android input uses a logical display ID:

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
