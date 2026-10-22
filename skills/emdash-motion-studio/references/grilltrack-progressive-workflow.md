# Progressive GrillTrack Animation Workflow, Mode D (Tactile Foil & Tear-Off), and Optional Web Audio Foley

This reference defines:
1. The **Progressive GrillTrack Animation Workflow** (`Round 0: 5 Start-to-Finish Stage Frameworks` → `Round 1..N: Piece-by-Piece Build, Render & Grill Loop`).
2. **Mode D: Tactile Paper, Holographic Foil & Perforated Tear-Off Pass** (selectable mode for coupons, tickets, gift cards, and COA badges — never forced on other animations).
3. **Optional Procedural Web Audio Micro-Foley** (zero-file `AudioContext` synthesis — strictly opt-in when requested by the user, never forced by default).

---

## 1. Progressive GrillTrack Animation Workflow

Complex animations (such as a multi-step hardware cutaway, a fulfillment assembly line, or a choreographed multiplane stage) must **not** be built as a single monolithic black-box reveal. Instead, `emdash-motion-studio` pairs with `grilltrack` so the user shapes the architecture first and then approves each animated piece one at a time.

### Round 0 — Align on Website Placement, 3D Engine Style (`Mode A1` vs. `Mode A2`), Single User Trigger & 5 Start-to-Finish Stage Frameworks

Before modeling 40+ internal mechanisms or fine-tuning curves, start Round 0 by locking the **Website Placement + 3D Engine Style (`Mode A1` vs. `Mode A2`) + Single User Trigger**, then propose **5 noticeably different start-to-finish stage frameworks** so the user can picture the entire build from `t = 0` (start) to `t = 0.5` (mid-action) to `t = 1.0` (completed state) before locking a direction.

0. **Website Placement + Single User Trigger (`chrome: 'stage-only'` Default) + 3D Engine Style (`Mode A1` vs. `Mode A2`):**
   - Align first on **where the animation sits on the website** (e.g., Marketing Homepage Hero card, `/orders/[id]` fulfillment header, `/checkout/success` confirmation receipt, or "Under the Hood" architecture section—using the High-Leverage Website Placement Guide as a starting point while keeping experimentation open anywhere on the site).
   - **When starting a 3D stage (Mode A), explicitly ask whether the user wants:**
     - **Mode A1 — Illustrated Isometric SVG (`assets/core.js` — Colorfigures style):** Hand-inked SVG outlines, warm paper fill, and 30–60 part mechanical cutaways (`See-through` + `Labels`), OR
     - **Mode A2 — Studio WebGL Three.js PBR (`assets/vendor/three.min.js` — Realistic 3D + Live Screen Texture):** Sleek physically-based anodized metal, glass, fabric, and corrugated kraft materials, soft contact shadows, high-DPI `THREE.CanvasTexture` live screen UI, and close-up guided camera choreography.
   - Lock a **single natural user trigger** (for example: clicking the closed 3D MacBook on the homepage hero card to open the lid, run the `template-store` checkout workflow on screen with `"Cha-Ching!"` + `$$$ · Order #`, or transition into `See-through` cutaway mode).
   - **Default to `chrome: 'stage-only'` with zero April Zhu multi-button debug pills:** Production and piece-grill stages must **not** render left-side multi-button debug pills (`Framework 1..5`, `Preview Start`, step lists), `See-through` / `Labels` toggle buttons, wobble sliders, or palette swatches unless the user explicitly asks for a multi-button control panel.
