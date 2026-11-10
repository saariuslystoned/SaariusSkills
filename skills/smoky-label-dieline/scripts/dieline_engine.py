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
import base64
import binascii
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
MAX_CMYK_TAC_PCT = 300.0


def validate_cmyk_pct(
    values: Any,
    name: str = "cmyk",
    max_tac_pct: float = MAX_CMYK_TAC_PCT,
) -> tuple[float, float, float, float]:
    """
    Validates a 4-channel CMYK percentage sequence (`[C, M, Y, K]` in `0..100`)
    and enforces total area ink coverage (`C + M + Y + K <= max_tac_pct`).
    """
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError(f"{name} must be a 4-element [C, M, Y, K] percentage sequence, got {values!r}")
    out: list[float] = []
    for idx, ch in enumerate(values):
        if isinstance(ch, bool) or not isinstance(ch, (int, float)):
            raise ValueError(f"{name}[{idx}] must be numeric percentage in [0, 100], got {ch!r}")
        val = float(ch)
        if not math.isfinite(val) or val < 0.0 or val > 100.0:
            raise ValueError(f"{name}[{idx}] must be within [0, 100]%, got {val!r}")
        out.append(val)
    tac = sum(out)
    if tac > max_tac_pct + 1e-6:
        raise ValueError(
            f"{name} total area ink coverage ({tac:.1f}%) exceeds {max_tac_pct:.0f}% prepress TAC limit: {out!r}"
        )
    return (out[0], out[1], out[2], out[3])


def validate_palette_cmyk(
    palette: Any,
    max_tac_pct: float = MAX_CMYK_TAC_PCT,
) -> dict[str, tuple[float, float, float, float]]:
    """Validates every entry in a custom `palette_cmyk` mapping against `[0, 100]%` channels and `TAC <= 300%`."""
    defaults = {
        "bg": (78.0, 42.0, 58.0, 35.0),
        "accent": (8.0, 25.0, 72.0, 2.0),
        "panel": (65.0, 50.0, 48.0, 78.0),
    }
    if palette is None:
        return dict(defaults)
    if not isinstance(palette, dict):
        raise ValueError(f"palette_cmyk must be a mapping of color role -> [C, M, Y, K], got {palette!r}")
    resolved = dict(defaults)
    for role, vals in palette.items():
        resolved[str(role)] = validate_cmyk_pct(vals, name=f"palette_cmyk.{role}", max_tac_pct=max_tac_pct)
    return resolved


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
            "has_leading_glue_flap": True,
            "glue_flap_in": round(glue, 4),
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
        corner_radius_in: float | None = None,
        top_width_in: float | None = None,
        fold_offsets_in: list[float] | None = None,
        inner_radius_in: float | None = None,
        outer_radius_in: float | None = None,
        sector_angle_deg: float | None = None,
        apex_down: bool = True,
        carton_net: dict[str, Any] | None = None,
        has_leading_glue_flap: bool | None = None,
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
        resolved_corner_in = (
            (0.1092 if shape == "rounded_rect" else 0.0)
            if corner_radius_in is None
            else float(corner_radius_in)
        )
        if resolved_corner_in < 0.0:
            raise ValueError(f"Panel {panel_id!r} corner_radius_in must be >= 0, got {resolved_corner_in}")
        self.corner_r = inch(resolved_corner_in)
        self.fold_offsets = [inch(f) for f in (fold_offsets_in or [])]
        self.has_leading_glue_flap: bool = (
            bool(has_leading_glue_flap)
            if has_leading_glue_flap is not None
            else (shape == "carton_sleeve" and len(self.fold_offsets) >= 4)
        )
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

    def offset_bbox(self, offset: float = 0.0) -> tuple[float, float, float, float]:
        """Returns exact axis-aligned `(min_x, min_y, width, height)` of the perpendicular `offset` contour."""
        if self.shape in ("conical_wrap", "tapered_wrap"):
            pts = self.annular_sector_points(offset)
        elif self.shape in ("tuck_box", "carton_flat") and self.carton_net is not None:
            pts = self.carton_outline_points(offset)
        elif self.shape == "flat_trapezoid":
            pts = self.trapezoid_vertices(offset)
        else:
            span_w = max(self.w, self.top_w)
            bw = max(2.0, span_w + 2.0 * offset)
            bh = max(2.0, self.h + 2.0 * offset)
            return (self.cx - bw / 2.0, self.cy - bh / 2.0, bw, bh)
        xs = [pt[0] for pt in pts]
        ys = [pt[1] for pt in pts]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return (min_x, min_y, max(2.0, max_x - min_x), max(2.0, max_y - min_y))

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
        elif self.corner_r <= 0.0:
            rw = max(2.0, self.w + 2 * offset)
            rh = max(2.0, self.h + 2 * offset)
            p.rect(self.cx - rw / 2.0, self.cy - rh / 2.0, rw, rh)
        else:
            rw = max(2.0, self.w + 2 * offset)
            rh = max(2.0, self.h + 2 * offset)
            rr = min(rw / 2.0, rh / 2.0, max(0.0, self.corner_r + offset))
            if rr <= 0.0:
                p.rect(self.cx - rw / 2.0, self.cy - rh / 2.0, rw, rh)
            else:
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

        max_x = max(p.offset_bbox(+p.bleed)[0] + p.offset_bbox(+p.bleed)[2] + inch(2.8) for p in panels)
        max_y = max(p.offset_bbox(+p.bleed)[1] + p.offset_bbox(+p.bleed)[3] + inch(1.4) for p in panels)
        self.page_w = inch(page_w_in) if page_w_in else max(1336.93, max_x)
        self.page_h = inch(page_h_in) if page_h_in else max(696.35, max_y)
        if self.page_w <= 0 or self.page_h <= 0:
            raise ValueError(f"Sheet page dimensions must be positive, got {self.page_w}x{self.page_h} pt")
        for p in panels:
            bx0, by0, bw, bh = p.offset_bbox(+p.bleed)
            if bx0 < -1e-6 or by0 < -1e-6 or (bx0 + bw) > self.page_w + 1e-6 or (by0 + bh) > self.page_h + 1e-6:
                raise ValueError(
                    f"Panel {p.panel_id!r} bleed bounds ({bx0 / PT_PER_INCH:.3f}\"..{(bx0 + bw) / PT_PER_INCH:.3f}\" W, "
                    f"{by0 / PT_PER_INCH:.3f}\"..{(by0 + bh) / PT_PER_INCH:.3f}\" H) exceed sheet bounds "
                    f"({self.page_w / PT_PER_INCH:.3f}\" x {self.page_h / PT_PER_INCH:.3f}\"); "
                    "increase page_w_in/page_h_in or adjust cx_in/cy_in."
                )

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
        mark_len = 9.0
        span_w = max(p.w, p.top_w)
        x0, y0 = p.cx - span_w / 2.0, p.cy - p.h / 2.0
        x1, y1 = p.cx + span_w / 2.0, p.cy + p.h / 2.0
        bx0, by0, bw, bh = p.offset_bbox(+p.bleed)
        bx1, by1 = bx0 + bw, by0 + bh
        c.line(bx0 - 4.0 - mark_len, y0, bx0 - 4.0, y0)
        c.line(bx1 + 4.0, y0, bx1 + 4.0 + mark_len, y0)
        c.line(bx0 - 4.0 - mark_len, y1, bx0 - 4.0, y1)
        c.line(bx1 + 4.0, y1, bx1 + 4.0 + mark_len, y1)
        c.line(x0, by0 - 4.0 - mark_len, x0, by0 - 4.0)
        c.line(x0, by1 + 4.0, x0, by1 + 4.0 + mark_len)
        c.line(x1, by0 - 4.0 - mark_len, x1, by0 - 4.0)
        c.line(x1, by1 + 4.0, x1, by1 + 4.0 + mark_len)
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
            bx0, by0, bw, bh = p.offset_bbox(+p.bleed)
            bx1, by1 = bx0 + bw, by0 + bh
            wy = by1 + 18.0
            c.line(x0, wy - 7, x0, wy + 7)
            c.line(x1, wy - 7, x1, wy + 7)
            c.line(x0, wy, x1, wy)
            c.setFont(resolve_font("Avenir-Demi"), 10.5)
            c.drawCentredString(p.cx, wy + 8.5, f'{p.width_in:.2f}"')

            is_left = p.cx < self.page_w * 0.42
            hx = (bx0 - 18.0) if is_left else (bx1 + 18.0)
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
        origin_line = str(self.meta.get("origin_line", "ORIGIN:   MURPHY, NORTH CAROLINA  •  SMOKYPRODUCT.CO"))
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
# Automated Pre-Flight Inspector (Full PyMuPDF + Pikepdf + Fail-Closed Stdlib Stream Decoder)
# ---------------------------------------------------------------------------
_FILTER_TOKENS_RE = re.compile(rb"/Filter\s*(?:\[\s*([^\]]*)\]|(/[A-Za-z0-9#._+-]+))")
_FILTER_INDIRECT_RE = re.compile(rb"/Filter\s+\d+\s+\d+\s+R\b")
_NAME_TOKEN_RE = re.compile(rb"/[A-Za-z0-9#._+-]+")


def _extract_stream_dict_bytes(prefix: bytes) -> bytes:
    """Extracts the PDF stream dictionary (`<< ... >>`) immediately preceding a `stream` keyword."""
    obj_idx = prefix.rfind(b"obj")
    window = prefix[obj_idx:] if obj_idx != -1 else prefix[-1024:]
    start = window.find(b"<<")
    end = window.rfind(b">>")
    if start != -1 and end != -1 and end >= start:
        return window[start : end + 2]
    return window


def _decode_single_pdf_stream(chunk: bytes, stream_dict: bytes) -> tuple[bytes | None, bool]:
    """
    Decodes a raw PDF stream body according to `/Filter` in `stream_dict`.
    Preserves unfiltered (uncompressed) streams and fails closed (`ok=False`) on corrupt,
    indirect, or unsupported filter chains.
    """
    if _FILTER_INDIRECT_RE.search(stream_dict):
        return None, False

    m = _FILTER_TOKENS_RE.search(stream_dict)
    if m is None:
        return chunk, True

    raw_filters = m.group(1) if m.group(1) is not None else m.group(2)
    filters = _NAME_TOKEN_RE.findall(raw_filters or b"")
    if not filters:
        return chunk, True

    data = chunk
    for flt in filters:
        if flt in (b"/FlateDecode", b"/Fl"):
            decoded: bytes | None = None
            for cand in (data, data.rstrip(b"\r\n")):
                for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
                    try:
                        decoded = zlib.decompress(cand, wbits)
                        break
                    except Exception:
                        continue
                if decoded is not None:
                    break
            if decoded is None:
                return None, False
            data = decoded
        elif flt in (b"/ASCIIHexDecode", b"/AHx"):
            try:
                hex_body = re.sub(rb"\s+", b"", data)
                eod = hex_body.find(b">")
                if eod != -1:
                    hex_body = hex_body[:eod]
                if len(hex_body) % 2 == 1:
                    hex_body += b"0"
                data = binascii.unhexlify(hex_body)
            except Exception:
                return None, False
        elif flt in (b"/ASCII85Decode", b"/A85"):
            try:
                s = data.lstrip()
                if not s.startswith(b"<~"):
                    s = b"<~" + s
                eod = s.find(b"~>")
                s = s[: eod + 2] if eod != -1 else (s + b"~>")
                data = base64.a85decode(s, adobe=True)
            except Exception:
                return None, False
        elif flt == b"/Crypt":
            continue
        else:
            return None, False
    return data, True


