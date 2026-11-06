# Extended `sprite_version: 2` Pet Rig Contract & Prompt Templates

## 1. Atlas Geometry (`1536×2288` RGBA PNG)

| Property | Value |
| --- | --- |
| **Schema Version** | `sprite_version: 2` (`extended` layout) |
| **Canvas Dimensions** | `1536 × 2288` px (`RGBA` 8-bit/channel PNG) |
| **Cell Dimensions** | `192 × 208` px per frame |
| **Grid Layout** | `8` columns × `11` rows = `88` total cells |
| **Populated Frames** | `73` active frames (`[6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8]`) |
| **Unused Cells** | `15` cells (must be 100% transparent: `R=0, G=0, B=0, A=0`) |
| **Standing Baseline** | `bottom_y = 201` (or `202`), leaving `6–7px` bottom margin |
| **Horizontal Anchor** | `center_x = 96.0` (computed on the `38%–76%` torso/hip band) |

## 2. Row-by-Row Specification

| Row | State Name | Active Frames | Unused Cells | Frame Interval (`ms`) | Loop | Structural Invariant |
| --- | --- | --- | --- | --- | --- | --- |
| `Row 0` | `idle` | `6` (`c0..c5`) | `c6..c7` | `120` | Yes | Gentle 2px vertical breathing cycle; feet locked to `bottom_y = 201..202`; `r0c0` serves as canonical standing base. |
| `Row 1` | `running-right` | `8` (`c0..c7`) | — | `90` | Yes | Full 8-step right-facing stride (`bottom_y = 197..201`, `center_x = 96.0`). |
| `Row 2` | `running-left` | `8` (`c0..c7`) | — | `90` | Yes | Horizontal mirror of `Row 1` (`ImageOps.mirror`) re-centered on `center_x = 96.0`. |
| `Row 3` | `waving` | `4` (`c0..c3`) | `c4..c7` | `120` | Yes | Friendly greeting arc (`low → high → peak → high`); feet anchored at `bottom_y = 201`. |
| `Row 4` | `jumping` | `5` (`c0..c4`) | `c5..c7` | `110` | No | `c0` crouch (`201`), `c1` launch (`183`), `c2` apex (`157`, `44px` lift), `c3` descent (`186`), `c4` landing (`201`, `landing_delta_pixels = 0`). |
| `Row 5` | `failed` | `8` (`c0..c7`) | — | `110` | No | `c0..c1` startled jolt (`! !`), `c2..c7` overheated/slumped (`X X`) with rising smoke curls. |
| `Row 6` | `waiting` | `6` (`c0..c5`) | `c6..c7` | `120` | Yes | `c0..c2` foot/claw tap with `? ?` telemetry; `c3..c5` sleepy standby (`- -`). |
| `Row 7` | `running` | `6` (`c0..c5`) | `c6..c7` | `110` | Yes | Focused work cycle (alternating left/right typing or forging strokes). |
| `Row 8` | `review` | `6` (`c0..c5`) | `c6..c7` | `120` | Yes | `c0..c3` magnifying-glass code inspection; `c4..c5` approval nod with checkmark. |
| `Row 9` | `look_000_to_157_5` | `8` (`c0..c7`) | — | `95` | Yes (with Row 10) | Clockwise gaze angles `0°, 22.5°, 45°, 67.5°, 90°, 112.5°, 135°, 157.5°`. |
| `Row 10` | `look_180_to_337_5` | `8` (`c0..c7`) | — | `95` | Yes (with Row 9) | Clockwise gaze angles `180°, 202.5°, 225°, 247.5°, 270°, 292.5°, 315°, 337.5°`. |

## 3. Prompt Templates for Six `2×2` `#FF00FF` Chroma-Key Sheets

Pass the locked **Master Hero Avatar** and **4-Angle Turnaround Sheet** as reference images to every prompt below. Replace `<CHARACTER_DESCRIPTION>` with the locked character spec.

### Sheet 1 — `chroma_idle_gaze.png`
```text
Generate a 1:1 square 2x2 grid sprite sheet of <CHARACTER_DESCRIPTION> on a 100% SOLID FLAT PURE MAGENTA (#FF00FF) chroma-key background.
CRITICAL:
- Background MUST be completely flat, unlit, solid #FF00FF (RGB 255, 0, 255) everywhere with ZERO ground shadows, ZERO floor lines, ZERO text labels, and ZERO panel borders.
- Do NOT use magenta or pink anywhere on the character.
- Leave generous #FF00FF margin around each of the 4 full-body poses so nothing touches quadrant edges.
- Identical 1.6x chibi proportions and scale across all 4 quadrants:
  * Top-Left (TL): Front-facing neutral standing idle pose, looking straight ahead (0 deg).
  * Top-Right (TR): Front-facing alert standing idle pose, slightly puffed chest, joyful ^ ^ eyes.
  * Bottom-Left (BL): Standing front body, head/gaze turned 45 degrees front-right (NE).
  * Bottom-Right (BR): Standing front body, head/gaze turned 45 degrees front-left (NW).
```

### Sheet 2 — `chroma_cardinal_gaze.png`
```text
Generate a 1:1 square 2x2 grid turnaround sheet of <CHARACTER_DESCRIPTION> on a 100% SOLID FLAT PURE MAGENTA (#FF00FF) chroma-key background.
CRITICAL: Flat #FF00FF background, ZERO shadows, ZERO text, ZERO grid lines, generous margin around each full-body pose:
  * Top-Left (TL): Full 90-degree right side profile view (East).
  * Top-Right (TR): 135-degree back-right three-quarter view (South-East).
  * Bottom-Left (BL): Full 180-degree rear back view (South).
  * Bottom-Right (BR): Full 270-degree left side profile view (West).
```

