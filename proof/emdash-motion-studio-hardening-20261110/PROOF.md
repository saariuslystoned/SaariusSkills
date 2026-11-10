# Proof: Harden `emdash-motion-studio` (3-Plate Kinematics, Ambient `stage-only` Default, CDP Mobile & 24fps Loop Proof)

## Summary

Merges current `origin/main` cleanly into `agy/emdash-motion-studio` (PR #195) and hardens `skills/emdash-motion-studio/` with field-verified multiplane rigging, zero-jerk kinematics, ambient stage defaults, true mobile CDP device emulation, and `24 fps` MP4/GIF proof recording:

1. **Ambient `chrome: 'stage-only'` Default (`scripts/build.py` & `assets/multiplane.js`):**
   - `build.py --astro` and embedded `mountMultiplane` now default to `chrome: 'stage-only'`, omitting `.mp-hud-top` and `.mp-hud-bottom` from the DOM (`role="img"`, `aria-label`, zero `.mp-stops` / `.mp-toolbar` debug chrome, `.mp-plane-fg { pointer-events: none }`) while preserving `?t=0..1` and `?explode=1` URL inspection hooks.
2. **Zero-Jerk Kinematics & Periodic Pendulum Helpers (`assets/multiplane.js` & `assets/examples/foundry-hoist-multiplane.html`):**
   - Adds `smooth7(a, b, x)` (`C³` septic smoothstep with zero velocity, acceleration, and jerk at station boundaries) and `preintegratePeriodicPendulum(xFn, opts)` (3-pass periodic damped harmonic pendulum ODE solver with zero `t = 0 / 1` loop seam), maintaining zero `/\bany\b/u` matches.
   - Adds domain-neutral reference stage `assets/examples/foundry-hoist-multiplane.html` demonstrating Plane 01 reactive `mix-blend-mode: screen` blooms, Plane 02 overhead trolley + grooved pulley wheel + differential taut/slack chain + pendulum payload, and Plane 03 foreground steel truss occlusion.
3. **True `390×844` Mobile Viewport & `24 fps` MP4/GIF Loop Recorder (`scripts/verify_motion.py`):**
   - Replaces bare Chrome `--window-size` (clamped to `500px` minimum width by macOS `NSWindow`) with a zero-dependency stdlib Chrome DevTools Protocol client (`Emulation.setDeviceMetricsOverride`), verifying `inner_width == 390` and `overflow_x == False`.
   - Adds `--record-mp4`, `--record-gif`, and `--record-explode` (`--fps 24`) to capture deterministic `24 fps` H.264 `.mp4` and palette-optimized `.gif` loops via CDP + `ffmpeg`.
4. **Asset-Fidelity, Chroma-Safe Despill & Motion Gate Docs (`SKILL.md`, `references/*`):**
   - Codifies the Hard Asset-Fidelity Rule (banning primitive cylinder characters and hand-coded Bezier creatures in favor of `smoky-character-studio` sprites or RGBA depth plates), `#00FF00` lime / two-pass difference despill instead of `#FF00FF` magenta on warm/crimson subjects, Plane 03 rig healing, and the mandatory `24 fps` MP4 + GIF GrillTrack motion gate.

## Verification Commands & Results

1. `python3 -m unittest tests.test_packaging -q` -> `Ran 35 tests in 1.585s — OK`
2. `python3 skills/emdash-motion-studio/scripts/verify_motion.py skills/emdash-motion-studio/assets/examples/foundry-hoist-multiplane.html --out-dir <scratch> --record-mp4 --record-gif --record-explode --frames 24`:
   - `overall_passed: true`, zero DOM errors, zero `NaN`, `mobile_390x844` verified at `iw=390, sw=390`
   - Generated `loop-24fps.mp4`, `loop-24fps.gif`, `loop-24fps-exploded.mp4`, and `loop-24fps-exploded.gif`
3. `python3 skills/smoky-skill-cleaner/scripts/audit-skills --skill skills/emdash-motion-studio --json` -> `packaging_errors: []`

## Gates

- Merge remains human-gated. Non-force push only (`git merge origin/main`).