def _decode_pdf_streams_stdlib(raw: bytes) -> tuple[bytes, bytes, bool]:
    """
    Extracts `(corpus, content_streams_only, all_streams_decoded_ok)` from raw PDF bytes.
    Uncompressed streams (no `/Filter`), `/FlateDecode`, `/ASCIIHexDecode`, and `/ASCII85Decode`
    are decoded and inspected; corrupt or unsupported filters mark `all_streams_decoded_ok=False`.
    """
    corpus_parts = bytearray()
    stream_parts = bytearray()
    all_ok = True
    pos = 0

    for m in re.finditer(rb"(?<!end)stream(?:\r\n|\n)", raw):
        hdr = raw[pos : m.start()]
        corpus_parts.extend(hdr)
        start = m.end()
        end = raw.find(b"endstream", start)
        if end == -1:
            all_ok = False
            break
        pos = end + len(b"endstream")
        sdict = _extract_stream_dict_bytes(hdr)

        # Skip binary font programs and raster image payloads (image color spaces live in `sdict` / `hdr`).
        if (
            b"/Length1" in sdict
            or re.search(rb"/Subtype\s*/(?:Image|Type1C|CIDFontType0C|OpenType)\b", sdict)
        ):
            continue
        # Skip cross-reference tables and metadata XML streams (not graphics content).
        if re.search(rb"/Type\s*/(?:XRef|Metadata)\b", sdict):
            continue

        raw_body = raw[start:end]
        if raw_body.endswith(b"\r\n"):
            raw_body = raw_body[:-2]
        elif raw_body.endswith((b"\n", b"\r")):
            raw_body = raw_body[:-1]

        decoded, ok = _decode_single_pdf_stream(raw_body, sdict)
        if not ok or decoded is None:
            all_ok = False
            continue

        corpus_parts.extend(b"\n")
        corpus_parts.extend(decoded)
        if not (
            b"/FunctionType" in sdict
            or re.search(rb"/Type\s*/ObjStm\b", sdict)
            or b"/N " in sdict and b"/Alternate" in sdict  # ICC profile stream
        ):
            stream_parts.extend(b"\n")
            stream_parts.extend(decoded)

    corpus_parts.extend(raw[pos:])
    return bytes(corpus_parts), bytes(stream_parts), all_ok


def _extract_pdf_text_and_content_streams(raw: bytes) -> bytes:
    """Extracts PDF object headers + decoded non-font content streams (including uncompressed streams)."""
    corpus, _, _ = _decode_pdf_streams_stdlib(raw)
    return corpus


_RGB_OP_RE = re.compile(
    rb"(?:^|[\s\[\]>])(?:\d+(?:\.\d+)?|\.\d+)\s+(?:\d+(?:\.\d+)?|\.\d+)\s+(?:\d+(?:\.\d+)?|\.\d+)\s+(?:rg|RG)(?=[\s/\[<]|$)"
)
_CMYK_OP_RE = re.compile(
    rb"(?:^|[\s\[\]>])([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s+([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s+([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s+([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s+(?:k|K)(?=[\s/\[<]|$)"
)


def _extract_pdf_content_streams_only(raw: bytes) -> bytes:
    """Extracts decoded non-font, non-image page content streams (including uncompressed streams)."""
    _, streams_only, _ = _decode_pdf_streams_stdlib(raw)
    return streams_only


def _collect_pikepdf_drawable_streams(pk_doc: Any) -> tuple[bytes, bytes, bool]:
    """Extracts decoded page content streams, Form XObjects, Tiling Patterns, and resource dicts via pikepdf."""
    stream_buf = bytearray()
    meta_buf = bytearray()
    visited: set[tuple[int, int]] = set()
    ok = True

    def _visit_resources(res_obj: Any) -> None:
        nonlocal ok
        if res_obj is None:
            return
        try:
            if "/ColorSpace" in res_obj:
                meta_buf.extend(repr(res_obj["/ColorSpace"]).encode("utf-8", errors="ignore"))
                meta_buf.extend(b"\n")
        except Exception:
            ok = False

        for group_key, req_subtype in (("/XObject", "/Form"), ("/Pattern", None)):
            if group_key not in res_obj:
                continue
            try:
                grp = res_obj[group_key]
                items = list(grp.values())
            except Exception:
                ok = False
                continue
            for item in items:
                try:
                    og = getattr(item, "objgen", (0, 0))
                    if og != (0, 0):
                        if og in visited:
                            continue
                        visited.add(og)
                    subtype = str(item.get("/Subtype", ""))
                    if subtype == "/Image":
                        meta_buf.extend(str(item.get("/ColorSpace", "")).encode("utf-8", errors="ignore"))
                        meta_buf.extend(b"\n")
                        continue
                    if req_subtype and subtype != req_subtype:
                        continue
                    if hasattr(item, "read_bytes"):
                        stream_buf.extend(b"\n")
                        stream_buf.extend(item.read_bytes())
                    if "/Resources" in item:
                        _visit_resources(item["/Resources"])
                except Exception:
                    ok = False

    for page in pk_doc.pages:
        try:
            contents = page.get("/Contents")
            if contents is not None:
                if hasattr(contents, "read_bytes"):
                    stream_buf.extend(b"\n")
                    stream_buf.extend(contents.read_bytes())
                else:
                    for c_stream in contents:
                        stream_buf.extend(b"\n")
                        stream_buf.extend(c_stream.read_bytes())
            _visit_resources(page.get("/Resources"))
        except Exception:
            ok = False

    return bytes(stream_buf), bytes(meta_buf), ok


def _verify_ocg_print_states_stdlib(corpus: bytes) -> bool:
    """
    Validates individual OCG object dictionaries in stdlib mode:
      - PDF catalog `/OCProperties` `/D` `/AS` defines an `/Event /Print` auto-state entry with `/Category [/Print]`
        referencing every technical OCG object ID;
      - Every OCG object exists for the 6 canonical layers (`Artwork`, `Diecut`, `Safety`, `Bleed`, `Dimensions`, `Die Template`),
        with `Artwork` set to `/PrintState /ON` and every non-`Artwork` OCG set to `/PrintState /OFF`.
    """
    ocg_states: dict[str, tuple[int, int, str]] = {}
    for m_obj in re.finditer(rb"(\d+)\s+(\d+)\s+obj\b(.*?)endobj", corpus, flags=re.DOTALL):
        obj_num = int(m_obj.group(1))
        gen_num = int(m_obj.group(2))
        body = m_obj.group(3)
        if not re.search(rb"/Type\s*/OCG\b", body):
            continue
        m_name = re.search(rb"/Name\s*(?:\(([^)]*)\)|/([A-Za-z0-9#._+-]+))", body)
        if not m_name:
            return False
        raw_name = m_name.group(1) if m_name.group(1) is not None else m_name.group(2)
        name_str = (raw_name or b"").decode("latin-1", errors="ignore").replace("#20", " ").strip()
        m_ps = re.search(rb"/Print\s*<<[^>]*?/PrintState\s*(/[A-Za-z]+)", body, flags=re.DOTALL)
        if not m_ps:
            return False
        pstate = m_ps.group(1).decode("ascii", errors="ignore")
        if name_str in ocg_states and ocg_states[name_str][2] != pstate:
            return False
        ocg_states[name_str] = (obj_num, gen_num, pstate)

    required_names = {human_name for _, human_name in SmokyDielineSheet.OCG_ORDER}
    if not required_names.issubset(set(ocg_states.keys())):
        return False

    tech_refs: list[tuple[int, int]] = []
    for name_str, (onum, gnum, pstate) in ocg_states.items():
        expected = "/ON" if name_str == "Artwork" else "/OFF"
        if pstate != expected:
            return False
        if name_str != "Artwork":
            tech_refs.append((onum, gnum))

    for m_as in re.finditer(rb"<<([^>]*?/Event\s*/Print\b.*?)>>", corpus, flags=re.DOTALL):
        as_body = m_as.group(1)
        if not re.search(rb"/Category\s*\[\s*[^\]]*?/Print\b", as_body, flags=re.DOTALL):
            continue
        m_ocgs = re.search(rb"/OCGs\s*\[([^\]]*)\]", as_body, flags=re.DOTALL)
        if not m_ocgs:
            continue
        listed_refs = {
            (int(r.group(1)), int(r.group(2)))
            for r in re.finditer(rb"(\d+)\s+(\d+)\s+R\b", m_ocgs.group(1))
        }
        if all(ref in listed_refs for ref in tech_refs):
            return True

    return False


