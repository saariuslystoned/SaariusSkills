---
name: emdash-motion-studio
description: Build interactive 3D isometric cutaway figures, multiplane occlusion shadowbox stages, pigment-drift watercolor backgrounds, choreographed timeline/scroll animations, and optional tactile foil/tear-off passes for EmDash Astro websites or standalone HTML. Operates as a progressive GrillTrack animation workflow: first renders 5 noticeably different start-to-finish stage frameworks (validated via validate_picker.py) so the user can lock the overall build framework, then builds, verifies, and grills one core animation piece at a time on the locked cumulative canvas.
---

# EmDash Motion Studio

Create tactile, engineered, zero-dependency animations for EmDash CMS storefronts, editorial sites, and standalone interactive showcases through a **progressive GrillTrack workflow**.

## 1. Choose the Animation Mode (and Optional Add-Ons)

Every motion request maps to one of four selectable zero-dependency modes (or a hybrid combining them):

| Mode | Engine / Pattern | Best For | Signature Mechanics |
| --- | --- | --- | --- |
| **Mode A1 — Illustrated Isometric Cutaway** | `assets/core.js` (`mountFigure` — Colorfigures style) | Playful mechanical explainers, editorial diagrams, coffee/tea gear, arcade/claw games, "how it works inside" illustrations | Hand-inked 3D orthographic SVG outlines, warm paper fill, 360° drag turntable (`turn:'full'`), `See-through` ghosted shell (`xrGhost`) revealing 30–60 real moving internal parts, live lit `Labels` (`xrCallouts`), clickable parts (`act`), and EmDash `storefront` chrome |
| **Mode A2 — Studio WebGL 3D PBR + Live Screen Texture** | `assets/vendor/three.min.js` (`THREE.WebGLRenderer` PBR style) | Sleek SaaS/e-commerce product & hardware heroes (like `DinkusKit.com`), realistic laptops/devices with live UI workflows, fulfillment/packaging assembly lines | Physically-based anodized metal, glass, fabric, and corrugated kraft materials (`ACESFilmicToneMapping`, `PCFSoftShadowMap`, studio lighting), high-DPI live `THREE.CanvasTexture` screen UI, articulated `THREE.Group` hinges, and close-up guided camera choreography (`camera.position` / `camera.lookAt` tracking) |
| **Mode B — Multiplane Occlusion Stage + Pigment Drift** | `assets/multiplane.js` (`mountMultiplane`) | Hero banners, transit/delivery trackers, architectural scenes, editorial storytelling, watercolor/ink-bleed sections | 3-layer shadowbox (`background` stage, animated `midground` vehicles/actors, `foreground` occlusion masks that actors pass *behind*), **Artwork-Led HUD** where the moving actor *is* the progress bar (`stops`), **Pigment Drift** SVG turbulence/watercolor wash, and 3D **Exploded Multiplane View** (`?explode=1`) |
| **Mode C — Choreographed Timeline / Scroll Stage** | `assets/choreo.js` (`mountChoreo`) | Technical showcases, orbital/spatial diagrams, multi-step process choreography, scroll-linked or scrubbed data stages | Normalized timeline (`t` in `0..1`) with named `cues`, camera keyframe interpolation (`lerpCam`), live telemetry HUD (`hud`), and `'autoplay' \| 'scroll' \| 'scrub'` playback |
| **Mode D — Tactile Paper, Holographic Foil & Tear-Off Pass** *(Subject-Specific Option)* | `assets/tactile-audio.js` (`mountReceipt`, `mountRubberStamp`, `renderBarcodeSvg`, `mountFoilTicket`) + [references/tactile-foil-and-web-audio.md](references/tactile-foil-and-web-audio.md) | Promotional coupons (`SAVE20`), golden/event tickets, gift cards, thermal order receipts, dry-ink rubber stamps (`[PAID · STRIPE TEST]`, `[SHIPPED · PB SANDBOX]`), COA badges | **Select only when the subject is a ticket, coupon, receipt, stamp, card, or badge — never force on Mode A/B/C scenes.** Includes `Ephemera` stationery primitives (`conic-gradient` serrated thermal receipt with `steps(28, end)` line-feed reveal & deterministic FNV-1a SVG barcode `renderBarcodeSvg(code)`, plus `<feTurbulence>` + `<feDisplacementMap>` dry-ink rubber stamp with `cubic-bezier(0.22, 1, 0.36, 1)` thud), 3D tilt-reactive holographic foil sheen, punched perforation line with `tearProgress` (`0..1`), and `See-through / X-Ray` security thread view (`?xr=1`) |

