---
name: smoky-label-dieline
description: Generate press-ready CMYK packaging and label dielines (PDF + PNG proofs) with OCG layers, spot color separations (Die, Safety, Bleed, Fold), stroke overprint, 100% K vector UPC-A/QR codes, and container-to-dieline math for lids, wraps, ovals, cones, pouches, and cartons.
---

# Smoky Label & Packaging Dieline Engine (`smoky-label-dieline`)

Generate vendor-deliverable, press-ready CMYK vector PDF dielines and proof sheets for any product container—directly from user dimensions or container supplier specifications—without waiting on manual Illustrator prepress turnaround.

Read [references/prepress-and-container-specs.md](references/prepress-and-container-specs.md) for container-to-label dimensional formulas (cylindrical gap/overlap wraps, recessed lids, tapered cones, pouches, folding cartons), FINAT/TLMI roll unwind directions (`#1`–`#4`), and commercial CMYK/TAC/barcode prepress rules.

---

## 1. Commercial Prepress Guarantees

Every PDF produced by [`scripts/dieline_engine.py`](scripts/dieline_engine.py) enforces flexographic and digital label press invariants:

1. **Exact `1:1` Point Geometry (`72.0 pt = 1.0000 in`)**:
   - Trim (`Diecut`), Safety (`-0.0625"` default), and Bleed (`+0.125"` default) lock mathematically to target specs, including concentric radial/arc normal offsets on `conical_wrap` sectors and rectilinear offsets on `tuck_box` carton nets.
   - Artwork clips cleanly to the outer `+bleed` boundary so full-bleed backgrounds extend past the rotary die knife with zero white slivers.
2. **True Illustrator / RIP Optional Content Groups (`OCG` Layers) with Non-Printing Technical Usage**:
   - `Artwork` — printing CMYK vector artwork plus outer `100% K` trim registration ticks (`/Usage/Print/PrintState /ON`).
   - `Diecut` (`Spot: Die Line` + `Spot: Fold Line`), `Safety` (`Spot: Safety Line`), `Bleed` (`Spot: Bleed Line`), `Dimensions`, and `Die Template` — visible in on-screen proofs (`/ViewState /ON`) and explicitly suppressed during printing (`/PrintState /OFF` + `/OCProperties/D/AS` `/Print` usage application).
3. **Spot Color Separations + Stroke Overprint (`OP=true, op=true, OPM=1`)**:
   - Technical lines use `/Separation` spot plates with `/GSOverprint` so they never knock out underlying CMYK ink or contaminate process plates.