### Sheet 3 — `chroma_run_right.png`
```text
Generate a 1:1 square 2x2 grid locomotion sheet of <CHARACTER_DESCRIPTION> running toward the RIGHT on a 100% SOLID FLAT PURE MAGENTA (#FF00FF) chroma-key background.
CRITICAL: Flat #FF00FF background, ZERO shadows, ZERO text, ZERO grid lines, generous margin around each full-body pose:
  * Top-Left (TL): Run right Pose 1 — Contact stride (leading leg forward, trailing leg back).
  * Top-Right (TR): Run right Pose 2 — Down/passing stride (legs passing center).
  * Bottom-Left (BL): Run right Pose 3 — Push-off stride (driving forward).
  * Bottom-Right (BR): Run right Pose 4 — High energetic stride.
```

### Sheet 4 — `chroma_wave_jump.png`
```text
Generate a 1:1 square 2x2 grid action sheet of <CHARACTER_DESCRIPTION> on a 100% SOLID FLAT PURE MAGENTA (#FF00FF) chroma-key background.
CRITICAL: Flat #FF00FF background, ZERO shadows, ZERO text, ZERO grid lines, generous margin around each full-body pose:
  * Top-Left (TL): Friendly wave hello — right arm/claw raised at shoulder height, happy ^ ^ eyes.
  * Top-Right (TR): High enthusiastic wave — right arm/claw raised high above head, joyful ^ ^ eyes.
  * Bottom-Left (BL): Deep pre-jump crouch — knees/legs compressed low, preparing to launch upward.
  * Bottom-Right (BR): Airborne jump apex — tucked high in the air with limbs/thrusters flared.
```

### Sheet 5 — `chroma_fail_wait.png`
```text
Generate a 1:1 square 2x2 grid status sheet of <CHARACTER_DESCRIPTION> on a 100% SOLID FLAT PURE MAGENTA (#FF00FF) chroma-key background.
CRITICAL: Flat #FF00FF background, ZERO shadows, ZERO text, ZERO grid lines, generous margin around each full-body pose:
  * Top-Left (TL): Startled error jolt — surprised ! ! eyes, warning flare.
  * Top-Right (TR): Overheated failed slump — dizzy X X eyes, slumped posture, small dark smoke puff.
  * Bottom-Left (BL): Patient waiting pose — tapping foot/claw, curious ? ? eyes.
  * Bottom-Right (BR): Sleepy standby pose — relaxed - - eyes, dimmed core glow.
```

### Sheet 6 — `chroma_work_review.png`
```text
Generate a 1:1 square 2x2 grid work & code-review sheet of <CHARACTER_DESCRIPTION> on a 100% SOLID FLAT PURE MAGENTA (#FF00FF) chroma-key background.
CRITICAL: Flat #FF00FF background, ZERO shadows, ZERO text, ZERO grid lines, generous margin around each full-body pose:
  * Top-Left (TL): Active coding/forging left stroke — focused > < eyes, working at a floating mini holo-console.
  * Top-Right (TR): Active coding/forging right stroke — focused > < eyes, alternate hand/claw strike.
  * Bottom-Left (BL): Code review inspection — holding a glowing magnifying glass up to one eye.
  * Bottom-Right (BR): Code review approved — nodding with a glowing green checkmark badge.
```

## 4. Distilled Lessons Across Three Character Generations

| Generation | Track / PR | What Worked | What Needed Improvement & How It Was Solved |
| --- | --- | --- | --- |
| **1. Clank** (`Cannabis + Computers Robot`) | GrillTrack `gt-20261006143347-afa759` (`work-pets/0.1.6`) | 5-option GrillTrack intake (`A–E`), expression grill (`mischievous, nerdy, mellow, friendly, furious`), and `robot-dance` motion study locked a distinct personality fast. | Generating `8×1` horizontal strips caused row-to-row scale pops (`1.18–1.22` area ratio at `157.5°→180°` and `337.5°→0°`) and interior chroma holes (`850–1250px` warnings). Solved in Gen 2 & 3 by switching to `2×2` key-pose sheets + deterministic Python atlas compilation. |
| **2. Bobby Bones** (`Skeleton Cyborg Hoodie Robot`) | `saari-co/x-api#713` (`bobby-bones-pet-avatar-20261015`) | Introduced `2×2` `#FF00FF` chroma-key sheets, torso-band (`38%–76%`) centroid alignment, and a feathered **U-shaped hoodie collar socket** (`Rows 9–10`) mounting 3D rotated skulls onto a locked `r0c0` torso (`0.0px` drift). | `spritesheet-extended.png` was re-saved with `optimize=True` *after* the initial manifest SHA-256 was computed, requiring a manifest refresh. Solved in Gen 3 by always writing and optimizing `spritesheet-extended.png` *before* computing hashes. |
| **3. Blaze** (`OpenClaw Hermit-Wisp Magma-Crab V4`) | `saari-co/x-api#871` (`blaze-pet-avatar-20261105`) | Two-stage GrillTrack funnel (`5 Archetypes → 5 Hybrid Variations`) + Master Character Sheet Triad (`Avatar + 4-Angle Turnaround + 6-State Expression Sheet`) + locked-carapace 16-angle compass visor gaze (`0.0px` drift, `1.0` width ratio, `44px` jump lift, `0` residue). | Established the canonical 19-asset immutable release shelf manifest (`saari-co/swarm-pr-assets`) paired with repo-committed text/JSON proof (`review-tools proof-assets` `result=pass`). |
