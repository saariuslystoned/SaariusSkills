#!/usr/bin/env python3
"""Deterministic sprite_version: 2 extended pet atlas compiler, verifier, and preview generator."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path
from typing import Any, Sequence


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CELL_W = 192
CELL_H = 208
COLS = 8
ROWS = 11
ATLAS_W = CELL_W * COLS  # 1536
ATLAS_H = CELL_H * ROWS  # 2288

ROW_SPEC: list[tuple[str, int, int, bool]] = [
    ("idle", 6, 120, True),
    ("running-right", 8, 90, True),
    ("running-left", 8, 90, True),
    ("waving", 4, 120, True),
    ("jumping", 5, 110, False),
    ("failed", 8, 110, False),
    ("waiting", 6, 120, True),
    ("running", 6, 110, True),
    ("review", 6, 120, True),
    ("look_000_to_157_5", 8, 95, True),
    ("look_180_to_337_5", 8, 95, True),
]

LOOK_ANGLES = [
    "000",
    "022_5",
    "045",
    "067_5",
    "090",
    "112_5",
    "135",
    "157_5",
    "180",
    "202_5",
    "225",
    "247_5",
    "270",
    "292_5",
    "315",
    "337_5",
]


class PetAtlasError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        exit_code: int = 2,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.exit_code = exit_code


def inspect_png_header(data: bytes) -> dict[str, Any]:
    if not data.startswith(PNG_SIGNATURE):
        raise PetAtlasError(
            "NOT_A_PNG",
            "File does not begin with a valid PNG signature.",
            exit_code=3,
        )
    if len(data) < 33 or data[12:16] != b"IHDR":
        raise PetAtlasError(
            "MALFORMED_PNG",
            "File is missing a valid PNG IHDR chunk.",
            exit_code=3,
        )
    width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
    return {
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "color_type": color_type,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _require_pillow_numpy() -> tuple[Any, Any, Any, Any]:
    try:
        import numpy as np
        from PIL import Image, ImageDraw, ImageOps

        return np, Image, ImageDraw, ImageOps
    except ImportError as exc:
        raise PetAtlasError(
            "PILLOW_OR_NUMPY_MISSING",
            "Pillow and NumPy are required for pixel-level atlas verification and preview generation.",
            details={"reason": str(exc)},
            exit_code=3,
        ) from exc


def despill_magenta_rgba(arr: Any, np: Any) -> Any:
    """Remove #FF00FF chroma background and suppress magenta spill with zero transparent RGB residue."""
    out = arr.astype(np.float32).copy()
    r, g, b = out[:, :, 0], out[:, :, 1], out[:, :, 2]
    dist = np.sqrt((r - 255.0) ** 2 + (g - 0.0) ** 2 + (b - 255.0) ** 2)
    alpha = np.clip((dist - 62.0) / 52.0, 0.0, 1.0)
    excess = np.maximum(0.0, np.minimum(r, b) - g)
    is_magenta_tint = (r > g + 16.0) & (b > g + 16.0)
    suppress = np.where(is_magenta_tint, excess * 0.92, 0.0)
    out[:, :, 0] = np.clip(r - suppress, 0.0, 255.0)
    out[:, :, 2] = np.clip(b - suppress, 0.0, 255.0)
    out[:, :, 1] = np.clip(g + suppress * 0.20, 0.0, 255.0)
    alpha_u8 = (alpha * 255.0).astype(np.uint8)
    alpha_u8[alpha_u8 < 28] = 0
    alpha_u8[alpha_u8 > 235] = 255
    res = out.astype(np.uint8)
    res[:, :, 3] = alpha_u8
    res[alpha_u8 == 0] = [0, 0, 0, 0]
    return res


