---
name: smoky-character-studio
description: Bring a character, mascot, or AI agent persona to life through a 5-candidate GrillTrack concept funnel, a 3-sheet Master Identity Pack, 2x2 #FF00FF chroma-key pose sheets, and deterministic sprite_version 2 extended pet rig compilation (1536x2288 RGBA PNG, 73 frames). Use when asked to create a character, design an agent avatar, build a Clank/Bobby Bones/Blaze style robot or pet character, or compile a work-pets sprite sheet.
---

# Smoky Character Studio

Bring an agent persona, robot mascot, or brand character to life—from initial concept grilling to a complete **Master Identity Pack** and a validated **`sprite_version: 2` Extended Pet Rig** (`1536×2288` RGBA PNG, `8×11` of `192×208` cells = `73` populated frames).

This workflow synthesizes the battle-tested architecture and lessons across three generations of character builds (**Clank**, **Bobby Bones**, and **Blaze**) plus brand mascot kits:

```text
5 Archetypes (Grill R1) -> 5 Hybrid Variations (Grill R2) -> 3 Master Identity Sheets -> 6 Chroma-Key 2x2 Pose Sheets -> Deterministic Atlas Compiler -> QA & Release Proof
```

Read [references/sprite-v2-contract.md](references/sprite-v2-contract.md) for the exact `8×11` cell grid, row frame counts, prompt templates, and lessons learned from prior character builds.

## Phase 1 — GrillTrack Concept Funnel (`5 Archetypes → 5 Hybrids → Lock`)

Never jump straight to sprite strips before the character's silhouette, head-to-body ratio, and material language are locked.

1. **Initialize a GrillTrack Ledger (`.grilltrack/ledger.json`)**:
   - Record the character name, role (e.g., coding companion, OpenClaw agent, brand mascot), and core motifs.
2. **Round 1A — Five Distinct Archetypes (`1:1` Square Portraits)**:
   - Generate **five genuinely divergent character archetypes** in parallel (for example: *Tactile Retro-Bot*, *Armored Mecha Creature*, *Living Elemental/Plasma Entity*, *Streetwear Mascot*, *Minimalist Holographic Construct*).
   - Keep framing consistent (`1:1` square, 3/4 front hero angle, dark studio background) so the user compares character identity rather than camera distance.
3. **Round 1B — Five Hybrid Variations (When the User Combines Two Favorites)**:
   - Users frequently pick two archetypes to fuse (for example, *Armored Magma-Crab × Living Plasma Wisp*).
   - Immediately run a second 5-candidate visual round exploring **five distinct structural ratios** of that hybrid:
     1. `V1 — 50/50 Balanced Exoskeleton Rig` (equal armor and core visibility).
     2. `V2 — Hovering Core + Detached Magnetic Limbs` (maximum elemental/floating feel).
     3. `V3 — Heavy Industrial Mech` (80% armored chassis with an exposed furnace/reactor core).
     4. `V4 — Hermit / Shell-Dweller` (compact creature nestled inside an oversized protective shell or hood).
     5. `V5 — Signature Operator Edition` (custom badge, glass container, or operator-themed finishes).
4. **Lock the Winner**:
   - Record the chosen candidate ID, structural proportions, color tokens, and material finish in `.grilltrack/ledger.json` before generating multi-angle sheets.

## Phase 2 — Master Character Sheet Triad

Before producing animation frames, generate three canonical reference sheets in parallel, **passing the locked Phase 1 concept image as the visual reference input** to every call:

1. **Master Hero Profile Avatar (`1:1` Square)**:
   - Framing: waist-up or full-body hero portrait with dramatic rim lighting and clean studio backdrop, suitable for GitHub, Slack, Discord, Google Workspace, and OpenClaw avatars.
2. **4-Angle Orthographic Turnaround Sheet (`16:9` Wide)**:
   - Views: `FRONT VIEW`, `3/4 FRONT VIEW`, `SIDE PROFILE VIEW`, and `BACK VIEW` standing on a shared horizontal ground baseline.
   - Purpose: locks 360° geometry (rear shell/backpack vents, side depth, collar socket geometry, and leg attachment points) so turnaround and run frames never hallucinate missing back details.