### Optional Add-On: Procedural Web Audio Micro-Foley (Never Forced)
- **Strictly Opt-In:** Not every animation needs sound. **Never force Web Audio onto an animation by default.** Include zero-file `AudioContext` micro-foley (`createMicroFoley()` in `assets/tactile-audio.js` or custom synthesized chimes like a `"Cha-Ching!"` cash-register bell, mechanical detent clicks, paper-tear bandpass noise bursts, stamp thuds, thermal print hums) **only when the user asks for sound or tactile audio feedback**, and unlock `AudioContext` on user interaction. See [references/tactile-foil-and-web-audio.md](references/tactile-foil-and-web-audio.md) and [references/grilltrack-progressive-workflow.md](references/grilltrack-progressive-workflow.md).

### Companion Skill Boundary (`emdash-surface-fx`)
- Use `emdash-motion-studio` for **bespoke 3D stages (Mode A1 Illustrated SVG Cutaway & Mode A2 Studio WebGL Three.js PBR), 3-layer multiplane shadowboxes (Mode B), and choreographed timeline stages (Mode C)** (plus Mode D tactile stationery stages).
- For **page-level surface effects, Bayer/halftone shaders (`dithercn`), viewport WebGL pooling, obstacle-aware text reflow (`@chenglou/pretext`), live number tickers (`number-flow`), hand-drawn SVG annotations (`rough-notation`), and card micro-interactions**, use the companion skill [`$emdash-surface-fx`](../emdash-surface-fx/SKILL.md).

---

## 1B. High-Leverage Website Placement Guide (Strong Defaults + Open Experimentation)

> **Proven Starting Points, Not Rigid Limits:** The placements below map each mode and companion surface effect to concrete, high-value surfaces across **E-Commerce, SaaS, Docs, Editorial, and Portfolio** websites. Treat these as battle-tested defaults—**users and agents are free to experiment, remix, and apply any mode or effect anywhere on a site**.