def analyze_cell(cell_arr: Any, np: Any) -> dict[str, Any]:
    alpha = cell_arr[:, :, 3]
    r = cell_arr[:, :, 0].astype(np.int32)
    g = cell_arr[:, :, 1].astype(np.int32)
    b = cell_arr[:, :, 2].astype(np.int32)

    trans_mask = alpha == 0
    trans_residue = int(
        np.sum(trans_mask & ((r != 0) | (g != 0) | (b != 0)))
    )

    opaque_mask = alpha > 0
    opaque_pixels = int(np.sum(opaque_mask))
    if opaque_pixels == 0:
        return {
            "empty": True,
            "opaque_pixels": 0,
            "transparent_rgb_residue_pixels": trans_residue,
            "opaque_chroma_key_pixels": 0,
            "semi_transparent_fringe_pixels": 0,
            "edge_touch_pixels": 0,
        }

    chroma_mask = opaque_mask & (r > 235) & (g < 25) & (b > 235)
    semi_fringe_mask = (alpha > 0) & (alpha < 180) & (r > g + 95) & (b > g + 95) & (np.abs(r - b) < 35)

    ys, xs = np.where(alpha > 20)
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    w = x1 - x0 + 1
    h = y1 - y0 + 1

    # Torso band centroid (38%..76% of bbox height) for horizontal stability
    band_y0 = y0 + int(h * 0.38)
    band_y1 = max(band_y0 + 1, y0 + int(h * 0.76))
    band_alpha = alpha[band_y0:band_y1, :]
    if np.sum(band_alpha > 20) > 0:
        _, bxs = np.where(band_alpha > 20)
        center_x = round(float(np.mean(bxs)), 2)
    else:
        center_x = round(float(np.mean(xs)), 2)
    center_y = round(float(np.mean(ys)), 2)

    edge_touch = int(
        np.sum(alpha[0, :] > 0)
        + np.sum(alpha[-1, :] > 0)
        + np.sum(alpha[:, 0] > 0)
        + np.sum(alpha[:, -1] > 0)
    )

    return {
        "empty": False,
        "bbox": [x0, y0, x1, y1],
        "width": w,
        "height": h,
        "bottom_y": y1,
        "top_y": y0,
        "center_x": center_x,
        "center_y": center_y,
        "opaque_pixels": opaque_pixels,
        "transparent_rgb_residue_pixels": trans_residue,
        "opaque_chroma_key_pixels": int(np.sum(chroma_mask)),
        "semi_transparent_fringe_pixels": int(np.sum(semi_fringe_mask)),
        "edge_touch_pixels": edge_touch,
    }