1. **Five Distinct Spatial/Choreographic Architectures:**
   - Every candidate must differ in **stage topology, camera/spatial flow, and UI/story framing** — never five minor color tweaks of the same layout.
   - Example 5-framework spread (DinkusKit "Commerce on the MacBook" benchmark):
     - **Candidate 1 (`Assembly Line Desk`):** Left-to-right horizontal conveyor desk flow — Closed MacBook on the left hinges open → live `template-store` checkout + `"Cha-Ching!"` (or internal commerce cutaway) → middle packing station (overhead folded tee + packing slip drop into open box, 4 flaps fold, kraft tape seals) → right-side Pitney Bowes thermal printer slaps 4×6 label → far-right mail chute into outbound tote.
     - **Candidate 2 (`Isometric Command Island + Multiplane Horizon`):** Centerpiece angled MacBook Pro in foreground with split-level cutaway dock underneath + wide David East Multiplane Occlusion + Pigment Drift city/harbor skyline behind it where packed & labeled boxes ride a bridge track after leaving the desk printer.
     - **Candidate 3 (`Exploded Vertical Stack / Architecture Tower`):** 3-tier vertical cutaway stack — Top tier: MacBook Storefront + Coupon Stamp; Middle tier: Suspended transparent Commerce Engine Room (Cloudflare Edge, Stripe Vault, D1 Inventory); Bottom tier: Automated Fulfillment Bay (Box Packer + Thermal Label Slap + Mail Drop).
     - **Candidate 4 (`Split-Screen Cockpit: 3D Desk + Live Telemetry & Tear-Off Coupon HUD`):** Combines the 3D MacBook/Printer/Box desk stage with an interactive order timeline, optional perforated coupon stub, and live telemetry strip (`ORDERS`, `STRIPE NET`, `PB TRACKING`) along the bottom rail.
     - **Candidate 5 (`Radial Turntable Workshop`):** Circular rotating workbench divided into 4 quadrants around the central MacBook hub (`Q1`: Order & Coupon Ingress, `Q2`: Stripe & Inventory Vault, `Q3`: Box Packing & Taping Arm, `Q4`: Pitney Bowes Thermal Printer & Mail Launcher).
2. **Start-to-Finish Visibility (`t = 0.0` → `t = 0.5` → `t = 1.0`):**
   - Each framework candidate must clearly show how the animation starts (`t = 0.0`), how the core transfer/action unfolds (`t = 0.5`), and how it finishes (`t = 1.0`), both via interactive timeline scrubbing (`?candidate=1..5&t=0..1`) and a start-to-finish framework blueprint strip.
3. **Validated GrillTrack Picker Manifest (`validate_picker.py`):**
   - Write `.grilltrack/work/<round-id>/picker-manifest.json` adhering to `grilltrack-picker/v0.1`:
     - Exactly 5 candidates (`candidates`), presented neutrally (`recommended` omitted or `false`).
     - `slots` tracking the unresolved framework slot (`active_slot`) and any prior locked decisions.
     - `controls: { "keyboard": true, "pointer": true, "mobile": true }` and `"production": false`.
   - Validate with:
     ```bash
     python3 "<repo-or-plugin-root>/skills/grilltrack/scripts/validate_picker.py" .grilltrack/work/<round-id>/picker-manifest.json
     ```
4. **Headless Chrome Framework Proof:**
   - Render high-resolution PNG screenshots for all 5 candidates (including start `t=0`, mid `t=0.5`, and finish `t=1.0` states) using `scripts/verify_motion.py` so the user can visually compare all 5 frameworks and lock one.

---

### Rounds 1..N — Piece-by-Piece Build, Render & Grill Loop

Once the user locks one of the 5 stage frameworks in Round 0, **preserve that locked framework as the cumulative canvas** (embedded inside its real website placement context with `chrome: 'stage-only'` and zero debug buttons) and build the animation **one core piece at a time**:

```text
Lock Placement + 3D Engine (A1/A2) + Single Trigger + Framework (Round 0)
  └──► Build & Render Piece 1 (stage-only in site context) ──► Verify PNGs ──► Grill User on Piece 1
         └──► Lock Piece 1 on Canvas
                └──► Build & Render Piece 2 ──► Verify PNGs ──► Grill User on Piece 2
                       └──► Lock Pieces 1+2 on Canvas
                              └──► Build & Render Piece 3 ──► Verify PNGs ──► Grill User on Piece 3
```