| Mode / Surface Family | Locked DinkusKit / EmDash & Cross-Site Placements | E-Commerce, SaaS, Docs, Editorial & Portfolio Examples |
| --- | --- | --- |
| **Mode A1 & Mode A2 (3D Object / Hardware / Cutaway Stage)** | **Marketing Homepage Hero** (*"How the platform works"* in 1 click, e.g., **1-Click MacBook Order-to-Box** in either **Mode A2 Studio WebGL PBR** with live `template-store` screen + guided camera tracking or **Mode A1 Illustrated Cutaway**), **Flagship Hardware/Product Breakdown**, **Interactive Feature Spotlight**. | **E-Commerce:** Sleek 3D PBR MacBook + overhead tee & box fulfillment line (`Mode A2`) or editorial cutaway explainer (`Mode A1`).<br>**SaaS:** 1-click "Click device to run live screen workflow" hero.<br>**Docs / Editorial / Portfolios:** Interactive mechanism figure or industrial design case study. |
| **Mode B (Multiplane Depth + Pigment Drift)** | **Live Order Tracking / Shipping Status Header** (`/orders/[id]`, `/checkout/success` with delivery van crossing behind bridge trusses under a time-of-day sky), **Brand Story / Chapter Divider**, **Weather/Location Banner**. | **E-Commerce:** Post-purchase fulfillment tracker where the courier vehicle *is* the progress bar.<br>**Editorial / Portfolios:** Full-bleed chapter opener with SVG watercolor pigment wash.<br>**SaaS:** Global region/edge transit header. |
| **Mode C (Scroll / Step Choreographed Data Flow)** | **Landing Page "Under the Hood" Architecture Section**, **Merchant Onboarding Journeys** (step-by-step visual pipeline as you configure `Stripe -> D1 -> Shipping`), **Interactive Documentation Diagrams**. | **SaaS / Docs:** Scroll-linked or step-synced request lifecycle (`Edge -> Auth -> DB -> Webhook`).<br>**E-Commerce:** Setup wizard accompaniment.<br>**Portfolios:** System architecture walkthrough. |
| **Mode D (Opt-In Tactile Paper, Foil, Tear-Off & Thermal Receipt)** | • **Perforated Foil Tear-Off Stub:** Storefront Promo Banner / Drop Card where tearing the perforation **purely reveals the coupon code + copies it to clipboard** (zero backend coupon engine required by default, optional callback hook if wired later).<br>• **Serrated Thermal Receipt + Dry-Ink Rubber Stamp:** `/checkout/success` Order Confirmation Receipt (`conic-gradient` serrated edges, FNV-1a SVG barcode, `steps()` thermal feed, `[PAID]` rubber stamp thud). | **E-Commerce:** Seasonal drop pass, VIP ticket, or post-checkout itemized thermal receipt with `[PAID]` / `[SHIPPED]` stamp.<br>**SaaS / Portfolios:** Event pass, Founder badge, or verifiable release certificate. |
| **`emdash-surface-fx` (Page-Level JS Polish)** | • **`dithercn` (Bayer/Blue-Noise Shaders, SVG Patterns, CSS Masks):** Hero/section backgrounds, retro-editorial image hover treatments, dithered section dividers bound to `tokens.css` `light-dark()`.<br>• **`NumberFlow` / Tabular Ticker:** Cart drawer subtotals, item quantity badges, pricing plan toggles (monthly/annual), live dashboard metrics.<br>• **`RoughNotation` (Hand-Drawn SVG Callouts):** Circling *"Free Shipping"*, underlining sale prices or key docs takeaways when scrolled into view.<br>• **`@chenglou/pretext` (Obstacle Text Wrap):** Best reserved for **editorial lookbooks / magazine-style story pages** (or auto-floating illustrations); **not needed on standard e-commerce product/checkout pages** where `dithercn`, `NumberFlow`, `mountHoverTilt`, `RoughNotation`, and `Ephemera` receipts carry the real storefront value.<br>• **Vanilla 3D Card Tilt (`mountHoverTilt`):** Featured product cards, bento grid cells, badge cards. | Enhances native Astro/HTML layout blocks in-place across storefronts, SaaS pricing pages, documentation callouts, longform editorial essays, and portfolio grids without full stage mounts. |

---

## 2. Progressive GrillTrack Animation Workflow (Core Contract)

For any non-trivial or multi-piece animation (e.g., MacBook + Shipping Box + Thermal Printer, or a multi-stage product explainer), **never build the entire animation in one monolithic shot**. Run the **Progressive GrillTrack Animation Loop** documented in [references/grilltrack-progressive-workflow.md](references/grilltrack-progressive-workflow.md):

### Round 0 — 5 Materially Distinct End-to-End Build Frameworks
0. **Align on Website Placement + Single User Trigger (`chrome: 'stage-only'` Default) + 3D Engine Style (`Mode A1` vs. `Mode A2`):**
   - Start Round 0 by locking **where the animation lives on the website** (e.g., Marketing Homepage Hero card, `/orders/[id]` header, `/checkout/success` receipt) and its **single natural user trigger** (e.g., clicking the 3D MacBook or a single hero CTA).
   - **When starting a 3D stage (Mode A), explicitly ask whether the user wants:**
     - **Mode A1 — Illustrated Isometric SVG (`assets/core.js` — Colorfigures style):** Hand-inked outlines, warm paper fill, and 30–60 part mechanical cutaways (`See-through` + `Labels`), OR
     - **Mode A2 — Studio WebGL Three.js PBR (`assets/vendor/three.min.js` — Realistic 3D + Live Screen Texture):** Sleek physically-based anodized metal/glass/fabric/kraft materials, high-DPI live `THREE.CanvasTexture` UI on device screens, and close-up guided camera tracking.
   - Default to **`chrome: 'stage-only'`** with **zero April Zhu multi-button debug pills (`Framework 1..5`, `See-through`, `Labels`, `Preview Start`, wobble sliders, or palette swatches)** on the production stage unless the user explicitly asks for a multi-button control panel.
