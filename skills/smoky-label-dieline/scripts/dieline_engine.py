#!/usr/bin/env python3
"""
Smoky Label & Packaging Dieline Engine (`dieline_engine.py`)

Generates press-ready CMYK vector PDFs and runs stdlib container/barcode/preflight checks:
- True Optional Content Groups (OCG layers): Artwork, Diecut, Safety, Bleed, Dimensions, Die Template
- Non-printing Spot Color Separations (`Die Line`, `Safety Line`, `Bleed Line`, `Fold Line`) with Overprint (`OP=true`, `OPM=1`)
- Exact 1:1 point geometry (72 pt = 1.0000 in) across circles, wraps, ovals, tapered cones, pouches, and folding cartons
- Pure 100% K vector UPC-A (Modulo-10 verified, 95 modules) & QR code generation
- Zero-dependency stdlib modes (`--help`, `--calc-container`, `--encode-upca`, `--preflight`) for hermetic CI and container math
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import zlib
from pathlib import Path
from typing import Any, Callable

try:
    from reportlab.lib.colors import PCMYKColor, PCMYKColorSep
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    HAS_REPORTLAB = True
except ImportError:  # pragma: no cover - exercised in stdlib-only CI environments
    PCMYKColor = Any  # type: ignore[misc,assignment]
    PCMYKColorSep = Any  # type: ignore[misc,assignment]
    pdfmetrics = None  # type: ignore[assignment]
    TTFont = None  # type: ignore[assignment]
    canvas = Any  # type: ignore[misc,assignment]
    HAS_REPORTLAB = False

PT_PER_INCH = 72.0


def inch(val: float) -> float:
    return float(val) * PT_PER_INCH


# ---------------------------------------------------------------------------
# Cross-Platform Font Registration & Type1 Core Fallback (macOS + Linux + CI)
# ---------------------------------------------------------------------------
MACOS_FONT_CANDIDATES: dict[str, list[tuple[str, int | None]]] = {
    "DINCond-Bold": [
        ("/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf", None),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", None),
        ("/usr/share/fonts/truetype/liberation2/LiberationSansNarrow-Bold.ttf", None),
    ],
    "DINAlt-Bold": [
        ("/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf", None),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", None),
    ],
    "AvenirCond-Heavy": [
        ("/System/Library/Fonts/Avenir Next Condensed.ttc", 8),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", None),
    ],
    "AvenirCond-Bold": [
        ("/System/Library/Fonts/Avenir Next Condensed.ttc", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", None),
    ],
    "AvenirCond-Demi": [
        ("/System/Library/Fonts/Avenir Next Condensed.ttc", 2),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", None),
    ],
    "AvenirCond-Med": [
        ("/System/Library/Fonts/Avenir Next Condensed.ttc", 5),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf", None),
    ],
    "AvenirCond-Reg": [
        ("/System/Library/Fonts/Avenir Next Condensed.ttc", 7),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf", None),
    ],
    "Avenir-Heavy": [
        ("/System/Library/Fonts/Avenir Next.ttc", 8),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", None),
    ],
    "Avenir-Bold": [
        ("/System/Library/Fonts/Avenir Next.ttc", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", None),
    ],
    "Avenir-Demi": [
        ("/System/Library/Fonts/Avenir Next.ttc", 2),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", None),
    ],
    "Avenir-Med": [
        ("/System/Library/Fonts/Avenir Next.ttc", 5),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", None),
    ],
    "Avenir-Reg": [
        ("/System/Library/Fonts/Avenir Next.ttc", 7),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", None),
    ],
    "Avenir-Italic": [
        ("/System/Library/Fonts/Avenir Next.ttc", 4),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", None),
    ],
    "Avenir-BoldItalic": [
        ("/System/Library/Fonts/Avenir Next.ttc", 1),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf", None),
    ],
    "Futura-Bold": [
        ("/System/Library/Fonts/Supplemental/Futura.ttc", 2),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", None),
    ],
    "Futura-CondExtra": [
        ("/System/Library/Fonts/Supplemental/Futura.ttc", 4),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", None),
    ],
    "Georgia-Bold": [
        ("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", None),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", None),
    ],
    "Georgia-Italic": [
        ("/System/Library/Fonts/Supplemental/Georgia Italic.ttf", None),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf", None),
    ],
    "Copperplate": [
        ("/System/Library/Fonts/Supplemental/Copperplate.ttc", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", None),
    ],
    "Copperplate-Bold": [
        ("/System/Library/Fonts/Supplemental/Copperplate.ttc", 2),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", None),
    ],
}

CORE_TYPE1_FALLBACKS: dict[str, str] = {
    "DINCond-Bold": "Helvetica-Bold",
    "DINAlt-Bold": "Helvetica-Bold",
    "AvenirCond-Heavy": "Helvetica-Bold",
    "AvenirCond-Bold": "Helvetica-Bold",
    "AvenirCond-Demi": "Helvetica-Bold",
    "AvenirCond-Med": "Helvetica",
    "AvenirCond-Reg": "Helvetica",
    "Avenir-Heavy": "Helvetica-Bold",
    "Avenir-Bold": "Helvetica-Bold",
    "Avenir-Demi": "Helvetica-Bold",
    "Avenir-Med": "Helvetica",
    "Avenir-Reg": "Helvetica",
    "Avenir-Italic": "Helvetica-Oblique",
    "Avenir-BoldItalic": "Helvetica-BoldOblique",
    "Futura-Bold": "Helvetica-Bold",
    "Futura-CondExtra": "Helvetica-Bold",
    "Georgia-Bold": "Times-Bold",
    "Georgia-Italic": "Times-Italic",
    "Copperplate": "Helvetica-Bold",
    "Copperplate-Bold": "Helvetica-Bold",
}


def register_fonts() -> None:
    if not HAS_REPORTLAB:
        return
    registered = set(pdfmetrics.getRegisteredFontNames())
    for alias, candidates in MACOS_FONT_CANDIDATES.items():
        if alias in registered:
            continue
        for font_path, sub_idx in candidates:
            if not os.path.exists(font_path):
                continue
            try:
                if sub_idx is not None:
                    pdfmetrics.registerFont(TTFont(alias, font_path, subfontIndex=sub_idx))
                else:
                    pdfmetrics.registerFont(TTFont(alias, font_path))
                registered.add(alias)
                break
            except Exception:
                continue


def resolve_font(font_name: str) -> str:
    if not HAS_REPORTLAB:
        return font_name
    registered = set(pdfmetrics.getRegisteredFontNames())
    if font_name in registered:
        return font_name
    return CORE_TYPE1_FALLBACKS.get(font_name, "Helvetica")


# ---------------------------------------------------------------------------
# Spot & Process CMYK Colors (PCMYKColor uses 0..100 integer percentages)
# ---------------------------------------------------------------------------
if HAS_REPORTLAB:
    SPOT_DIELINE = PCMYKColorSep(81, 0, 8, 0, spotName="Die Line", density=100)
    SPOT_SAFETY = PCMYKColorSep(0, 92, 86, 0, spotName="Safety Line", density=100)
    SPOT_BLEED = PCMYKColorSep(65, 0, 95, 0, spotName="Bleed Line", density=100)
    SPOT_FOLD = PCMYKColorSep(15, 85, 0, 0, spotName="Fold Line", density=100)

    CMYK_RICH_BLACK = PCMYKColor(55, 45, 45, 92)
    CMYK_100K = PCMYKColor(0, 0, 0, 100)
    CMYK_DARK_CHARCOAL = PCMYKColor(35, 30, 30, 86)
    CMYK_WHITE = PCMYKColor(0, 0, 0, 0)
    CMYK_PAPER_GRAY = PCMYKColor(6, 4, 4, 8)
    CMYK_SMOKE_GOLD = PCMYKColor(12, 24, 58, 4)
    CMYK_SMOKE_SLATE = PCMYKColor(35, 22, 18, 35)
    CMYK_MAGENTA_CHECK = PCMYKColor(0, 95, 20, 0)
else:  # pragma: no cover
    SPOT_DIELINE = SPOT_SAFETY = SPOT_BLEED = SPOT_FOLD = None
    CMYK_RICH_BLACK = CMYK_100K = CMYK_DARK_CHARCOAL = CMYK_WHITE = None
    CMYK_PAPER_GRAY = CMYK_SMOKE_GOLD = CMYK_SMOKE_SLATE = CMYK_MAGENTA_CHECK = None


# ---------------------------------------------------------------------------
# Pure-Stdlib Container-to-Dieline Calculator & UPC-A Encoder
# ---------------------------------------------------------------------------
UPC_L = {
    "0": "0001101", "1": "0011001", "2": "0010011", "3": "0111101", "4": "0100011",
    "5": "0110001", "6": "0101111", "7": "0111011", "8": "0110111", "9": "0001011",
}
UPC_R = {k: "".join("1" if b == "0" else "0" for b in v) for k, v in UPC_L.items()}


def upc_check_digit(digits11: str) -> str:
    if len(digits11) != 11 or not digits11.isdigit():
        raise ValueError(f"Expected exactly 11 numeric digits for UPC-A payload, got {digits11!r}")
    odd_sum = sum(int(digits11[i]) for i in range(0, 11, 2))
    even_sum = sum(int(digits11[i]) for i in range(1, 11, 2))
    total = odd_sum * 3 + even_sum
    return str((10 - (total % 10)) % 10)


def normalize_and_encode_upca(code: str) -> tuple[str, str]:
    """Validates or computes a 12-digit UPC-A code and returns `(digits12, bits95)`."""
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    if len(digits) == 11:
        digits += upc_check_digit(digits)
    elif len(digits) == 12:
        expected = upc_check_digit(digits[:11])
        if digits[11] != expected:
            raise ValueError(
                f"Invalid UPC-A check digit in {digits!r}: expected {expected!r} for payload {digits[:11]!r}"
            )
    else:
        raise ValueError(f"UPC-A requires 11 or 12 digits, got {code!r}")

    bits = "101"
    for d in digits[:6]:
        bits += UPC_L[d]
    bits += "01010"
    for d in digits[6:]:
        bits += UPC_R[d]
    bits += "101"
    return digits, bits


GS1_UPCA_MIN_X_IN = 0.0104
GS1_UPCA_MODULES_TOTAL = 113  # 9X left quiet + 95X symbol + 9X right quiet
GS1_UPCA_MIN_WIDTH_IN = GS1_UPCA_MODULES_TOTAL * GS1_UPCA_MIN_X_IN  # 1.1752 in (84.6144 pt)
GS1_UPCA_MIN_BAR_HEIGHT_IN = 0.72  # GS1 80% minimum retail bar height (51.84 pt)
QR_MIN_QUIET_MODULES = 4.0  # ISO/IEC 18004 / DENSO Wave 4-module quiet zone


def develop_conical_wrap(
    arc_inner_in: float,
    arc_outer_in: float,
    band_height_in: float,
    apex_down: bool = True,
) -> dict[str, Any]:
    """
    Develops a non-stretch tapered cone/frustum band into an exact concentric annular sector.
    Rejects non-positive bands or extreme squat funnels (> 170 deg sector sweep).
    """
    if arc_inner_in <= 0 or arc_outer_in <= 0 or band_height_in <= 0:
        raise ValueError("Conical wrap arc lengths and slant band height must be positive")
    s_small = min(arc_inner_in, arc_outer_in)
    s_large = max(arc_inner_in, arc_outer_in)
    if s_large - s_small < 1e-6:
        raise ValueError("Equal inner and outer arcs define a cylindrical rectangle, not a conical sector")
    theta = (s_large - s_small) / band_height_in
    theta_deg = math.degrees(theta)
    if theta <= 0 or theta_deg > 170.0:
        raise ValueError(
            f"Unsupported conical sector angle {theta_deg:.2f} deg (must be in (0, 170] deg for single-piece flat development)"
        )
    r_inner = s_small / theta
    r_outer = r_inner + band_height_in
    bbox_w = 2.0 * r_outer * math.sin(theta / 2.0)
    bbox_h = r_outer - r_inner * math.cos(theta / 2.0)
    return {
        "inner_radius_in": round(r_inner, 6),
        "outer_radius_in": round(r_outer, 6),
        "sector_angle_deg": round(theta_deg, 6),
        "arc_inner_in": round(s_small, 4),
        "arc_outer_in": round(s_large, 4),
        "band_height_in": round(band_height_in, 4),
        "apex_down": bool(apex_down),
        "bbox_width_in": round(bbox_w, 4),
        "bbox_height_in": round(bbox_h, 4),
    }


def build_reverse_tuck_carton(
    width_in: float,
    depth_in: float,
    height_in: float,
    glue_flap_in: float = 0.50,
    tuck_tongue_in: float | None = None,
    dust_flap_in: float | None = None,
) -> dict[str, Any]:
    """
    Computes a complete Reverse Tuck End (RTE) folding carton net including glue flap,
    four body panels [W, D, W, D], top/bottom dust flaps on D panels, and opposite
    main closure panels + friction tuck tongues on W panels.
    """
    if width_in <= 0 or depth_in <= 0 or height_in <= 0 or glue_flap_in <= 0:
        raise ValueError("Carton width, depth, height, and glue flap dimensions must be positive")
    tongue = float(tuck_tongue_in) if tuck_tongue_in is not None else round(min(0.625, max(0.375, depth_in * 0.45)), 4)
    dust = float(dust_flap_in) if dust_flap_in is not None else round(min(0.75 * depth_in, width_in * 0.48), 4)
    if tongue <= 0 or dust <= 0:
        raise ValueError("Carton tuck tongue and dust flap lengths must be positive")
    ext = depth_in + tongue
    total_w = glue_flap_in + 2.0 * width_in + 2.0 * depth_in
    total_h = height_in + 2.0 * ext

    x0 = 0.0
    x1 = glue_flap_in
    x2 = x1 + width_in
    x3 = x2 + depth_in
    x4 = x3 + width_in
    x5 = x4 + depth_in

    y_body_bot = ext
    y_body_top = ext + height_in

    columns = [
        {"name": "glue_flap", "x0_in": round(x0, 6), "x1_in": round(x1, 6), "y0_in": round(y_body_bot, 6), "y1_in": round(y_body_top, 6)},
        {"name": "front_panel", "x0_in": round(x1, 6), "x1_in": round(x2, 6), "y0_in": round(y_body_bot, 6), "y1_in": round(total_h, 6)},
        {"name": "right_panel", "x0_in": round(x2, 6), "x1_in": round(x3, 6), "y0_in": round(y_body_bot - dust, 6), "y1_in": round(y_body_top + dust, 6)},
        {"name": "back_panel", "x0_in": round(x3, 6), "x1_in": round(x4, 6), "y0_in": 0.0, "y1_in": round(y_body_top, 6)},
        {"name": "left_panel", "x0_in": round(x4, 6), "x1_in": round(x5, 6), "y0_in": round(y_body_bot - dust, 6), "y1_in": round(y_body_top + dust, 6)},
    ]
    fold_lines_in = [
        [round(x1, 6), round(y_body_bot, 6), round(x1, 6), round(y_body_top, 6)],
        [round(x2, 6), round(y_body_bot, 6), round(x2, 6), round(y_body_top, 6)],
        [round(x3, 6), round(y_body_bot, 6), round(x3, 6), round(y_body_top, 6)],
        [round(x4, 6), round(y_body_bot, 6), round(x4, 6), round(y_body_top, 6)],
        [round(x1, 6), round(y_body_top, 6), round(x2, 6), round(y_body_top, 6)],
        [round(x1, 6), round(y_body_top + depth_in, 6), round(x2, 6), round(y_body_top + depth_in, 6)],
        [round(x2, 6), round(y_body_top, 6), round(x3, 6), round(y_body_top, 6)],
        [round(x2, 6), round(y_body_bot, 6), round(x3, 6), round(y_body_bot, 6)],
        [round(x3, 6), round(y_body_bot, 6), round(x4, 6), round(y_body_bot, 6)],
        [round(x3, 6), round(tongue, 6), round(x4, 6), round(tongue, 6)],
        [round(x4, 6), round(y_body_top, 6), round(x5, 6), round(y_body_top, 6)],
        [round(x4, 6), round(y_body_bot, 6), round(x5, 6), round(y_body_bot, 6)],
    ]
    flap_slits_in = [
        [round(x2, 6), round(y_body_top, 6), round(x2, 6), round(y_body_top + dust, 6)],
        [round(x3, 6), round(y_body_bot - dust, 6), round(x3, 6), round(y_body_bot, 6)],
        [round(x4, 6), round(y_body_bot - dust, 6), round(x4, 6), round(y_body_bot, 6)],
    ]
    return {
        "style": "reverse_tuck_end",
        "face_width_in": round(width_in, 4),
        "depth_in": round(depth_in, 4),
        "body_height_in": round(height_in, 4),
        "glue_flap_in": round(glue_flap_in, 4),
        "tuck_tongue_in": round(tongue, 4),
        "dust_flap_in": round(dust, 4),
        "body_y0_in": round(y_body_bot, 4),
        "body_y1_in": round(y_body_top, 4),
        "total_width_in": round(total_w, 4),
        "total_height_in": round(total_h, 4),
        "columns": columns,
        "fold_lines_in": fold_lines_in,
        "flap_slits_in": flap_slits_in,
    }


def calculate_container_dieline(container: dict[str, Any]) -> dict[str, Any]:
    """
    Computes recommended finished diecut, bleed, and safety dimensions (in inches and PDF points)
    from physical container measurements (cylinder jar/bottle, tapered cone/tube, pouch, carton, or sleeve).
    """
    kind = str(container.get("type", container.get("container_type", "cylinder"))).lower()
    bleed_in = float(container.get("bleed_in", 0.125))
    safety_in = float(container.get("safety_in", 0.0625))
    panels: list[dict[str, Any]] = []

    if kind in ("cylinder", "cylinder_wrap", "jar", "bottle"):
        diam = float(container["diameter_in"])
        wall_h_raw = container.get("straight_height_in", container.get("straight_panel_h_in"))
        if wall_h_raw is None:
            raise KeyError("straight_height_in")
        wall_h = float(wall_h_raw)
        overlap_mode = str(container.get("wrap_mode", "gap")).lower()
        gap_in = float(container.get("gap_in", 0.125))
        overlap_in = float(container.get("overlap_in", 0.25))
        shoulder_clear = float(container.get("vertical_clearance_in", 0.125))

        if overlap_mode == "overlap":
            wrap_w = math.pi * diam + overlap_in
        else:
            wrap_w = math.pi * diam - gap_in
        wrap_h = wall_h - shoulder_clear
        if wrap_w <= 0 or wrap_h <= 0:
            raise ValueError("Computed cylinder wrap dimensions must be positive")

        if "lid_recess_in" in container and container["lid_recess_in"] is not None:
            lid_clear = float(container.get("lid_clearance_in", 0.0625))
            lid_d = float(container["lid_recess_in"]) - lid_clear
            if lid_d <= 0:
                raise ValueError("Computed lid circle diameter must be positive")
            panels.append({
                "panel_id": "lid_circle",
                "shape": "circle",
                "width_in": round(lid_d, 4),
                "height_in": round(lid_d, 4),
                "bleed_in": bleed_in,
                "safety_in": safety_in,
                "width_pt": round(inch(lid_d), 2),
                "height_pt": round(inch(lid_d), 2),
                "label_desc": f'{lid_d:.2f}" CIRCLE (LID)',
            })

        panels.append({
            "panel_id": "body_wrap",
            "shape": "rounded_rect",
            "width_in": round(wrap_w, 4),
            "height_in": round(wrap_h, 4),
            "corner_radius_in": round(float(container.get("corner_radius_in", 0.0625)), 4),
            "bleed_in": bleed_in,
            "safety_in": safety_in,
            "width_pt": round(inch(wrap_w), 2),
            "height_pt": round(inch(wrap_h), 2),
            "label_desc": f'{wrap_w:.2f}"(W) x {wrap_h:.2f}"(H) WRAP',
        })
    elif kind in ("tapered", "cone", "tapered_wrap", "conical_wrap"):
        d_bot = float(container["bottom_diameter_in"])
        d_top = float(container["top_diameter_in"])
        v_h = float(container["vertical_height_in"])
        gap_in = float(container.get("gap_in", 0.125))
        v_clear = float(container.get("vertical_clearance_in", 0.125))
        if d_bot <= 0 or d_top <= 0 or v_h <= 0:
            raise ValueError("Tapered container diameters and vertical height must be positive")
        if abs(d_top - d_bot) < 1e-6:
            return calculate_container_dieline({
                "type": "cylinder",
                "diameter_in": d_bot,
                "straight_height_in": v_h,
                "gap_in": gap_in,
                "vertical_clearance_in": v_clear,
                "bleed_in": bleed_in,
                "safety_in": safety_in,
            })
        s_wall = math.hypot(v_h, (d_top - d_bot) / 2.0)
        band_h = s_wall - v_clear
        if band_h <= 0:
            raise ValueError("Computed tapered wrap slant height must be positive")
        r_bot, r_top = d_bot / 2.0, d_top / 2.0
        inset = v_clear / 2.0
        r1 = r_bot + (r_top - r_bot) * (inset / s_wall)
        r2 = r_top - (r_top - r_bot) * (inset / s_wall)
        r_small, r_large = min(r1, r2), max(r1, r2)
        r_inner_cone = (r_small * band_h) / (r_large - r_small)
        theta_full = (2.0 * math.pi * r_small) / r_inner_cone
        theta_net = theta_full - (gap_in / r_inner_cone)
        if theta_net <= 0:
            raise ValueError("Seam gap exceeds narrow-end circumference of tapered container")
        arc_small = r_inner_cone * theta_net
        arc_large = (r_inner_cone + band_h) * theta_net
        sector = develop_conical_wrap(
            arc_inner_in=arc_small,
            arc_outer_in=arc_large,
            band_height_in=band_h,
            apex_down=(d_top > d_bot),
        )
        panels.append({
            "panel_id": "conical_wrap",
            "shape": "conical_wrap",
            "width_in": sector["bbox_width_in"],
            "height_in": sector["bbox_height_in"],
            "inner_radius_in": sector["inner_radius_in"],
            "outer_radius_in": sector["outer_radius_in"],
            "sector_angle_deg": sector["sector_angle_deg"],
            "arc_inner_in": sector["arc_inner_in"],
            "arc_outer_in": sector["arc_outer_in"],
            "band_height_in": sector["band_height_in"],
            "apex_down": sector["apex_down"],
            "bleed_in": bleed_in,
            "safety_in": safety_in,
            "width_pt": round(inch(sector["bbox_width_in"]), 2),
            "height_pt": round(inch(sector["bbox_height_in"]), 2),
            "label_desc": f'{sector["bbox_width_in"]:.2f}"(W) x {sector["bbox_height_in"]:.2f}"(H) CONICAL SECTOR ({sector["sector_angle_deg"]:.1f} DEG)',
        })
    elif kind in ("pouch", "bag"):
        pw = float(container["pouch_width_in"]) - float(container.get("seam_clearance_in", 0.50))
        ph = float(container["face_height_in"]) - float(container.get("vertical_clearance_in", 0.375))
        if pw <= 0 or ph <= 0:
            raise ValueError("Computed pouch panel dimensions must be positive")
        for side in ("front", "back"):
            panels.append({
                "panel_id": f"pouch_{side}",
                "shape": "rounded_rect",
                "width_in": round(pw, 4),
                "height_in": round(ph, 4),
                "corner_radius_in": round(float(container.get("corner_radius_in", 0.125)), 4),
                "bleed_in": bleed_in,
                "safety_in": safety_in,
                "width_pt": round(inch(pw), 2),
                "height_pt": round(inch(ph), 2),
            })
    elif kind in ("carton", "tuck_box", "box"):
        w = float(container["width_in"])
        d = float(container["depth_in"])
        h = float(container["height_in"])
        glue = float(container.get("glue_flap_in", 0.50))
        net = build_reverse_tuck_carton(
            width_in=w,
            depth_in=d,
            height_in=h,
            glue_flap_in=glue,
            tuck_tongue_in=container.get("tuck_tongue_in"),
            dust_flap_in=container.get("dust_flap_in"),
        )
        panels.append({
            "panel_id": "carton_rte_net",
            "shape": "tuck_box",
            "width_in": net["total_width_in"],
            "height_in": net["total_height_in"],
            "carton_net": net,
            "corner_radius_in": 0.0,
            "bleed_in": bleed_in,
            "safety_in": safety_in,
            "width_pt": round(inch(net["total_width_in"]), 2),
            "height_pt": round(inch(net["total_height_in"]), 2),
            "label_desc": f'{net["total_width_in"]:.2f}"(W) x {net["total_height_in"]:.2f}"(H) RTE FOLDING CARTON',
        })
    elif kind in ("sleeve", "carton_sleeve"):
        w = float(container["width_in"])
        d = float(container["depth_in"])
        h = float(container["height_in"])
        glue = float(container.get("glue_flap_in", 0.50))
        if w <= 0 or d <= 0 or h <= 0 or glue <= 0:
            raise ValueError("Sleeve dimensions must be positive")
        total_w = 2 * w + 2 * d + glue
        folds = [round(glue, 4), round(glue + w, 4), round(glue + w + d, 4), round(glue + 2 * w + d, 4)]
        panels.append({
            "panel_id": "open_sleeve",
            "shape": "carton_sleeve",
            "width_in": round(total_w, 4),
            "height_in": round(h, 4),
            "fold_offsets_in": folds,
            "corner_radius_in": 0.0,
            "bleed_in": bleed_in,
            "safety_in": safety_in,
            "width_pt": round(inch(total_w), 2),
            "height_pt": round(inch(h), 2),
            "label_desc": f'{total_w:.2f}"(W) x {h:.2f}"(H) OPEN SLEEVE',
        })
    else:
        raise ValueError(f"Unsupported container type {kind!r}; expected cylinder, tapered, pouch, carton, or sleeve")

    return {"container_type": kind, "panels": panels}


# ---------------------------------------------------------------------------
# Vector Asset Loader (Smoky Co. Cloud Mark & Smoky Mountain CBD Mark)
# ---------------------------------------------------------------------------
def load_brand_vectors(override_path: Path | None = None) -> dict[str, Any]:
    asset_path = override_path or (Path(__file__).resolve().parent.parent / "assets" / "brand_vectors.json")
    if asset_path.exists():
        return json.loads(asset_path.read_text(encoding="utf-8"))
    return {}


def draw_normalized_vector(
    c: canvas.Canvas,
    vec: dict[str, Any],
    cx: float,
    cy: float,
    target_w: float,
    text_color: PCMYKColor,
    smoke_color: PCMYKColor | None = None,
) -> tuple[float, float]:
    """Draws normalized top-down vector paths centered at (cx, cy) in bottom-up PDF space."""
    if not vec:
        return (0.0, 0.0)
    vw = vec["width"]
    vh = vec["height"]
    scale = target_w / vw
    target_h = vh * scale
    x0 = cx - target_w / 2.0
    y_top = cy + target_h / 2.0

    for p_info in vec["paths"]:
        role = p_info.get("role", "text")
        if role == "smoke":
            if smoke_color is None:
                continue
            c.setFillColor(smoke_color)
        else:
            c.setFillColor(text_color)

        path = c.beginPath()
        items = p_info["items"]
        last_pt = None
        for it in items:
            op = it[0]
            if op == "l":
                p1, p2 = it[1], it[2]
                x1, y1 = x0 + p1[0] * scale, y_top - p1[1] * scale
                x2, y2 = x0 + p2[0] * scale, y_top - p2[1] * scale
                if last_pt is None or math.hypot(last_pt[0] - x1, last_pt[1] - y1) > 0.08 * scale:
                    path.moveTo(x1, y1)
                path.lineTo(x2, y2)
                last_pt = (x2, y2)
            elif op == "c":
                p1, p2, p3, p4 = it[1], it[2], it[3], it[4]
                x1, y1 = x0 + p1[0] * scale, y_top - p1[1] * scale
                x2, y2 = x0 + p2[0] * scale, y_top - p2[1] * scale
                x3, y3 = x0 + p3[0] * scale, y_top - p3[1] * scale
                x4, y4 = x0 + p4[0] * scale, y_top - p4[1] * scale
                if last_pt is None or math.hypot(last_pt[0] - x1, last_pt[1] - y1) > 0.08 * scale:
                    path.moveTo(x1, y1)
                path.curveTo(x2, y2, x3, y3, x4, y4)
                last_pt = (x4, y4)
        mode = 0 if p_info.get("even_odd") else 1
        c.drawPath(path, stroke=0, fill=1, fillMode=mode)
    return (target_w, target_h)


# ---------------------------------------------------------------------------
# Pure Vector UPC-A Barcode & Vector QR Code
# ---------------------------------------------------------------------------
def validate_upca_box(
    w_pt: float,
    h_pt: float,
    bg_pad: float = 2.0,
    allow_non_retail_truncation: bool = False,
) -> dict[str, float]:
    """
    Computes UPC-A module width, 9X quiet zones, and bar heights in points.
    Enforces GS1 80% retail minimums (X >= 0.0104 in, bar height >= 0.72 in)
    unless allow_non_retail_truncation=True is explicitly requested.
    """
    mod_w = w_pt / float(GS1_UPCA_MODULES_TOTAL)
    quiet_w = 9.0 * mod_w
    text_h = min(5.2, max(4.2, h_pt * 0.09))
    bar_bottom_short_off = bg_pad + text_h
    guard_drop = min(text_h - 0.8, 5.0 * mod_w)
    bar_bottom_guard_off = max(bg_pad + 0.8, bar_bottom_short_off - guard_drop)
    bar_top_off = h_pt - bg_pad
    short_bar_h = bar_top_off - bar_bottom_short_off
    if not allow_non_retail_truncation:
        min_mod_pt = inch(GS1_UPCA_MIN_X_IN)
        min_bar_pt = inch(GS1_UPCA_MIN_BAR_HEIGHT_IN)
        if mod_w + 1e-6 < min_mod_pt or short_bar_h + 1e-6 < min_bar_pt:
            raise ValueError(
                f"Retail UPC-A box ({w_pt / PT_PER_INCH:.3f}\" x {h_pt / PT_PER_INCH:.3f}\") violates GS1 80% minimums: "
                f"got X={mod_w / PT_PER_INCH:.4f}\" (min {GS1_UPCA_MIN_X_IN:.4f}\", total width >= {GS1_UPCA_MIN_WIDTH_IN:.4f}\") "
                f"and bar_height={short_bar_h / PT_PER_INCH:.3f}\" (min {GS1_UPCA_MIN_BAR_HEIGHT_IN:.2f}\"). "
                "Enlarge the barcode/panel, omit 'upc', or explicitly set allow_non_retail_truncation=True."
            )
    if mod_w <= 0 or short_bar_h <= 2.0:
        raise ValueError("UPC-A box dimensions are non-positive or degenerate")
    return {
        "mod_w_pt": mod_w,
        "quiet_w_pt": quiet_w,
        "text_h_pt": text_h,
        "bar_bottom_short_off_pt": bar_bottom_short_off,
        "bar_bottom_guard_off_pt": bar_bottom_guard_off,
        "bar_top_off_pt": bar_top_off,
        "short_bar_h_pt": short_bar_h,
    }


def compute_qr_layout(size_pt: float, matrix_n: int, quiet_modules: float = QR_MIN_QUIET_MODULES) -> dict[str, float]:
    """
    Sizes a QR code's quiet zone strictly in matrix modules (>= 4 clear modules per side per ISO/IEC 18004).
    """
    if size_pt <= 0 or matrix_n <= 0:
        raise ValueError("QR size and matrix dimension must be positive")
    if quiet_modules + 1e-9 < QR_MIN_QUIET_MODULES:
        raise ValueError(f"QR quiet zone must be >= {QR_MIN_QUIET_MODULES:.1f} modules per ISO/IEC 18004; got {quiet_modules}")
    total_modules = float(matrix_n) + 2.0 * float(quiet_modules)
    cell_pt = size_pt / total_modules
    quiet_pad_pt = float(quiet_modules) * cell_pt
    return {
        "cell_pt": cell_pt,
        "quiet_pad_pt": quiet_pad_pt,
        "quiet_modules": float(quiet_modules),
        "total_modules": total_modules,
    }


def draw_vector_upca(
    c: canvas.Canvas,
    code: str,
    x: float,
    y: float,
    w: float,
    h: float,
    bg_pad: float = 2.0,
    allow_non_retail_truncation: bool = False,
) -> None:
    """Draws a Modulo-10 verified, GS1-sized 100% K pure-vector UPC-A barcode inside a 9X quiet-zone box."""
    digits, bits = normalize_and_encode_upca(code)
    metrics = validate_upca_box(w, h, bg_pad=bg_pad, allow_non_retail_truncation=allow_non_retail_truncation)

    c.saveState()
    c.setFillColor(CMYK_WHITE)
    c.rect(x, y, w, h, fill=1, stroke=0)

    mod_w = metrics["mod_w_pt"]
    quiet_w = metrics["quiet_w_pt"]
    text_h = metrics["text_h_pt"]
    bar_bottom_short = y + metrics["bar_bottom_short_off_pt"]
    bar_bottom_guard = y + metrics["bar_bottom_guard_off_pt"]
    bar_top = y + metrics["bar_top_off_pt"]

    c.setFillColor(CMYK_100K)
    i = 0
    while i < 95:
        if bits[i] == "1":
            j = i
            while j < 95 and bits[j] == "1":
                j += 1
            is_guard = (i < 10) or (45 <= i < 50) or (i >= 85)
            by = bar_bottom_guard if is_guard else bar_bottom_short
            bx = x + quiet_w + i * mod_w
            bw = (j - i) * mod_w
            c.rect(bx, by, bw, max(1.0, bar_top - by), fill=1, stroke=0)
            i = j
        else:
            i += 1

    c.setFont(resolve_font("AvenirCond-Demi"), min(4.8, text_h * 0.90))
    c.drawCentredString(x + quiet_w * 0.50, y + bg_pad + 0.4, digits[0])
    c.drawCentredString(x + quiet_w + 27.5 * mod_w, y + bg_pad + 0.4, digits[1:6])
    c.drawCentredString(x + quiet_w + 67.5 * mod_w, y + bg_pad + 0.4, digits[6:11])
    c.drawCentredString(x + w - quiet_w * 0.50, y + bg_pad + 0.4, digits[11])
    c.restoreState()


def draw_vector_qr(
    c: canvas.Canvas,
    url: str,
    x: float,
    y: float,
    size: float,
    quiet_modules: float = QR_MIN_QUIET_MODULES,
) -> None:
    """Draws a crisp 100% K pure-vector QR code with an ISO/IEC 18004 >= 4-module white quiet zone."""
    import qrcode

    qr_obj = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=0,
    )
    qr_obj.add_data(url)
    qr_obj.make(fit=True)
    matrix = qr_obj.get_matrix()
    n = len(matrix)
    layout = compute_qr_layout(size, n, quiet_modules=quiet_modules)
    cell = layout["cell_pt"]
    quiet_pad = layout["quiet_pad_pt"]

    c.saveState()
    c.setFillColor(CMYK_WHITE)
    c.rect(x, y, size, size, fill=1, stroke=0)
    c.setFillColor(CMYK_100K)
    for r_idx, row in enumerate(matrix):
        c_idx = 0
        while c_idx < n:
            if row[c_idx]:
                end = c_idx
                while end < n and row[end]:
                    end += 1
                rx = x + quiet_pad + c_idx * cell
                ry = y + size - quiet_pad - (r_idx + 1) * cell
                has_below = (r_idx + 1 < n) and any(matrix[r_idx + 1][k] for k in range(c_idx, end))
                h_rect = cell + (0.03 if has_below else 0.0)
                y_rect = ry - (0.03 if has_below else 0.0)
                c.rect(rx, y_rect, (end - c_idx) * cell, h_rect, fill=1, stroke=0)
                c_idx = end
            else:
                c_idx += 1
    c.restoreState()


# ---------------------------------------------------------------------------
# Curved & Tracked Typography Helpers
# ---------------------------------------------------------------------------
def draw_arched_text(
    c: canvas.Canvas,
    text: str,
    cx: float,
    cy: float,
    radius: float,
    font_name: str,
    font_size: float,
    color: PCMYKColor,
    tracking_pt: float = 0.8,
    top_arc: bool = True,
    center_angle_deg: float | None = None,
) -> None:
    """Draws crisp tracked text optically centered along a circular arc around `(cx, cy)`."""
    fn = resolve_font(font_name)
    c.saveState()
    c.setFont(fn, font_size)
    c.setFillColor(color)
    chars = list(text)
    if not chars:
        c.restoreState()
        return
    widths = [pdfmetrics.stringWidth(ch, fn, font_size) for ch in chars]
    total_w = sum(widths) + tracking_pt * max(0, len(chars) - 1)
    r_eff = max(2.0, (radius - font_size * 0.36) if top_arc else (radius + font_size * 0.36))
    total_angle = total_w / r_eff

    if top_arc:
        ang_deg = 90.0 if center_angle_deg is None else center_angle_deg
        start_theta = math.radians(ang_deg) + total_angle / 2.0
        cur_s = 0.0
        for i, ch in enumerate(chars):
            w = widths[i]
            theta = start_theta - (cur_s + w / 2.0) / r_eff
            px = cx + r_eff * math.cos(theta)
            py = cy + r_eff * math.sin(theta)
            c.saveState()
            c.translate(px, py)
            c.rotate(math.degrees(theta) - 90.0)
            c.drawCentredString(0, 0, ch)
            c.restoreState()
            cur_s += w + tracking_pt
    else:
        ang_deg = 270.0 if center_angle_deg is None else center_angle_deg
        start_theta = math.radians(ang_deg) - total_angle / 2.0
        cur_s = 0.0
        for i, ch in enumerate(chars):
            w = widths[i]
            theta = start_theta + (cur_s + w / 2.0) / r_eff
            px = cx + r_eff * math.cos(theta)
            py = cy + r_eff * math.sin(theta)
            c.saveState()
            c.translate(px, py)
            c.rotate(math.degrees(theta) + 90.0)
            c.drawCentredString(0, 0, ch)
            c.restoreState()
            cur_s += w + tracking_pt
    c.restoreState()


def draw_tracked_text(
    c: canvas.Canvas,
    text: str,
    cx: float,
    y: float,
    font_name: str,
    font_size: float,
    color: PCMYKColor,
    tracking_pt: float = 0.6,
    align: str = "center",
) -> float:
    """Draws horizontally tracked text and returns total rendered width in points."""
    fn = resolve_font(font_name)
    c.saveState()
    c.setFont(fn, font_size)
    c.setFillColor(color)
    chars = list(text)
    widths = [pdfmetrics.stringWidth(ch, fn, font_size) for ch in chars]
    total_w = sum(widths) + tracking_pt * max(0, len(chars) - 1)
    if align == "center":
        x = cx - total_w / 2.0
    elif align == "right":
        x = cx - total_w
    else:
        x = cx
    for ch, w in zip(chars, widths):
        c.drawString(x, y, ch)
        x += w + tracking_pt
    c.restoreState()
    return total_w


# ---------------------------------------------------------------------------
# Dieline Panel Geometry Primitives (Any Packaging Shape)
# ---------------------------------------------------------------------------
class DielinePanel:
    """Represents one packaging piece on a press sheet (circle, rect/rounded_rect, oval, conical_wrap, tuck_box, carton_sleeve)."""

    def __init__(
        self,
        panel_id: str,
        shape: str,
        cx: float,
        cy: float,
        width_in: float,
        height_in: float,
        bleed_in: float = 0.125,
        safety_in: float = 0.0625,
        corner_radius_in: float = 0.1092,
        top_width_in: float | None = None,
        fold_offsets_in: list[float] | None = None,
        inner_radius_in: float | None = None,
        outer_radius_in: float | None = None,
        sector_angle_deg: float | None = None,
        apex_down: bool = True,
        carton_net: dict[str, Any] | None = None,
        label_desc: str | None = None,
    ):
        if width_in <= 0 or height_in <= 0:
            raise ValueError(f"Panel {panel_id!r} dimensions must be positive, got {width_in}x{height_in}")
        self.panel_id = panel_id
        self.shape = shape
        self.cx = cx
        self.cy = cy
        self.width_in = float(width_in)
        self.height_in = float(height_in)
        self.bleed = inch(bleed_in)
        self.safety = inch(safety_in)
        self.bleed_in = float(bleed_in)
        self.safety_in = float(safety_in)
        self.corner_r = inch(corner_radius_in)
        self.fold_offsets = [inch(f) for f in (fold_offsets_in or [])]
        self.inner_radius_in: float | None = None
        self.outer_radius_in: float | None = None
        self.sector_angle_deg: float | None = None
        self.apex_down: bool = bool(apex_down)
        self.carton_net: dict[str, Any] | None = carton_net

        if self.shape in ("conical_wrap", "tapered_wrap"):
            if inner_radius_in is not None and outer_radius_in is not None and sector_angle_deg is not None:
                r_in = float(inner_radius_in)
                r_out = float(outer_radius_in)
                ang_deg = float(sector_angle_deg)
                if r_in <= 0 or r_out <= r_in or ang_deg <= 0 or ang_deg > 170.0:
                    raise ValueError(f"Invalid conical sector parameters: r_in={r_in}, r_out={r_out}, angle={ang_deg}")
                self.inner_radius_in = r_in
                self.outer_radius_in = r_out
                self.sector_angle_deg = ang_deg
                theta = math.radians(ang_deg)
                self.width_in = 2.0 * r_out * math.sin(theta / 2.0)
                self.height_in = r_out - r_in * math.cos(theta / 2.0)
            else:
                tw_in = float(top_width_in) if top_width_in is not None else float(width_in)
                sec = develop_conical_wrap(
                    arc_inner_in=min(float(width_in), tw_in),
                    arc_outer_in=max(float(width_in), tw_in),
                    band_height_in=float(height_in),
                    apex_down=(tw_in >= float(width_in)),
                )
                self.inner_radius_in = sec["inner_radius_in"]
                self.outer_radius_in = sec["outer_radius_in"]
                self.sector_angle_deg = sec["sector_angle_deg"]
                self.apex_down = sec["apex_down"]
                self.width_in = sec["bbox_width_in"]
                self.height_in = sec["bbox_height_in"]
            self.top_w = inch(self.width_in)
        elif self.shape in ("tuck_box", "carton_flat"):
            if self.carton_net is None:
                glue_in = 0.50
                avail_w = max(1.0, float(width_in) - glue_in)
                face_w = avail_w * 0.30
                depth_d = avail_w * 0.20
                tongue_t = round(min(0.625, max(0.375, depth_d * 0.45)), 4)
                body_h = max(1.0, float(height_in) - 2.0 * (depth_d + tongue_t))
                self.carton_net = build_reverse_tuck_carton(
                    width_in=face_w,
                    depth_in=depth_d,
                    height_in=body_h,
                    glue_flap_in=glue_in,
                    tuck_tongue_in=tongue_t,
                )
            self.width_in = float(self.carton_net["total_width_in"])
            self.height_in = float(self.carton_net["total_height_in"])
            self.top_w = inch(self.width_in)
        else:
            self.top_w = inch(top_width_in) if top_width_in is not None else inch(self.width_in)

        self.w = inch(self.width_in)
        self.h = inch(self.height_in)
        self.label_desc = label_desc or self._default_desc()

    def _default_desc(self) -> str:
        if self.shape == "circle":
            return f'{self.width_in:.2f}" CIRCLE'
        if self.shape == "oval":
            return f'{self.width_in:.2f}"(W) x {self.height_in:.2f}"(H) OVAL'
        if self.shape in ("conical_wrap", "tapered_wrap"):
            return f'{self.width_in:.2f}"(W) x {self.height_in:.2f}"(H) CONICAL SECTOR'
        if self.shape in ("tuck_box", "carton_flat"):
            return f'{self.width_in:.2f}"(W) x {self.height_in:.2f}"(H) RTE FOLDING CARTON'
        if self.shape == "carton_sleeve":
            return f'{self.width_in:.2f}"(W) x {self.height_in:.2f}"(H) OPEN SLEEVE'
        return f'{self.width_in:.2f}"(W) x {self.height_in:.2f}"(H) RECTANGLE'

    @property
    def x0(self) -> float:
        return self.cx - self.w / 2.0

    @property
    def y0(self) -> float:
        return self.cy - self.h / 2.0

    def annular_sector_points(self, offset: float = 0.0, arc_steps: int = 96) -> list[tuple[float, float]]:
        """Computes exact perpendicular normal-offset points along concentric inner/outer arcs and radial rays."""
        assert self.inner_radius_in is not None and self.outer_radius_in is not None and self.sector_angle_deg is not None
        r1_0 = inch(self.inner_radius_in)
        r2_0 = inch(self.outer_radius_in)
        half_theta = math.radians(self.sector_angle_deg) / 2.0
        r1 = max(2.0, r1_0 - offset)
        r2 = max(r1 + 2.0, r2_0 + offset)
        a1 = max(0.002, half_theta + math.asin(max(-0.95, min(0.95, offset / r1))))
        a2 = max(0.002, half_theta + math.asin(max(-0.95, min(0.95, offset / r2))))

        pts: list[tuple[float, float]] = []
        if self.apex_down:
            y_apex = self.cy - 0.5 * (r2_0 + r1_0 * math.cos(half_theta))
            for i in range(arc_steps + 1):
                ang = -a2 + (2.0 * a2 * i) / arc_steps
                pts.append((self.cx + r2 * math.sin(ang), y_apex + r2 * math.cos(ang)))
            for i in range(arc_steps + 1):
                ang = a1 - (2.0 * a1 * i) / arc_steps
                pts.append((self.cx + r1 * math.sin(ang), y_apex + r1 * math.cos(ang)))
        else:
            y_apex = self.cy + 0.5 * (r2_0 + r1_0 * math.cos(half_theta))
            for i in range(arc_steps + 1):
                ang = -a2 + (2.0 * a2 * i) / arc_steps
                pts.append((self.cx + r2 * math.sin(ang), y_apex - r2 * math.cos(ang)))
            for i in range(arc_steps + 1):
                ang = a1 - (2.0 * a1 * i) / arc_steps
                pts.append((self.cx + r1 * math.sin(ang), y_apex - r1 * math.cos(ang)))
        return pts

    def carton_outline_points(self, offset: float = 0.0) -> list[tuple[float, float]]:
        """Computes exact rectilinear normal-offset silhouette vertices around a Reverse Tuck End carton net."""
        assert self.carton_net is not None
        cols = self.carton_net["columns"]
        n = len(cols)
        x_orig = self.x0
        y_orig = self.y0
        x0s = [x_orig + inch(col["x0_in"]) for col in cols]
        x1s = [x_orig + inch(col["x1_in"]) for col in cols]
        bs = [y_orig + inch(col["y0_in"]) for col in cols]
        ts = [y_orig + inch(col["y1_in"]) for col in cols]

        pts: list[tuple[float, float]] = []
        for i in range(n):
            if i == 0:
                xl = x0s[0] - offset
            elif ts[i] > ts[i - 1] + 1e-6:
                xl = x0s[i] - offset
            elif ts[i] < ts[i - 1] - 1e-6:
                xl = x0s[i] + offset
            else:
                xl = x0s[i]

            if i == n - 1:
                xr = x1s[n - 1] + offset
            elif ts[i + 1] > ts[i] + 1e-6:
                xr = x1s[i] - offset
            elif ts[i + 1] < ts[i] - 1e-6:
                xr = x1s[i] + offset
            else:
                xr = x1s[i]
            pts.append((xl, ts[i] + offset))
            pts.append((xr, ts[i] + offset))

        for i in range(n - 1, -1, -1):
            if i == n - 1:
                xr = x1s[n - 1] + offset
            elif bs[i + 1] < bs[i] - 1e-6:
                xr = x1s[i] - offset
            elif bs[i + 1] > bs[i] + 1e-6:
                xr = x1s[i] + offset
            else:
                xr = x1s[i]

            if i == 0:
                xl = x0s[0] - offset
            elif bs[i - 1] < bs[i] - 1e-6:
                xl = x0s[i] + offset
            elif bs[i - 1] > bs[i] + 1e-6:
                xl = x0s[i] - offset
            else:
                xl = x0s[i]
            pts.append((xr, bs[i] - offset))
            pts.append((xl, bs[i] - offset))
        return pts

    def fold_segments(self) -> list[tuple[float, float, float, float]]:
        """Returns score/fold segments `(x1, y1, x2, y2)` in PDF points for cartons and sleeves."""
        if self.carton_net:
            return [
                (self.x0 + inch(seg[0]), self.y0 + inch(seg[1]), self.x0 + inch(seg[2]), self.y0 + inch(seg[3]))
                for seg in self.carton_net.get("fold_lines_in", [])
            ]
        return [(self.x0 + fx, self.y0, self.x0 + fx, self.y0 + self.h) for fx in self.fold_offsets]

    def extra_cut_segments(self) -> list[tuple[float, float, float, float]]:
        """Returns interior die-knife flap-separation slits `(x1, y1, x2, y2)` in PDF points."""
        if self.carton_net:
            return [
                (self.x0 + inch(seg[0]), self.y0 + inch(seg[1]), self.x0 + inch(seg[2]), self.y0 + inch(seg[3]))
                for seg in self.carton_net.get("flap_slits_in", [])
            ]
        return []

    def trapezoid_vertices(self, offset: float = 0.0) -> list[tuple[float, float]]:
        """Computes exact parallel normal-offset vertices `(bl, br, tr, tl)` for `flat_trapezoid` prism faces."""
        delta = (self.top_w - self.w) / 2.0
        slant = math.hypot(self.h, delta)
        half_bot = max(1.0, self.w / 2.0 + offset * (slant - delta) / self.h)
        half_top = max(1.0, self.top_w / 2.0 + offset * (slant + delta) / self.h)
        y_bot = self.cy - self.h / 2.0 - offset
        y_top = self.cy + self.h / 2.0 + offset
        return [
            (self.cx - half_bot, y_bot),
            (self.cx + half_bot, y_bot),
            (self.cx + half_top, y_top),
            (self.cx - half_top, y_top),
        ]

    def make_path(self, c: canvas.Canvas, offset: float = 0.0):
        """Builds a ReportLab Path for perpendicular `offset` (`+bleed`, `0.0=diecut`, `-safety`)."""
        p = c.beginPath()
        if self.shape == "circle":
            r = max(1.0, self.w / 2.0 + offset)
            p.circle(self.cx, self.cy, r)
        elif self.shape == "oval":
            rx = max(1.0, self.w / 2.0 + offset)
            ry = max(1.0, self.h / 2.0 + offset)
            p.ellipse(self.cx - rx, self.cy - ry, 2 * rx, 2 * ry)
        elif self.shape in ("conical_wrap", "tapered_wrap"):
            pts = self.annular_sector_points(offset)
            p.moveTo(*pts[0])
            for pt in pts[1:]:
                p.lineTo(*pt)
            p.close()
        elif self.shape in ("tuck_box", "carton_flat"):
            pts = self.carton_outline_points(offset)
            p.moveTo(*pts[0])
            for pt in pts[1:]:
                p.lineTo(*pt)
            p.close()
        elif self.shape == "flat_trapezoid":
            bl, br, tr, tl = self.trapezoid_vertices(offset)
            p.moveTo(*bl)
            p.lineTo(*br)
            p.lineTo(*tr)
            p.lineTo(*tl)
            p.close()
        else:
            rw = max(2.0, self.w + 2 * offset)
            rh = max(2.0, self.h + 2 * offset)
            rr = max(0.0, self.corner_r + offset)
            p.roundRect(self.cx - rw / 2.0, self.cy - rh / 2.0, rw, rh, rr)
        return p


# ---------------------------------------------------------------------------
# Press Sheet / Smoky Co. Master Dieline Template Builder
# ---------------------------------------------------------------------------
class SmokyDielineSheet:
    """
    Constructs a press-ready PDF sheet with Illustrator/RIP OCG layers,
    non-printing spot separations with stroke overprint, crop marks, dimension callouts,
    Unwind Chart, and branded production footer block.
    """

    OCG_ORDER = [
        ("LayerDieTemplate", "Die Template"),
        ("LayerDimensions", "Dimensions"),
        ("LayerBleed", "Bleed"),
        ("LayerSafety", "Safety"),
        ("LayerDiecut", "Diecut"),
        ("LayerArtwork", "Artwork"),
    ]

    def __init__(
        self,
        out_pdf: Path,
        panels: list[DielinePanel],
        title: str,
        sku_meta: dict[str, Any] | None = None,
        page_w_in: float | None = None,
        page_h_in: float | None = None,
        brand_vectors_path: Path | None = None,
    ):
        if not HAS_REPORTLAB:
            raise RuntimeError(
                "Missing PDF rendering dependencies; run via: "
                "uv run --with reportlab,pikepdf,pymupdf,qrcode,pillow python3 ..."
            )
        if not panels:
            raise ValueError("SmokyDielineSheet requires at least one DielinePanel")

        register_fonts()
        self.out_pdf = Path(out_pdf)
        self.panels = panels
        self.title = title
        self.meta = sku_meta or {}
        self.brand_vecs = load_brand_vectors(brand_vectors_path)

        max_x = max(p.cx + max(p.w, p.top_w) / 2.0 + p.bleed + inch(2.8) for p in panels)
        max_y = max(p.cy + p.h / 2.0 + p.bleed + inch(1.4) for p in panels)
        self.page_w = inch(page_w_in) if page_w_in else max(1336.93, max_x)
        self.page_h = inch(page_h_in) if page_h_in else max(696.35, max_y)

        self.c = canvas.Canvas(str(self.out_pdf), pagesize=(self.page_w, self.page_h))
        self.c.setTitle(self.title)
        self.c.setAuthor(str(self.meta.get("company", "Smoky Product Company — Automated Dieline Engine")))
        self.c.setSubject("CMYK Press-Ready Label & Packaging Dieline")

    def begin_layer(self, tag: str) -> None:
        self.c.saveState()
        self.c._code.append(f"/OC /{tag} BDC")

    def end_layer(self) -> None:
        self.c._code.append("EMC")
        self.c.restoreState()

    def draw_artwork(self, artwork_fn: Callable[[canvas.Canvas, list[DielinePanel], dict[str, Any]], None]) -> None:
        self.begin_layer("LayerArtwork")
        for p in self.panels:
            self._draw_crop_marks(p)
        artwork_fn(self.c, self.panels, self.brand_vecs)
        self.end_layer()

    def _draw_crop_marks(self, p: DielinePanel) -> None:
        c = self.c
        c.saveState()
        c.setStrokeColor(CMYK_100K)
        c.setLineWidth(0.5)
        gap = p.bleed + 4.0
        mark_len = 9.0
        span_w = max(p.w, p.top_w)
        x0, y0 = p.cx - span_w / 2.0, p.cy - p.h / 2.0
        x1, y1 = p.cx + span_w / 2.0, p.cy + p.h / 2.0
        c.line(x0 - gap - mark_len, y0, x0 - gap, y0)
        c.line(x1 + gap, y0, x1 + gap + mark_len, y0)
        c.line(x0 - gap - mark_len, y1, x0 - gap, y1)
        c.line(x1 + gap, y1, x1 + gap + mark_len, y1)
        c.line(x0, y0 - gap - mark_len, x0, y0 - gap)
        c.line(x0, y1 + gap, x0, y1 + gap + mark_len)
        c.line(x1, y0 - gap - mark_len, x1, y0 - gap)
        c.line(x1, y1 + gap, x1, y1 + gap + mark_len)
        c.restoreState()

    def draw_technical_overlays(self) -> None:
        c = self.c

        # 1. Bleed Layer (Spot Green Dashed, Overprint)
        self.begin_layer("LayerBleed")
        c._code.append("/GSOverprint gs")
        c.setStrokeColor(SPOT_BLEED)
        c.setLineWidth(0.85)
        c.setDash([3.5, 2.5], 0)
        for p in self.panels:
            c.drawPath(p.make_path(c, +p.bleed), stroke=1, fill=0)
        self.end_layer()

        # 2. Safety Layer (Spot Red Dashed, Overprint)
        self.begin_layer("LayerSafety")
        c._code.append("/GSOverprint gs")
        c.setStrokeColor(SPOT_SAFETY)
        c.setLineWidth(0.95)
        c.setDash([3.0, 3.0], 0)
        for p in self.panels:
            c.drawPath(p.make_path(c, -p.safety), stroke=1, fill=0)
        self.end_layer()

        # 3. Diecut Layer (Spot Cyan "Die Line" Solid 1pt, Overprint + Flap Slits + Fold lines)
        self.begin_layer("LayerDiecut")
        c._code.append("/GSOverprint gs")
        c.setStrokeColor(SPOT_DIELINE)
        c.setLineWidth(1.1)
        c.setDash([], 0)
        for p in self.panels:
            c.drawPath(p.make_path(c, 0.0), stroke=1, fill=0)
            for x1, y1, x2, y2 in p.extra_cut_segments():
                c.line(x1, y1, x2, y2)
            folds = p.fold_segments()
            if folds:
                c.setStrokeColor(SPOT_FOLD)
                c.setDash([4.0, 2.5], 0)
                for x1, y1, x2, y2 in folds:
                    c.line(x1, y1, x2, y2)
                c.setStrokeColor(SPOT_DIELINE)
                c.setDash([], 0)
        self.end_layer()

        # 4. Dimensions Layer (Exact callout bars & inch measurements)
        self.begin_layer("LayerDimensions")
        c.setStrokeColor(CMYK_DARK_CHARCOAL)
        c.setFillColor(CMYK_DARK_CHARCOAL)
        c.setLineWidth(0.9)
        for p in self.panels:
            span_w = max(p.w, p.top_w)
            x0, y0 = p.cx - span_w / 2.0, p.cy - p.h / 2.0
            x1, y1 = p.cx + span_w / 2.0, p.cy + p.h / 2.0
            wy = y1 + p.bleed + 18.0
            c.line(x0, wy - 7, x0, wy + 7)
            c.line(x1, wy - 7, x1, wy + 7)
            c.line(x0, wy, x1, wy)
            c.setFont(resolve_font("Avenir-Demi"), 10.5)
            c.drawCentredString(p.cx, wy + 8.5, f'{p.width_in:.2f}"')

            is_left = p.cx < self.page_w * 0.42
            hx = (x0 - p.bleed - 18.0) if is_left else (x1 + p.bleed + 18.0)
            c.line(hx - 7, y0, hx + 7, y0)
            c.line(hx - 7, y1, hx + 7, y1)
            c.line(hx, y0, hx, y1)
            if is_left:
                c.drawRightString(hx - 9.0, p.cy - 3.5, f'{p.height_in:.2f}"')
            else:
                c.drawString(hx + 9.0, p.cy - 3.5, f'{p.height_in:.2f}"')
        self.end_layer()

        # 5. Die Template Layer (Branded Proof Banner + Unwind Chart + Specs + Legend)
        self.begin_layer("LayerDieTemplate")
        self._draw_unwind_chart()
        self._draw_smoky_footer_banner()
        self.end_layer()

    def _draw_unwind_chart(self) -> None:
        c = self.c
        unwind_sel = int(self.meta.get("unwind", 3))
        box_w = 57.0
        box_h = 80.0
        total_w = box_w * 4
        start_x = self.page_w - total_w - 28.0
        base_y = 156.0

        c.setFillColor(CMYK_DARK_CHARCOAL)
        c.setFont(resolve_font("Avenir-Heavy"), 11.5)
        c.drawCentredString(start_x + total_w / 2.0, base_y + box_h + 21.0, "UNWIND CHART")
        c.setFont(resolve_font("Avenir-BoldItalic"), 9.2)
        c.drawCentredString(start_x + total_w / 2.0, base_y + box_h + 8.5, "LABEL SIDE OUT")

        rotations = {1: 0, 2: 180, 3: 90, 4: -90}
        for idx in range(1, 5):
            bx = start_x + (idx - 1) * box_w
            c.setStrokeColor(CMYK_DARK_CHARCOAL)
            c.setLineWidth(1.4)
            c.rect(bx, base_y, box_w, box_h, stroke=1, fill=0)

            c.setLineWidth(0.85)
            web = c.beginPath()
            web.moveTo(bx + 12, base_y + 27)
            web.curveTo(bx + 7, base_y + 46, bx + 9, base_y + 62, bx + 16, base_y + 73)
            web.lineTo(bx + 42, base_y + 73)
            web.curveTo(bx + 35, base_y + 62, bx + 33, base_y + 46, bx + 36, base_y + 26)
            web.close()
            c.drawPath(web, stroke=1, fill=0)

            rcx, rcy = bx + 44.0, base_y + 32.0
            c.setFillColor(CMYK_WHITE)
            c.circle(rcx, rcy, 9.0, stroke=1, fill=1)
            c.circle(rcx, rcy, 5.5, stroke=1, fill=0)
            c.setFillColor(CMYK_DARK_CHARCOAL)
            c.circle(rcx, rcy, 2.3, stroke=0, fill=1)
            c.line(bx + 12, base_y + 27, rcx - 3, rcy - 8.6)

            c.saveState()
            c.translate(bx + 23.5, base_y + 50.5)
            c.rotate(rotations[idx])
            c.setFillColor(CMYK_DARK_CHARCOAL)
            c.setFont(resolve_font("AvenirCond-Bold"), 5.8)
            c.drawCentredString(0, 5.2, "LABEL READS")
            c.drawCentredString(0, -1.8, "THIS WAY")
            c.restoreState()

            c.setFillColor(CMYK_DARK_CHARCOAL)
            c.setFont(resolve_font("Avenir-BoldItalic"), 10.0)
            c.drawRightString(bx + 23.0, base_y + 7.0, str(idx))
            chk_x, chk_y = bx + 27.0, base_y + 5.5
            if idx == unwind_sel:
                c.setFillColor(CMYK_MAGENTA_CHECK)
                c.rect(chk_x, chk_y, 12.0, 12.0, stroke=1, fill=1)
                c.setStrokeColor(CMYK_WHITE)
                c.setLineWidth(1.5)
                c.line(chk_x + 2.5, chk_y + 6.0, chk_x + 5.2, chk_y + 3.2)
                c.line(chk_x + 5.2, chk_y + 3.2, chk_x + 9.8, chk_y + 9.2)
            else:
                c.rect(chk_x, chk_y, 12.0, 12.0, stroke=1, fill=0)

    def _draw_smoke_clouds(self, x0: float, y0: float, w: float, h: float) -> None:
        c = self.c
        c.saveState()
        clip = c.beginPath()
        clip.rect(x0, y0, w, h)
        c.clipPath(clip, stroke=0, fill=0)

        c.setFillColor(CMYK_RICH_BLACK)
        c.rect(x0, y0, w, h, stroke=0, fill=1)

        cloud_layers = [
            (PCMYKColor(48, 36, 34, 80), [
                (x0 + 35, y0 + 18, 62), (x0 + 95, y0 + 12, 48), (x0 + 150, y0 + 6, 38),
                (x0 + 18, y0 + 75, 44), (x0 + 72, y0 + 122, 52), (x0 + 140, y0 + 132, 38),
                (x0 + w - 40, y0 + 22, 66), (x0 + w - 105, y0 + 10, 50), (x0 + w - 165, y0 + 8, 36),
                (x0 + w - 25, y0 + 92, 48), (x0 + w - 85, y0 + 126, 54),
            ]),
            (PCMYKColor(40, 28, 26, 68), [
                (x0 + 15, y0 + 10, 44), (x0 + 68, y0 + 4, 34), (x0 + 42, y0 + 134, 36),
                (x0 + w - 18, y0 + 14, 46), (x0 + w - 72, y0 + 4, 36), (x0 + w - 48, y0 + 135, 38),
            ]),
        ]
        for col, puffs in cloud_layers:
            c.setFillColor(col)
            for px, py, pr in puffs:
                c.circle(px, py, pr, stroke=0, fill=1)

        c.setStrokeColor(PCMYKColor(32, 22, 20, 58))
        c.setLineWidth(2.2)
        for side in (-1, 1):
            sx = x0 + w / 2.0 + side * 125
            wisp = c.beginPath()
            wisp.moveTo(sx, y0 + 34)
            wisp.curveTo(sx + side * 45, y0 + 52, sx + side * 30, y0 + 88, sx + side * 88, y0 + 104)
            wisp.curveTo(sx + side * 128, y0 + 114, sx + side * 145, y0 + 82, sx + side * 195, y0 + 96)
            c.drawPath(wisp, stroke=1, fill=0)

        c.setStrokeColor(CMYK_SMOKE_GOLD)
        c.setLineWidth(0.75)
        c.line(x0 + 18, y0 + h - 8, x0 + w - 18, y0 + h - 8)
        c.line(x0 + 18, y0 + 8, x0 + w - 18, y0 + 8)
        c.restoreState()

    def _draw_smoky_footer_banner(self) -> None:
        c = self.c
        bar_h = 138.6
        y0 = 0.7
        w = self.page_w - 1.4
        x0 = 0.7

        c.setFillColor(CMYK_WHITE)
        c.rect(x0, y0, w, bar_h, stroke=0, fill=1)

        col_strip = 16.5
        col_desc_end = 315.0
        col_brand_end = self.page_w - 314.5
        col_color_end = self.page_w - 164.0

        # 1. Left vertical "DIELINE INFO" strip
        c.setFillColor(CMYK_PAPER_GRAY)
        c.rect(x0, y0, col_strip, bar_h, stroke=0, fill=1)
        c.setFillColor(CMYK_DARK_CHARCOAL)
        c.setFont(resolve_font("AvenirCond-Bold"), 7.6)
        letters = list("DIELINE INFO")
        step = (bar_h - 18.0) / len(letters)
        for i, ch in enumerate(letters):
            c.drawCentredString(x0 + col_strip / 2.0, y0 + bar_h - 15.0 - i * step, ch)

        # 2. Description & Production Spec Column
        tx = x0 + col_strip + 11.0
        ty = y0 + bar_h - 20.0
        c.setFillColor(CMYK_DARK_CHARCOAL)
        c.setFont(resolve_font("Avenir-Bold"), 11.0)
        c.drawString(tx, ty, "Description:")
        ty -= 15.5
        c.setFont(resolve_font("AvenirCond-Demi"), 10.5)
        for p in self.panels:
            c.drawString(tx, ty, p.label_desc)
            ty -= 14.2

        stock = self.meta.get("stock", "WHITE BOPP / PAPER STOCK")
        finish = self.meta.get("finish", "MATTE LAMINATE FINISH")
        imprint = self.meta.get("imprint", "CMYK PROCESS IMPRINT")
        sku_code = self.meta.get("sku", "")
        for spec_line in [imprint, stock, finish]:
            c.drawString(tx, ty, spec_line)
            ty -= 14.0
        if sku_code:
            c.setFont(resolve_font("AvenirCond-Med"), 8.5)
            c.setFillColor(PCMYKColor(25, 20, 20, 55))
            c.drawString(tx, y0 + 8.5, f'SKU: {sku_code}  |  BLEED: 0.125"  |  SAFETY: 0.0625"')

        # 3. Center Branded Production Panel
        brand_w = col_brand_end - col_desc_end
        self._draw_smoke_clouds(col_desc_end, y0, brand_w, bar_h)
        smoky_vec = self.brand_vecs.get("smoky_co")
        bcx = col_desc_end + brand_w / 2.0
        company_title = str(self.meta.get("company_header", "SMOKY PRODUCT COMPANY"))
        origin_line = str(self.meta.get("origin_line", "ORIGIN:   MURPHY, NORTH CAROLINA  •  SMOKYMOUNTAINCBD.COM"))
        if smoky_vec:
            draw_normalized_vector(
                c,
                smoky_vec,
                cx=bcx - 165.0,
                cy=y0 + bar_h / 2.0 + 1.5,
                target_w=108.0,
                text_color=CMYK_WHITE,
                smoke_color=PCMYKColor(25, 18, 16, 45),
            )
            rx = bcx - 92.0
            draw_tracked_text(
                c, company_title, rx, y0 + 82.0,
                "Avenir-Heavy", 15.0, CMYK_WHITE, tracking_pt=2.2, align="left"
            )
            draw_tracked_text(
                c, "PRESS-READY PACKAGING & LABEL DIELINE MASTER", rx, y0 + 63.0,
                "AvenirCond-Demi", 9.5, CMYK_SMOKE_GOLD, tracking_pt=1.8, align="left"
            )
            c.setStrokeColor(PCMYKColor(20, 15, 15, 50))
            c.setLineWidth(0.6)
            c.line(rx, y0 + 55.0, rx + 310.0, y0 + 55.0)
            c.setFillColor(PCMYKColor(8, 6, 6, 12))
            c.setFont(resolve_font("Avenir-Med"), 8.2)
            prod_title = self.meta.get("product_line", self.title)
            c.drawString(rx, y0 + 40.0, f"PROJECT:  {prod_title}")
            c.drawString(rx, y0 + 26.5, origin_line)
        else:
            draw_tracked_text(
                c, company_title, bcx, y0 + 62.0,
                "Avenir-Heavy", 24.0, CMYK_WHITE, tracking_pt=2.5
            )

        # 4. Color Specification Column
        cx_col = col_brand_end + 12.0
        c.setFillColor(CMYK_DARK_CHARCOAL)
        c.setFont(resolve_font("Avenir-Bold"), 10.5)
        c.drawString(cx_col, y0 + bar_h - 20.0, "Color Specification")
        swatches = [
            ("Cyan", PCMYKColor(100, 0, 0, 0)),
            ("Magenta", PCMYKColor(0, 100, 0, 0)),
            ("Yellow", PCMYKColor(0, 0, 100, 0)),
            ("Black", PCMYKColor(0, 0, 0, 100)),
            ("White / BOPP", CMYK_WHITE),
        ]
        sy = y0 + bar_h - 42.0
        for s_name, s_col in swatches:
            c.setFillColor(s_col)
            c.setStrokeColor(CMYK_DARK_CHARCOAL)
            c.setLineWidth(0.5)
            c.rect(cx_col, sy, 13.0, 13.0, stroke=1, fill=1)
            c.setFillColor(CMYK_DARK_CHARCOAL)
            c.setFont(resolve_font("Avenir-Med"), 8.5)
            c.drawString(cx_col + 20.0, sy + 3.0, s_name)
            sy -= 20.0

        # 5. Legend Column (Dieline / Safety / Bleed / Fold)
        lx = col_color_end + 12.0
        c.setFillColor(CMYK_DARK_CHARCOAL)
        c.setFont(resolve_font("Avenir-Bold"), 10.5)
        c.drawString(lx, y0 + bar_h - 20.0, "Legend (Non-Printing)")
        legend_items = [
            ("Dieline (Cut)", SPOT_DIELINE, [], "Spot: Die Line"),
            ("Safety Zone", SPOT_SAFETY, [3.0, 3.0], "Spot: Safety Line"),
            ("Full Bleed", SPOT_BLEED, [3.5, 2.5], "Spot: Bleed Line"),
        ]
        if any(p.fold_segments() for p in self.panels):
            legend_items.append(("Fold / Score", SPOT_FOLD, [4.0, 2.5], "Spot: Fold Line"))

        ly = y0 + bar_h - 40.0
        for l_label, l_col, l_dash, l_sub in legend_items:
            c.saveState()
            c.setStrokeColor(l_col)
            c.setLineWidth(1.3)
            c.setDash(l_dash, 0)
            c.line(lx, ly + 4.0, lx + 22.0, ly + 4.0)
            c.restoreState()
            c.setFillColor(CMYK_DARK_CHARCOAL)
            c.setFont(resolve_font("Avenir-Demi"), 8.5)
            c.drawString(lx + 28.0, ly + 1.0, l_label)
            c.setFont(resolve_font("Avenir-Reg"), 6.8)
            c.setFillColor(PCMYKColor(20, 15, 15, 55))
            c.drawString(lx + 28.0, ly - 7.5, l_sub)
            ly -= 24.5

        c.setStrokeColor(CMYK_DARK_CHARCOAL)
        c.setLineWidth(1.2)
        c.rect(x0, y0, w, bar_h, stroke=1, fill=0)
        for div_x in [x0 + col_strip, col_desc_end, col_brand_end, col_color_end]:
            c.line(div_x, y0, div_x, y0 + bar_h)

    def save_and_postprocess(self) -> dict[str, Any]:
        """Saves PDF and injects OCG layer dictionary (with non-printing PrintState OFF on technical layers) + Overprint ExtGState + PDF boxes via pikepdf."""
        import pikepdf

        self.c.save()

        pdf = pikepdf.open(self.out_pdf, allow_overwriting_input=True)
        page = pdf.pages[0]
        if "/Resources" not in page:
            page["/Resources"] = pikepdf.Dictionary()
        if "/Properties" not in page.Resources:
            page.Resources["/Properties"] = pikepdf.Dictionary()
        if "/ExtGState" not in page.Resources:
            page.Resources["/ExtGState"] = pikepdf.Dictionary()

        gs_op = pdf.make_indirect(
            pikepdf.Dictionary(
                Type=pikepdf.Name.ExtGState,
                OP=True,
                op=True,
                OPM=1,
            )
        )
        page.Resources["/ExtGState"]["/GSOverprint"] = gs_op

        ocg_list = []
        for prop_key, human_name in self.OCG_ORDER:
            is_artwork = human_name == "Artwork"
            usage_dict = pikepdf.Dictionary(
                CreatorInfo=pikepdf.Dictionary(
                    Creator="Smoky Co. Dieline Engine",
                    Subtype=pikepdf.Name.Artwork if is_artwork else pikepdf.Name.Technical,
                ),
                View=pikepdf.Dictionary(ViewState=pikepdf.Name.ON),
                Print=pikepdf.Dictionary(
                    PrintState=pikepdf.Name.ON if is_artwork else pikepdf.Name.OFF,
                ),
            )
            ocg = pdf.make_indirect(
                pikepdf.Dictionary(
                    Type=pikepdf.Name.OCG,
                    Name=human_name,
                    Intent=[pikepdf.Name.View, pikepdf.Name.Design],
                    Usage=usage_dict,
                )
            )
            page.Resources["/Properties"][f"/{prop_key}"] = ocg
            ocg_list.append(ocg)

        pdf.Root["/OCProperties"] = pikepdf.Dictionary(
            OCGs=ocg_list,
            D=pikepdf.Dictionary(
                Name="Smoky Co. Press Layers",
                BaseState=pikepdf.Name.ON,
                ON=ocg_list,
                Order=ocg_list,
                AS=[
                    pikepdf.Dictionary(
                        Event=pikepdf.Name.View,
                        OCGs=ocg_list,
                        Category=[pikepdf.Name.View],
                    ),
                    pikepdf.Dictionary(
                        Event=pikepdf.Name.Print,
                        OCGs=ocg_list,
                        Category=[pikepdf.Name.Print],
                    ),
                ],
            ),
        )

        box = [0, 0, round(self.page_w, 3), round(self.page_h, 3)]
        page["/MediaBox"] = box
        page["/CropBox"] = box
        page["/BleedBox"] = box
        page["/TrimBox"] = box

        pdf.save(self.out_pdf)
        pdf.close()
        return verify_dieline_pdf(self.out_pdf, self.panels)


# ---------------------------------------------------------------------------
# Automated Pre-Flight Inspector (Full PyMuPDF + Stdlib Zlib Fallback)
# ---------------------------------------------------------------------------
def _extract_pdf_text_and_content_streams(raw: bytes) -> bytes:
    """Extracts PDF object headers + decompressed non-font FlateDecode content streams."""
    parts = bytearray()
    pos = 0
    for m in re.finditer(rb"(?<!end)stream\r?\n", raw):
        hdr = raw[pos : m.start()]
        parts.extend(hdr)
        start = m.end()
        end = raw.find(b"endstream", start)
        if end == -1:
            break
        pos = end + len(b"endstream")
        hdr_tail = hdr[-320:]
        if b"/Length1" in hdr_tail or b"/Subtype /Image" in hdr_tail or b"/Subtype/Image" in hdr_tail:
            continue
        chunk = raw[start:end].rstrip(b"\r\n")
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                parts.extend(b"\n")
                parts.extend(zlib.decompress(chunk, wbits))
                break
            except Exception:
                continue
    parts.extend(raw[pos:])
    return bytes(parts)


_RGB_OP_RE = re.compile(
    rb"(?:^|[\s\[\]>])(?:\d+(?:\.\d+)?|\.\d+)\s+(?:\d+(?:\.\d+)?|\.\d+)\s+(?:\d+(?:\.\d+)?|\.\d+)\s+(?:rg|RG)(?=[\s/\[<]|$)"
)
_CMYK_OP_RE = re.compile(
    rb"(?:^|[\s\[\]>])(?:\d+(?:\.\d+)?|\.\d+)\s+(?:\d+(?:\.\d+)?|\.\d+)\s+(?:\d+(?:\.\d+)?|\.\d+)\s+(?:\d+(?:\.\d+)?|\.\d+)\s+(?:k|K)(?=[\s/\[<]|$)"
)


def verify_dieline_pdf(pdf_path: Path, expected_panels: list[DielinePanel] | None = None) -> dict[str, Any]:
    """Verifies OCG layers, non-printing technical PrintState, spot separations, overprint, zero RGB leaks, and exact trim dimensions."""
    raw = Path(pdf_path).read_bytes()
    corpus = _extract_pdf_text_and_content_streams(raw)

    has_dieline_spot = (b"Die#20Line" in corpus) or (b"Die Line" in corpus)
    has_safety_spot = (b"Safety#20Line" in corpus) or (b"Safety Line" in corpus)
    has_bleed_spot = (b"Bleed#20Line" in corpus) or (b"Bleed Line" in corpus)
    has_overprint = (b"/GSOverprint" in corpus) and (b"/OP true" in corpus or b"/OPM 1" in corpus)
    has_rgb = (b"/DeviceRGB" in corpus) or bool(_RGB_OP_RE.search(corpus))
    has_cmyk = (b"/DeviceCMYK" in corpus) or bool(_CMYK_OP_RE.search(corpus))
    has_nonprinting_tech = (
        ((b"/PrintState /OFF" in corpus) or (b"/PrintState/OFF" in corpus))
        and ((b"/PrintState /ON" in corpus) or (b"/PrintState/ON" in corpus))
        and ((b"/Event /Print" in corpus) or (b"/Event/Print" in corpus))
    )

    try:
        import pikepdf

        with pikepdf.open(pdf_path) as pk:
            oc_props = pk.Root.get("/OCProperties")
            if oc_props is not None:
                ocg_objs = list(oc_props.get("/OCGs", []))
                as_list = list(oc_props.get("/D", {}).get("/AS", []))
                has_print_event = any(
                    str(item.get("/Event", "")) == "/Print" and "/Print" in [str(cat) for cat in item.get("/Category", [])]
                    for item in as_list
                )
                states_ok = bool(ocg_objs) and all(
                    str(ocg.get("/Usage", {}).get("/Print", {}).get("/PrintState", ""))
                    == ("/ON" if str(ocg.get("/Name", "")) == "Artwork" else "/OFF")
                    for ocg in ocg_objs
                )
                has_nonprinting_tech = bool(has_print_event and states_ok)
    except ImportError:
        pass

    panel_checks: list[dict[str, Any]] = []
    ocgs: list[str] = []

    try:
        import pymupdf

        doc = pymupdf.open(str(pdf_path))
        ocgs = [v["name"] for v in doc.get_ocgs().values()]
        page = doc[0]
        drawings = page.get_drawings()
        die_rects = [d["rect"] for d in drawings if d.get("layer") == "Diecut"]
        for p in expected_panels or []:
            expected_span_in = max(p.width_in, p.top_w / PT_PER_INCH)
            matched = any(
                abs(r.width / PT_PER_INCH - expected_span_in) < 0.005
                and abs(r.height / PT_PER_INCH - p.height_in) < 0.005
                for r in die_rects
            )
            panel_checks.append({
                "panel": p.panel_id,
                "expected_in": [round(expected_span_in, 4), round(p.height_in, 4)],
                "matched_exact_diecut": matched,
            })
        doc.close()
    except ImportError:
        for _, human_name in SmokyDielineSheet.OCG_ORDER:
            if human_name.encode("utf-8") in corpus:
                ocgs.append(human_name)

    ok = (
        has_dieline_spot
        and has_safety_spot
        and has_bleed_spot
        and has_overprint
        and has_nonprinting_tech
        and has_cmyk
        and not has_rgb
        and len(ocgs) >= 5
        and all(c["matched_exact_diecut"] for c in panel_checks)
    )
    return {
        "file": str(pdf_path),
        "size_kb": round(len(raw) / 1024.0, 1),
        "preflight_pass": ok,
        "cmyk_only_no_rgb": (has_cmyk and not has_rgb),
        "overprint_enabled": has_overprint,
        "non_printing_tech_layers": has_nonprinting_tech,
        "spot_separations": {
            "Die Line": has_dieline_spot,
            "Safety Line": has_safety_spot,
            "Bleed Line": has_bleed_spot,
        },
        "ocg_layers": ocgs,
        "panel_geometry": panel_checks,
    }


def render_previews(pdf_path: Path, out_dir: Path, stem: str, dpi: int = 220) -> dict[str, str]:
    """Renders full proof PNG + artwork-only (non-printing layers OFF) PNG proof using PyMuPDF OCG control."""
    import pymupdf

    out_dir.mkdir(parents=True, exist_ok=True)
    proof_png = out_dir / f"{stem}_proof.png"
    clean_png = out_dir / f"{stem}_artwork_only.png"

    doc = pymupdf.open(str(pdf_path))
    doc[0].get_pixmap(dpi=dpi).save(str(proof_png))

    on_xrefs = [xref for xref, info in doc.get_ocgs().items() if info["name"] == "Artwork"]
    off_xrefs = [xref for xref, info in doc.get_ocgs().items() if info["name"] != "Artwork"]
    doc.set_layer(-1, basestate="OFF", on=on_xrefs, off=off_xrefs)
    doc_clean = pymupdf.open("pdf", doc.tobytes())
    doc_clean[0].get_pixmap(dpi=dpi).save(str(clean_png))
    doc_clean.close()
    doc.close()
    return {"proof_png": str(proof_png), "clean_png": str(clean_png)}


# ---------------------------------------------------------------------------
# Responsive Generic Spec-Driven Artwork Renderer
# ---------------------------------------------------------------------------
def build_generic_spec_artwork(spec: dict[str, Any]) -> Callable[[canvas.Canvas, list[DielinePanel], dict[str, Any]], None]:
    """Creates clean, responsive CMYK packaging artwork scaled to arbitrary panel dimensions."""
    theme = spec.get("palette_cmyk", {})
    bg_col = PCMYKColor(*theme.get("bg", [78, 42, 58, 35]))
    accent_col = PCMYKColor(*theme.get("accent", [8, 25, 72, 2]))
    panel_col = PCMYKColor(*theme.get("panel", [65, 50, 48, 78]))

    brand = spec.get("brand", "SMOKY MOUNTAIN CBD")
    product_name = spec.get("product_name", "TOPICAL BALM")
    subtitle = spec.get("subtitle", "FULL SPECTRUM HEMP EXTRACT")
    net_wt = spec.get("net_wt", "NET WT. 4 OZ (113G)")
    cannabinoids = spec.get("cannabinoids", [{"mg": "500MG", "name": "CBD"}])
    ingredients = spec.get("ingredients", "Octyldodecanol, Squalane, Hemp Extract.")
    directions = spec.get("directions", "Apply to affected area and massage thoroughly as needed.")
    upc = spec.get("upc", "850043413028") if "upc" not in spec else spec.get("upc")
    allow_upc_trunc = bool(spec.get("allow_non_retail_upc_truncation", False))
    coa_url = spec.get("coa_url", "https://smokymountaincbd.com/lab-results/")

    def _render(c: canvas.Canvas, panels: list[DielinePanel], brand_vecs: dict[str, Any]) -> None:
        smcbd_vec = brand_vecs.get("smcbd")
        fn_reg = resolve_font("AvenirCond-Reg")
        fn_bold = resolve_font("AvenirCond-Bold")
        min_gs1_w = inch(GS1_UPCA_MIN_WIDTH_IN) + 1.4  # ~86.0 pt (1.195 in)
        min_gs1_h = inch(GS1_UPCA_MIN_BAR_HEIGHT_IN) + 10.2  # ~62.04 pt (0.862 in -> >=0.72 in short bar height)

        for p in panels:
            c.saveState()
            c.clipPath(p.make_path(c, +p.bleed), stroke=0, fill=0)
            span_w = max(p.w, p.top_w)
            bx0, by0 = p.cx - span_w / 2.0 - p.bleed, p.cy - p.h / 2.0 - p.bleed
            bw, bh = span_w + 2 * p.bleed, p.h + 2 * p.bleed
            c.setFillColor(bg_col)
            c.rect(bx0, by0, bw, bh, stroke=0, fill=1)

            if p.shape == "circle":
                r_safe = p.w / 2.0 - p.safety
                sc = max(0.32, min(1.3, p.w / 180.0))
                c.setStrokeColor(accent_col)
                c.setLineWidth(1.1 * sc)
                c.circle(p.cx, p.cy, r_safe - 3.0 * sc, stroke=1, fill=0)
                if p.w >= 95.0:
                    draw_arched_text(c, subtitle, p.cx, p.cy, r_safe - 10.0 * sc, "AvenirCond-Demi", 5.8 * sc, accent_col, 0.8 * sc, top_arc=True)
                if smcbd_vec:
                    draw_normalized_vector(c, smcbd_vec, p.cx, p.cy + (r_safe * 0.18 if p.w >= 95 else 0.0), p.w * (0.36 if p.w >= 95 else 0.52), CMYK_WHITE)
                else:
                    draw_tracked_text(c, brand, p.cx, p.cy + r_safe * 0.18, "AvenirCond-Heavy", 10.0 * sc, CMYK_WHITE, 0.8 * sc)
                if p.w >= 95.0:
                    draw_tracked_text(c, product_name.upper(), p.cx, p.cy - r_safe * 0.18, "DINCond-Bold", 16.0 * sc, CMYK_WHITE, 1.0 * sc)
                    badge_line = " • ".join(f"{cb['mg']} {cb['name']}" for cb in cannabinoids)
                    draw_tracked_text(c, badge_line, p.cx, p.cy - r_safe * 0.42, "AvenirCond-Bold", 6.0 * sc, accent_col, 0.4 * sc)
                    draw_tracked_text(c, net_wt, p.cx, p.cy - r_safe * 0.62, "AvenirCond-Med", 5.4 * sc, CMYK_WHITE, 0.6 * sc)
            elif p.shape in ("conical_wrap", "tapered_wrap"):
                assert p.inner_radius_in is not None and p.outer_radius_in is not None and p.sector_angle_deg is not None
                r1 = inch(p.inner_radius_in)
                r2 = inch(p.outer_radius_in)
                half_theta = math.radians(p.sector_angle_deg) / 2.0
                r_mid = 0.5 * (r1 + r2)
                band_safe = (r2 - r1) - 2.0 * p.safety
                arc_safe = 2.0 * r1 * half_theta - 2.0 * p.safety
                y_apex = (
                    p.cy - 0.5 * (r2 + r1 * math.cos(half_theta))
                    if p.apex_down
                    else p.cy + 0.5 * (r2 + r1 * math.cos(half_theta))
                )
                sc = max(0.55, min(1.25, band_safe / 108.0))
                top_mode = bool(p.apex_down)
                sgn = 1.0 if top_mode else -1.0
                draw_arched_text(c, brand.upper(), p.cx, y_apex, r_mid + sgn * band_safe * 0.30, "AvenirCond-Bold", 7.0 * sc, accent_col, 0.8 * sc, top_arc=top_mode, center_angle_deg=90.0 if top_mode else 270.0)
                draw_arched_text(c, product_name.upper(), p.cx, y_apex, r_mid + sgn * band_safe * 0.08, "DINCond-Bold", 15.0 * sc, CMYK_WHITE, 1.0 * sc, top_arc=top_mode, center_angle_deg=90.0 if top_mode else 270.0)
                badge_line = " • ".join(f"{cb['mg']} {cb['name']}" for cb in cannabinoids)
                draw_arched_text(c, f"{subtitle.upper()}  |  {badge_line}", p.cx, y_apex, r_mid - sgn * band_safe * 0.14, "AvenirCond-Demi", 6.0 * sc, accent_col, 0.6 * sc, top_arc=top_mode, center_angle_deg=90.0 if top_mode else 270.0)
                draw_arched_text(c, net_wt, p.cx, y_apex, r_mid - sgn * band_safe * 0.32, "AvenirCond-Med", 5.6 * sc, CMYK_WHITE, 0.6 * sc, top_arc=top_mode, center_angle_deg=90.0 if top_mode else 270.0)

                qr_sz = min(42.0 * sc, band_safe * 0.52)
                if qr_sz >= 18.0 and half_theta > 0.18:
                    ang_qr = -half_theta * 0.62
                    qx = p.cx + r_mid * math.sin(ang_qr)
                    qy = y_apex + (r_mid * math.cos(ang_qr) if top_mode else -r_mid * math.cos(ang_qr))
                    c.saveState()
                    c.translate(qx, qy)
                    c.rotate(-math.degrees(ang_qr) if top_mode else math.degrees(ang_qr))
                    draw_vector_qr(c, coa_url, -qr_sz / 2.0, -qr_sz / 2.0, qr_sz, quiet_modules=QR_MIN_QUIET_MODULES)
                    c.restoreState()

                if upc:
                    upc_w = min_gs1_w if not allow_upc_trunc else min(min_gs1_w, arc_safe * 0.36)
                    upc_h = min_gs1_h if not allow_upc_trunc else min(min_gs1_h, band_safe * 0.75)
                    if not allow_upc_trunc and (band_safe < upc_h or arc_safe * 0.42 < upc_w):
                        raise ValueError(
                            f"Conical panel {p.panel_id!r} safe band ({arc_safe / PT_PER_INCH:.2f}\" arc x {band_safe / PT_PER_INCH:.2f}\" slant) "
                            "cannot fit a GS1 80% retail UPC-A symbol; omit 'upc', enlarge container, or set allow_non_retail_upc_truncation=True."
                        )
                    ang_u = half_theta * 0.60
                    ux = p.cx + r_mid * math.sin(ang_u)
                    uy = y_apex + (r_mid * math.cos(ang_u) if top_mode else -r_mid * math.cos(ang_u))
                    c.saveState()
                    c.translate(ux, uy)
                    c.rotate(-math.degrees(ang_u) if top_mode else math.degrees(ang_u))
                    draw_vector_upca(c, str(upc), -upc_w / 2.0, -upc_h / 2.0, upc_w, upc_h, bg_pad=2.0, allow_non_retail_truncation=allow_upc_trunc)
                    c.restoreState()
            else:
                if p.carton_net is not None:
                    act_x0 = p.x0 + inch(float(p.carton_net["glue_flap_in"]))
                    act_w = p.w - inch(float(p.carton_net["glue_flap_in"]))
                    act_y0 = p.y0 + inch(float(p.carton_net["body_y0_in"]))
                    act_h = inch(float(p.carton_net["body_y1_in"]) - float(p.carton_net["body_y0_in"]))
                else:
                    act_x0, act_y0, act_w, act_h = p.x0, p.y0, p.w, p.h

                act_cy = act_y0 + act_h / 2.0
                sc_w = max(0.52, min(1.25, act_w / 462.0))
                sc_h = max(0.65, min(1.25, act_h / 121.0))
                sc = min(sc_w, sc_h)

                avail_safe_h = act_h - 2.0 * p.safety - 5.0
                if upc:
                    if not allow_upc_trunc:
                        upc_w = max(min_gs1_w, min(104.0 * sc_w, act_w * 0.34))
                        upc_h = max(min_gs1_h, min(70.0 * sc_h, avail_safe_h * 0.64))
                        req_right_w = upc_w + p.safety + 9.0 * sc
                        if avail_safe_h < min_gs1_h or act_w * 0.48 < req_right_w:
                            raise ValueError(
                                f"Panel {p.panel_id!r} safe area ({(act_w - 2 * p.safety) / PT_PER_INCH:.2f}\" x {avail_safe_h / PT_PER_INCH:.2f}\") "
                                f"cannot fit a GS1 80% retail UPC-A symbol (>={GS1_UPCA_MIN_WIDTH_IN:.3f}\" W, >={GS1_UPCA_MIN_BAR_HEIGHT_IN:.2f}\" bar H). "
                                "Enlarge panel, omit 'upc', or set allow_non_retail_upc_truncation=True."
                            )
                    else:
                        upc_w = min(min_gs1_w, act_w * 0.34)
                        upc_h = min(min_gs1_h, max(24.0, avail_safe_h * 0.50))
                        req_right_w = upc_w + p.safety + 9.0 * sc
                else:
                    upc_w, upc_h, req_right_w = 0.0, 0.0, 0.0

                right_w = max(act_w * 0.29, req_right_w)
                left_w = min(act_w * 0.26, max(act_w * 0.20, (act_w - right_w) * 0.42))
                center_x0 = act_x0 + left_w
                center_w = act_w - left_w - right_w
                center_cx = center_x0 + center_w / 2.0

                c.setFillColor(panel_col)
                c.rect(bx0, by0, (center_x0 - bx0), bh, stroke=0, fill=1)
                c.rect(act_x0 + act_w - right_w, by0, (bx0 + bw) - (act_x0 + act_w - right_w), bh, stroke=0, fill=1)
                c.setStrokeColor(accent_col)
                c.setLineWidth(0.8)
                c.line(center_x0, by0, center_x0, by0 + bh)
                c.line(act_x0 + act_w - right_w, by0, act_x0 + act_w - right_w, by0 + bh)

                sx0 = act_x0 + p.safety + 4.0 * sc
                qr_sz = max(18.0, min(42.0 * sc, left_w - p.safety - 10.0, act_h * 0.44))
                draw_vector_qr(c, coa_url, sx0, act_cy - qr_sz * 0.25, qr_sz, quiet_modules=QR_MIN_QUIET_MODULES)
                rem_x0 = sx0 + qr_sz + 4.0 * sc
                rem_w = (act_x0 + left_w - 4.0 * sc) - rem_x0
                if smcbd_vec and rem_w >= 24.0:
                    draw_normalized_vector(c, smcbd_vec, rem_x0 + rem_w / 2.0, act_cy + qr_sz * 0.15, min(46.0 * sc, rem_w * 0.92), CMYK_WHITE)
                c.setFillColor(CMYK_WHITE)
                f_fda = max(3.6, 4.4 * sc)
                c.setFont(fn_reg, f_fda)
                fda_words = "FDA DISCLAIMER: NOT EVALUATED BY THE FDA. NOT INTENDED TO DIAGNOSE, TREAT, CURE, OR PREVENT ANY DISEASE.".split()
                line, ly = "", act_y0 + p.safety + 12.0 * sc
                max_lw = left_w - p.safety - 8.0 * sc
                for wd in fda_words:
                    test = (line + " " + wd).strip()
                    if pdfmetrics.stringWidth(test, fn_reg, f_fda) <= max_lw:
                        line = test
                    else:
                        if ly >= act_y0 + p.safety + 2.0:
                            c.drawString(sx0, ly, line)
                        ly -= f_fda * 1.15
                        line = wd
                if line and ly >= act_y0 + p.safety + 2.0:
                    c.drawString(sx0, ly, line)

                hero_fs = min(22.0 * sc_h, (center_w * 0.86) / max(1, len(product_name) * 0.46))
                sub_fs = min(6.8 * sc_h, (center_w * 0.86) / max(1, len(subtitle) * 0.52))
                draw_tracked_text(c, product_name.upper(), center_cx, act_cy + 14.0 * sc_h, "DINCond-Bold", hero_fs, CMYK_WHITE, 1.0 * sc)
                draw_tracked_text(c, subtitle.upper(), center_cx, act_cy + 3.0 * sc_h, "AvenirCond-Demi", sub_fs, accent_col, 0.7 * sc)

                n_cb = max(1, len(cannabinoids))
                grid_w = center_w * 0.88
                cell_w = grid_w / n_cb
                gx0 = center_cx - grid_w / 2.0
                gy0 = act_y0 + p.safety + 13.5 * sc_h
                gh = 21.0 * sc_h
                c.setFillColor(panel_col)
                c.setStrokeColor(accent_col)
                c.setLineWidth(0.7)
                c.roundRect(gx0, gy0, grid_w, gh, 2.0, stroke=1, fill=1)
                for idx, cb in enumerate(cannabinoids):
                    cx_i = gx0 + idx * cell_w
                    if idx > 0:
                        c.setLineWidth(0.45)
                        c.line(cx_i, gy0 + 3.0, cx_i, gy0 + gh - 3.0)
                    draw_tracked_text(c, cb["mg"], cx_i + cell_w / 2.0, gy0 + gh * 0.52, "DINCond-Bold", 8.0 * sc, CMYK_WHITE, 0.25)
                    draw_tracked_text(c, cb["name"], cx_i + cell_w / 2.0, gy0 + gh * 0.16, "AvenirCond-Bold", 5.2 * sc, accent_col, 0.35)
                draw_tracked_text(c, net_wt, center_cx, act_y0 + p.safety + 4.0 * sc_h, "AvenirCond-Demi", 5.8 * sc, CMYK_WHITE, 0.6 * sc)

                rx0 = act_x0 + act_w - right_w + 5.0 * sc
                rw_inner = right_w - p.safety - 7.5 * sc
                c.setFillColor(accent_col)
                c.setFont(fn_bold, 5.2 * sc)
                c.drawString(rx0, act_y0 + act_h - p.safety - 8.5 * sc_h, "DIRECTIONS & INGREDIENTS")
                c.setFillColor(CMYK_WHITE)
                f_ing = max(3.6, 4.4 * sc)
                c.setFont(fn_reg, f_ing)
                words = f"{directions} Ingredients: {ingredients}".split()
                line, ly = "", act_y0 + act_h - p.safety - 15.0 * sc_h
                min_ly = act_y0 + p.safety + (upc_h + 6.5 if upc else 4.0)
                for wd in words:
                    test = (line + " " + wd).strip()
                    if pdfmetrics.stringWidth(test, fn_reg, f_ing) <= rw_inner:
                        line = test
                    else:
                        if ly >= min_ly:
                            c.drawString(rx0, ly, line)
                        ly -= f_ing * 1.12
                        line = wd
                if line and ly >= min_ly:
                    c.drawString(rx0, ly, line)
                if upc:
                    draw_vector_upca(
                        c,
                        str(upc),
                        act_x0 + act_w - p.safety - upc_w - 2.0,
                        act_y0 + p.safety + 2.5,
                        upc_w,
                        upc_h,
                        bg_pad=2.0,
                        allow_non_retail_truncation=allow_upc_trunc,
                    )
            c.restoreState()

    return _render


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoky Parametric CMYK Packaging & Label Dieline Engine")
    parser.add_argument("--spec", default=None, help="Path to JSON packaging specification to render as press PDF")
    parser.add_argument("--out", default=None, help="Output press-ready PDF path (required with --spec)")
    parser.add_argument("--preview-dir", default=None, help="Optional directory to render PNG proof & clean artwork previews")
    parser.add_argument("--brand-vectors", default=None, help="Optional custom normalized vector logo JSON path")
    parser.add_argument("--calc-container", default=None, help="Stdlib JSON container spec (cylinder/tapered/pouch/carton/sleeve) to compute label dimensions")
    parser.add_argument("--encode-upca", default=None, help="Stdlib 11- or 12-digit UPC-A to validate/compute check digit and 95-module bitstring")
    parser.add_argument("--preflight", default=None, help="Run CMYK, spot-separation, overprint, and OCG preflight on an existing PDF")
    args = parser.parse_args()

    if args.calc_container:
        raw_arg = args.calc_container.strip()
        cfg = json.loads(Path(raw_arg).read_text(encoding="utf-8")) if Path(raw_arg).is_file() else json.loads(raw_arg)
        print(json.dumps(calculate_container_dieline(cfg), indent=2))
        return

    if args.encode_upca:
        digits, bits = normalize_and_encode_upca(args.encode_upca)
        print(json.dumps({"upc12": digits, "check_digit": digits[-1], "modules": len(bits), "bits": bits}, indent=2))
        return

    if args.preflight:
        report = verify_dieline_pdf(Path(args.preflight))
        print(json.dumps(report, indent=2))
        if not report["preflight_pass"]:
            sys.exit(1)
        return

    if not args.spec or not args.out:
        parser.error("Provide --spec <spec.json> --out <out.pdf>, or one of --calc-container / --encode-upca / --preflight")

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    raw_panels = spec.get("panels")
    if not raw_panels and "container" in spec:
        raw_panels = calculate_container_dieline(spec["container"])["panels"]
    if not raw_panels:
        raise ValueError("Specification JSON must include a non-empty 'panels' list or 'container' dictionary")

    panels: list[DielinePanel] = []
    explicit_positions: list[tuple[float | None, float | None]] = []
    for idx, p_cfg in enumerate(raw_panels):
        w_in = float(p_cfg["width_in"])
        tw_in = float(p_cfg["top_width_in"]) if p_cfg.get("top_width_in") is not None else None
        h_in = float(p_cfg["height_in"])
        explicit_positions.append(
            (
                float(p_cfg["cx_in"]) if "cx_in" in p_cfg and p_cfg["cx_in"] is not None else None,
                float(p_cfg["cy_in"]) if "cy_in" in p_cfg and p_cfg["cy_in"] is not None else None,
            )
        )
        panels.append(
            DielinePanel(
                panel_id=p_cfg.get("panel_id") or p_cfg.get("id") or f"panel_{idx+1}",
                shape=p_cfg.get("shape", "rect"),
                cx=0.0,
                cy=0.0,
                width_in=w_in,
                height_in=h_in,
                bleed_in=p_cfg.get("bleed_in", 0.125),
                safety_in=p_cfg.get("safety_in", 0.0625),
                corner_radius_in=p_cfg.get("corner_radius_in", 0.1092),
                top_width_in=tw_in,
                fold_offsets_in=p_cfg.get("fold_offsets_in"),
                inner_radius_in=p_cfg.get("inner_radius_in"),
                outer_radius_in=p_cfg.get("outer_radius_in"),
                sector_angle_deg=p_cfg.get("sector_angle_deg"),
                apex_down=p_cfg.get("apex_down", True),
                carton_net=p_cfg.get("carton_net"),
                label_desc=p_cfg.get("label_desc"),
            )
        )

    gap_in = 1.45
    total_span_in = sum(max(p.width_in, p.top_w / PT_PER_INCH) for p in panels) + gap_in * max(0, len(panels) - 1)
    sheet_w_in = float(spec.get("page_w_in") or max(18.5685, total_span_in + 5.0))
    sheet_h_in = float(spec.get("page_h_in") or max(9.6715, max(p.height_in for p in panels) + 5.8))
    cur_left_in = (sheet_w_in - total_span_in) / 2.0
    default_cy_in = (sheet_h_in - 1.925) * 0.54 + 1.925

    for p, (cx_exp, cy_exp) in zip(panels, explicit_positions):
        span_in = max(p.width_in, p.top_w / PT_PER_INCH)
        cx_in = cx_exp if cx_exp is not None else (cur_left_in + span_in / 2.0)
        cy_in = cy_exp if cy_exp is not None else default_cy_in
        p.cx = inch(cx_in)
        p.cy = inch(cy_in)
        cur_left_in += span_in + gap_in

    meta = dict(spec.get("meta", {}))
    for k in ("sku", "product_line", "imprint", "stock", "finish", "unwind", "company_header", "origin_line"):
        if k in spec and k not in meta:
            meta[k] = spec[k]

    out_pdf = Path(args.out)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    bv_path = Path(args.brand_vectors) if args.brand_vectors else None
    sheet = SmokyDielineSheet(
        out_pdf=out_pdf,
        panels=panels,
        title=spec.get("title", "Smoky Co. Packaging Dieline"),
        sku_meta=meta,
        page_w_in=sheet_w_in,
        page_h_in=sheet_h_in,
        brand_vectors_path=bv_path,
    )
    sheet.draw_artwork(build_generic_spec_artwork(spec))
    sheet.draw_technical_overlays()
    report = sheet.save_and_postprocess()

    if args.preview_dir:
        report["previews"] = render_previews(out_pdf, Path(args.preview_dir), out_pdf.stem)

    print(json.dumps(report, indent=2))
    if not report["preflight_pass"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