#### Rules for Every Piece Round
1. **One Core Piece per Round (with Live Screen Workflow / Cutaway & Callouts):**
   - **Piece 1 example (Mode A2 Studio WebGL PBR):** 3D Space-Black MacBook Pro unibody at rest (`t = 0.0`) with single-click trigger (`"Click MacBook to Place Order"`), close-up guided camera zoom onto the hinged Retina display (`0° → 108°`) showing the live `template-store` checkout workflow (Product Page → Add to Cart → `/cart` → Stripe Checkout → Paid!), plus synthesized `"Cha-Ching!"` audio chime and floating `$$$ · ORDER #DK-402 PAID` badge (or in Mode A1: automatic `See-through` cutaway revealing internal parts).
   - **Piece 2 example:** Overhead Merch Inventory Tray holding folded DinkusKit Graphic Tees (never coming out of the laptop!), 3D folded Graphic Tee + thermal Packing Slip dropping inside the open corrugated cardboard box, 4 hinged folding flaps (`0° → 90°`), and kraft packing tape seal.
   - **Piece 3 example:** Pitney Bowes 4×6 thermal label printer (`LABEL ROLL` + `TAMP APPLICATOR`), high-res 4×6 barcode label pressed flat onto the top of the sealed box, and outgoing Mail Chute dropping the box into an Outbound Tote filled with packed & labeled DinkusKit boxes.
2. **Cumulative Canvas Preservation:**
   - Never discard or regress previously locked pieces. Piece 2 builds directly on the locked Piece 1 canvas; Piece 3 builds directly on the locked Pieces 1 + 2 canvas.
   - If the user asks for an adjustment to Piece `k` during its grill checkpoint (e.g., "make the box flaps fold slower" or "change the angle of the thermal label"), refine Piece `k`, re-verify in headless Chrome, and confirm the lock before starting Piece `k + 1`.
3. **Deterministic Proof at Every Checkpoint:**
   - Run `scripts/verify_motion.py` for the active piece's keyframe range (`?t=...`) and show the rendered proof frames alongside focused GrillTrack questions on the piece's visual craft and motion feel.

---

## 2. Mode D: Tactile Paper, Holographic Foil & Perforated Tear-Off Pass (Optional / Subject-Specific)

> **When to use Mode D:** Select Mode D **only** when the subject is a tactile paper/card artifact — such as a **promotional coupon (`SAVE20`), event/golden ticket, gift card, perforated receipt stub, shipping manifest tag, or certificate of authenticity (COA) badge**. Never force Mode D onto standard Mode A/B/C hardware or architectural scenes.