4. **Pure CMYK Process Space (`0` RGB Leaks), Enforced `TAC <= 300%`, & Explicit `100% K` Vector Codes**:
   - Zero `/DeviceRGB` objects, with channel bounds (`0..100%`) and total area ink coverage (`C + M + Y + K <= 300%`) enforced on custom `palette_cmyk` specs and verified in `--preflight` (`tac_within_limit: true`).
   - Retail `12`-digit UPC-A barcodes render only when `"upc"` is explicitly supplied in the product spec (never defaulting to another SKU's GTIN). When present, Modulo-10 check digits and `95` bar modules + `9X` left/right quiet zones (`113X`) enforce GS1 80% minimum retail dimensions (`X >= 0.0104"`, total width `>= 1.1752"`, short bar height `>= 0.72"`) unless `allow_non_retail_upc_truncation: true`.
   - Optional QR codes (`"qr_url"` or `"coa_url"`) render only when explicitly supplied, using pure `CMYK(0, 0, 0, 100)` vector modules with an ISO/IEC 18004 `>= 4`-module clear quiet zone on every side.

---

## 2. Supported Packaging & Container Shapes

`DielinePanel` supports arbitrary packaging formats:

- `circle` — Jar lids, tamper cap seals, bottom warning stickers (`width_in == height_in == diameter`).
- `rect` / `rounded_rect` — Sharp-cornered rectangular labels (`rect`, `corner_radius_in = 0` default) and rotary die-cut rounded rectangles (`rounded_rect`, `0.0625"`–`0.1092"` corner radius default) for cylindrical jar wraps, Boston round tincture bottles (`1 oz` / `2 oz`), and mylar pouch front/back panels.
- `oval` — Oval squeeze bottles, cosmetic tubes, apothecary medallions.
- `conical_wrap` / `tapered_wrap` — Non-stretch conical tubes, cups, and tapered containers unfolded into exact concentric **annular sectors** (`inner_radius_in`, `outer_radius_in`, `sector_angle_deg`). Use `flat_trapezoid` only for flat-walled prism faces.
- `tuck_box` — Complete **Reverse Tuck End (`RTE`)** folding carton nets with glue flap, four body panels (`[W, D, W, D]`), four dust flaps, opposite top/bottom closure panels + tuck tongues, interior flap-separation slits (`Spot: Die Line`), and vertical + horizontal score lines (`Spot: Fold Line`), keeping every barcode, QR code, and copy block strictly within a single flat panel between fold creases. Use `carton_sleeve` when an open 4-panel wraparound sleeve without end closures is intended.

---

## 3. Workflow

### Step 1: Resolve or Compute Exact Dieline Dimensions

If the user supplies raw container measurements (or a container vendor spec sheet) rather than finished label dimensions, run the zero-dependency stdlib calculator first:

```bash
python3 skills/smoky-label-dieline/scripts/dieline_engine.py \
  --calc-container '{"type":"cylinder","diameter_in":2.12,"straight_height_in":1.82,"lid_recess_in":2.56}'
```

Validate or compute a retail UPC-A check digit and 95-module bit pattern before layout:

```bash
python3 skills/smoky-label-dieline/scripts/dieline_engine.py --encode-upca 85004341302
```

### Step 2: Render Parametric Spec or Bespoke Multi-SKU Series

For fast JSON spec-driven dielines (auto-positions panels and scales 3-zone artwork):

```bash
uv run --with reportlab,pikepdf,pymupdf,qrcode,pillow python3 \
  skills/smoky-label-dieline/scripts/dieline_engine.py \
  --spec path/to/spec.json \
  --out path/to/output_dieline.pdf \
  --preview-dir path/to/previews
```

For bespoke multi-SKU packaging artwork (custom botanical geometry, mountain ridges, cryo facets, thermal contours):
- Import `DielinePanel`, `SmokyDielineSheet`, `draw_vector_upca`, `draw_vector_qr`, `draw_arched_text`, `draw_tracked_text`, `draw_normalized_vector`, and `render_previews` from `scripts/dieline_engine.py`.
- Draw CMYK vector artwork inside `artwork_fn(c, panels, brand_vecs)` clipped to `panel.make_path(c, +panel.bleed)`.
- **Design Guardrail**: Never use cramped floating pill bubbles for potency or active-ingredient badges. Use architectural hairline-divided potency ledgers with exact matched totals between lid and wrap panels, and keep arched bottom lid copy optically centered (`top_arc=False`) inside its annular track.

### Step 3: Automated Preflight & Visual Proof Inspection (Mandatory)

1. Verify `preflight_pass: true`, `cmyk_only_no_rgb: true`, all spot separations, and exact diecut geometry (`--preflight path/to/output_dieline.pdf` works with `pymupdf` or falls back to stdlib PDF stream inspection).
2. Render both `<stem>_proof.png` (all OCG layers ON) and `<stem>_artwork_only.png` (technical OCG layers OFF, leaving pure full-bleed CMYK artwork + trim crop ticks).
3. Visually inspect the rendered PNGs at `220–300 DPI` to confirm zero text clipping, clean safety-line clearance, legible `100% K` barcodes, and consistent math across every panel.

This skill owns prepress dieline generation, artwork composition, and preflight verification only; repository commits, release asset uploads, vendor submissions, and production print runs follow the active repository's authorization gates.
