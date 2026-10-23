# Mode A2: Studio WebGL Three.js PBR & Procedural Binary `.glb` Engineering

This reference captures the architecture and hard-won engineering guardrails for **Mode A2 (`assets/vendor/three.min.js` + `assets/vendor/GLTFLoader.js`)**, covering both full-stage hardware workflows (`assets/examples/dinkuskit-macbook-pbr.html`) and compact multi-canvas 3D icon/product stages (`assets/examples/dinkuskit-plugin-cubes-pbr.html`).

---

## 1. Dual-Delivery Binary glTF 2.0 (`.glb`) Pipeline & Paired CMS `.webp` Poster

When building brand-faithful 3D product icons or hardware assemblies, avoid raw runtime primitive soup (`THREE.BoxGeometry` / `THREE.CylinderGeometry`), which creates internal z-fighting at corners and cannot express recessed cutouts or mitered architectural roofs. Instead, generate deterministic binary glTF 2.0 (`.glb`) assets in Python and pair each 3D stage with an EmDash Media Library `.webp` poster:

1. **Deterministic Binary `.glb` Serializer**:
   - Pack embedded procedural PNG textures (`baseColorTexture`, `emissiveTexture`, `normalTexture`), `POSITION` / `NORMAL` / `TEXCOORD_0` float32 buffer views, and uint32 `SCALAR` triangle indices into a single self-contained `.glb` binary chunk.
   - Expose articulated parts as named top-level glTF nodes with local pivot `translation` origins (`card_assembly`, `stratum_bottom`, `stratum_middle`, `stratum_top`, `flap_left`, `flap_right`, `tape_back`, `tape_top`, `tape_front`).
2. **Direct HTTP `.glb` Fetch + `file:`-Only Base64 Fallback**:
   - Write `.glb` files to `public/models/...` for production HTTP/HTTPS serving (`new THREE.GLTFLoader().load(glbUrl, onLoad, undefined, onError)`) AND emit a deterministic base64 JS bundle (`assets/vendor/plugin-cubes-glb.js` setting `window.DINKUS_PLUGIN_CUBES_GLB_B64`) decoded via `new THREE.GLTFLoader().parse(arrayBuffer, '', onLoad)`.
   - **Never load the multi-megabyte base64 JS bundle on live HTTP/HTTPS pages.** Gate `<script>` injection of `plugin-cubes-glb.js` strictly behind `if (window.location.protocol === 'file:' && !window.DINKUS_PLUGIN_CUBES_GLB_B64)`. Over `http:` and `https:`, fetch only the individual `public/models/.../*.glb` binaries (`338–863 KB` raw, `~120–280 KB` brotli) needed by the current page, while `scripts/verify_motion.py` still renders identically over `file://` in headless Chrome without `fetch()` CORS errors.
3. **Paired `.glb` 3D Stage + EmDash Media Library `.webp` Poster (`onModelLoaded` Progressive Reveal)**:
   - Upstream EmDash's `/_emdash/admin` Media Library (`EXTENSION_TO_MIME`, `GLOBAL_UPLOAD_ALLOWLIST`, and `/_emdash/api/media/file/[...key].ts` `SAFE_INLINE_TYPES`) is designed for editorial raster images (`image/webp`, `image/png`, `image/jpeg`, `image/avif`), video, audio, and PDFs; it serves non-allowlisted binary formats with `Content-Disposition: attachment`.
   - Therefore, keep 3D `.glb` geometry in `public/models/...` as a versioned code asset, and map its **2D `.webp` fallback poster** into the EmDash `/_emdash/admin` Media Library (`type: "image"`, seeded via `$media` in `seed/seed.json` and rendered via `<Image />` from `'emdash/ui'` or `/_emdash/api/media/file/<key>`).
   - Keep the WebGL container `[data-plugin-cube-stage][hidden]` and keep the 2D `.webp` poster visible during SSR and while `three.min.js`, `GLTFLoader.js`, and the `.glb` download over HTTP/HTTPS. Only set `stage.hidden = false`, add `.has-3d-cube` (which hides `[data-plugin-cube-fallback]`), and call `resize()` **inside `onModelLoaded`** after the `.glb` finishes parsing and mounting. If WebGL is unavailable, `prefers-reduced-motion: reduce` is active, or `.glb` loading fails, the CMS-editable 2D `.webp` poster remains visible with zero blank frames.

---

## 2. `MeshPhysicalMaterial` Upgrade & 6-Strip HDR Studio Cubemap

`THREE.GLTFLoader` (r128) constructs `THREE.MeshStandardMaterial` instances by default. To achieve MacBook-grade studio realism:

1. **6-Strip HDR Softbox `PMREMGenerator` Cubemap**:
   - Build an offscreen `THREE.Scene` (`0x030509` background) populated with 6 strategically angled HDR softbox `PlaneGeometry` strips (overhead key `[3.4, 3.2, 3.0]`, warm front-left grazing `[3.4, 2.5, 1.8]`, cool sky front-right rim `[1.8, 3.0, 4.5]`, back-top horizon `[3.6, 2.8, 1.8]`, low bevel kickers) and compile via `pmrem.fromScene(envScene, 0.0).texture`.
   - When rendering multiple `<canvas>` stages on one page (`Payments`, `Ship`, `Inventory`, `Commerce`), generate a per-renderer cubemap so WebGL textures are never shared across separate `WebGLRenderingContext` instances.
2. **Runtime `upgradeCubeMaterials()` Pass**:
   - Traverse `gltf.scene` and upgrade meshes to `THREE.MeshPhysicalMaterial` with `clearcoat`, `clearcoatRoughness`, `envMapIntensity`, and max hardware anisotropic texture filtering (`renderer.capabilities.getMaxAnisotropy()`).