def verify_atlas(
    atlas_path: Path,
    *,
    slug: str,
    out_dir: Path | None = None,
    render_previews: bool = False,
    bundle_zip: bool = False,
) -> dict[str, Any]:
    raw_bytes = atlas_path.read_bytes()
    header = inspect_png_header(raw_bytes)
    if header["width"] != ATLAS_W or header["height"] != ATLAS_H:
        raise PetAtlasError(
            "INVALID_ATLAS_DIMENSIONS",
            f"Expected {ATLAS_W}x{ATLAS_H} PNG, got {header['width']}x{header['height']}.",
            details=header,
            exit_code=3,
        )

    np, Image, ImageDraw, _ = _require_pillow_numpy()
    atlas_img = Image.open(atlas_path).convert("RGBA")
    atlas_arr = np.array(atlas_img)

    manifest_rows: dict[str, Any] = {}
    frames_meta: dict[str, Any] = {}
    populated_cells = 0
    empty_unused_cells = 0
    non_empty_unused_cells = 0
    total_trans_residue = 0
    total_chroma_pixels = 0
    total_fringe_pixels = 0
    edge_touch_frames = 0

    for r_idx, (r_name, r_count, r_ms, r_loop) in enumerate(ROW_SPEC):
        row_cells = []
        for c_idx in range(COLS):
            cell_arr = atlas_arr[
                r_idx * CELL_H : (r_idx + 1) * CELL_H,
                c_idx * CELL_W : (c_idx + 1) * CELL_W,
            ]
            stats = analyze_cell(cell_arr, np)
            total_trans_residue += stats["transparent_rgb_residue_pixels"]
            if c_idx < r_count:
                populated_cells += 1
                total_chroma_pixels += stats["opaque_chroma_key_pixels"]
                total_fringe_pixels += stats["semi_transparent_fringe_pixels"]
                if stats["edge_touch_pixels"] > 0:
                    edge_touch_frames += 1
                key = f"r{r_idx}c{c_idx}"
                frames_meta[key] = {
                    "row": r_idx,
                    "col": c_idx,
                    "state": r_name,
                    **stats,
                }
                row_cells.append(stats)
            else:
                if stats["empty"] and stats["transparent_rgb_residue_pixels"] == 0:
                    empty_unused_cells += 1
                else:
                    non_empty_unused_cells += 1

        manifest_rows[str(r_idx)] = {
            "name": r_name,
            "frames": r_count,
            "frame_interval_ms": r_ms,
            "loop": r_loop,
            "bottom_y_values": [c.get("bottom_y", 0) for c in row_cells],
            "center_x_values": [c.get("center_x", 0.0) for c in row_cells],
        }

    # Jump arc metrics (Row 4)
    idle_baseline = int(frames_meta["r0c0"].get("bottom_y", 201))
    jump_bottoms = [int(frames_meta[f"r4c{c}"].get("bottom_y", idle_baseline)) for c in range(5)]
    jump_heights = [max(1, int(frames_meta[f"r4c{c}"].get("height", 1))) for c in range(5)]
    airborne_lift = idle_baseline - min(jump_bottoms)
    landing_delta = abs(jump_bottoms[4] - idle_baseline)
    jump_height_ratio = round(max(jump_heights) / max(1, min(jump_heights)), 4)

    # Clockwise look ring metrics (Rows 9 & 10)
    look_keys = [f"r9c{c}" for c in range(8)] + [f"r10c{c}" for c in range(8)]
    look_cx = [float(frames_meta[k].get("center_x", 96.0)) for k in look_keys]
    look_w = [max(1, int(frames_meta[k].get("width", 1))) for k in look_keys]
    look_drift = round(max(look_cx) - min(look_cx), 3)
    look_w_ratio = round(max(look_w) / max(1, min(look_w)), 4)

    checks_ok = (
        populated_cells == 73
        and empty_unused_cells == 15
        and non_empty_unused_cells == 0
        and total_trans_residue == 0
        and total_chroma_pixels == 0
        and total_fringe_pixels == 0
        and edge_touch_frames == 0
        and airborne_lift >= 32
        and landing_delta <= 2
        and look_drift <= 6.0
        and look_w_ratio <= 1.18
    )

    manifest = {
        "schema": "work-pets.spritesheet-extended-manifest.v2",
        "sprite_version": 2,
        "character": slug,
        "atlas": {
            "filename": atlas_path.name,
            "width": ATLAS_W,
            "height": ATLAS_H,
            "cell_width": CELL_W,
            "cell_height": CELL_H,
            "columns": COLS,
            "rows": ROWS,
            "total_cells": COLS * ROWS,
            "populated_frames": populated_cells,
            "unused_empty_cells": empty_unused_cells,
            "sha256": header["sha256"],
            "bytes": header["bytes"],
        },
        "rows": manifest_rows,
        "look_angles": LOOK_ANGLES,
        "frames": frames_meta,
    }

    validation = {
        "schema": "work-pets.validation-extended.v2",
        "result": "ok" if checks_ok else "failed",
        "sprite_version": 2,
        "atlas_sha256": header["sha256"],
        "atlas_bytes": header["bytes"],
        "dimensions": {
            "width": ATLAS_W,
            "height": ATLAS_H,
            "cell_width": CELL_W,
            "cell_height": CELL_H,
            "columns": COLS,
            "rows": ROWS,
        },
        "cell_accounting": {
            "populated_cells": populated_cells,
            "unused_transparent_cells": empty_unused_cells,
            "non_empty_unused_cells": non_empty_unused_cells,
        },
        "transparency_and_chroma": {
            "transparent_rgb_residue_pixels": total_trans_residue,
            "opaque_chroma_key_pixels": total_chroma_pixels,
            "semi_transparent_fringe_pixels": total_fringe_pixels,
            "edge_touch_frames": edge_touch_frames,
        },
        "jump_arc": {
            "idle_baseline_y": idle_baseline,
            "bottom_y_sequence": jump_bottoms,
            "airborne_lift_pixels": airborne_lift,
            "landing_delta_pixels": landing_delta,
            "height_ratio": jump_height_ratio,
            "status": "ok" if airborne_lift >= 32 and landing_delta <= 2 else "failed",
        },
        "look_turnaround": {
            "total_angles": 16,
            "maximum_center_drift_pixels": look_drift,
            "maximum_width_ratio": look_w_ratio,
            "status": "ok" if look_drift <= 6.0 and look_w_ratio <= 1.18 else "failed",
        },
    }

    preflight = {
        "schema": "work-pets.preflight.v2",
        "status": "ok" if checks_ok else "failed",
        "sprite_version": 2,
        "character": slug,
        "atlas_sha256": header["sha256"],
        "checks": {
            "dimensions_1536x2288": True,
            "rgba_mode": True,
            "populated_frames_73": populated_cells == 73,
            "unused_cells_15_zeroed": empty_unused_cells == 15 and non_empty_unused_cells == 0,
            "zero_chroma_key_residue": total_chroma_pixels == 0 and total_fringe_pixels == 0,
            "zero_transparent_rgb_residue": total_trans_residue == 0,
            "zero_edge_clipping": edge_touch_frames == 0,
            "jump_lift_verified": airborne_lift >= 32,
            "look_ring_16_angles_continuous": look_drift <= 6.0 and look_w_ratio <= 1.18,
        },
    }

    quality = {
        "schema": "work-pets.pet-quality.v2",
        "status": "ok" if checks_ok else "failed",
        "overall_status": "pass" if checks_ok else "fail",
        "character": slug,
        "sprite_version": 2,
        "metrics": {
            "standing_baseline_y": idle_baseline,
            "horizontal_anchor_x": 96.0,
            "jump_airborne_lift_px": airborne_lift,
            "jump_height_ratio": jump_height_ratio,
            "look_max_center_drift_px": look_drift,
            "look_max_width_ratio": look_w_ratio,
            "chroma_fringe_pixels": total_fringe_pixels,
            "transparent_rgb_residue_pixels": total_trans_residue,
        },
    }

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        qa_dir = out_dir / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "spritesheet-extended-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        (qa_dir / "validation-extended.json").write_text(
            json.dumps(validation, indent=2) + "\n", encoding="utf-8"
        )
        (qa_dir / "pets-preflight.json").write_text(
            json.dumps(preflight, indent=2) + "\n", encoding="utf-8"
        )
        (qa_dir / "pet-quality.json").write_text(
            json.dumps(quality, indent=2) + "\n", encoding="utf-8"
        )

        if render_previews:
            _render_previews_and_contact(
                atlas_img=atlas_img,
                out_dir=out_dir,
                qa_dir=qa_dir,
                slug=slug,
                bundle_zip=bundle_zip,
                atlas_path=atlas_path,
                Image=Image,
                ImageDraw=ImageDraw,
            )

    return {
        "schema": "smoky-character-studio.verify.v1",
        "result": "ok" if checks_ok else "failed",
        "character": slug,
        "atlas": manifest["atlas"],
        "validation": validation,
        "preflight": preflight,
        "quality": quality,
    }