3. **6-State Expression & Action Sheet (`16:9` Wide, `3×2` Grid)**:
   - States: `IDLE / HAPPY`, `WAVING HELLO`, `RUNNING TASK / FOCUSED`, `CODE REVIEW / INSPECTING`, `WAITING / SLEEPY`, and `FAILED / OVERHEATED`.
   - Purpose: locks the character's emotional range, HUD/LED eye telemetry (`^ ^`, `? ?`, `X X`), and signature props (magnifying glass, holographic clipboard, steam vents) prior to sprite generation.

## Phase 3 — Six `2×2` `#FF00FF` Chroma-Key Pose Sheets

> **Critical Lesson (Clank vs. Bobby Bones & Blaze):** Do **not** ask image generators for `8×1` horizontal sprite strips (`1536×208`). Wide strips cause severe aspect-ratio crowding, inconsistent character scale across rows, clipped limbs, and interior transparency holes. Instead, generate **six `1:1` square `2×2` key-pose sheets** (`4` full-body poses per sheet = `24` master key poses) on a **100% flat, solid pure magenta (`#FF00FF`) background**.

Use the prompt templates in [references/sprite-v2-contract.md](references/sprite-v2-contract.md) and pass the locked **Master Hero Avatar** and **Turnaround Sheet** as reference images for all six sheets:

1. **`chroma_idle_gaze.png` (`2×2`)**:
   - `TL`: Neutral front standing idle (`Row 0` & `Row 9–10` base body).
   - `TR`: Alert front standing idle with slightly raised posture.
   - `BL`: Standing front body, head/gaze turned `45°` front-right (`NE`).
   - `BR`: Standing front body, head/gaze turned `45°` front-left (`NW`).
2. **`chroma_cardinal_gaze.png` (`2×2`)**:
   - `TL`: Full `90°` right profile (`E`).
   - `TR`: `135°` back-right three-quarter view (`SE`).
   - `BL`: Full `180°` back view (`S`).
   - `BR`: Full `270°` left profile (`W`).
3. **`chroma_run_right.png` (`2×2`)**:
   - Four distinct right-facing locomotion phases (`Contact`, `Down/Pass`, `Push-off`, `High-stride`). Mirror horizontally in the compiler to synthesize `Row 2` (`running-left`) with zero scale drift.
4. **`chroma_wave_jump.png` (`2×2`)**:
   - `TL`: Friendly wave right arm raised low.
   - `TR`: Friendly wave right arm raised high.
   - `BL`: Deep pre-jump crouch compressed toward the floor.
   - `BR`: Airborne jump apex with limbs/thrusters flared.
5. **`chroma_fail_wait.png` (`2×2`)**:
   - `TL`: Startled jolt (`! !` eyes, warning flare).
   - `TR`: Overheated/failed slump (`X X` eyes, smoke curls).
   - `BL`: Patiently waiting, tapping foot/claw (`? ?` eyes).
   - `BR`: Sleepy standby (`- -` eyes, dimmed core).
6. **`chroma_work_review.png` (`2×2`)**:
   - `TL`: Active task execution left stroke (typing/forging).
   - `TR`: Active task execution right stroke.
   - `BL`: Holding magnifying glass inspecting code/data.
   - `BR`: Approval nod with checkmark/clipboard telemetry.

### Non-Negotiable Chroma Prompt Rules

- Background must be **solid, unlit, flat `#FF00FF` magenta** with **zero ground shadow, zero floor grid, zero text labels, and zero divider lines**.
- Never use magenta (`#FF00FF`) or hot pink inside the character's own palette; use warm amber, orange, cyan, gold, emerald, or bone white so edge-local chroma despill never erodes interior pixels.
- Leave at least `12%` solid `#FF00FF` margin around every pose in all four quadrants so claws, ears, antennas, and props never clip a quadrant border.

## Phase 4 — Deterministic `sprite_version: 2` Atlas Compilation & QA

Compile the six `2×2` chroma-key sheets into the `1536×2288` RGBA atlas (`8` columns × `11` rows of `192×208` cells = `73` populated frames + `15` transparent padding cells) and run structural verification:

```bash
python3 skills/smoky-character-studio/scripts/compile_pet_atlas.py --help
python3 skills/smoky-character-studio/scripts/compile_pet_atlas.py verify \
  --atlas <path/to/spritesheet-extended.png> \
  --slug <character-slug> \
  --out-dir <path/to/output-dir> \
  --pretty
```

