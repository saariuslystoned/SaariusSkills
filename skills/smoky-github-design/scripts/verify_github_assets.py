#!/usr/bin/env python3
"""Deterministic stdlib verifier for GitHub front-door assets and README markup.

Validates:
- Image dimensions & aspect ratios for PNG, JPEG, WebP, GIF, and SVG without
  requiring third-party packages.
- GitHub's strict < 1 MiB (1,048,576 bytes) upload limit on avatars and
  1280x640 social preview images.
- README `<picture>` dark/light `prefers-color-scheme` sources, `alt` text, and
  public-repository asset URL safety (flagging private-only or local-filesystem
  image links).
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

GITHUB_ONE_MIB = 1_048_576
GITHUB_SETTINGS_RASTER_FORMATS = frozenset({"png", "jpeg", "gif"})
GITHUB_EXTERNAL_ASSET_RE = re.compile(
    r"^https?://(?:"
    r"github\.com/(?P<gh_owner>[^/\s\"']+)/(?P<gh_repo>[^/\s\"']+)/(?:releases/download|raw|blob)/"
    r"|raw\.githubusercontent\.com/(?P<raw_owner>[^/\s\"']+)/(?P<raw_repo>[^/\s\"']+)/"
    r")",
    flags=re.IGNORECASE,
)


def parse_png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("Invalid PNG header")
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def parse_gif_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 10 or data[:6] not in (b"GIF87a", b"GIF89a"):
        raise ValueError("Invalid GIF header")
    width, height = struct.unpack("<HH", data[6:10])
    return int(width), int(height)


def parse_webp_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("Invalid WebP header")
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        w = 1 + int.from_bytes(data[24:27], "little")
        h = 1 + int.from_bytes(data[27:30], "little")
        return w, h
    if chunk == b"VP8 " and len(data) >= 30:
        w, h = struct.unpack("<HH", data[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        w = (bits & 0x3FFF) + 1
        h = ((bits >> 14) & 0x3FFF) + 1
        return w, h
    raise ValueError(f"Unsupported WebP chunk: {chunk!r}")


def parse_jpeg_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise ValueError("Invalid JPEG header")
    idx = 2
    sof_markers = {
        0xC0, 0xC1, 0xC2, 0xC3,
        0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB,
        0xCD, 0xCE, 0xCF,
    }
    while idx + 4 <= len(data):
        while idx < len(data) and data[idx] != 0xFF:
            idx += 1
        while idx < len(data) and data[idx] == 0xFF:
            idx += 1
        if idx >= len(data):
            break
        marker = data[idx]
        idx += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        if idx + 2 > len(data):
            break
        seg_len = struct.unpack(">H", data[idx : idx + 2])[0]
        if seg_len < 2 or idx + seg_len > len(data):
            break
        if marker in sof_markers and seg_len >= 7:
            height, width = struct.unpack(">HH", data[idx + 3 : idx + 7])
            return int(width), int(height)
        idx += seg_len
    raise ValueError("Could not locate JPEG SOF dimensions")


def parse_svg_dimensions(data: bytes) -> tuple[int, int]:
    root = ET.fromstring(data.decode("utf-8"))
    view_box = root.attrib.get("viewBox")
    if view_box:
        parts = [float(p) for p in re.split(r"[\s,]+", view_box.strip()) if p]
        if len(parts) == 4:
            return int(round(parts[2])), int(round(parts[3]))
    w_raw = re.sub(r"[^0-9.]", "", root.attrib.get("width", ""))
    h_raw = re.sub(r"[^0-9.]", "", root.attrib.get("height", ""))
    if w_raw and h_raw:
        return int(round(float(w_raw))), int(round(float(h_raw)))
    raise ValueError("SVG missing numeric viewBox or width/height attributes")


def inspect_image(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        fmt = "png"
        width, height = parse_png_dimensions(data)
    elif data[:2] == b"\xff\xd8":
        fmt = "jpeg"
        width, height = parse_jpeg_dimensions(data)
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        fmt = "webp"
        width, height = parse_webp_dimensions(data)
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        fmt = "gif"
        width, height = parse_gif_dimensions(data)
    elif suffix == ".svg" or b"<svg" in data[:512]:
        fmt = "svg"
        width, height = parse_svg_dimensions(data)
    else:
        raise ValueError(f"Unrecognized image format for {path}")
    return {
        "path": str(path),
        "format": fmt,
        "bytes": len(data),
        "width": width,
        "height": height,
        "aspect_ratio": round(width / height, 4) if height else 0.0,
    }


def check_role(
    info: dict[str, Any],
    role: str,
    max_bytes: int = GITHUB_ONE_MIB,
) -> list[str]:
    errors: list[str] = []
    if info["bytes"] > max_bytes:
        errors.append(
            f"{role} ({info['path']}) exceeds byte cap: {info['bytes']} > {max_bytes}"
        )
    w, h = info["width"], info["height"]
    ratio = w / h if h else 0.0
    if role == "social":
        if info["format"] not in GITHUB_SETTINGS_RASTER_FORMATS:
            errors.append(
                f"social preview ({info['path']}) must be PNG, JPEG, or GIF for GitHub upload, got {info['format']}"
            )
        if (w, h) != (1280, 640):
            errors.append(
                f"social preview ({info['path']}) must be exact 1280x640, got {w}x{h}"
            )
    elif role == "avatar":
        if info["format"] not in GITHUB_SETTINGS_RASTER_FORMATS:
            errors.append(
                f"avatar ({info['path']}) must be PNG, JPEG, or GIF for GitHub upload, got {info['format']}"
            )
        if w != h or w < 256:
            errors.append(
                f"avatar ({info['path']}) must be 1:1 square >= 256x256, got {w}x{h}"
            )
    elif role == "banner":
        if not (1.65 <= ratio <= 3.6):
            errors.append(
                f"banner ({info['path']}) aspect ratio {ratio:.2f} outside 16:9..3.5:1 range ({w}x{h})"
            )
    elif role == "mark":
        if w != h:
            errors.append(f"mark ({info['path']}) must have 1:1 aspect ratio, got {w}x{h}")
    return errors


def inspect_readme(
    readme_path: Path,
    repo_visibility: str,
    private_hosts_or_repos: list[str],
    allowed_public_shelves: list[str] | None = None,
) -> dict[str, Any]:
    text = readme_path.read_text(encoding="utf-8")
    errors: list[str] = []
    warnings: list[str] = []
    allowed_shelves = {
        shelf.strip().strip("/").lower()
        for shelf in (allowed_public_shelves or [])
        if shelf and shelf.strip()
    }

    has_picture = "<picture>" in text and "</picture>" in text
    has_dark = "prefers-color-scheme: dark" in text
    has_light = "prefers-color-scheme: light" in text
    if has_picture and not (has_dark and has_light):
        warnings.append(
            "<picture> present without both prefers-color-scheme: dark and light <source> tags"
        )

    for img_tag in re.findall(r"<img\b[^>]*>", text, flags=re.IGNORECASE):
        if not re.search(r'\balt\s*=\s*["\'][^"\']+["\']', img_tag, flags=re.IGNORECASE):
            errors.append(f"<img> tag missing non-empty alt attribute: {img_tag[:80]}")

    urls = re.findall(r'(?:src|srcset)\s*=\s*["\']([^"\']+)["\']', text)
    urls += re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)

    for raw_url in urls:
        url = raw_url.strip().split()[0]
        if url.startswith(("file://", "/Users/", "/home/")):
            errors.append(f"README references machine-local path: {url}")
        if "private-user-images.githubusercontent.com" in url.lower():
            errors.append(f"README references expiring signed GitHub asset URL: {url}")
        if repo_visibility == "PUBLIC":
            matched_forbidden = False
            for priv in private_hosts_or_repos:
                if priv and priv.lower() in url.lower():
                    errors.append(
                        f"PUBLIC README references private asset shelf '{priv}': {url}"
                    )
                    matched_forbidden = True
            gh_match = GITHUB_EXTERNAL_ASSET_RE.match(url)
            if gh_match and not matched_forbidden:
                owner = gh_match.group("gh_owner") or gh_match.group("raw_owner")
                repo = gh_match.group("gh_repo") or gh_match.group("raw_repo")
                slug = f"{owner}/{repo}".lower()
                if slug not in allowed_shelves:
                    errors.append(
                        f"PUBLIC README references unverified GitHub asset shelf '{owner}/{repo}' "
                        f"(verify unauthenticated HTTP 200 and pass --allow-public-shelf {owner}/{repo}, "
                        f"or use repo-local .github/assets/): {url}"
                    )

    return {
        "path": str(readme_path),
        "has_picture": has_picture,
        "has_dark_source": has_dark,
        "has_light_source": has_light,
        "image_ref_count": len(urls),
        "errors": errors,
        "warnings": warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify GitHub repository/org banners, social previews, marks, and README markup."
    )
    parser.add_argument("--banner", action="append", default=[], help="16:9 or wide README banner file")
    parser.add_argument("--social", action="append", default=[], help="1280x640 social preview file")
    parser.add_argument("--avatar", action="append", default=[], help="1:1 square avatar/badge file")
    parser.add_argument("--mark", action="append", default=[], help="1:1 SVG/PNG mark file")
    parser.add_argument("--readme", type=Path, help="README.md or profile/README.md to audit")
    parser.add_argument(
        "--repo-visibility",
        choices=("PUBLIC", "PRIVATE"),
        default="PUBLIC",
        help="Target repository GitHub visibility (default: PUBLIC)",
    )
    parser.add_argument(
        "--forbid-in-public",
        action="append",
        default=[],
        help="Substring (e.g. private asset repo slug or internal host) forbidden in PUBLIC README image URLs",
    )
    parser.add_argument(
        "--allow-public-shelf",
        action="append",
        default=[],
        help="GitHub <owner/repo> shelf explicitly verified as PUBLIC (unauthenticated HTTP 200) for PUBLIC README release/raw image URLs",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assets: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    for role, paths in (
        ("banner", args.banner),
        ("social", args.social),
        ("avatar", args.avatar),
        ("mark", args.mark),
    ):
        for raw in paths:
            p = Path(raw)
            if not p.is_file():
                errors.append(f"Missing {role} file: {p}")
                continue
            try:
                info = inspect_image(p)
                info["role"] = role
                assets.append(info)
                errors.extend(check_role(info, role))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{role} ({p}): {exc}")

    readme_report: dict[str, Any] | None = None
    if args.readme is not None:
        if not args.readme.is_file():
            errors.append(f"Missing README file: {args.readme}")
        else:
            readme_report = inspect_readme(
                args.readme,
                args.repo_visibility,
                args.forbid_in_public,
                args.allow_public_shelf,
            )
            errors.extend(readme_report["errors"])
            warnings.extend(readme_report["warnings"])

    payload = {
        "schema": "smoky-github-design.verify.v1",
        "ok": len(errors) == 0,
        "assets": assets,
        "readme": readme_report,
        "warnings": warnings,
        "errors": errors,
    }
    print(json.dumps(payload, indent=2 if args.pretty else None))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