1. **Propose & Render 5 Noticeably Different Stage Frameworks:**
   - Before building detailed mechanisms, author an interactive 5-candidate framework explorer (e.g., `dinkuskit-macbook-frameworks.html`) where each candidate (`?candidate=1..5`) lays out a **materially distinct start-to-finish spatial architecture** (such as *1. Horizontal Assembly Line Desk*, *2. Isometric Command Island + Multiplane Horizon*, *3. Exploded 3-Tier Vertical Stack*, *4. Split-Screen Cockpit + Live Telemetry/Coupon HUD*, *5. Radial Turntable Workshop*).
   - Every candidate must show the **entire build from start (`t = 0.0`) to mid-action (`t = 0.5`) to finish (`t = 1.0`)** so the user can visualize the complete animation start-to-finish before choosing a direction.
2. **Validate the GrillTrack Picker Manifest:**
   - Write `.grilltrack/work/<round-id>/picker-manifest.json` (`schema_version: "grilltrack-picker/v0.1"`, 5 neutral candidates with no `recommended: true`, `controls: {keyboard: true, pointer: true, mobile: true}`, `production: false`) and validate it with `skills/grilltrack/scripts/validate_picker.py`.
3. **Render Headless Chrome Framework Screenshots & Pause for Lock:**
   - Capture high-resolution headless Chrome PNGs of all 5 candidates (across start/mid/end states) and present them so the user locks **one overall framework** before Piece 1 begins.

### Rounds 1..N — Piece-by-Piece Build, Render & Grill Loop (Cumulative Canvas)
Once the user locks one of the 5 frameworks, build the animation **one core piece at a time** on the locked canvas (embedded in its real website placement context with `chrome: 'stage-only'` and zero debug chrome):
1. **Piece 1 Build, Verify & Grill:** Complete Piece 1 on the locked framework (e.g., 3D MacBook lid opening + live storefront checkout workflow + `"Cha-Ching!"` / `$$$ · Order #` or `See-through` cutaway), render proof screenshots/motion via `scripts/verify_motion.py`, and **stop to grill the user on Piece 1's look and animation** before moving on.
2. **Piece 2 Build, Verify & Grill:** Keep Piece 1 locked on the canvas, build Piece 2 (e.g., overhead folded graphic tee + thermal packing slip dropping into open corrugated box + 4-flap fold + kraft tape seal), render proof frames/motion, and **grill the user on Piece 2** to confirm it looks and animates right.
3. **Piece 3 Build, Verify & Grill (and so on):** Keep Pieces 1 & 2 locked on the canvas, build Piece 3 (e.g., Pitney Bowes 4×6 thermal printer + top label slap + mail chute into outbound tote of packed boxes), render proof frames/motion, and **grill the user on Piece 3**.

---

## 3. EmDash & Stitch Contract (One-Way Input, Zero Stitch Round-Tripping)

- **Never use Google Stitch to author or preview animations.** Stitch is a static UI screen generator; round-tripping motion through Stitch wastes time and flattens interactivity.
- **One-way design intake:** When working inside an EmDash repository (especially one designed with `emdash-stitch-design`), read:
  1. `design.md` and `.stitch/DESIGN.md` (atmosphere, line weight, typography role system, non-goals).
  2. `src/styles/tokens.css` (`@layer base` CSS custom properties using `light-dark()`).