When writing a character-specific pose synthesizer or using `compile_pet_atlas.py`, enforce these five deterministic compiler invariants:

1. **Edge-Local `#FF00FF` Chroma Despill & Zero Residue**:
   - Strip 8px quadrant borders before connected-component bounding-box extraction so border artifacts never merge with the character silhouette.
   - Suppress magenta spill on semi-transparent and edge pixels (`excess = min(R, B) - G`; reduce `R` and `B`, boost `G` slightly) and zero out RGB channels wherever `alpha == 0`.
   - Required QA gates: `transparent_rgb_residue_pixels == 0`, `opaque_chroma_key_pixels == 0`, `chroma_fringe_pixels == 0`, `semi_transparent_fringe_pixels == 0`, and `edge_touch_frames == 0`.
2. **Torso/Hip Horizontal Centroid Registration (`center_x = 96.0`)**:
   - Compute horizontal center of mass from the **middle torso band (`38%–76%` of normalized height)** rather than the full bounding box. That way a raised waving arm, wide pincer, or magnifying glass never pulls the standing body off `center_x = 96.0`.
3. **True `44px` Jump Arc (`Row 4`)**:
   - Anchor standing idle feet to `baseline_bottom_y = 201` (or `202`).
   - Place `r4c0` (crouch) and `r4c4` (landing) on the floor baseline (`landing_delta_pixels == 0`), `r4c1`/`r4c3` at `bottom_y = 183..186`, and `r4c2` (apex) at `bottom_y = 157..158` (`airborne_lift_pixels >= 40`, target `44px`), with `height_ratio <= 1.25`.
4. **Locked-Body / U-Collar Socket 16-Angle Clockwise Gaze Ring (`Rows 9–10`, `0°–337.5°`)**:
   - Naive row slicing across 16 turnaround frames causes center drift and width-ratio jumps at row boundaries (`157.5° → 180°` and `337.5° → 0°`).
   - Instead, **freeze the `r0c0` standing lower body/carapace across all 16 frames** (`Rows 9–10`) and composite the rotating head/visor into a feathered U-shaped collar socket (or shift the HUD visor reticle along the `16` compass angles `0°..337.5°` inside the locked chamber).
   - Required QA gates: `maximum_center_drift_pixels == 0.0` (hard limit `<= 6.0`) and `maximum_width_ratio == 1.0` (hard limit `<= 1.18`).
5. **Save `spritesheet-extended.png` *Before* Computing Manifest SHA-256**:
   - Always finish writing `spritesheet-extended.png` (including any PNG optimization flags) **before** computing its SHA-256 digest so `spritesheet-extended-manifest.json`, `validation-extended.json`, `pets-preflight.json`, and `pet-quality.json` record the exact same byte size and SHA-256 hash.

## Phase 5 — Preview Suite, Bundle, & Proof Shelf Packaging

1. **Generate the Standard 12-GIF Preview Suite + Contact Sheet + Zip Bundle**:
   - Use `compile_pet_atlas.py verify --render-previews --bundle-zip` to emit:
     - `spritesheet-extended-manifest.json`, `validation-extended.json`, `pets-preflight.json`, `pet-quality.json`
     - `contact-extended.png` (labeled `8×11` dark-card grid)
     - Per-state GIFs: `idle.gif`, `running-right.gif`, `running-left.gif`, `waving.gif`, `jumping.gif`, `failed.gif`, `waiting.gif`, `running.gif`, `review.gif`, `look-clockwise.gif`
     - Composite GIFs: `all-states.gif` (`3×3` labeled board) and `full-reel.gif` (`5×2` 10-panel showcase)
     - `<slug>-pet-v1.zip` containing the atlas, manifests, contact sheet, and previews.
2. **Respect Repository Hygiene for Binary Media**:
   - Never commit multi-megabyte PNGs, GIFs, or ZIP bundles directly into source-only product repositories when an external immutable release shelf is configured.
   - Upload binary media to the repository's designated immutable asset shelf (or attach to a release tag), verify `200 OK` / release asset digests, and commit only the design specification (`docs/design/<slug>-character-and-pet-rig.md`) and text/JSON proof (`proof/<slug>-pet-avatar-<date>/PROOF.md`).
