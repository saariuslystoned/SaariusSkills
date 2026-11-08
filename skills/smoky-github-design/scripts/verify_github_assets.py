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
import html
import json
import re
import struct
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

GITHUB_ONE_MIB = 1_048_576
GITHUB_SETTINGS_RASTER_FORMATS = frozenset({"png", "jpeg", "gif"})
EPHEMERAL_GITHUB_HOSTS = frozenset(
    {
        "private-user-images.githubusercontent.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
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
    if w <= 0 or h <= 0:
        errors.append(
            f"{role} ({info['path']}) must have positive dimensions, got {w}x{h}"
        )
        return errors
    ratio = w / h
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


def _normalize_ref_label(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip()).casefold()


def _peel_blockquotes(line: str, max_depth: int | None = None) -> tuple[int, str]:
    """Peel CommonMark leading '>' markers, returning (bq_depth, remainder_expanded)."""
    expanded = line.expandtabs(4)
    depth = 0
    while max_depth is None or depth < max_depth:
        stripped = expanded.lstrip(" ")
        lead = len(expanded) - len(stripped)
        if lead <= 3 and stripped.startswith(">"):
            depth += 1
            after = stripped[1:]
            if after.startswith(" "):
                after = after[1:]
            expanded = after
        else:
            break
    return depth, expanded


def _strip_code_and_comments(markdown_text: str) -> str:
    out_lines: list[str] = []
    fence_char = ""
    fence_len = 0
    fence_bq = 0
    fence_list_depth = 0
    in_indented_code = False
    in_html_block = False
    in_html_comment = False
    comment_bq = 0
    comment_list_depth = 0
    raw_html_close: str | None = None
    raw_html_bq = 0
    raw_html_list_depth = 0
    in_paragraph = False
    prev_bq = 0
    list_stack: list[int] = []

    for line in markdown_text.splitlines(keepends=True):
        nl = "\n" if line.endswith("\n") else ""
        bq_depth, body = _peel_blockquotes(
            line, max_depth=fence_bq if fence_char else None
        )
        body_no_eol = body.rstrip("\r\n")
        stripped = body_no_eol.lstrip(" ")
        col_indent = len(body_no_eol) - len(stripped)
        is_blank = stripped == ""

        if bq_depth != prev_bq:
            if fence_char and bq_depth < fence_bq:
                fence_char = ""
                fence_len = 0
            if in_html_comment and bq_depth < comment_bq:
                in_html_comment = False
            if raw_html_close is not None and bq_depth < raw_html_bq:
                raw_html_close = None
            in_indented_code = False
            in_html_block = False
            if bq_depth > prev_bq or is_blank:
                in_paragraph = False
            list_stack.clear()
            prev_bq = bq_depth

        if not is_blank:
            while list_stack and col_indent < list_stack[-1]:
                list_stack.pop()
            if fence_char and len(list_stack) < fence_list_depth:
                fence_char = ""
                fence_len = 0
            if in_html_comment and len(list_stack) < comment_list_depth:
                in_html_comment = False
            if raw_html_close is not None and len(list_stack) < raw_html_list_depth:
                raw_html_close = None

        if fence_char:
            if not is_blank:
                base_indent = list_stack[-1] if list_stack else 0
                rel_indent = col_indent - base_indent
                m_close = (
                    re.match(rf"^({re.escape(fence_char)}{{{fence_len},}})[ \t]*$", stripped)
                    if 0 <= rel_indent <= 3
                    else None
                )
                if m_close and bq_depth == fence_bq:
                    fence_char = ""
                    fence_len = 0
            out_lines.append(nl)
            continue

        if in_html_comment:
            if "-->" in body_no_eol:
                idx_end = body_no_eol.find("-->") + 3
                out_lines.append(body_no_eol[idx_end:] + nl)
                in_html_comment = False
            else:
                out_lines.append(nl)
            continue

        if raw_html_close is not None:
            if re.search(rf"</{raw_html_close}\s*>", body_no_eol, flags=re.IGNORECASE):
                raw_html_close = None
            out_lines.append(nl)
            continue

        if is_blank:
            in_paragraph = False
            in_html_block = False
            out_lines.append(nl)
            continue

        base_indent = list_stack[-1] if list_stack else 0
        rel_indent = col_indent - base_indent

        if in_indented_code:
            if rel_indent >= 4:
                out_lines.append(nl)
                continue
            in_indented_code = False

        # Peel CommonMark list markers on this line (supports nested lists & list-item fences)
        empty_list_line = False
        while rel_indent <= 3 and not in_html_block:
            if re.match(
                r"^(?:-[ \t]*){3,}$|^(?:\*[ \t]*){3,}$|^(?:_[ \t]*){3,}$",
                stripped.strip(),
            ):
                break
            m_list = re.match(r"^([-*+]|\d{1,9}[.)])(?:([ \t]+)(.*)|()())$", stripped)
            if not m_list:
                break
            marker = m_list.group(1)
            spaces = m_list.group(2)
            rest = m_list.group(3)
            # In CommonMark, an empty list item or ordered list != 1 cannot interrupt a paragraph
            if in_paragraph and (
                rest == "" or (marker[0].isdigit() and marker[:-1] != "1")
            ):
                break
            marker_len = len(marker)
            in_paragraph = False
            in_indented_code = False
            if rest == "":
                list_stack.append(col_indent + marker_len + 1)
                empty_list_line = True
                break
            space_count = len(spaces)
            if space_count >= 5:
                content_base = col_indent + marker_len + 1
                raw_after_col = col_indent + marker_len + space_count
            else:
                content_base = col_indent + marker_len + space_count
                raw_after_col = content_base
            list_stack.append(content_base)
            base_indent = content_base
            stripped = rest.lstrip(" ")
            col_indent = raw_after_col + (len(rest) - len(stripped))
            rel_indent = col_indent - base_indent
            body_no_eol = (" " * col_indent) + stripped

        if empty_list_line:
            out_lines.append(nl)
            continue

        if rel_indent <= 3 and not in_html_block:
            m_fence = re.match(r"^(`{3,}|~{3,})(.*)$", stripped)
            if m_fence and ("`" not in m_fence.group(2) if m_fence.group(1)[0] == "`" else True):
                fence_char = m_fence.group(1)[0]
                fence_len = len(m_fence.group(1))
                fence_bq = bq_depth
                fence_list_depth = len(list_stack)
                in_paragraph = False
                in_html_block = False
                out_lines.append(nl)
                continue

        if rel_indent >= 4 and not in_paragraph and not in_html_block:
            in_indented_code = True
            out_lines.append(nl)
            continue

        if in_html_block:
            out_lines.append(body_no_eol + nl)
            continue

        if rel_indent <= 3:
            if stripped.startswith("<!--"):
                in_paragraph = False
                cleaned_line = re.sub(r"<!--.*?-->", "", body_no_eol)
                if "<!--" in cleaned_line:
                    in_html_comment = True
                    comment_bq = bq_depth
                    comment_list_depth = len(list_stack)
                    out_lines.append(cleaned_line[: cleaned_line.find("<!--")] + nl)
                else:
                    out_lines.append(cleaned_line + nl)
                continue

            m_raw = re.match(
                r"^<(pre|script|style|textarea)(?:[\s>]|$)",
                stripped,
                flags=re.IGNORECASE,
            )
            if m_raw:
                tag_nm = m_raw.group(1).lower()
                in_paragraph = False
                if not re.search(rf"</{tag_nm}\s*>", stripped, flags=re.IGNORECASE):
                    raw_html_close = tag_nm
                    raw_html_bq = bq_depth
                    raw_html_list_depth = len(list_stack)
                out_lines.append(nl)
                continue

            if re.match(r"^</?[A-Za-z][A-Za-z0-9-]*(?:[\s/>]|$)|^<![A-Za-z]|^<\?", stripped):
                in_html_block = True
                in_paragraph = False
                out_lines.append(body_no_eol + nl)
                continue

            if re.match(r"^#{1,6}(?:[ \t]+|$)", stripped) or re.match(
                r"^(?:-[ \t]*){3,}$|^(?:\*[ \t]*){3,}$|^(?:_[ \t]*){3,}$",
                stripped.strip(),
            ):
                in_paragraph = False
                out_lines.append(body_no_eol + nl)
                continue

        in_paragraph = True
        out_lines.append(body_no_eol + nl)

    without_blocks = "".join(out_lines)

    # Blank CommonMark inline code spans within each paragraph block before HTML parsing
    blocks = re.split(r"(\r?\n[ \t]*\r?\n)", without_blocks)
    cleaned_blocks = [
        re.sub(
            r"(`+)(?!`)([\s\S]*?)(?<!`)\1(?!`)",
            lambda m: re.sub(r"[^\r\n]", " ", m.group(0)),
            blk,
        )
        for blk in blocks
    ]
    without_inline_code = "".join(cleaned_blocks)
    without_comments = re.sub(r"<!--[\s\S]*?-->", "", without_inline_code)
    return re.sub(
        r"<(code|pre)\b[^>]*>[\s\S]*?</\1>",
        lambda m: re.sub(r"[^\r\n]", " ", m.group(0)),
        without_comments,
        flags=re.IGNORECASE,
    )


def _find_balanced_bracket(text: str, open_idx: int) -> int:
    depth = 0
    idx = open_idx
    while idx < len(text):
        ch = text[idx]
        if ch == "\\":
            idx += 2
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return idx
        idx += 1
    return -1


def extract_readme_image_urls(rendered_text: str) -> list[str]:
    urls: list[str] = []

    # 1. HTML media tags (<img>, <source>, <video poster>, <object data>, <embed>, <image>)
    for tag_match in re.finditer(
        r"<(?:img|source|video|object|embed|image)\b(?:[^>'\"/]|/[^>]|\"[^\"]*\"|'[^']*')*/?>",
        rendered_text,
        flags=re.IGNORECASE,
    ):
        tag = tag_match.group(0)
        for attr_match in re.finditer(
            r"""\b(src|srcset|poster|data|href|xlink:href)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>"']+))""",
            tag,
            flags=re.IGNORECASE,
        ):
            attr_name = attr_match.group(1).lower()
            raw_val = html.unescape(
                attr_match.group(2)
                if attr_match.group(2) is not None
                else (
                    attr_match.group(3)
                    if attr_match.group(3) is not None
                    else (attr_match.group(4) or "")
                )
            ).strip()
            if not raw_val:
                continue
            if attr_name == "srcset":
                for candidate in raw_val.split(","):
                    parts = candidate.strip().split()
                    if parts:
                        urls.append(parts[0])
            else:
                urls.append(raw_val)

    # 2. GFM link reference definitions: [label]: url or [label]: <url>
    no_inline_code = rendered_text
    ref_defs: dict[str, str] = {}
    for ref_match in re.finditer(
        r"^[ ]{0,3}\[([^\^\]]+)\]:[ \t]*(?:\n[ \t]*)?(?:<([^>\n]+)>|([^\s\n]+))",
        no_inline_code,
        flags=re.MULTILINE,
    ):
        key = _normalize_ref_label(ref_match.group(1))
        dest = (ref_match.group(2) or ref_match.group(3) or "").strip()
        if key and dest and key not in ref_defs:
            ref_defs[key] = html.unescape(dest)

    # 3. GFM inline ![alt](dest), full ![alt][ref], collapsed ![alt][], and shortcut ![alt]
    idx = 0
    length = len(no_inline_code)
    while idx < length - 1:
        if no_inline_code[idx] == "\\":
            idx += 2
            continue
        if no_inline_code[idx : idx + 2] == "![":
            close_alt = _find_balanced_bracket(no_inline_code, idx + 1)
            if close_alt != -1:
                alt_text = no_inline_code[idx + 2 : close_alt]
                nxt = close_alt + 1
                if nxt < length and no_inline_code[nxt] == "(":
                    p = nxt + 1
                    while p < length and no_inline_code[p] in " \t\r\n":
                        p += 1
                    if p < length and no_inline_code[p] == "<":
                        end_angle = no_inline_code.find(">", p + 1)
                        if end_angle != -1:
                            urls.append(html.unescape(no_inline_code[p + 1 : end_angle].strip()))
                            close_paren = no_inline_code.find(")", end_angle + 1)
                            idx = (close_paren + 1) if close_paren != -1 else (end_angle + 1)
                            continue
                    elif p < length:
                        paren_depth = 0
                        start_dest = p
                        while p < length:
                            ch = no_inline_code[p]
                            if ch == "\\":
                                p += 2
                                continue
                            if ch == "(":
                                paren_depth += 1
                            elif ch == ")":
                                if paren_depth == 0:
                                    break
                                paren_depth -= 1
                            elif ch in " \t\r\n" and paren_depth == 0:
                                break
                            p += 1
                        dest = no_inline_code[start_dest:p].strip()
                        close_paren = p
                        while close_paren < length and no_inline_code[close_paren] != ")":
                            close_paren += 1
                        if close_paren < length and dest:
                            urls.append(html.unescape(dest))
                            idx = close_paren + 1
                            continue
                elif nxt < length and no_inline_code[nxt] == "[":
                    close_ref = _find_balanced_bracket(no_inline_code, nxt)
                    if close_ref != -1:
                        raw_label = no_inline_code[nxt + 1 : close_ref] or alt_text
                        resolved = ref_defs.get(_normalize_ref_label(raw_label))
                        if resolved:
                            urls.append(resolved)
                        idx = close_ref + 1
                        continue
                else:
                    resolved = ref_defs.get(_normalize_ref_label(alt_text))
                    if resolved:
                        urls.append(resolved)
                        idx = close_alt + 1
                        continue
        idx += 1

    return urls


def classify_github_asset_repo(url: str) -> tuple[str | None, str | None, bool]:
    """Return ((owner/repo) or None, surface_kind or None, is_ephemeral_signed_host)."""
    candidate = "https:" + url if url.startswith("//") else url
    parsed = urllib.parse.urlsplit(candidate)
    host = urllib.parse.unquote(parsed.hostname or "").lower()
    if not host:
        return None, None, False
    if host in EPHEMERAL_GITHUB_HOSTS:
        return None, "ephemeral", True
    segments = [
        urllib.parse.unquote(seg)
        for seg in parsed.path.split("/")
        if seg
    ]
    if host in {"github.com", "www.github.com"} and len(segments) >= 3:
        owner, repo, surface = segments[0], segments[1], segments[2].lower()
        if owner.lower() != "user-attachments" and surface in {
            "releases",
            "raw",
            "blob",
            "assets",
            "archive",
        }:
            return f"{owner}/{repo}", surface, False
    elif host in {"raw.githubusercontent.com", "codeload.github.com"} and len(segments) >= 2:
        return f"{segments[0]}/{segments[1]}", "raw", False
    elif host == "media.githubusercontent.com" and len(segments) >= 3 and segments[0].lower() == "media":
        return f"{segments[1]}/{segments[2]}", "media", False
    return None, None, False


def inspect_readme(
    readme_path: Path,
    repo_visibility: str,
    private_hosts_or_repos: list[str],
    allowed_public_shelves: list[str] | None = None,
) -> dict[str, Any]:
    raw_text = readme_path.read_text(encoding="utf-8")
    text = _strip_code_and_comments(raw_text)
    errors: list[str] = []
    warnings: list[str] = []
    allowed_shelves = {
        shelf.strip().strip("/").lower()
        for shelf in (allowed_public_shelves or [])
        if shelf and shelf.strip()
    }

    has_picture = bool(
        re.search(r"<picture\b", text, flags=re.IGNORECASE)
        and re.search(r"</picture>", text, flags=re.IGNORECASE)
    )
    has_dark = "prefers-color-scheme: dark" in text.lower()
    has_light = "prefers-color-scheme: light" in text.lower()
    if has_picture and not (has_dark and has_light):
        warnings.append(
            "<picture> present without both prefers-color-scheme: dark and light <source> tags"
        )

    for img_match in re.finditer(
        r"<img\b(?:[^>'\"/]|/[^>]|\"[^\"]*\"|'[^']*')*/?>",
        text,
        flags=re.IGNORECASE,
    ):
        img_tag = img_match.group(0)
        alt_match = re.search(
            r"""\balt\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>"'=]+))""",
            img_tag,
            flags=re.IGNORECASE,
        )
        alt_val = html.unescape(
            (
                alt_match.group(1)
                if alt_match and alt_match.group(1) is not None
                else (
                    alt_match.group(2)
                    if alt_match and alt_match.group(2) is not None
                    else (alt_match.group(3) if alt_match else "")
                )
            )
            or ""
        ).strip()
        if not alt_val:
            errors.append(f"<img> tag missing non-empty alt attribute: {img_tag[:80]}")

    urls = extract_readme_image_urls(text)

    for raw_url in urls:
        url = raw_url.strip()
        unquoted_url = urllib.parse.unquote(url)
        if url.startswith(("file://", "/Users/", "/home/")):
            errors.append(f"README references machine-local path: {url}")
        gh_repo_slug, gh_surface, is_ephemeral = classify_github_asset_repo(url)
        if is_ephemeral:
            errors.append(f"README references expiring signed GitHub asset URL: {url}")
        if repo_visibility == "PUBLIC":
            matched_forbidden = False
            for priv in private_hosts_or_repos:
                if priv and (
                    priv.lower() in url.lower() or priv.lower() in unquoted_url.lower()
                ):
                    errors.append(
                        f"PUBLIC README references private asset shelf '{priv}': {url}"
                    )
                    matched_forbidden = True
            if gh_repo_slug and not matched_forbidden:
                if gh_repo_slug.lower() not in allowed_shelves:
                    errors.append(
                        f"PUBLIC README references unverified GitHub asset shelf '{gh_repo_slug}' "
                        f"(verify unauthenticated HTTP 200 and pass --allow-public-shelf {gh_repo_slug}, "
                        f"or use repo-local .github/assets/): {url}"
                    )
        elif (
            repo_visibility == "PRIVATE"
            and gh_repo_slug
            and gh_surface == "releases"
            and gh_repo_slug.lower() not in allowed_shelves
        ):
            errors.append(
                f"PRIVATE README embeds GitHub release URL '{gh_repo_slug}' that fails under "
                f"GitHub's unauthenticated Camo image proxy (use repo-local .github/assets/ for "
                f"embedded README images, or pass --allow-public-shelf {gh_repo_slug} if the shelf is public): {url}"
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
