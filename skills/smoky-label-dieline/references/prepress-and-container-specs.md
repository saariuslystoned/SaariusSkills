# Prepress Anatomy, Container-to-Dieline Math, and Roll Unwind Standards

## 1. Container-to-Label Dimensional Math (`72.0 pt = 1.0000 in`)

When a user supplies physical container dimensions or a supplier spec page (for example Berlin Packaging, Cary Company, Uline, Container & Packaging, Calyx, or Chubby Gorilla) instead of finished label dimensions, compute exact dieline geometry with `--calc-container` or these formulas:

| Container Type | Primary Measurements | Finished Cut (`Diecut`) Formula | Default Bleed / Safety |
| --- | --- | --- | --- |
| **Cylindrical Jar / Bottle (Gap Wrap)** | Outer diameter $D$, straight vertical wall height $H_{\text{wall}}$ | $\text{Width} = \pi \cdot D - 0.125"$ (prevents overlap edge lift on rigid glass/PET)<br>$\text{Height} = H_{\text{wall}} - 0.125"$ (`0.0625"` top & bottom shoulder clearance) | `+0.125"` bleed<br>`-0.0625"` safety |
| **Cylindrical Bottle / Tube (Full Overlap Wrap)** | Outer diameter $D$, straight wall height $H_{\text{wall}}$ | $\text{Width} = \pi \cdot D + 0.25"$ (varnish-free overlap strip on flexible BOPP)<br>$\text{Height} = H_{\text{wall}} - 0.125"$ | `+0.125"` bleed<br>`-0.0625"` safety |
| **Recessed Jar Lid / Bottom Seal (`circle`)** | Flat lid recess diameter $D_{\text{recess}}$ | $\text{Diameter} = D_{\text{recess}} - 0.0625"$ (prevents edge curl against lid rim) | `+0.125"` bleed<br>`-0.0625"` safety |
| **Tapered Cone / Pre-Roll Tube (`tapered_wrap`)** | Bottom diameter $D_1$, top diameter $D_2$, vertical height $H$ | Slant height $S = \sqrt{H^2 + ((D_2 - D_1)/2)^2}$<br>Flat chord/trapezoid wrap: $W_{\text{bot}} = \pi D_1 - 0.125"$, $W_{\text{top}} = \pi D_2 - 0.125"$, height $S - 0.125"$ | Perpendicular normal offset `+0.125"` / `-0.0625"` |
| **Stand-Up Mylar Pouch (`rect` / `rounded_rect`)** | Pouch width $W_{\text{pouch}}$, flat face height above zipper/gusset $H_{\text{face}}$ | $\text{Width} = W_{\text{pouch}} - 0.50"$ (`0.25"` clear of heat-seal side seams)<br>$\text{Height} = H_{\text{face}} - 0.375"$ | `+0.125"` bleed<br>`-0.0625"` safety |
| **Folding Carton (`tuck_box` / `carton_flat`)** | Carton width $W$, depth $D_{\text{depth}}$, height $H_{\text{box}}$, glue flap $G$ (`0.50"`) | Total flat width $= 2W + 2D_{\text{depth}} + G$<br>`fold_offsets_in` $= [W,\; W + D_{\text{depth}},\; 2W + D_{\text{depth}},\; 2W + 2D_{\text{depth}}]$ | `+0.125"` bleed<br>`-0.0625"` safety + `Spot: Fold Line` |

---

## 2. Flexographic & Digital Roll Unwind Directions (FINAT / TLMI `#1`–`#8`)

Automatic label applicators require an explicit **Unwind Direction** checkbox on the dieline proof sheet:

- **Label Side Out (Wound Out — Standard `#1`–`#4` on Proof Sheet)**:
  - **`#1` Top Edge Leading**: Top of label feeds off the roll first (`0°`).
  - **`#2` Bottom Edge Leading**: Bottom of label feeds off the roll first (`180°`).
  - **`#3` Right Edge Leading**: Right side of label feeds off the roll first (`90°` CCW — standard for horizontal jar/bottle wrap applicators).
  - **`#4` Left Edge Leading**: Left side of label feeds off the roll first (`90°` CW).
- **Label Side In (Wound In — `#5`–`#8`)**: Same four leading edges with adhesive facing outward; specify in `meta.imprint` or `meta.finish` when requested by a co-packer.

---

## 3. Commercial Prepress Color & Typography Rules

1. **Pure CMYK Process Space (`0..100` Scale)**:
   - Never emit `/DeviceRGB` colors or embed unprofiled sRGB PNGs on vector artwork.
   - Keep **Total Area Coverage (`TAC`) $\le 300\%$** on rich dark backgrounds (for example `C=55, M=45, Y=45, K=92` = `237%` TAC) to prevent ink set-off or BOPP lamination delamination.
2. **Single-Plate `100% K` for Barcodes & Micro-Copy**:
   - UPC-A/EAN-13 bars, COA QR modules, and dark micro-text (`< 6 pt` on light backgrounds) must use **`CMYK(0, 0, 0, 100)`** (`100% K` only), never 4-color rich black, so `0.1 mm` press plate misregistration cannot blur scannability.
   - Conversely, reverse white micro-text knocked out of dark rich-black panels should use a crisp medium/demi condensed weight (`>= 4.3 pt` cap-safe) with a dark keyline (`K >= 80%`) carrying the edge definition.
3. **Spot Separations + Stroke Overprint**:
   - Technical paths (`Die Line`, `Safety Line`, `Bleed Line`, `Fold Line`) must be defined as PDF `/Separation` color spaces with `OP=true, op=true, OPM=1` (`/GSOverprint`) and isolated on dedicated Optional Content Groups (`OCG`) so RIP operators can toggle or suppress non-printing plates in one click without white knockouts.
4. **Structured Potency & Ingredient Architecture**:
   - Avoid floating rounded "pill bubbles" for active-ingredient or cannabinoid breakdowns. Frame potency metrics in **architectural hairline-divided ledgers** with matched totals across lid and wrap panels.
   - Ensure UPC-A codes validate their Modulo-10 check digit before rendering (`11` payload digits + `1` check digit = `95` modules + `9X` left/right quiet zones).