- **Automatic token binding:** All engines (`core.js`, `three.min.js` stages, `multiplane.js`, `choreo.js`) read `--color-canvas`, `--color-surface`, `--color-ink`, `--color-muted`, `--color-border`, `--color-accent`, and `--color-shadow` from their host container when mounted in an EmDash site, falling back to warm paper (`#f2efe7`) and deep ink (`#231e16`) when standalone.
- **Scoped container mounting (`target`):** Never wipe `document.body` inside an EmDash page. Pass `target: containerEl` (or build with `scripts/build.py input.html Out.astro --astro`) so the animation mounts cleanly inside a scoped `<div class="emdash-motion-stage">`.
- **Storefront UI chrome (`chrome: 'storefront' | 'stage-only' | 'full'`):**
  - `'full'` (standalone default): Title header, interactive action buttons, stats, wobble slider, palette swatch picker, view buttons, and footer.
  - `'storefront'` (EmDash default): Interactive stage + action buttons + compact `See-through` / `Labels` / `Turntable` pills; hides debug wobble sliders, colour swatch pickers, standalone headers, and footers.
  - `'stage-only'`: Pure interactive stage without control bars.

Read [references/astro-integration.md](references/astro-integration.md) for EmDash Astro component props, `defineBlockComponents` wiring, and `FEATURE_MAP.md` hooks.

---

## 4. Mode A1 & Mode A2: 3D Stages (`assets/core.js` Illustrated Cutaway & `assets/vendor/three.min.js` Studio WebGL PBR)

### Mode A1 — Illustrated Isometric Cutaway (`assets/core.js` — Colorfigures Style)

#### Truth First (How the Real Thing Works)
1. **Write how it really works** in a top-of-script comment block before any geometry: step-by-step material path (water in tank → pump → boiler → group → cup; order in → edge router → payment vault → inventory rack → thermal printer → shipping box). Every button triggers a real physical step.
2. **Write the parts list** grouped by `case`, `structure`, `mechanism`, `power`, `controls`. Aim for **30–60 real internal parts** in `See-through` (`xrGhost`): motors, gears, shafts, springs, boards, sensors, wiring, tubes, brackets.
3. **Every part is held by another:** Nothing floats. Wires and tubes run port-to-port along walls and floors. Every driving part touches what it drives (gear rim to gear rim, shaft to bracket).

#### Coordinates, Camera & Depth Sorting (No Depth Buffer)
- `x` = depth (front face at `x = W`), `y` = width (`+y` goes viewer-left at default view), `z` = up (`z = 0` ground). Scale ≈ 1 unit per cm (`size: [W, D, H]`).
- **Never write a fixed back-to-front drawing order.** Pass every separate part through `byDepth([{ at:[x,y,z], box:[[x0,y0,z0],[x1,y1,z1]], svg }])` and **give every part a `box`**.
- **Faces (`vis(n)` / `facing(n)`):** Draw a face and everything mounted on it only when it faces the viewer. Draw front-mounted parts *after* the body when facing the viewer and *before* the body when facing away.
- **Wrapping shapes & tall poles:** Use `openShell(A, B, colour, contents)` and `nearHalf()` / `farHalf()` for open containers. Split tall poles/columns by height alongside adjacent parts so sorting loops never form.
- **Real backs:** Model service panels, vents, cords, and ratings plates on the back (`x = 0`). Once verified from all 360° angles, set `turn: 'full'`.