Inspired by tactile WebGL/CSS paper & foil studies (such as Sam Aing's *Argon 4 Golden Ticket Tear*):

### Core Mechanics of Mode D
1. **3D Tilt & Specular Foil Sheen:**
   - Pointer/drag or timeline angle drives `rotateX` / `rotateY` tilt and shifts a multi-stop iridescent/metallic foil gradient (`linear-gradient(115deg, ...)` with `mix-blend-mode: color-dodge` or SVG `<linearGradient>` specular bands) across embossed badges, serial numbers, and stamp seals.
2. **Perforated Punch-Hole Seam & Deterministic Tear Physics (`tearProgress` in `0..1`):**
   - Model the perforation line explicitly with punched semicircular notches on both edges and dashed die-cut rules across the seam.
   - Drive the stub separation deterministically from `tearProgress` (`0..1`):
     - `0.00..0.35`: Seam tension & progressive SVG clip/path notch separation from left to right.
     - `0.35..0.75`: Detached stub pivots around the remaining corner fiber (`rotateZ(14deg) rotateX(-18deg)`) with a jagged fiber-edge polygon along the torn seam.
     - `0.75..1.00`: Stub releases with gravity drop + flutter (`translateY`, `rotateZ`) while **purely revealing the coupon code + copying it to the clipboard (`navigator.clipboard.writeText(code)`)** — requiring **zero backend coupon engine by default**, with an optional `onRedeem(code)` callback hook if wired later.
3. **X-Ray / See-Through Security Layer (`?xr=1`):**
   - Just like Mode A's `See-through` toggle, Mode D supports an `X-Ray` inspection toggle (`?xr=1`) that ghosts the outer cotton-paper fibers to reveal embedded security watermarks, NFC/RFID copper antenna coils, cryptographic signature hashes, and micro-printed verification threads.
4. **Ephemera Stationery Primitives (`assets/tactile-audio.js` & [references/tactile-foil-and-web-audio.md](tactile-foil-and-web-audio.md)):**
   - **Thermal Receipt (`mountReceipt` & `renderBarcodeSvg(code)`):** Ideal for `/checkout/success` Order Confirmation Receipts — `conic-gradient` serrated top/bottom teeth, deterministic 32-bit FNV-1a hash-to-SVG barcode generator (`renderBarcodeSvg(code)`), and `steps(28, end)` thermal line-feed reveal.
   - **Dry-Ink Rubber Stamp (`mountRubberStamp`):** Inline SVG `<feTurbulence type="fractalNoise" baseFrequency="0.09" numOctaves="4">` + `<feDisplacementMap>` dry-ink erosion filter + `cubic-bezier(0.22, 1, 0.36, 1)` stamp thud animation (ideal for `[PAID]`, `[PAID · STRIPE TEST]`, `[SHIPPED · PB SANDBOX]`, `[PAID · D1]`).

---

## 3. Optional Add-On: Procedural Web Audio Micro-Foley (Never Forced)

> **Opt-In Policy:** Not every animation needs sound. **Never force Web Audio onto an animation by default.** Include Procedural Web Audio Micro-Foley **only** when the user explicitly asks for sound effects, audio foley, or tactile acoustic feedback (and always provide a visible `Sound: Off/On` mute toggle that defaults to muted/safe until user gesture).

When requested, synthesize zero-dependency acoustic micro-foley directly in JavaScript using the browser's native `AudioContext` (zero external `.mp3` / `.wav` files required):

```javascript
function createMicroFoley() {
  let ctx = null, enabled = false;
  const ensure = () => {
    if (!enabled) return null;
    if (!ctx && typeof AudioContext !== 'undefined') ctx = new AudioContext();
    if (ctx && ctx.state === 'suspended') ctx.resume();
    return ctx;
  };
  return {
    setEnabled(v) { enabled = !!v; if (enabled) ensure(); },
    isEnabled() { return enabled; },
    // Crisp mechanical detent click / stamp thud
    click(freq = 920, dur = 0.028) {
      const ac = ensure(); if (!ac) return;
      const osc = ac.createOscillator(), g = ac.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(freq, ac.currentTime);
      osc.frequency.exponentialRampToValueAtTime(140, ac.currentTime + dur);
      g.gain.setValueAtTime(0.18, ac.currentTime);
      g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + dur);
      osc.connect(g); g.connect(ac.destination);
      osc.start(); osc.stop(ac.currentTime + dur);
    },
    // Bandpass-filtered white-noise burst for paper tear, kraft tape pull, or thermal print head burn
    paperTear(dur = 0.16, centerHz = 1800) {
      const ac = ensure(); if (!ac) return;
      const len = Math.floor(ac.sampleRate * dur);
      const buf = ac.createBuffer(1, len, ac.sampleRate);
      const data = buf.getChannelData(0);
      for (let i = 0; i < len; i++) {
        const env = Math.sin((i / len) * Math.PI);
        data[i] = (Math.random() * 2 - 1) * env * (0.6 + 0.4 * Math.sin(i * 0.08));
      }
      const src = ac.createBufferSource(); src.buffer = buf;
      const bp = ac.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = centerHz; bp.Q.value = 1.4;
      const g = ac.createGain(); g.gain.value = 0.22;
      src.connect(bp); bp.connect(g); g.connect(ac.destination);
      src.start();
    }
  };
}
```