def _save_dark_gif(frames: list[Any], path: Path, duration_ms: int, Image: Any) -> None:
    gif_frames = []
    for f in frames:
        bg = Image.new("RGBA", f.size, (18, 16, 22, 255))
        bg.alpha_composite(f)
        gif_frames.append(
            bg.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        )
    gif_frames[0].save(
        path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=False,
    )


def _render_previews_and_contact(
    *,
    atlas_img: Any,
    out_dir: Path,
    qa_dir: Path,
    slug: str,
    bundle_zip: bool,
    atlas_path: Path,
    Image: Any,
    ImageDraw: Any,
) -> None:
    prev_dir = qa_dir / "previews-final"
    prev_dir.mkdir(parents=True, exist_ok=True)

    # Contact sheet
    contact = Image.new("RGBA", (ATLAS_W, ATLAS_H), (16, 14, 20, 255))
    cdraw = ImageDraw.Draw(contact)
    for r_idx, (r_name, r_count, _, _) in enumerate(ROW_SPEC):
        for c_idx in range(COLS):
            x0, y0 = c_idx * CELL_W, r_idx * CELL_H
            if c_idx < r_count:
                cdraw.rectangle(
                    [x0 + 2, y0 + 2, x0 + CELL_W - 3, y0 + CELL_H - 3],
                    fill=(26, 22, 32, 255),
                    outline=(85, 60, 45, 255),
                    width=1,
                )
                cdraw.line(
                    [(x0 + 12, y0 + 201), (x0 + CELL_W - 12, y0 + 201)],
                    fill=(120, 75, 45, 140),
                    width=1,
                )
                cell = atlas_img.crop((x0, y0, x0 + CELL_W, y0 + CELL_H))
                contact.alpha_composite(cell, (x0, y0))
                cdraw.text(
                    (x0 + 6, y0 + 5),
                    f"r{r_idx}c{c_idx} {r_name[:10]}",
                    fill=(255, 190, 110, 230),
                )
            else:
                cdraw.rectangle(
                    [x0 + 2, y0 + 2, x0 + CELL_W - 3, y0 + CELL_H - 3],
                    fill=(12, 10, 15, 255),
                    outline=(38, 34, 45, 255),
                    width=1,
                )
    contact_path = qa_dir / "contact-extended.png"
    contact.save(contact_path, "PNG", optimize=True)

    # Per-row GIFs (Rows 0..8)
    for r_idx in range(9):
        r_name, r_count, r_ms, _ = ROW_SPEC[r_idx]
        frames = [
            atlas_img.crop(
                (c * CELL_W, r_idx * CELL_H, (c + 1) * CELL_W, (r_idx + 1) * CELL_H)
            )
            for c in range(r_count)
        ]
        _save_dark_gif(frames, prev_dir / f"{r_name}.gif", r_ms, Image)

    # 16-angle look-clockwise.gif
    look_frames = [
        atlas_img.crop((c * CELL_W, 9 * CELL_H, (c + 1) * CELL_W, 10 * CELL_H))
        for c in range(8)
    ] + [
        atlas_img.crop((c * CELL_W, 10 * CELL_H, (c + 1) * CELL_W, 11 * CELL_H))
        for c in range(8)
    ]
    _save_dark_gif(look_frames, prev_dir / "look-clockwise.gif", 95, Image)

    # 3x3 all-states.gif
    board_frames = []
    for t in range(24):
        board = Image.new("RGBA", (CELL_W * 3, CELL_H * 3), (16, 14, 20, 255))
        bdraw = ImageDraw.Draw(board)
        for idx in range(9):
            r_name, r_count, _, _ = ROW_SPEC[idx]
            gx, gy = (idx % 3) * CELL_W, (idx // 3) * CELL_H
            bdraw.rectangle(
                [gx + 3, gy + 3, gx + CELL_W - 4, gy + CELL_H - 4],
                fill=(26, 22, 32, 255),
                outline=(95, 65, 45, 255),
                width=1,
            )
            c = t % r_count
            cell = atlas_img.crop(
                (c * CELL_W, idx * CELL_H, (c + 1) * CELL_W, (idx + 1) * CELL_H)
            )
            board.alpha_composite(cell, (gx, gy))
            bdraw.text((gx + 8, gy + 6), r_name.upper(), fill=(255, 195, 115, 255))
        board_frames.append(board)
    _save_dark_gif(board_frames, prev_dir / "all-states.gif", 105, Image)

    # 5x2 full-reel.gif
    reel_frames = []
    for t in range(16):
        reel = Image.new("RGBA", (CELL_W * 5, CELL_H * 2), (16, 14, 20, 255))
        rdraw = ImageDraw.Draw(reel)
        for idx in range(10):
            gx, gy = (idx % 5) * CELL_W, (idx // 5) * CELL_H
            rdraw.rectangle(
                [gx + 3, gy + 3, gx + CELL_W - 4, gy + CELL_H - 4],
                fill=(26, 22, 32, 255),
                outline=(95, 65, 45, 255),
                width=1,
            )
            if idx < 9:
                r_name, r_count, _, _ = ROW_SPEC[idx]
                c = t % r_count
                cell = atlas_img.crop(
                    (c * CELL_W, idx * CELL_H, (c + 1) * CELL_W, (idx + 1) * CELL_H)
                )
                label = r_name.upper()
            else:
                cell = look_frames[t % 16]
                label = "LOOK-360"
            reel.alpha_composite(cell, (gx, gy))
            rdraw.text((gx + 8, gy + 6), label, fill=(255, 195, 115, 255))
        reel_frames.append(reel)
    _save_dark_gif(reel_frames, prev_dir / "full-reel.gif", 100, Image)

    if bundle_zip:
        zip_path = out_dir / f"{slug}-pet-v1.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(atlas_path, "spritesheet-extended.png")
            zf.write(
                out_dir / "spritesheet-extended-manifest.json",
                "spritesheet-extended-manifest.json",
            )
            for qf in (
                "validation-extended.json",
                "pets-preflight.json",
                "pet-quality.json",
                "contact-extended.png",
            ):
                zf.write(qa_dir / qf, f"qa/{qf}")
            for gf in sorted(prev_dir.glob("*.gif")):
                zf.write(gf, f"qa/previews-final/{gf.name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify sprite_version 2 extended pet atlases (1536x2288 RGBA PNG, 73 frames) and render QA previews."
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify_parser = subparsers.add_parser(
        "verify",
        help="Validate a 1536x2288 sprite_version 2 atlas and optionally emit manifests, GIF previews, and a zip bundle.",
    )
    verify_parser.add_argument(
        "--atlas", required=True, help="Path to spritesheet-extended.png."
    )
    verify_parser.add_argument(
        "--slug", default="character", help="Character slug (e.g., clank, bobby-bones, blaze)."
    )
    verify_parser.add_argument(
        "--out-dir", help="Optional output directory for manifests, QA JSONs, previews, and zip bundle."
    )
    verify_parser.add_argument(
        "--render-previews",
        action="store_true",
        help="Render contact-extended.png and all 12 animated GIF previews.",
    )
    verify_parser.add_argument(
        "--bundle-zip",
        action="store_true",
        help="Package atlas, manifests, contact sheet, and GIFs into <slug>-pet-v1.zip (requires --out-dir and --render-previews).",
    )
    verify_parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print JSON output."
    )

    spec_parser = subparsers.add_parser(
        "spec",
        help="Print the canonical sprite_version 2 extended row and angle specification as JSON.",
    )
    spec_parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print JSON output."
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    pretty = bool(getattr(args, "pretty", False))
    try:
        if args.command == "spec":
            payload = {
                "schema": "work-pets.spec.v2",
                "sprite_version": 2,
                "atlas_width": ATLAS_W,
                "atlas_height": ATLAS_H,
                "cell_width": CELL_W,
                "cell_height": CELL_H,
                "columns": COLS,
                "rows": [
                    {
                        "row": idx,
                        "name": name,
                        "frames": count,
                        "frame_interval_ms": ms,
                        "loop": loop,
                    }
                    for idx, (name, count, ms, loop) in enumerate(ROW_SPEC)
                ],
                "populated_frames": sum(r[1] for r in ROW_SPEC),
                "unused_cells": COLS * ROWS - sum(r[1] for r in ROW_SPEC),
                "look_angles": LOOK_ANGLES,
            }
            print(json.dumps(payload, indent=2 if pretty else None, sort_keys=True))
            return 0
        if args.command == "verify":
            atlas_path = Path(args.atlas).expanduser().resolve()
            if not atlas_path.is_file():
                raise PetAtlasError(
                    "ATLAS_NOT_FOUND",
                    f"Atlas file not found: {atlas_path}",
                    exit_code=3,
                )
            out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else None
            payload = verify_atlas(
                atlas_path,
                slug=args.slug,
                out_dir=out_dir,
                render_previews=args.render_previews,
                bundle_zip=args.bundle_zip,
            )
            print(json.dumps(payload, indent=2 if pretty else None, sort_keys=True))
            return 0 if payload["result"] == "ok" else 4
        parser.error("unknown command")
    except PetAtlasError as exc:
        error = {
            "schema": "smoky-character-studio.error.v1",
            "result": "blocked",
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        }
        print(json.dumps(error, sort_keys=True), file=sys.stderr)
        return exc.exit_code
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