#### Look, See-Through & Labels
- **Shading & Ink:** Palette `m = {l, m, d}` shaded with `tone(normal, m)` (sunlit exterior) or `toneI(normal, m)` (interior/props). Materials: `METAL`, `CLEAR`, `CERAMIC`, `DARK`, or `matOf('#hex')`. Wrap outer silhouettes in `hullInk(points, ~2.8)`.
- **Cast shadow:** `castShadow(points, z0, clip)` drawn before the body (clipped to `boardTop(...)` when standing on a `board(...)`).
- **See-through & Labels:** In `scene(st, m)`, compute `const k = ease(st.xr || 0);`. When `k > 0`, wrap the shell in `xrGhost(body, '', k, OUT, 0, W, m)` (or `xrGhostRings` / `xrUnder`) and draw the internal mechanism on top at `<g opacity="${f(k)}">`. When `k > 0.6`, append `xrCallouts([{ at:[x,y,z], text:'PART NAME', on: isWorking }], bounds)`. Call `xrMount(() => ui, captionFn)` after `mountFigure`.
- **Reserved Globals in `core.js`:** Never redeclare `PALS METAL CLEAR CERAMIC DARK INK SHADOW C S OX OY VIEW RC RCZ VIEW_NAMES TURNS YAW0 PITCH0 YAW PITCH CAM_R CAM_U CAM_V CAM_D CAM_B0 CAM_LIM camBasis setCam camDot camTo rotV yawTurn rotXY P0 P Dv depthOf boxMid sepOrder byDepth nearHalf farHalf openShell f pd sp arcUV rrUV rectUV ellUV PX PY PZ on sub dot cross norm avg vis facing SHADOW_K AZ_MIN AZ_MAX SHADOW_LEN L SH setLight LIN SOFT step3 tone toneI mix matOf ease ink fill face shape line loft hull hullInk box extrude cyl cylX rod txM tx txY castShadow BOARD WOOD boardTop board act tag clipTo INK_REF_VB INK_K inkScale CORE_CSS filterFor bakeNoise mountFigure xrCallouts xrGhost xrGhostRings xrUnder xrWrap xrMount mountKeypad`.

Inspect the reference figures in `assets/examples/toaster.html`, `assets/examples/lamp.html`, `assets/examples/claw.html`, `assets/examples/dinkuskit-macbook-commerce.html`, and `assets/examples/dinkuskit-macbook-illustrated.html`.

### Mode A2 — Studio WebGL 3D PBR + Live Screen Texture (`assets/vendor/three.min.js`)
- **Vendored Three.js r128 (`assets/vendor/three.min.js`):** Load via `<script src="../vendor/three.min.js"></script>` (or `/skills/emdash-motion-studio/assets/vendor/three.min.js`) so the 589KB bundle is not inlined into `.astro` text checks (`/\bany\b/u`).
- **PBR Studio Lighting & Renderer:** Initialize `new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true })` with `THREE.ACESFilmicToneMapping`, `renderer.shadowMap.enabled = true` (`THREE.PCFSoftShadowMap`), procedural `THREE.PMREMGenerator` studio environment reflections, key/fill/rim directional and spot lights, and soft contact shadows.
- **High-DPI Live `THREE.CanvasTexture` Screen UI:** Render dynamic 2D canvas interfaces (`1600×1000`) onto 3D device displays (`texture.needsUpdate = true`) so users can watch real product workflows (e.g., `template-store` Product Page → Add to Cart → `/cart` → Stripe Checkout → Payment Approved) up close in 3D.
- **Articulated `THREE.Group` Hinges & Physical Separation:** Use pivot groups (`THREE.Group`) for laptop lids (`0° → 108°`), 4 corrugated box flaps (`0° → 90°`), thermal printer tamp arms, and mail chutes. Physical merchandise drops into boxes from an **overhead inventory shelf/tray at the packing station** (never out of the laptop!).
- **Close-Up Guided Camera Choreography:** Smoothly interpolate `camera.position` and `camera.lookAt` across normalized timeline `t` (`0..1`)—zooming in on the laptop display during screen checkout, then panning right across the roller conveyor to follow packing, folding, taping, 4×6 top-labeling, and chute dispatch into the outbound tote.
- **Headless Verification Compatibility:** Keep `preserveDrawingBuffer: true` on the WebGL renderer and include a synchronized `#fig` SVG overlay/telemetry layer so `scripts/verify_motion.py` captures crisp WebGL screenshots and passes DOM/SVG geometry audits (`has_fig_svg` + `svg_primitive_count > 5` + zero `NaN`). Inspect `assets/examples/dinkuskit-macbook-pbr.html`.

---

## 5. Mode B: Multiplane Occlusion Stage + Pigment Drift (`assets/multiplane.js`)

Use `mountMultiplane(cfg)` when building layered architectural/editorial scenes, transit/fulfillment route visualizers, or watercolor/ink-bleed hero canvases. Read [references/multiplane-and-pigment-drift.md](references/multiplane-and-pigment-drift.md) for full patterns.

