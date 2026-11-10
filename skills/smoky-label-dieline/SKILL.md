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
   - Trim (`Diecut`), Safety (`-0.0625"` default), and Bleed (`+0.125"` default) lock mathematically to target specs, including true perpendicular normal offsets on sloped `tapered_wrap` edges.
   - Artwork clips cleanly to the outer `+bleed` boundary so full-bleed backgrounds extend past the rotary die knife with zero white slivers.
2. **True Illustrator / RIP Optional Content Groups (`OCG` Layers)**:
   - `Artwork` — printing CMYK vector artwork plus outer `100% K` trim registration ticks.
   - `Diecut` — non-printing cut path (`Spot: Die Line`) plus optional carton score lines (`Spot: Fold Line`).
   - `Safety` — non-printing inner safe margin (`Spot: Safety Line`).
   - `Bleed` — non-printing outer bleed boundary (`Spot: Bleed Line`).
   - `Dimensions` — width and height callout bars in inches.
   - `Die Template` — branded production proof footer (`assets/brand_vectors.json` or custom `--brand-vectors`), Roll Unwind Chart (`#1`–`#4` Label Side Out), stock/finish table, CMYK + White swatches, and non-printing legend.
3. **Spot Color Separations + Stroke Overprint (`OP=true, op=true, OPM=1`)**:
   - Technical lines use `/Separation` spot plates with `/GSOverprint` so they never knock out underlying CMYK ink or contaminate process plates.
4. **Pure CMYK Process Space (`0` RGB Leaks) & Validated `100% K` Vector Codes**:
   - Zero `/DeviceRGB` objects (`TAC <= 300%` on rich dark fills).
   - Retail `12`-digit UPC-A barcodes (Modulo-10 check-digit verified, `95` modules with guard bar drop heights) and COA QR codes render as pure `CMYK(0, 0, 0, 100)` vector paths inside white quiet zones.

---

## 2. Supported Packaging & Container Shapes

`DielinePanel` supports arbitrary packaging formats:

- `circle` — Jar lids, tamper cap seals, bottom warning stickers (`width_in == height_in == diameter`).
- `rect` / `rounded_rect` — Cylindrical jar wraps, Boston round tincture bottles (`1 oz` / `2 oz`), mylar pouch front/back panels (`width_in`, `height_in`, `corner_radius_in`).
- `oval` — Oval squeeze bottles, cosmetic tubes, apothecary medallions.
- `tapered_wrap` — Conical pre-roll tubes and tapered containers (`width_in` bottom width, `top_width_in` top width, `height_in`).
- `tuck_box` — Folding cartons and boxes (`fold_offsets_in` emits `Spot: Fold Line` score lines inside the cut perimeter).

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