3. **Material Classification & Tone-Mapping Guardrails**:
   - **`emSum` Glow Threshold Discipline**: If runtime material classification uses `isGlow = (em.r + em.g + em.b) > 0.08`, **never** assign a dark recessed cavity wall (`commerce_asterisk_wall`, `payments_slot_throat`) an `emissiveFactor` whose channel sum exceeds `0.08`. Keep recessed cavity walls near-zero emissive (`[0.002, 0.012, 0.006]`) so they frame glowing inlays with crisp dark contrast instead of turning into neon filaments.
   - **Avoiding `ACESFilmicToneMapping` White Blowout**: Under `THREE.ACESFilmicToneMapping`, high near-equal RGB emissive vectors (e.g., `[0.85, 0.98, 0.88]`) desaturate to pure white. Keep the primary brand channel dominant (`emissive: [0.42, 0.95, 0.64]` for emerald, `[0.08, 0.52, 0.94]` for cyan, `[0.98, 0.34, 0.04]` for orange) and ensure procedural texture generators fill the full stroke width with saturated brand chroma rather than a narrow white Gaussian spine.
   - **Disabling Shadow-Map Self-Occlusion on Recessed Emissive Floors**: When an emissive emblem (`commerce_asterisk_floor`) sits inside a recessed roof or wall cavity (`well_bot_y < well_top_y`) under a shadow-casting `DirectionalLight`, the surrounding opaque cutout rim will cast a dark shadow band across half the recessed floor. Explicitly set `node.castShadow = false; node.receiveShadow = false;` on recessed emissive floor and window materials, and keep roof cavity depth shallow (`~0.026` units) so isometric cameras (`camera.position.set(0, 2.35, 5.85)`) see the entire glyph without wall or shadow occlusion.

---

## 3. Topological Cutouts & Polar Monotonic Contours

When cutting a typographical or geometric emblem (such as DinkusKit's 6-bar blunt-ended `*` asterisk on the `Commerce` storefront roof) directly into a 3D rounded slab:

- **Never use radial star alternation (`r_outer`, `r_inner`) for a typographical asterisk**: Connecting outer tips directly to inner valleys produces a pointed star rather than rectangular bars.
- **Polar Monotonic Arm Profile `(u, v)`**:
  - Define a single arm's local `(u, v)` contour (`u` along the arm axis, `v` signed perpendicular offset across the bar width `±half_w`, with rounded outer corners and a flat blunt end cap at `u = arm_len`) such that the polar angle `atan2(v, u)` increases **strictly monotonically** from `-30°` to `+30°` (`18` points per arm × `6` arms = `108` vertices).
  - Ray-cast (`rounded_square_ray(cos θ, sin θ)`) from each of the 108 contour vertices to the outer rounded roof perimeter so the top deck, inner cavity bevel walls, and upward-facing (`+Y`) emissive floor form a watertight 1-to-1 quad ring with zero T-junctions or overlapping faces.

---

## 4. Articulated Hinges, Structural Cavity Walls & Timeline Sequencing

1. **Full-Height Structural Walls Under Outer Neon Edge Frames**:
   - When modeling a container whose top flaps open (`ship.glb`) or a chassis with a recessed slot (`payments.glb`), build full-height structural walls (`y = -0.96 .. +0.94`) right up to the outer 12-edge neon piping (`corner_offset = 0.958`) around a hollow dark interior cavity (`parcel_interior`). Never truncate the walls below the top edge frame, which leaves the neon cage floating in empty air when the flaps open.
   - Assign inner flap edges a non-emissive cut-kraft/structural rim material (`ship_kraft_rim`) rather than the outer neon edge material (`ship_orange_core`) so the center seam does not glow neon when the flaps open.
2. **Right-Hand Rule Hinge Rotation Signs (`tape_back` vs. `tape_front`)**:
   - For vertical packing-tape tabs hanging downward (`y_local < 0`) from top-edge pivots (`y = +0.96, z = ±0.88`), under right-handed X-axis rotation ($z' = y\sin\theta + z\cos\theta$):
     - Lifting the `-Z` back tab (`tape_back`, $z = -0.88$) **outward** away from the back wall ($z' < -0.968$) requires $\theta > 0$: `tapeBack.rotation.x = +(1 - tapeBackP) * 0.48`.
     - Lifting the `+Z` front tab (`tape_front`, $z = +0.88$) **outward** away from the front wall ($z' > +0.968$) requires $\theta < 0$: `tapeFront.rotation.x = -(1 - tapeFrontP) * 0.55`.
   - Inverting these signs folds the unsealed tape tabs *through the interior* of the solid carton walls. Always verify intermediate hinge states (`p ≈ 0.5`), not just `p = 0` and `p = 1`.
3. **Non-Overlapping Sequential Smoothstep Windows & DOM-Order-Independent Phase**:
   - Sequence dependent mechanical actions with strictly non-overlapping `smoothstep` intervals: retract `tape_front -> tape_top -> tape_back` completely (`cyc <= 0.34`) before `flap_right` and `flap_left` begin opening (`cyc >= 0.35`), and close both flaps completely (`cyc <= 0.59`) before `tape_back -> tape_top -> tape_front` begin applying (`cyc >= 0.60`).
   - Always compute per-instance cycle time as `const shipT = t - inst.phaseOffset;` rather than hardcoding an index offset (`t - 1.35`), so changing card order between a standalone demo and an Astro page (`/start`) never shifts a model's initial `t = 0` rest state.