1. **Three-Layer Shadowbox Contract:**
   - `background(st, t, ctx)`: Distant skyline, terrain, sky/water wash, timelapse lighting, and optional `renderPigmentDrift(...)` watercolor/ink bleed. No foreground occluders or moving midground vehicles.
   - `midground(st, t, ctx)`: Moving actors (trains, delivery vans, ferries, gondolas, signal pulses) positioned deterministically from normalized progress `t` (`0..1`).
   - `foreground(st, t, ctx)`: Occlusion masks registered to the background plate (bridge towers, truss spans, highway overpasses, glass conservatory arches, columns). Actors in `midground` naturally pass *behind* these structures.
2. **Artwork-Led UI (`stops` & `stats`):**
   - Let the artwork lead: the moving midground actor *is* the progress indicator, paired with a minimal top-left status header (`eyebrow`, `title`), top-right metric (`stats`), and bottom route/timeline stop bar (`stops: [{ label, status, at }]`).
3. **Exploded 3D Multiplane Inspection (`?explode=1`):**
   - `multiplane.js` includes a built-in `Layers` toggle (`?explode=1`) that tilts and separates the Background, Midground, and Foreground planes in 3D perspective (`rotateX`/`rotateY`/`translateZ`) like a physical shadowbox camera rig.

Inspect `assets/examples/harbor-transit-multiplane.html`.

---

## 6. Mode C: Choreographed Timeline / Scroll Stage (`assets/choreo.js`)

Use `mountChoreo(cfg)` when building multi-cue technical narratives, orbital/telemetry stages, or scroll-driven 3D diagrams.

- **Normalized Timeline (`t` in `0..1`) & Named Cues:** Define `cues: [{ id, label, range: [t0, t1] }]`. Use `subRange(t, t0, t1)` and `easeInOutCubic` / `lerpCam` so every frame is a pure deterministic function of `t`.
- **Playback Modes:** `mode: 'autoplay' | 'scroll' | 'scrub'`. Even when `mode: 'scroll'` is used on a page, `?t=0..1` overrides scroll position for deterministic headless Chrome verification.

Inspect `assets/examples/argon-orbital-choreo.html`.

---

## 7. Build & Verify Pipeline (`scripts/build.py` & `scripts/verify_motion.py`)

Never hand over an unverified framework or piece. Run the build and headless Chrome verification loop (at most 3 fix iterations) at **both Round 0 (5 frameworks)** and **every Piece 1..N checkpoint**:

1. **Author the source HTML** next to `core.js`, `multiplane.js`, or `choreo.js` (or referencing `../core.js`).
2. **Build standalone HTML and/or EmDash Astro component:**
   ```bash
   # Standalone self-contained HTML artifact
   python3 "<skill-dir>/scripts/build.py" scene.html OUT.html

   # Zero-dependency EmDash Astro component (scoped container + tokens.css bridge)
   python3 "<skill-dir>/scripts/build.py" scene.html src/components/motion/HeroMotion.astro --astro --chrome storefront
   ```
3. **Run deterministic headless Chrome verification:**
   ```bash
   python3 "<skill-dir>/scripts/verify_motion.py" OUT.html --out-dir .grilltrack/proof/motion
   ```
   `verify_motion.py` automatically captures retina PNG screenshots across:
   - Custom `<meta name="motion-probes" content="...">` probes (including `?candidate=1..5` for Round 0 framework explorers),
   - Camera angles (`yaw=45,135,225,315` closed + `xr=1&labels=1` cutaway) for Mode A,
   - Timeline scrubs (`t=0.0,0.25,0.5,0.75,1.0` + `explode=1` multiplane check) for Modes B & C,
   - Interactive button sequences (`--press "Push the lever@200"`),
   - Mobile viewport (`390x844`),
   - DOM & geometry health audit: fails closed if `<html data-errors="...">` is non-empty, if `NaN` appears anywhere in the rendered DOM/SVG, or if the `<svg>` bounding box is empty.
4. **Inspect the rendered PNGs** visually to confirm no depth-sorting inversions, no floating parts, no clipped labels, and clean mobile layout before grilling the user on the active piece.
