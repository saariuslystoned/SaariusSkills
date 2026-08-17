# Android display contract

## Two ID namespaces

Android screenshot and input commands may use different display namespaces:

- `adb shell dumpsys SurfaceFlinger --display-id` reports physical display IDs
  for `screencap -d`. These may be large 64-bit values.
- `adb shell input -d` accepts logical display IDs from the display service.
  The default motion display is commonly `0`, but never assume that on a
  foldable or multi-display route.

Do not substitute `0`, `1`, or `2` for an observed physical ID. Do not pass a
large physical ID to `input -d`.

## Capture rules

1. Inventory displays before capture.
2. Exclude virtual shell/stdout displays from physical-screen selection.
3. With multiple physical displays, require an explicit physical ID. Guessing
   the cover or inner screen is a proof failure.
4. Capture with `adb exec-out screencap -p -d <physical-id>`.
5. Validate that byte zero begins the PNG signature. Some foldables can prepend
   a multiple-display warning to otherwise valid PNG bytes.
6. Record byte count, dimensions, and SHA-256.
7. Treat an unusually small full-screen image as suspicious. A powered-off
   cover display may produce a valid, highly compressed black PNG.
8. Load and inspect the image. Structural validation does not establish that
   text is legible, controls are reachable, or the right app is visible.

The bundled helper implements steps 1–6 and the small-file warning. It fails
closed when multiple physical displays exist and no explicit selection exists.

## Align human and agent views

Vysor, scrcpy, and Android Studio's Running Devices (Device Mirroring) window
are useful human mirrors. ADB screenshots remain suitable for headless agent
proof. When the views differ, compare:

- physical capture ID and display name;
- logical input display ID;
- folded/unfolded or cover/inner posture;
- orientation and resolution;
- foreground package/activity;
- whether the display is on.

Ask for the human's current view early. Do not spend repair cycles on an app
until both parties are looking at the same screen.

## Coordinate driving

Use coordinates only after the target screen and logical display are explicit.
Keep gestures within current display bounds, prefer semantic automation when
available, and capture immediately afterward. If a tap misses while the target
is visible, recheck display mapping before changing coordinates.