def verify_dieline_pdf(pdf_path: Path, expected_panels: list[DielinePanel] | None = None) -> dict[str, Any]:
    """Verifies OCG layers, non-printing technical PrintState, spot separations, overprint, zero RGB leaks, TAC <= 300%, and exact trim dimensions."""
    raw = Path(pdf_path).read_bytes()
    corpus, stdlib_streams_only, stdlib_streams_ok = _decode_pdf_streams_stdlib(raw)
    streams_only = stdlib_streams_only
    streams_decoded_ok = stdlib_streams_ok

    has_nonprinting_tech = _verify_ocg_print_states_stdlib(corpus)

    try:
        import pikepdf

        try:
            with pikepdf.open(pdf_path) as pk:
                pk_streams, pk_meta, pk_streams_ok = _collect_pikepdf_drawable_streams(pk)
                if pk_streams:
                    streams_only = stdlib_streams_only + b"\n" + pk_streams
                    corpus = corpus + b"\n" + pk_streams + b"\n" + pk_meta
                else:
                    corpus = corpus + b"\n" + pk_meta
                streams_decoded_ok = bool(pk_streams_ok and (stdlib_streams_ok or bool(pk_streams)))

                oc_props = pk.Root.get("/OCProperties")
                if oc_props is not None:
                    ocg_objs = list(oc_props.get("/OCGs", []))
                    ocg_by_name = {str(ocg.get("/Name", "")): ocg for ocg in ocg_objs}
                    req_names = {human_name for _, human_name in SmokyDielineSheet.OCG_ORDER}
                    as_list = list(oc_props.get("/D", {}).get("/AS", []))
                    tech_objgens = {
                        getattr(ocg, "objgen", None)
                        for ocg in ocg_objs
                        if str(ocg.get("/Name", "")) != "Artwork"
                    }
                    has_print_event = False
                    for item in as_list:
                        if str(item.get("/Event", "")) != "/Print":
                            continue
                        if "/Print" not in [str(cat) for cat in item.get("/Category", [])]:
                            continue
                        as_objgens = {getattr(o, "objgen", None) for o in item.get("/OCGs", [])}
                        if tech_objgens.issubset(as_objgens):
                            has_print_event = True
                            break
                    states_ok = (
                        bool(ocg_objs)
                        and req_names.issubset(set(ocg_by_name.keys()))
                        and all(
                            str(ocg.get("/Usage", {}).get("/Print", {}).get("/PrintState", ""))
                            == ("/ON" if str(ocg.get("/Name", "")) == "Artwork" else "/OFF")
                            for ocg in ocg_objs
                        )
                    )
                    has_nonprinting_tech = bool(has_print_event and states_ok)
                else:
                    has_nonprinting_tech = False
        except Exception:
            streams_decoded_ok = False
    except ImportError:
        pass

    cmyk_ops = [
        (float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
        for m in _CMYK_OP_RE.finditer(streams_only or corpus)
    ]
    max_tac_pct = round(max((sum(op) * 100.0 for op in cmyk_ops), default=0.0), 2)
    tac_within_limit = all(
        all(-1e-6 <= ch <= 1.0 + 1e-6 for ch in op) and (sum(op) * 100.0 <= MAX_CMYK_TAC_PCT + 1e-3)
        for op in cmyk_ops
    )

    has_dieline_spot = (b"Die#20Line" in corpus) or (b"Die Line" in corpus)
    has_safety_spot = (b"Safety#20Line" in corpus) or (b"Safety Line" in corpus)
    has_bleed_spot = (b"Bleed#20Line" in corpus) or (b"Bleed Line" in corpus)
    has_overprint = (b"/GSOverprint" in corpus) and (b"/OP true" in corpus or b"/OPM 1" in corpus)
    has_rgb = (
        (b"/DeviceRGB" in corpus)
        or (b"/CalRGB" in corpus)
        or bool(_RGB_OP_RE.search(corpus))
        or bool(_RGB_OP_RE.search(streams_only))
    )
    has_cmyk = (b"/DeviceCMYK" in corpus) or bool(cmyk_ops)

    panel_checks: list[dict[str, Any]] = []
    ocgs: list[str] = []

    try:
        import pymupdf

        doc = pymupdf.open(str(pdf_path))
        ocgs = [v["name"] for v in doc.get_ocgs().values()]
        page = doc[0]
        drawings = page.get_drawings()
        die_drawings = [d for d in drawings if d.get("layer") == "Diecut"]
        for p in expected_panels or []:
            expected_span_in = max(p.width_in, p.top_w / PT_PER_INCH)
            matched = False
            for d in die_drawings:
                r = d["rect"]
                if (
                    abs(r.width / PT_PER_INCH - expected_span_in) < 0.005
                    and abs(r.height / PT_PER_INCH - p.height_in) < 0.005
                ):
                    has_curves = any(it[0] == "c" for it in d.get("items", []))
                    if p.shape in ("rect", "carton_sleeve") and p.corner_r <= 0.0 and has_curves:
                        continue
                    if p.shape == "rounded_rect" and p.corner_r > 0.0 and not has_curves:
                        continue
                    matched = True
                    break
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
        streams_decoded_ok
        and has_dieline_spot
        and has_safety_spot
        and has_bleed_spot
        and has_overprint
        and has_nonprinting_tech
        and has_cmyk
        and not has_rgb
        and tac_within_limit
        and len(ocgs) >= 5
        and all(c["matched_exact_diecut"] for c in panel_checks)
    )
    return {
        "file": str(pdf_path),
        "size_kb": round(len(raw) / 1024.0, 1),
        "preflight_pass": ok,
        "streams_decoded_ok": streams_decoded_ok,
        "cmyk_only_no_rgb": (has_cmyk and not has_rgb),
        "tac_within_limit": tac_within_limit,
        "max_tac_pct": max_tac_pct,
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
# Responsive Generic Spec-Driven Artwork Planner & Renderer
# ---------------------------------------------------------------------------
FDA_DISCLAIMER_DEFAULT = (
    "FDA DISCLAIMER: NOT EVALUATED BY THE FDA. NOT INTENDED TO DIAGNOSE, "
    "TREAT, CURE, OR PREVENT ANY DISEASE."
)


def measure_text_width(text: str, font_name: str, font_size: float) -> float:
    """Measures exact PDF glyph string width when ReportLab is available, with calibrated stdlib fallback."""
    if not text:
        return 0.0
    if HAS_REPORTLAB:
        register_fonts()
        return float(pdfmetrics.stringWidth(text, resolve_font(font_name), font_size))
    is_cond = "Cond" in font_name
    factor = 0.48 if is_cond else 0.56
    if any(wt in font_name for wt in ("Bold", "Heavy", "Demi")):
        factor += 0.03
    total = 0.0
    for ch in text:
        if ch == " ":
            total += 0.28 * font_size
        elif ch in "Iil1.,:;|!'":
            total += 0.26 * font_size
        elif ch in "MWm%@#":
            total += (factor + 0.22) * font_size
        elif ch.isupper():
            total += (factor + 0.06) * font_size
        else:
            total += factor * font_size
    return total


def measure_tracked_width(text: str, font_name: str, font_size: float, tracking_pt: float) -> float:
    if not text:
        return 0.0
    return sum(measure_text_width(ch, font_name, font_size) for ch in text) + tracking_pt * max(0, len(text) - 1)


def fit_tracked_line(
    text: str,
    font_name: str,
    max_fs: float,
    min_fs: float,
    max_w: float,
    base_tracking: float,
    panel_id: str,
    field_name: str,
) -> dict[str, Any]:
    """Scales single-line tracked text to fit within `max_w`, raising ValueError if even `min_fs` overflows."""
    if not text.strip():
        return {"text": "", "font_name": font_name, "font_size": max_fs, "tracking_pt": 0.0, "width_pt": 0.0}
    hi = max(min_fs, max_fs)
    steps = max(1, int(round((hi - min_fs) / 0.2)))
    candidates = [max(min_fs, hi - 0.2 * i) for i in range(steps + 1)]
    if candidates[-1] > min_fs + 1e-6:
        candidates.append(min_fs)
    for fs in candidates:
        trk = base_tracking * (fs / max(hi, 0.1))
        w = measure_tracked_width(text, font_name, fs, trk)
        if w <= max_w + 1e-6:
            return {"text": text, "font_name": font_name, "font_size": fs, "tracking_pt": trk, "width_pt": w}
    w_zero = measure_tracked_width(text, font_name, min_fs, 0.0)
    if w_zero <= max_w + 1e-6:
        return {"text": text, "font_name": font_name, "font_size": min_fs, "tracking_pt": 0.0, "width_pt": w_zero}
    raise ValueError(
        f"Panel {panel_id!r}: {field_name} ({text!r}) exceeds width {max_w / PT_PER_INCH:.2f}\" at minimum legible size {min_fs:.1f}pt."
    )


def layout_wrapped_lines(
    text: str,
    font_name: str,
    max_fs: float,
    min_fs: float,
    max_w: float,
    max_h: float,
    line_gap: float = 1.14,
    panel_id: str = "",
    block_name: str = "copy",
) -> dict[str, Any]:
    """
    Wraps every word of `text` to fit strictly inside `max_w x max_h` down to `min_fs`.
    Never drops trailing words or lines; raises ValueError if complete rendering cannot fit.
    """
    raw_words = text.split()
    if not raw_words:
        return {"font_name": font_name, "font_size": max_fs, "leading_pt": max_fs * line_gap, "lines": [], "height_pt": 0.0}
    if max_w <= 4.0 or max_h + 1e-6 < min_fs:
        raise ValueError(
            f"Panel {panel_id!r}: insufficient space ({max_w / PT_PER_INCH:.2f}\" x {max_h / PT_PER_INCH:.2f}\") for {block_name}."
        )
    hi = max(min_fs, max_fs)
    steps = max(1, int(round((hi - min_fs) / 0.2)))
    candidates = [max(min_fs, hi - 0.2 * i) for i in range(steps + 1)]
    if candidates[-1] > min_fs + 1e-6:
        candidates.append(min_fs)

    for fs in candidates:
        lines: list[str] = []
        cur = ""
        fits_w = True
        for wd in raw_words:
            if measure_text_width(wd, font_name, fs) <= max_w + 1e-6:
                pieces = [wd]
            else:
                pieces = re.findall(r"[^/\-]+[/\-]?", wd)
                if not pieces or any(measure_text_width(pc, font_name, fs) > max_w + 1e-6 for pc in pieces):
                    fits_w = False
                    break
            for idx_p, pc in enumerate(pieces):
                sep = "" if (idx_p > 0 and cur.endswith(("/", "-"))) else (" " if cur else "")
                cand = cur + sep + pc
                if measure_text_width(cand, font_name, fs) <= max_w + 1e-6:
                    cur = cand
                else:
                    if cur:
                        lines.append(cur)
                    cur = pc
        if not fits_w:
            continue
        if cur:
            lines.append(cur)
        leading = fs * line_gap
        req_h = fs + (len(lines) - 1) * leading
        if req_h <= max_h + 1e-6:
            return {
                "font_name": font_name,
                "font_size": fs,
                "leading_pt": leading,
                "lines": lines,
                "height_pt": req_h,
            }

    raise ValueError(
        f"Panel {panel_id!r}: {block_name} overflows available region ({max_w / PT_PER_INCH:.2f}\" x {max_h / PT_PER_INCH:.2f}\") "
        f"at minimum legible size {min_fs:.1f}pt; enlarge panel, shorten {block_name}, or omit optional barcode."
    )


def _resolve_spec_upc(spec: dict[str, Any]) -> str | None:
    """Returns explicit normalized UPC string when `spec` provides `'upc'`, or `None` when omitted/empty."""
    raw = spec.get("upc")
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError(f"'upc' must be an 11- or 12-digit GTIN string or null, got {raw!r}")
    s = str(raw).strip()
    return s or None


def _resolve_spec_qr_url(spec: dict[str, Any]) -> str | None:
    """Returns explicit QR URL (`'qr_url'` or `'coa_url'`) when provided, or `None` when omitted/empty."""
    raw = spec.get("qr_url", spec.get("coa_url"))
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError(f"'qr_url' / 'coa_url' must be a URL string or null, got {raw!r}")
    s = str(raw).strip()
    return s or None


def _resolve_spec_metrics(spec: dict[str, Any]) -> list[dict[str, str]]:
    """Normalizes optional `'metrics'` (`[{'value': ..., 'label': ...}]`) or `'cannabinoids'` (`[{'mg': ..., 'name': ...}]`)."""
    raw = spec.get("metrics") if "metrics" in spec else spec.get("cannabinoids")
    if not raw:
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        val = str(item.get("value", item.get("mg", ""))).strip()
        lbl = str(item.get("label", item.get("name", ""))).strip()
        if val or lbl:
            out.append({"mg": val, "name": lbl})
    return out


def _resolve_spec_disclaimer(spec: dict[str, Any]) -> str:
    """Returns explicit `'disclaimer'` / `'fda_disclaimer'`, defaulting to `FDA_DISCLAIMER_DEFAULT` only when `'cannabinoids'` is supplied."""
    if "disclaimer" in spec:
        return "" if spec["disclaimer"] is None else str(spec["disclaimer"])
    if "fda_disclaimer" in spec:
        return "" if spec["fda_disclaimer"] is None else str(spec["fda_disclaimer"])
    if "cannabinoids" in spec and spec["cannabinoids"]:
        return FDA_DISCLAIMER_DEFAULT
    return ""


def _should_use_smcbd_vector(spec: dict[str, Any], has_smcbd_vec: bool) -> bool:
    """Uses the Smoky Mountain CBD vector mark only when `'logo_key': 'smcbd'` or brand is `'SMOKY MOUNTAIN CBD'`."""
    if not has_smcbd_vec:
        return False
    logo_key = spec.get("logo_key")
    if logo_key is not None:
        return str(logo_key).strip().lower() == "smcbd"
    brand = str(spec.get("brand", "SMOKY PRODUCT CO.")).strip().upper()
    return brand == "SMOKY MOUNTAIN CBD"


def _plan_qr_fda_zone(
    panel_id: str,
    x0: float,
    y0: float,
    w: float,
    h: float,
    fda_text: str,
    has_smcbd_vec: bool,
    has_qr: bool = True,
    brand: str = "",
) -> dict[str, Any]:
    if not has_qr:
        empty_fda = {"font_name": "AvenirCond-Reg", "font_size": 4.2, "leading_pt": 4.8, "lines": [], "height_pt": 0.0}
        vec_box: tuple[float, float, float, float] | None = None
        brand_line: dict[str, Any] | None = None
        fda_avail_h = h
        if has_smcbd_vec and h >= 22.0:
            vh = min(28.0, h * (0.34 if fda_text.strip() else 0.65))
            vy = (y0 + h - vh) if fda_text.strip() else (y0 + (h - vh) / 2.0)
            vec_box = (x0, vy, w, vh)
            fda_avail_h = (h - vh - 3.0) if fda_text.strip() else 0.0
        elif brand.strip() and (not fda_text.strip() or h >= 44.0):
            bfit = fit_tracked_line(
                brand.strip().upper(),
                "AvenirCond-Heavy",
                max_fs=min(7.2, max(3.8, h * 0.14)),
                min_fs=3.6,
                max_w=w * 0.94,
                base_tracking=0.5,
                panel_id=panel_id,
                field_name="side brand",
            )
            by = (y0 + h - 0.85 * bfit["font_size"]) if fda_text.strip() else (y0 + h / 2.0 - 0.35 * bfit["font_size"])
            brand_line = {**bfit, "cx": x0 + w / 2.0, "y": by}
            fda_avail_h = (h - bfit["font_size"] - 4.0) if fda_text.strip() else 0.0
        fda_layout = (
            layout_wrapped_lines(
                fda_text,
                "AvenirCond-Reg",
                max_fs=4.8,
                min_fs=3.6,
                max_w=w,
                max_h=fda_avail_h,
                line_gap=1.14,
                panel_id=panel_id,
                block_name="disclaimer",
            )
            if fda_text.strip()
            else empty_fda
        )
        fy = y0 + (fda_avail_h - fda_layout["height_pt"]) / 2.0 if (fda_text.strip() and vec_box is None and brand_line is None) else y0
        fh_out = fda_layout["height_pt"] if (fda_text.strip() and vec_box is None and brand_line is None) else fda_avail_h
        return {
            "qr_rect": None,
            "vec_box": vec_box,
            "brand_line": brand_line,
            "fda_box": (x0, fy, w, fh_out),
            "fda_layout": fda_layout,
        }

    min_qr = 22.0
    cand_qrs = sorted(
        {round(v, 3) for v in (min(42.0, w, h * 0.48), 34.0, 28.0, min_qr) if min_qr <= v <= min(w, h) + 1e-6},
        reverse=True,
    )
    for qr_sz in cand_qrs:
        fda_h = (h - qr_sz - 3.0) if fda_text.strip() else 0.0
        try:
            fda_layout = (
                layout_wrapped_lines(
                    fda_text,
                    "AvenirCond-Reg",
                    max_fs=4.6,
                    min_fs=3.6,
                    max_w=w,
                    max_h=fda_h,
                    line_gap=1.14,
                    panel_id=panel_id,
                    block_name="FDA disclaimer",
                )
                if fda_text.strip()
                else {"font_name": "AvenirCond-Reg", "font_size": 4.2, "leading_pt": 4.8, "lines": [], "height_pt": 0.0}
            )
            rem_w = w - qr_sz - 4.0
            qr_y = (y0 + h - qr_sz) if fda_text.strip() else (y0 + (h - qr_sz) / 2.0)
            if has_smcbd_vec and rem_w >= 24.0:
                qr_x = x0
                vec_box = (x0 + qr_sz + 4.0, qr_y, rem_w, qr_sz)
            else:
                qr_x = x0 + (w - qr_sz) / 2.0
                vec_box = None
            return {
                "qr_rect": (qr_x, qr_y, qr_sz, qr_sz),
                "vec_box": vec_box,
                "brand_line": None,
                "fda_box": (x0, y0, w, fda_h),
                "fda_layout": fda_layout,
            }
        except ValueError:
            continue

    if w >= 56.0 and h >= min_qr:
        qr_sz = min(34.0, h, w * 0.40)
        if qr_sz >= min_qr:
            fda_w = w - qr_sz - 4.0
            fda_layout = layout_wrapped_lines(
                fda_text,
                "AvenirCond-Reg",
                max_fs=4.4,
                min_fs=3.6,
                max_w=fda_w,
                max_h=h,
                line_gap=1.14,
                panel_id=panel_id,
                block_name="FDA disclaimer",
            )
            return {
                "qr_rect": (x0, y0 + (h - qr_sz) / 2.0, qr_sz, qr_sz),
                "vec_box": None,
                "brand_line": None,
                "fda_box": (x0 + qr_sz + 4.0, y0, fda_w, h),
                "fda_layout": fda_layout,
            }

    raise ValueError(
        f"Panel {panel_id!r}: COA QR code and FDA disclaimer overflow zone ({w / PT_PER_INCH:.2f}\" x {h / PT_PER_INCH:.2f}\")."
    )


def _plan_hero_zone(
    panel_id: str,
    x0: float,
    y0: float,
    w: float,
    h: float,
    brand: str,
    product_name: str,
    subtitle: str,
    cannabinoids: list[dict[str, str]],
    net_wt: str,
    has_smcbd_vec: bool,
    show_brand_header: bool = False,
) -> dict[str, Any]:
    if w < 44.0 or h < 34.0:
        raise ValueError(
            f"Panel {panel_id!r}: hero zone ({w / PT_PER_INCH:.2f}\" x {h / PT_PER_INCH:.2f}\") is too small for product identity."
        )
    sc_h = max(0.50, min(1.30, h / 112.0))
    sc_w = max(0.50, min(1.25, w / 190.0))
    sc = min(sc_w, sc_h)
    cx = x0 + w / 2.0

    net_line = fit_tracked_line(
        net_wt, "AvenirCond-Demi", max_fs=6.0 * sc, min_fs=3.6, max_w=w * 0.94, base_tracking=0.6 * sc, panel_id=panel_id, field_name="net_wt"
    )
    net_y = y0 + 0.25 * net_line["font_size"]
    net_top = (y0 + net_line["font_size"] + 2.0) if net_wt.strip() else y0

    cells: list[dict[str, Any]] = []
    grid_rect: tuple[float, float, float, float] | None = None
    if cannabinoids:
        n_cb = len(cannabinoids)
        gh = max(13.0, min(22.0 * sc_h, h * 0.24))
        grid_w = w * 0.92
        cell_w = grid_w / n_cb
        gx0 = cx - grid_w / 2.0
        gy0 = net_top + 1.5
        for idx, cb in enumerate(cannabinoids):
            mg_fit = fit_tracked_line(
                str(cb["mg"]), "DINCond-Bold", max_fs=min(8.2 * sc, gh * 0.42), min_fs=3.6, max_w=cell_w - 3.0, base_tracking=0.25, panel_id=panel_id, field_name="metric value"
            )
            nm_fit = fit_tracked_line(
                str(cb["name"]), "AvenirCond-Bold", max_fs=min(5.2 * sc, gh * 0.28), min_fs=3.4, max_w=cell_w - 3.0, base_tracking=0.30, panel_id=panel_id, field_name="metric label"
            )
            cells.append({"x0": gx0 + idx * cell_w, "w": cell_w, "mg": mg_fit, "name": nm_fit})
        grid_rect = (gx0, gy0, grid_w, gh)
        rem_y0 = gy0 + gh + 3.0
    else:
        rem_y0 = net_top + 2.0

    rem_h = (y0 + h) - rem_y0
    if rem_h < 11.0:
        raise ValueError(
            f"Panel {panel_id!r}: hero zone height ({h / PT_PER_INCH:.2f}\") cannot stack title, subtitle, metrics, and net weight without overlap."
        )

    brand_header: dict[str, Any] | None = None
    if show_brand_header and (has_smcbd_vec or brand.strip()):
        if has_smcbd_vec and rem_h >= 42.0:
            bh_alloc = min(32.0, rem_h * 0.28)
            brand_header = {"kind": "vector", "cx": cx, "cy": y0 + h - bh_alloc / 2.0, "w": min(w * 0.56, bh_alloc * 1.65)}
            rem_h -= bh_alloc + 2.5
        elif rem_h >= 22.0:
            bh_alloc = min(28.0, max(6.0, rem_h * 0.24))
            b_fit = fit_tracked_line(
                brand.upper(), "AvenirCond-Heavy", max_fs=min(8.5 * sc, bh_alloc * 0.72), min_fs=3.6, max_w=w * 0.94, base_tracking=0.7 * sc, panel_id=panel_id, field_name="brand"
            )
            brand_header = {"kind": "text", "cx": cx, "y": y0 + h - 0.85 * b_fit["font_size"], "line": b_fit}
            rem_h -= max(b_fit["font_size"] + 2.0, bh_alloc * 0.75)
        elif brand.strip():
            raise ValueError(
                f"Panel {panel_id!r}: hero zone height ({h / PT_PER_INCH:.2f}\") cannot stack brand, product_name, and optional fields without overlap."
            )

    sub_layout = layout_wrapped_lines(
        subtitle.upper(),
        "AvenirCond-Demi",
        max_fs=min(6.8 * sc_h, max(3.8, rem_h * 0.28)),
        min_fs=3.6,
        max_w=w * 0.94,
        max_h=max(4.0, rem_h * 0.42),
        line_gap=1.08,
        panel_id=panel_id,
        block_name="subtitle",
    )
    sub_gap = 2.0 if sub_layout["lines"] else 0.0
    title_avail_h = rem_h - sub_layout["height_pt"] - sub_gap
    if title_avail_h < 4.5:
        raise ValueError(f"Panel {panel_id!r}: hero title and subtitle overflow vertical safe height.")

    title_mode: dict[str, Any]
    try:
        t_single = fit_tracked_line(
            product_name.upper(),
            "DINCond-Bold",
            max_fs=min(22.0 * sc_h, title_avail_h * 0.88),
            min_fs=max(4.5, min(6.8, title_avail_h * 0.55)),
            max_w=w * 0.94,
            base_tracking=0.9 * sc,
            panel_id=panel_id,
            field_name="product_name",
        )
        title_mode = {"kind": "tracked", "line": t_single, "height_pt": t_single["font_size"]}
    except ValueError:
        t_wrap = layout_wrapped_lines(
            product_name.upper(),
            "DINCond-Bold",
            max_fs=min(15.0 * sc_h, title_avail_h * 0.58),
            min_fs=4.4,
            max_w=w * 0.94,
            max_h=title_avail_h,
            line_gap=1.06,
            panel_id=panel_id,
            block_name="product_name",
        )
        title_mode = {"kind": "wrapped", "layout": t_wrap, "height_pt": t_wrap["height_pt"]}

    stack_h = title_mode["height_pt"] + sub_gap + sub_layout["height_pt"]
    stack_top = rem_y0 + (rem_h + stack_h) / 2.0
    return {
        "x0": x0,
        "w": w,
        "cx": cx,
        "brand_header": brand_header,
        "title": title_mode,
        "title_top": stack_top,
        "subtitle": sub_layout,
        "subtitle_top": stack_top - title_mode["height_pt"] - sub_gap,
        "grid_rect": grid_rect,
        "cells": cells,
        "net_line": net_line,
        "net_y": net_y,
    }


def _plan_directions_upc_zone(
    panel_id: str,
    x0: float,
    y0: float,
    w: float,
    h: float,
    directions: str,
    ingredients: str,
    upc: str | None,
    allow_upc_trunc: bool,
    allow_side_by_side: bool = True,
) -> dict[str, Any]:
    min_gs1_w = inch(GS1_UPCA_MIN_WIDTH_IN) + 1.4
    min_gs1_h = inch(GS1_UPCA_MIN_BAR_HEIGHT_IN) + 10.2
    copy_parts: list[str] = []
    if directions and directions.strip():
        copy_parts.append(directions.strip())
    if ingredients and ingredients.strip():
        copy_parts.append(f"Ingredients: {ingredients.strip()}")
    copy_text = " ".join(copy_parts)

    def _fit_hdr(avail_w: float, avail_h: float) -> dict[str, Any]:
        last_err: Exception | None = None
        for txt in ("DIRECTIONS & INGREDIENTS", "DIRECTIONS / INGREDIENTS"):
            try:
                return fit_tracked_line(
                    txt,
                    "AvenirCond-Bold",
                    max_fs=min(5.4, max(3.8, avail_h * 0.12)),
                    min_fs=3.6,
                    max_w=avail_w,
                    base_tracking=0.0,
                    panel_id=panel_id,
                    field_name="directions header",
                )
            except ValueError as exc:
                last_err = exc
        assert last_err is not None
        raise last_err

    if not upc:
        if not copy_text:
            return {"hdr": None, "copy_box": None, "copy_layout": None, "upc_rect": None}
        hdr = _fit_hdr(w, h)
        hdr_h = hdr["font_size"] + 1.8
        copy_layout = layout_wrapped_lines(
            copy_text,
            "AvenirCond-Reg",
            max_fs=min(4.9, max(3.8, h * 0.068)),
            min_fs=3.6,
            max_w=w,
            max_h=h - hdr_h,
            line_gap=1.12,
            panel_id=panel_id,
            block_name="directions and ingredients",
        )
        return {
            "hdr": (x0, y0 + h - 0.80 * hdr["font_size"], hdr),
            "copy_box": (x0, y0, w, h - hdr_h),
            "copy_layout": copy_layout,
            "upc_rect": None,
        }

    normalize_and_encode_upca(str(upc))
    if not allow_upc_trunc:
        if w + 1e-6 < min_gs1_w or h + 1e-6 < min_gs1_h:
            raise ValueError(
                f"Panel {panel_id!r}: single flat panel safe area ({w / PT_PER_INCH:.2f}\" x {h / PT_PER_INCH:.2f}\") "
                f"cannot fit a GS1 80% retail UPC-A (>={GS1_UPCA_MIN_WIDTH_IN:.3f}\" W, >={GS1_UPCA_MIN_BAR_HEIGHT_IN:.2f}\" bar H) "
                "without crossing safety or fold boundaries; enlarge panel, omit 'upc', or set allow_non_retail_upc_truncation=True."
            )
        pref_w = min(104.0, max(min_gs1_w, w * 0.82), w)
        pref_h = min(70.0, max(min_gs1_h, h * 0.30), h)
        stacked_cands = [(pref_w, pref_h)]
        if pref_h > min_gs1_h + 0.5:
            stacked_cands.append((pref_w, min_gs1_h))
    else:
        tw = min(min_gs1_w, w * 0.92)
        th = min(min_gs1_h, max(22.0, h * 0.42))
        validate_upca_box(tw, th, bg_pad=2.0, allow_non_retail_truncation=True)
        stacked_cands = [(tw, th)]

    if not copy_text:
        uw, uh = stacked_cands[0]
        validate_upca_box(uw, uh, bg_pad=2.0, allow_non_retail_truncation=allow_upc_trunc)
        return {"hdr": None, "copy_box": None, "copy_layout": None, "upc_rect": (x0 + (w - uw) / 2.0, y0, uw, uh)}

    for uw, uh in stacked_cands:
        validate_upca_box(uw, uh, bg_pad=2.0, allow_non_retail_truncation=allow_upc_trunc)
        gap_u = 3.5
        avail_above = h - uh - gap_u
        if avail_above >= 8.5:
            try:
                hdr = _fit_hdr(w, avail_above)
                hdr_h = hdr["font_size"] + 1.8
                copy_layout = layout_wrapped_lines(
                    copy_text,
                    "AvenirCond-Reg",
                    max_fs=min(4.8, max(3.6, avail_above * 0.11)),
                    min_fs=3.6,
                    max_w=w,
                    max_h=avail_above - hdr_h,
                    line_gap=1.12,
                    panel_id=panel_id,
                    block_name="directions and ingredients",
                )
                return {
                    "hdr": (x0, y0 + h - 0.80 * hdr["font_size"], hdr),
                    "copy_box": (x0, y0 + uh + gap_u, w, avail_above - hdr_h),
                    "copy_layout": copy_layout,
                    "upc_rect": (x0 + (w - uw) / 2.0, y0, uw, uh),
                }
            except ValueError:
                pass

    sbs_uw = min_gs1_w if not allow_upc_trunc else min(min_gs1_w, w * 0.48)
    sbs_uh = min(h, min_gs1_h if not allow_upc_trunc else max(22.0, h * 0.85))
    if allow_side_by_side and w >= sbs_uw + 50.0 and h + 1e-6 >= (min_gs1_h if not allow_upc_trunc else 22.0):
        validate_upca_box(sbs_uw, sbs_uh, bg_pad=2.0, allow_non_retail_truncation=allow_upc_trunc)
        col_gap = 6.0
        copy_w = w - sbs_uw - col_gap
        hdr = _fit_hdr(copy_w, h)
        hdr_h = hdr["font_size"] + 1.8
        copy_layout = layout_wrapped_lines(
            copy_text,
            "AvenirCond-Reg",
            max_fs=min(4.6, max(3.6, h * 0.08)),
            min_fs=3.6,
            max_w=copy_w,
            max_h=h - hdr_h,
            line_gap=1.12,
            panel_id=panel_id,
            block_name="directions and ingredients",
        )
        return {
            "hdr": (x0, y0 + h - 0.80 * hdr["font_size"], hdr),
            "copy_box": (x0, y0, copy_w, h - hdr_h),
            "copy_layout": copy_layout,
            "upc_rect": (x0 + w - sbs_uw, y0 + (h - sbs_uh) / 2.0, sbs_uw, sbs_uh),
        }

    raise ValueError(
        f"Panel {panel_id!r}: directions/ingredients copy overflows available space alongside UPC-A within "
        f"({w / PT_PER_INCH:.2f}\" x {h / PT_PER_INCH:.2f}\"); enlarge panel, shorten copy, omit 'upc', or set allow_non_retail_upc_truncation=True."
    )


def plan_panel_artwork_layout(
    p: DielinePanel,
    spec: dict[str, Any],
    is_auxiliary_cap: bool = False,
    has_smcbd_vec: bool = True,
) -> dict[str, Any]:
    """
    Computes and validates complete, zero-truncation artwork layout coordinates for a single `DielinePanel`.
    Guarantees:
      - Custom `palette_cmyk` channels stay within `[0, 100]%` and `C + M + Y + K <= 300%` TAC.
      - Retail UPC-A barcodes and QR codes render only when explicitly supplied (`'upc'`, `'qr_url'`/`'coa_url'`).
      - Folded cartons (`tuck_box`) and sleeves (`fold_offsets`) place every barcode, QR code, and text block
        strictly within one flat body panel between fold scores (never wrapping across a crease).
      - Every word of directions, ingredients, disclaimer, and product identity fits without silent line drops.
    """
    validate_palette_cmyk(spec.get("palette_cmyk"))
    brand = str(spec.get("brand", "SMOKY PRODUCT CO."))
    product_name = str(spec.get("product_name", "PACKAGED PRODUCT"))
    subtitle = str(spec.get("subtitle", ""))
    net_wt = str(spec.get("net_wt", ""))
    cannabinoids = _resolve_spec_metrics(spec)
    ingredients = str(spec.get("ingredients", ""))
    directions = str(spec.get("directions", ""))
    upc = _resolve_spec_upc(spec)
    qr_url = _resolve_spec_qr_url(spec)
    has_qr = bool(qr_url)
    use_smcbd_vec = _should_use_smcbd_vector(spec, has_smcbd_vec)
    allow_upc_trunc = bool(spec.get("allow_non_retail_upc_truncation", False))
    fda_text = _resolve_spec_disclaimer(spec)
    min_gs1_w = inch(GS1_UPCA_MIN_WIDTH_IN) + 1.4

    has_left_content = bool(has_qr or fda_text.strip())
    has_right_content = bool(upc or directions.strip() or ingredients.strip())

    # 1. Circular cap / standalone circular sticker
    standalone_circle_needs_full_zones = (
        p.shape == "circle"
        and not is_auxiliary_cap
        and (has_left_content or has_right_content)
    )
    if p.shape == "circle" and not standalone_circle_needs_full_zones:
        r_safe = p.w / 2.0 - p.safety
        if r_safe < 14.0:
            raise ValueError(f"Circular panel {p.panel_id!r} safe radius ({r_safe / PT_PER_INCH:.2f}\") is too small.")
        sc = max(0.32, min(1.3, p.w / 180.0))
        ring_r = r_safe - 3.0 * sc
        arch_sub = None
        hero_lines = None
        if r_safe < 42.0 and not is_auxiliary_cap:
            if product_name.strip():
                raise ValueError(
                    f"Circular panel {p.panel_id!r} safe radius ({r_safe / PT_PER_INCH:.2f}\") is too small to fit brand and product_name; enlarge circle or set product_name=''."
                )
            if subtitle.strip() or cannabinoids or net_wt.strip():
                raise ValueError(
                    f"Circular panel {p.panel_id!r} safe radius ({r_safe / PT_PER_INCH:.2f}\") cannot fit subtitle/metrics/net_wt."
                )
        if r_safe >= 42.0:
            if subtitle.strip():
                r_arch = r_safe - 10.0 * sc
                sub_fit = fit_tracked_line(
                    subtitle.upper(), "AvenirCond-Demi", max_fs=5.8 * sc, min_fs=3.6, max_w=math.pi * r_arch * 1.15, base_tracking=0.8 * sc, panel_id=p.panel_id, field_name="lid subtitle"
                )
                arch_sub = {"radius": r_arch, "line": sub_fit}
            chord_title = 2.0 * math.sqrt(max(4.0, (r_safe - 4.0) ** 2 - (r_safe * 0.18) ** 2))
            chord_badge = 2.0 * math.sqrt(max(4.0, (r_safe - 4.0) ** 2 - (r_safe * 0.42) ** 2))
            chord_net = 2.0 * math.sqrt(max(4.0, (r_safe - 4.0) ** 2 - (r_safe * 0.62) ** 2))
            badge_str = " • ".join(f"{cb['mg']} {cb['name']}".strip() for cb in cannabinoids)
            hero_lines = {
                "title": (p.cy - r_safe * 0.18, fit_tracked_line(product_name.upper(), "DINCond-Bold", 16.0 * sc, 4.2, chord_title * 0.92, 1.0 * sc, p.panel_id, "lid title")),
                "badge": (p.cy - r_safe * 0.42, fit_tracked_line(badge_str, "AvenirCond-Bold", 6.0 * sc, 3.6, chord_badge * 0.92, 0.4 * sc, p.panel_id, "lid metrics")),
                "net": (p.cy - r_safe * 0.62, fit_tracked_line(net_wt, "AvenirCond-Med", 5.4 * sc, 3.6, chord_net * 0.92, 0.6 * sc, p.panel_id, "lid net_wt")),
            }
        brand_y = p.cy + (r_safe * 0.18 if r_safe >= 42.0 else 0.0)
        chord_brand = 2.0 * math.sqrt(max(4.0, (r_safe - 4.0) ** 2 - (brand_y - p.cy) ** 2))
        brand_line = (
            None
            if use_smcbd_vec
            else fit_tracked_line(brand, "AvenirCond-Heavy", 10.0 * sc, 3.8, chord_brand * 0.90, 0.8 * sc, p.panel_id, "lid brand")
        )
        return {
            "mode": "circle_cap",
            "use_smcbd_vec": use_smcbd_vec,
            "ring_r": ring_r,
            "sc": sc,
            "arch_sub": arch_sub,
            "brand_y": brand_y,
            "brand_vec_w": min(p.w * (0.36 if r_safe >= 42.0 else 0.52), 2.0 * r_safe * 0.76),
            "brand_line": brand_line,
            "hero_lines": hero_lines,
            "upc_rect": None,
        }

    # 2. Conical wrap annular sector
    if p.shape in ("conical_wrap", "tapered_wrap"):
        assert p.inner_radius_in is not None and p.outer_radius_in is not None and p.sector_angle_deg is not None
        r1 = inch(p.inner_radius_in)
        r2 = inch(p.outer_radius_in)
        half_theta = math.radians(p.sector_angle_deg) / 2.0
        r1_safe = r1 + p.safety
        r2_safe = r2 - p.safety
        band_safe = r2_safe - r1_safe
        ang_pad = math.asin(min(0.95, p.safety / max(r1, 1.0)))
        half_theta_safe = half_theta - ang_pad
        if band_safe < 42.0 or half_theta_safe <= 0.06:
            raise ValueError(f"Conical panel {p.panel_id!r} safe annular band is too narrow for artwork.")
        r_mid = 0.5 * (r1 + r2)
        y_apex = (
            p.cy - 0.5 * (r2 + r1 * math.cos(half_theta))
            if p.apex_down
            else p.cy + 0.5 * (r2 + r1 * math.cos(half_theta))
        )
        top_mode = bool(p.apex_down)
        sgn = 1.0 if top_mode else -1.0
        sc = max(0.55, min(1.25, band_safe / 108.0))
        max_hero_arc = min(140.0, 2.0 * r1_safe * half_theta_safe * 0.30)
        if max_hero_arc < 40.0:
            raise ValueError(
                f"Conical panel {p.panel_id!r} arc span ({2.0 * r1_safe * half_theta_safe / PT_PER_INCH:.2f}\") is too narrow for center and wing zones."
            )
        badge_line = " • ".join(f"{cb['mg']} {cb['name']}".strip() for cb in cannabinoids)
        sub_combo = "  |  ".join(part for part in (subtitle.strip().upper(), badge_line.strip()) if part)
        arched_specs = [
            (r_mid + sgn * band_safe * 0.30, fit_tracked_line(brand.upper(), "AvenirCond-Bold", 7.0 * sc, 3.8, max_hero_arc, 0.8 * sc, p.panel_id, "conical brand"), "accent"),
            (r_mid + sgn * band_safe * 0.08, fit_tracked_line(product_name.upper(), "DINCond-Bold", 15.0 * sc, 4.6, max_hero_arc, 1.0 * sc, p.panel_id, "conical title"), "white"),
        ]
        if sub_combo:
            arched_specs.append(
                (r_mid - sgn * band_safe * 0.14, fit_tracked_line(sub_combo, "AvenirCond-Demi", 6.0 * sc, 3.6, max_hero_arc, 0.6 * sc, p.panel_id, "conical subtitle"), "accent")
            )
        if net_wt.strip():
            arched_specs.append(
                (r_mid - sgn * band_safe * 0.32, fit_tracked_line(net_wt, "AvenirCond-Med", 5.6 * sc, 3.6, max_hero_arc, 0.6 * sc, p.panel_id, "conical net_wt"), "white")
            )
        theta_hero_half = max((item[1]["width_pt"] / 2.0) / max(r1_safe, 1.0) for item in arched_specs) + 0.014
        if not has_left_content and not has_right_content:
            return {
                "mode": "conical",
                "use_smcbd_vec": use_smcbd_vec,
                "y_apex": y_apex,
                "r_mid": r_mid,
                "top_mode": top_mode,
                "arched_specs": arched_specs,
                "ang_wing_mag": 0.0,
                "wing_size": None,
                "left_wing": None,
                "right_wing": None,
                "upc_rect": None,
            }
        if theta_hero_half >= half_theta_safe - 0.04:
            raise ValueError(f"Conical panel {p.panel_id!r} center hero copy leaves insufficient arc for QR/FDA and barcode wings.")

        ang_wing_mag = 0.5 * (theta_hero_half + half_theta_safe)
        ang_half_avail = 0.5 * (half_theta_safe - theta_hero_half)
        best_wing: tuple[float, float] | None = None
        last_wing_err: Exception | None = None
        for h_frac in (0.72, 0.62, 0.52, 0.44):
            wh = band_safe * h_frac
            r_in_edge = r_mid - wh / 2.0
            r_out_edge = r_mid + wh / 2.0
            if r_in_edge < r1_safe or r_out_edge >= r2_safe:
                continue
            max_hw_ang = r_in_edge * math.tan(ang_half_avail)
            max_hw_rad = math.sqrt(max(0.0, r2_safe**2 - r_out_edge**2))
            ww = 2.0 * min(max_hw_ang, max_hw_rad) - 2.0
            if ww < 24.0 or wh < 22.0:
                continue
            try:
                left_plan = (
                    _plan_qr_fda_zone(
                        p.panel_id,
                        -ww / 2.0,
                        -wh / 2.0,
                        ww,
                        wh,
                        fda_text,
                        use_smcbd_vec,
                        has_qr=has_qr,
                        brand="",
                    )
                    if has_left_content
                    else None
                )
                right_plan = (
                    _plan_directions_upc_zone(
                        p.panel_id, -ww / 2.0, -wh / 2.0, ww, wh, directions, ingredients, str(upc) if upc else None, allow_upc_trunc
                    )
                    if has_right_content
                    else None
                )
                best_wing = (ww, wh)
                return {
                    "mode": "conical",
                    "use_smcbd_vec": use_smcbd_vec,
                    "y_apex": y_apex,
                    "r_mid": r_mid,
                    "top_mode": top_mode,
                    "arched_specs": arched_specs,
                    "ang_wing_mag": ang_wing_mag,
                    "wing_size": best_wing,
                    "left_wing": left_plan,
                    "right_wing": right_plan,
                    "upc_rect": right_plan["upc_rect"] if right_plan else None,
                }
            except ValueError as exc:
                last_wing_err = exc
        if last_wing_err is not None:
            raise last_wing_err
        raise ValueError(
            f"Conical panel {p.panel_id!r} safe wing sector cannot fit QR/FDA, directions/ingredients, and retail UPC-A without crossing curved safety boundaries."
        )

    # 3. Multi-face folded panels (`tuck_box`, `carton_flat`, `carton_sleeve`, or explicit `fold_offsets`)
    if p.carton_net is not None or bool(p.fold_offsets):
        if p.carton_net is not None:
            by0 = p.y0 + inch(float(p.carton_net["body_y0_in"]))
            by1 = p.y0 + inch(float(p.carton_net["body_y1_in"]))
            faces = [
                {
                    "name": str(col["name"]),
                    "x0": p.x0 + inch(float(col["x0_in"])),
                    "x1": p.x0 + inch(float(col["x1_in"])),
                    "y0": by0,
                    "y1": by1,
                }
                for col in p.carton_net["columns"]
                if col["name"] != "glue_flap"
            ]
        else:
            xs = [0.0] + sorted(fx for fx in p.fold_offsets if 0.0 < fx < p.w) + [p.w]
            raw_faces = [
                {"name": f"face_{i}", "x0": p.x0 + xs[i], "x1": p.x0 + xs[i + 1], "y0": p.y0, "y1": p.y0 + p.h}
                for i in range(len(xs) - 1)
            ]
            if p.has_leading_glue_flap and len(raw_faces) >= 2:
                faces = [f for f in raw_faces[1:] if (f["x1"] - f["x0"]) > 2.0 * p.safety + 12.0]
            else:
                faces = [f for f in raw_faces if (f["x1"] - f["x0"]) > 2.0 * p.safety + 12.0]

        if len(faces) < 2:
            raise ValueError(f"Folded panel {p.panel_id!r} requires at least two usable faces between fold lines.")

        fold_pad = max(p.safety, inch(0.0625)) + 2.0

        def _safe_box(face: dict[str, Any]) -> tuple[float, float, float, float]:
            fw = (face["x1"] - face["x0"]) - 2.0 * fold_pad
            fh = (face["y1"] - face["y0"]) - 2.0 * fold_pad
            if fw <= 8.0 or fh <= 12.0:
                raise ValueError(f"Panel {p.panel_id!r} face {face['name']!r} is too narrow after fold safety clearance.")
            return (face["x0"] + fold_pad, face["y0"] + fold_pad, fw, fh)

        if len(faces) >= 4:
            hero_face, qr_face, upc_face, fda_face = faces[0], faces[1], faces[2], faces[3]
            if upc and ((upc_face["x1"] - upc_face["x0"] - 2.0 * fold_pad) + 1e-6 < (min_gs1_w if not allow_upc_trunc else 36.0)):
                by_w = sorted(faces[:4], key=lambda f: f["x1"] - f["x0"], reverse=True)
                hero_face, upc_face, qr_face, fda_face = by_w[0], by_w[1], by_w[2], by_w[3]
            if (qr_face["x1"] - qr_face["x0"] - 2.0 * fold_pad) >= 22.0 and (fda_face["x1"] - fda_face["x0"] - 2.0 * fold_pad) >= 18.0:
                hx, hy, hw, hh = _safe_box(hero_face)
                ux, uy, uw, uh = _safe_box(upc_face)
                qx, qy, qw, qh = _safe_box(qr_face)
                fx, fy, fw, fh = _safe_box(fda_face)

                hero_plan = _plan_hero_zone(
                    p.panel_id, hx, hy, hw, hh, brand, product_name, subtitle, cannabinoids, net_wt, use_smcbd_vec, show_brand_header=True
                )
                upc_plan = _plan_directions_upc_zone(
                    p.panel_id, ux, uy, uw, uh, directions, ingredients, str(upc) if upc else None, allow_upc_trunc
                )
                qr_plan = _plan_qr_fda_zone(p.panel_id, qx, qy, qw, qh, "", use_smcbd_vec, has_qr=has_qr, brand=brand)
                fda_only = layout_wrapped_lines(
                    fda_text, "AvenirCond-Reg", max_fs=4.8, min_fs=3.6, max_w=fw, max_h=fh, line_gap=1.15, panel_id=p.panel_id, block_name="disclaimer"
                )
                fda_y_mid = fy + (fh - fda_only["height_pt"]) / 2.0
                return {
                    "mode": "folded_4face",
                    "use_smcbd_vec": use_smcbd_vec,
                    "faces": faces,
                    "tinted_faces": [qr_face, fda_face],
                    "hero": hero_plan,
                    "upc_zone": upc_plan,
                    "qr_zone": qr_plan,
                    "fda_box": (fx, fda_y_mid, fw, fda_only["height_pt"]),
                    "fda_layout": fda_only,
                    "upc_face": upc_face,
                    "upc_rect": upc_plan["upc_rect"],
                }
            faces = [hero_face, upc_face]

        if len(faces) == 3:
            by_w = sorted(range(3), key=lambda idx: faces[idx]["x1"] - faces[idx]["x0"], reverse=True)
            hero_f = faces[by_w[0]]
            upc_f = faces[by_w[1]]
            qrfda_f = faces[by_w[2]]
            hx, hy, hw, hh = _safe_box(hero_f)
            ux, uy, uw, uh = _safe_box(upc_f)
            qx, qy, qw, qh = _safe_box(qrfda_f)
            hero_plan = _plan_hero_zone(
                p.panel_id, hx, hy, hw, hh, brand, product_name, subtitle, cannabinoids, net_wt, use_smcbd_vec, show_brand_header=True
            )
            upc_plan = _plan_directions_upc_zone(
                p.panel_id, ux, uy, uw, uh, directions, ingredients, str(upc) if upc else None, allow_upc_trunc
            )
            qrfda_plan = _plan_qr_fda_zone(p.panel_id, qx, qy, qw, qh, fda_text, use_smcbd_vec, has_qr=has_qr, brand=brand)
            return {
                "mode": "folded_3face",
                "use_smcbd_vec": use_smcbd_vec,
                "faces": faces,
                "tinted_faces": [qrfda_f],
                "hero": hero_plan,
                "upc_zone": upc_plan,
                "qr_zone": qrfda_plan,
                "upc_face": upc_f,
                "upc_rect": upc_plan["upc_rect"],
            }

        f_left, f_right = faces[0], faces[1]
        lx, ly, lw, lh = _safe_box(f_left)
        rx, ry, rw, rh = _safe_box(f_right)
        if has_left_content and has_right_content:
            sub_qr_w = max(24.0 if (has_qr and not fda_text.strip()) else 42.0, lw * 0.36)
            sub_hero_w = lw - sub_qr_w - 6.0
            if sub_hero_w < 44.0:
                raise ValueError(f"Folded 2-face panel {p.panel_id!r} face is too narrow for QR/FDA and hero content.")
            qrfda_plan = _plan_qr_fda_zone(p.panel_id, lx, ly, sub_qr_w, lh, fda_text, use_smcbd_vec, has_qr=has_qr, brand="")
            hero_plan = _plan_hero_zone(
                p.panel_id,
                lx + sub_qr_w + 6.0,
                ly,
                sub_hero_w,
                lh,
                brand,
                product_name,
                subtitle,
                cannabinoids,
                net_wt,
                use_smcbd_vec,
                show_brand_header=not bool(qrfda_plan.get("vec_box")),
            )
            upc_plan = _plan_directions_upc_zone(
                p.panel_id, rx, ry, rw, rh, directions, ingredients, str(upc) if upc else None, allow_upc_trunc
            )
        elif has_left_content:
            qrfda_plan = _plan_qr_fda_zone(p.panel_id, rx, ry, rw, rh, fda_text, use_smcbd_vec, has_qr=has_qr, brand="")
            hero_plan = _plan_hero_zone(
                p.panel_id,
                lx,
                ly,
                lw,
                lh,
                brand,
                product_name,
                subtitle,
                cannabinoids,
                net_wt,
                use_smcbd_vec,
                show_brand_header=not bool(qrfda_plan.get("vec_box")),
            )
            upc_plan = _plan_directions_upc_zone(p.panel_id, rx, ry, rw, rh, "", "", None, allow_upc_trunc)
        else:
            hero_plan = _plan_hero_zone(
                p.panel_id, lx, ly, lw, lh, brand, product_name, subtitle, cannabinoids, net_wt, use_smcbd_vec, show_brand_header=True
            )
            qrfda_plan = _plan_qr_fda_zone(p.panel_id, rx, ry, rw, rh, "", use_smcbd_vec, has_qr=False, brand="")
            upc_plan = _plan_directions_upc_zone(
                p.panel_id, rx, ry, rw, rh, directions, ingredients, str(upc) if upc else None, allow_upc_trunc
            )
        return {
            "mode": "folded_3face",
            "use_smcbd_vec": use_smcbd_vec,
            "faces": faces,
            "tinted_faces": [],
            "hero": hero_plan,
            "upc_zone": upc_plan,
            "qr_zone": qrfda_plan,
            "upc_face": f_right,
            "upc_rect": upc_plan["upc_rect"],
        }

    # 4. Single-face flat panels (`rect`, `rounded_rect`, `oval`, `flat_trapezoid`, or standalone `circle` with copy/UPC)
    if p.shape == "circle":
        r_safe = p.w / 2.0 - p.safety
        side = max(4.0, 2.0 * r_safe * math.sqrt(0.5))
        safe_x0, safe_y0, safe_w, safe_h = p.cx - side / 2.0, p.cy - side / 2.0, side, side
        draw_dividers = False
    elif p.shape == "oval":
        rx_s = max(2.0, p.w / 2.0 - p.safety)
        ry_s = max(2.0, p.h / 2.0 - p.safety)
        safe_w = 2.0 * rx_s * math.sqrt(0.5)
        safe_h = 2.0 * ry_s * math.sqrt(0.5)
        safe_x0, safe_y0 = p.cx - safe_w / 2.0, p.cy - safe_h / 2.0
        draw_dividers = False
    elif p.shape == "flat_trapezoid":
        v_s = p.trapezoid_vertices(-p.safety)
        half_inscribed = min(abs(v_s[1][0] - p.cx), abs(v_s[2][0] - p.cx))
        safe_w = max(4.0, 2.0 * half_inscribed - 4.0)
        safe_h = max(4.0, (v_s[2][1] - v_s[0][1]) - 4.0)
        safe_x0, safe_y0 = p.cx - safe_w / 2.0, p.cy - safe_h / 2.0
        draw_dividers = True
    else:
        corner_inset = max(0.0, (p.corner_r - p.safety) * 0.30)
        pad_x = p.safety + corner_inset + 2.0
        pad_y = p.safety + corner_inset + 2.0
        safe_x0 = p.x0 + pad_x
        safe_y0 = p.y0 + pad_y
        safe_w = p.w - 2.0 * pad_x
        safe_h = p.h - 2.0 * pad_y
        draw_dividers = True

    if safe_w <= 20.0 or safe_h <= 16.0:
        raise ValueError(f"Panel {p.panel_id!r} safe area ({safe_w / PT_PER_INCH:.2f}\" x {safe_h / PT_PER_INCH:.2f}\") is too small.")

    col_gap = max(6.0, min(11.0, safe_w * 0.022))
    req_upc_w = (min_gs1_w if not allow_upc_trunc else 36.0) if upc else 0.0

    if not has_left_content and not has_right_content:
        hero_plan = _plan_hero_zone(
            p.panel_id,
            safe_x0,
            safe_y0,
            safe_w,
            safe_h,
            brand,
            product_name,
            subtitle,
            cannabinoids,
            net_wt,
            use_smcbd_vec,
            show_brand_header=True,
        )
        return {
            "mode": "flat_3zone",
            "use_smcbd_vec": use_smcbd_vec,
            "draw_dividers": False,
            "div_left": None,
            "div_right": None,
            "qr_zone": None,
            "hero": hero_plan,
            "upc_zone": None,
            "upc_rect": None,
        }

    min_left = (22.0 if (has_qr and not fda_text.strip()) else 36.0) if has_left_content else 0.0
    min_right = max(36.0, req_upc_w) if has_right_content else 0.0

    if has_left_content and not has_right_content:
        split_candidates: list[tuple[float, float]] = [
            (max(min_left, min(safe_w * 0.34, safe_w - col_gap - 44.0)), 0.0),
            (min_left, 0.0),
        ]
    elif has_right_content and not has_left_content:
        split_candidates = [
            (0.0, max(min_right, min(safe_w * 0.42, safe_w - col_gap - 44.0))),
            (0.0, min_right),
        ]
        if upc and safe_w >= 200.0:
            split_candidates.append((0.0, max(safe_w * 0.48, req_upc_w + 48.0)))
    else:
        split_candidates = [
            (
                max(min_left, min(safe_w * 0.25, (safe_w - max(safe_w * 0.30, req_upc_w)) * 0.40)),
                max(safe_w * 0.30, min_right),
            ),
            (min_left, min_right),
        ]
        if upc and safe_w >= 260.0:
            wide_rw = max(safe_w * 0.43, req_upc_w + 58.0)
            wide_lw = max(min_left, (safe_w - wide_rw) * 0.38)
            split_candidates.append((wide_lw, wide_rw))

    last_err: Exception | None = None
    for left_w, right_w in split_candidates:
        n_gaps = (1 if left_w > 0 else 0) + (1 if right_w > 0 else 0)
        center_w = safe_w - left_w - right_w - n_gaps * col_gap
        if (left_w > 0 and left_w + 1e-6 < min_left) or center_w < 44.0 or (right_w > 0 and right_w + 1e-6 < min_right):
            last_err = ValueError(
                f"Panel {p.panel_id!r}: safe width ({safe_w / PT_PER_INCH:.2f}\") cannot accommodate requested columns without overlap."
            )
            continue
        try:
            qr_plan = (
                _plan_qr_fda_zone(
                    p.panel_id, safe_x0, safe_y0, left_w, safe_h, fda_text, use_smcbd_vec, has_qr=has_qr, brand=""
                )
                if left_w > 0
                else None
            )
            placed_side_logo = bool(qr_plan and qr_plan.get("vec_box"))
            hero_x0 = safe_x0 + (left_w + col_gap if left_w > 0 else 0.0)
            hero_plan = _plan_hero_zone(
                p.panel_id,
                hero_x0,
                safe_y0,
                center_w,
                safe_h,
                brand,
                product_name,
                subtitle,
                cannabinoids,
                net_wt,
                use_smcbd_vec,
                show_brand_header=not placed_side_logo,
            )
            upc_plan = (
                _plan_directions_upc_zone(
                    p.panel_id,
                    safe_x0 + safe_w - right_w,
                    safe_y0,
                    right_w,
                    safe_h,
                    directions,
                    ingredients,
                    str(upc) if upc else None,
                    allow_upc_trunc,
                )
                if right_w > 0
                else None
            )
            div_left = (safe_x0 + left_w + col_gap * 0.5) if left_w > 0 else None
            div_right = (safe_x0 + safe_w - right_w - col_gap * 0.5) if right_w > 0 else None
            return {
                "mode": "flat_3zone",
                "use_smcbd_vec": use_smcbd_vec,
                "draw_dividers": draw_dividers and (div_left is not None or div_right is not None),
                "div_left": div_left,
                "div_right": div_right,
                "qr_zone": qr_plan,
                "hero": hero_plan,
                "upc_zone": upc_plan,
                "upc_rect": upc_plan["upc_rect"] if upc_plan else None,
            }
        except ValueError as exc:
            last_err = exc

    assert last_err is not None
    raise last_err


def _draw_wrapped_block(c: canvas.Canvas, box: tuple[float, float, float, float], layout: dict[str, Any], color: PCMYKColor, align: str = "left") -> None:
    lines = layout["lines"]
    if not lines:
        return
    x0, y0, w, h = box
    fn = resolve_font(layout["font_name"])
    fs = layout["font_size"]
    leading = layout["leading_pt"]
    c.saveState()
    c.setFillColor(color)
    c.setFont(fn, fs)
    ly = y0 + h - 0.80 * fs
    for ln in lines:
        if align == "center":
            c.drawCentredString(x0 + w / 2.0, ly, ln)
        else:
            c.drawString(x0, ly, ln)
        ly -= leading
    c.restoreState()


def _draw_planned_qr_fda(
    c: canvas.Canvas,
    qr_plan: dict[str, Any],
    coa_url: str | None,
    smcbd_vec: dict[str, Any] | None,
    accent_col: PCMYKColor,
) -> None:
    if qr_plan.get("qr_rect") and coa_url:
        qx, qy, qw, _ = qr_plan["qr_rect"]
        draw_vector_qr(c, coa_url, qx, qy, qw, quiet_modules=QR_MIN_QUIET_MODULES)
    if qr_plan.get("vec_box") and smcbd_vec:
        vx, vy, vw, vh = qr_plan["vec_box"]
        draw_normalized_vector(c, smcbd_vec, vx + vw / 2.0, vy + vh / 2.0, min(46.0, vw * 0.92), CMYK_WHITE)
    elif qr_plan.get("brand_line"):
        bl = qr_plan["brand_line"]
        draw_tracked_text(c, bl["text"], bl["cx"], bl["y"], bl["font_name"], bl["font_size"], accent_col, bl["tracking_pt"])
    _draw_wrapped_block(c, qr_plan["fda_box"], qr_plan["fda_layout"], CMYK_WHITE)


def _draw_planned_hero(
    c: canvas.Canvas,
    hero_plan: dict[str, Any],
    smcbd_vec: dict[str, Any] | None,
    panel_col: PCMYKColor,
    accent_col: PCMYKColor,
) -> None:
    cx = hero_plan["cx"]
    bh = hero_plan.get("brand_header")
    if bh:
        if bh["kind"] == "vector" and smcbd_vec:
            draw_normalized_vector(c, smcbd_vec, bh["cx"], bh["cy"], bh["w"], CMYK_WHITE)
        elif bh["kind"] == "text":
            ln = bh["line"]
            draw_tracked_text(c, ln["text"], bh["cx"], bh["y"], ln["font_name"], ln["font_size"], CMYK_WHITE, ln["tracking_pt"])

    t_info = hero_plan["title"]
    t_top = hero_plan["title_top"]
    hx0 = hero_plan["x0"]
    hw = hero_plan["w"]
    if t_info["kind"] == "tracked":
        ln = t_info["line"]
        draw_tracked_text(c, ln["text"], cx, t_top - 0.80 * ln["font_size"], ln["font_name"], ln["font_size"], CMYK_WHITE, ln["tracking_pt"])
    else:
        tw_layout = t_info["layout"]
        _draw_wrapped_block(c, (hx0, t_top - tw_layout["height_pt"], hw, tw_layout["height_pt"]), tw_layout, CMYK_WHITE, align="center")

    sub_layout = hero_plan["subtitle"]
    sub_top = hero_plan["subtitle_top"]
    if sub_layout["lines"]:
        _draw_wrapped_block(c, (hx0, sub_top - sub_layout["height_pt"], hw, sub_layout["height_pt"]), sub_layout, accent_col, align="center")

    if hero_plan["grid_rect"] and hero_plan["cells"]:
        gx0, gy0, grid_w, gh = hero_plan["grid_rect"]
        c.setFillColor(panel_col)
        c.setStrokeColor(accent_col)
        c.setLineWidth(0.7)
        c.roundRect(gx0, gy0, grid_w, gh, 2.0, stroke=1, fill=1)
        for idx, cell in enumerate(hero_plan["cells"]):
            cx_i = cell["x0"]
            cw_i = cell["w"]
            if idx > 0:
                c.setLineWidth(0.45)
                c.line(cx_i, gy0 + 2.5, cx_i, gy0 + gh - 2.5)
            mg = cell["mg"]
            nm = cell["name"]
            draw_tracked_text(c, mg["text"], cx_i + cw_i / 2.0, gy0 + gh * 0.52, mg["font_name"], mg["font_size"], CMYK_WHITE, mg["tracking_pt"])
            draw_tracked_text(c, nm["text"], cx_i + cw_i / 2.0, gy0 + gh * 0.16, nm["font_name"], nm["font_size"], accent_col, nm["tracking_pt"])

    nl = hero_plan["net_line"]
    if nl["text"]:
        draw_tracked_text(c, nl["text"], cx, hero_plan["net_y"], nl["font_name"], nl["font_size"], CMYK_WHITE, nl["tracking_pt"])


def _draw_planned_directions_upc(
    c: canvas.Canvas,
    upc_plan: dict[str, Any],
    upc: str | None,
    allow_upc_trunc: bool,
    accent_col: PCMYKColor,
) -> None:
    if upc_plan.get("hdr"):
        hx, hy, h_line = upc_plan["hdr"]
        draw_tracked_text(c, h_line["text"], hx, hy, h_line["font_name"], h_line["font_size"], accent_col, h_line["tracking_pt"], align="left")
    if upc_plan.get("copy_box") and upc_plan.get("copy_layout"):
        _draw_wrapped_block(c, upc_plan["copy_box"], upc_plan["copy_layout"], CMYK_WHITE)
    if upc and upc_plan.get("upc_rect"):
        ux, uy, uw, uh = upc_plan["upc_rect"]
        draw_vector_upca(c, str(upc), ux, uy, uw, uh, bg_pad=2.0, allow_non_retail_truncation=allow_upc_trunc)


def build_generic_spec_artwork(spec: dict[str, Any]) -> Callable[[canvas.Canvas, list[DielinePanel], dict[str, Any]], None]:
    """Creates clean, responsive CMYK packaging artwork pre-verified for TAC <= 300%, fold boundaries, and zero copy overflow."""
    palette = validate_palette_cmyk(spec.get("palette_cmyk"))
    bg_col = PCMYKColor(*palette["bg"])
    accent_col = PCMYKColor(*palette["accent"])
    panel_col = PCMYKColor(*palette["panel"])
    upc = _resolve_spec_upc(spec)
    allow_upc_trunc = bool(spec.get("allow_non_retail_upc_truncation", False))
    coa_url = _resolve_spec_qr_url(spec)

    def _render(c: canvas.Canvas, panels: list[DielinePanel], brand_vecs: dict[str, Any]) -> None:
        raw_smcbd_vec = brand_vecs.get("smcbd")
        has_non_circle = any(op.shape != "circle" for op in panels)

        for p in panels:
            plan = plan_panel_artwork_layout(
                p,
                spec,
                is_auxiliary_cap=(p.shape == "circle" and has_non_circle),
                has_smcbd_vec=bool(raw_smcbd_vec),
            )
            smcbd_vec = raw_smcbd_vec if plan.get("use_smcbd_vec") else None
            c.saveState()
            c.clipPath(p.make_path(c, +p.bleed), stroke=0, fill=0)
            raw_bx0, raw_by0, raw_bw, raw_bh = p.offset_bbox(+p.bleed)
            bx0, by0 = raw_bx0 - 1.0, raw_by0 - 1.0
            bw, bh = raw_bw + 2.0, raw_bh + 2.0
            c.setFillColor(bg_col)
            c.drawPath(p.make_path(c, +p.bleed), stroke=0, fill=1)

            mode = plan["mode"]
            if mode == "circle_cap":
                c.setStrokeColor(accent_col)
                c.setLineWidth(1.1 * plan["sc"])
                c.circle(p.cx, p.cy, plan["ring_r"], stroke=1, fill=0)
                if plan["arch_sub"]:
                    asub = plan["arch_sub"]
                    ln = asub["line"]
                    draw_arched_text(c, ln["text"], p.cx, p.cy, asub["radius"], ln["font_name"], ln["font_size"], accent_col, ln["tracking_pt"], top_arc=True)
                if smcbd_vec:
                    draw_normalized_vector(c, smcbd_vec, p.cx, plan["brand_y"], plan["brand_vec_w"], CMYK_WHITE)
                elif plan["brand_line"]:
                    bl = plan["brand_line"]
                    draw_tracked_text(c, bl["text"], p.cx, plan["brand_y"], bl["font_name"], bl["font_size"], CMYK_WHITE, bl["tracking_pt"])
                if plan["hero_lines"]:
                    for key, col in (("title", CMYK_WHITE), ("badge", accent_col), ("net", CMYK_WHITE)):
                        ly, ln = plan["hero_lines"][key]
                        if ln["text"]:
                            draw_tracked_text(c, ln["text"], p.cx, ly, ln["font_name"], ln["font_size"], col, ln["tracking_pt"])

            elif mode == "conical":
                top_mode = plan["top_mode"]
                y_apex = plan["y_apex"]
                r_mid = plan["r_mid"]
                for r_line, ln, col_key in plan["arched_specs"]:
                    col = accent_col if col_key == "accent" else CMYK_WHITE
                    draw_arched_text(
                        c,
                        ln["text"],
                        p.cx,
                        y_apex,
                        r_line,
                        ln["font_name"],
                        ln["font_size"],
                        col,
                        ln["tracking_pt"],
                        top_arc=top_mode,
                        center_angle_deg=90.0 if top_mode else 270.0,
                    )
                for sign_ang, wing_plan, is_left in ((-1.0, plan["left_wing"], True), (+1.0, plan["right_wing"], False)):
                    if wing_plan is None:
                        continue
                    ang = sign_ang * plan["ang_wing_mag"]
                    wx = p.cx + r_mid * math.sin(ang)
                    wy = y_apex + (r_mid * math.cos(ang) if top_mode else -r_mid * math.cos(ang))
                    c.saveState()
                    c.translate(wx, wy)
                    c.rotate(-math.degrees(ang) if top_mode else math.degrees(ang))
                    if is_left:
                        _draw_planned_qr_fda(c, wing_plan, coa_url, smcbd_vec, accent_col)
                    else:
                        _draw_planned_directions_upc(c, wing_plan, str(upc) if upc else None, allow_upc_trunc, accent_col)
                    c.restoreState()

            elif mode in ("folded_4face", "folded_3face"):
                c.setFillColor(panel_col)
                for tf in plan["tinted_faces"]:
                    c.rect(tf["x0"], tf["y0"], tf["x1"] - tf["x0"], tf["y1"] - tf["y0"], stroke=0, fill=1)
                _draw_planned_hero(c, plan["hero"], smcbd_vec, panel_col, accent_col)
                _draw_planned_directions_upc(c, plan["upc_zone"], str(upc) if upc else None, allow_upc_trunc, accent_col)
                _draw_planned_qr_fda(c, plan["qr_zone"], coa_url, smcbd_vec, accent_col)
                if mode == "folded_4face":
                    _draw_wrapped_block(c, plan["fda_box"], plan["fda_layout"], CMYK_WHITE)

            else:
                if plan["draw_dividers"]:
                    c.setFillColor(panel_col)
                    if plan["div_left"] is not None:
                        c.rect(bx0, by0, plan["div_left"] - bx0, bh, stroke=0, fill=1)
                    if plan["div_right"] is not None:
                        c.rect(plan["div_right"], by0, (bx0 + bw) - plan["div_right"], bh, stroke=0, fill=1)
                    c.setStrokeColor(accent_col)
                    c.setLineWidth(0.8)
                    if plan["div_left"] is not None:
                        c.line(plan["div_left"], by0, plan["div_left"], by0 + bh)
                    if plan["div_right"] is not None:
                        c.line(plan["div_right"], by0, plan["div_right"], by0 + bh)
                if plan["qr_zone"] is not None:
                    _draw_planned_qr_fda(c, plan["qr_zone"], coa_url, smcbd_vec, accent_col)
                _draw_planned_hero(c, plan["hero"], smcbd_vec, panel_col, accent_col)
                if plan["upc_zone"] is not None:
                    _draw_planned_directions_upc(c, plan["upc_zone"], str(upc) if upc else None, allow_upc_trunc, accent_col)

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
                corner_radius_in=p_cfg.get("corner_radius_in"),
                top_width_in=tw_in,
                fold_offsets_in=p_cfg.get("fold_offsets_in"),
                inner_radius_in=p_cfg.get("inner_radius_in"),
                outer_radius_in=p_cfg.get("outer_radius_in"),
                sector_angle_deg=p_cfg.get("sector_angle_deg"),
                apex_down=p_cfg.get("apex_down", True),
                carton_net=p_cfg.get("carton_net"),
                has_leading_glue_flap=p_cfg.get("has_leading_glue_flap"),
                label_desc=p_cfg.get("label_desc"),
            )
        )

    gap_in = 1.45
    panel_bleed_boxes_pt = [p.offset_bbox(+p.bleed) for p in panels]
    panel_bleed_spans_in = [b[2] / PT_PER_INCH for b in panel_bleed_boxes_pt]
    panel_bleed_heights_in = [b[3] / PT_PER_INCH for b in panel_bleed_boxes_pt]
    total_span_in = sum(panel_bleed_spans_in) + gap_in * max(0, len(panels) - 1)
    max_bleed_h_in = max(panel_bleed_heights_in)
    sheet_w_in = float(spec.get("page_w_in") or max(18.5685, total_span_in + 5.0))
    sheet_h_in = float(spec.get("page_h_in") or max(9.6715, max_bleed_h_in + 5.8))
    cur_left_in = (sheet_w_in - total_span_in) / 2.0
    footer_top_in = 139.3 / PT_PER_INCH  # 1.9347" top of Die Template footer banner
    if spec.get("page_h_in") is not None:
        if sheet_h_in > footer_top_in + max_bleed_h_in + 0.10:
            default_cy_in = footer_top_in + (sheet_h_in - footer_top_in) * 0.50
        else:
            default_cy_in = sheet_h_in * 0.50
    else:
        default_cy_in = (sheet_h_in - 1.925) * 0.54 + 1.925

    for p, bbox_pt, span_in, bh_in, (cx_exp, cy_exp) in zip(
        panels, panel_bleed_boxes_pt, panel_bleed_spans_in, panel_bleed_heights_in, explicit_positions
    ):
        cx_offset_in = -(bbox_pt[0] + bbox_pt[2] / 2.0) / PT_PER_INCH
        cy_offset_in = -(bbox_pt[1] + bbox_pt[3] / 2.0) / PT_PER_INCH
        cx_in = cx_exp if cx_exp is not None else (cur_left_in + span_in / 2.0 + cx_offset_in)
        if cy_exp is not None:
            cy_in = cy_exp
        else:
            bleed_mid_y_in = default_cy_in
            half_bh_in = bh_in / 2.0
            pad_y_in = 0.05 if sheet_h_in >= bh_in + 0.10 else 0.0
            if sheet_h_in >= bh_in + 2.0 * pad_y_in:
                bleed_mid_y_in = min(sheet_h_in - pad_y_in - half_bh_in, max(pad_y_in + half_bh_in, bleed_mid_y_in))
            cy_in = bleed_mid_y_in + cy_offset_in
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
