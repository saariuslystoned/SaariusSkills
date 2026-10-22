#!/usr/bin/env python3
"""Deterministic headless Chrome verification runner for emdash-motion-studio.

Verifies Mode A (3D Cutaway / Colorfigures), Mode B (Multiplane Occlusion + Pigment Drift),
and Mode C (Choreographed Timeline Stage) animations across:
  - Camera angles (?free=1&yaw=...) and See-through + Labels (?xr=1&labels=1)
  - Deterministic timeline scrubs (?t=0.0..1.0) and 3D Exploded Multiplane (?explode=1)
  - Button/action sequences (?press=...)
  - Mobile viewport (390x844)
  - DOM & SVG geometry health (<html data-errors>, NaN attributes, non-empty SVG primitives)

Outputs retina PNG screenshots, proof-report.json, and PROOF.md in --out-dir.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD_PY = HERE / "build.py"

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
    "chromium-browser",
)


def find_chrome(override: str | None = None) -> str:
    if override:
        if Path(override).is_file() or shutil.which(override):
            return override
        sys.exit(f"error: specified --chrome-bin not found: {override}")
    for c in CHROME_CANDIDATES:
        if Path(c).is_file():
            return c
        w = shutil.which(c)
        if w:
            return w
    sys.exit("error: Google Chrome / Chromium binary not found")


def detect_mode(html_text: str) -> str:
    if "mountFigure(" in html_text:
        return "mode-a"
    if "mountMultiplane(" in html_text or 'src="multiplane.js"' in html_text:
        return "mode-b"
    if "mountChoreo(" in html_text or 'src="choreo.js"' in html_text:
        return "mode-c"
    if "mountDitherShader(" in html_text or "mountReceipt(" in html_text:
        return "mode-c"
    return "mode-a"


def extract_meta_probes(html_text: str) -> list[dict]:
    m = re.search(r'<meta\s+name=["\']motion-probes["\']\s+content=[\'"]([^\'"]+)[\'"]', html_text, re.I)
    if not m:
        return []
    out: list[dict] = []
    for item in m.group(1).split(";"):
        item = item.strip()
        if not item or ":" not in item:
            continue
        name, rest = item.split(":", 1)
        size = "960,820"
        if "@" in rest:
            rest, size = rest.rsplit("@", 1)
        out.append({
            "name": name.strip(),
            "query": rest.strip(),
            "size": size.strip(),
            "budget": 2200,
            "dump_dom": True,
        })
    return out


def default_probes(mode: str, full_angles: bool = False, press_seq: str | None = None) -> list[dict]:
    probes: list[dict] = []
    if mode == "mode-a":
        if full_angles:
            angles = [
                ("yaw_45", "free=1&yaw=45"),
                ("yaw_110", "free=1&yaw=110"),
                ("yaw_170", "free=1&yaw=170"),
                ("yaw_230", "free=1&yaw=230"),
                ("yaw_300", "free=1&yaw=300"),
                ("yaw_20_pitch_62", "free=1&yaw=20&pitch=62"),
                ("yaw_200_pitch_70", "free=1&yaw=200&pitch=70"),
            ]
        else:
            angles = [
                ("yaw_45_closed", "free=1&yaw=45"),
                ("yaw_225_back", "free=1&yaw=225"),
            ]
        for name, q in angles:
            probes.append({"name": name, "query": q, "size": "900,800", "budget": 1800, "dump_dom": False})
        probes.append(
            {
                "name": "cutaway_xr_labels",
                "query": "free=1&yaw=45&xr=1&labels=1",
                "size": "900,800",
                "budget": 2000,
                "dump_dom": True,
            }
        )
        probes.append(
            {
                "name": "scrub_t050_xr",
                "query": "free=1&yaw=45&xr=1&labels=1&t=0.5",
                "size": "900,800",
                "budget": 2000,
                "dump_dom": True,
            }
        )
        probes.append(
            {
                "name": "mobile_390x844",
                "query": "free=1&yaw=45&xr=1&labels=1&t=0.5&vw=390",
                "size": "390,844",
                "budget": 2000,
                "dump_dom": False,
            }
        )
    elif mode == "mode-b":
        for label, t_val in (("scrub_t012", "0.12"), ("scrub_t045", "0.45"), ("scrub_t088", "0.88")):
            probes.append(
                {
                    "name": label,
                    "query": f"t={t_val}",
                    "size": "1100,760",
                    "budget": 1800,
                    "dump_dom": label == "scrub_t045",
                }
            )
        probes.append(
            {
                "name": "exploded_multiplane",
                "query": "t=0.45&explode=1",
                "size": "1100,760",
                "budget": 1800,
                "dump_dom": True,
            }
        )
        probes.append(
            {
                "name": "mobile_390x844",
                "query": "t=0.45&vw=390",
                "size": "390,844",
                "budget": 1800,
                "dump_dom": False,
            }
        )
    else:  # mode-c
        for label, t_val in (("cue1_t012", "0.12"), ("cue2_t040", "0.40"), ("cue3_t068", "0.68"), ("cue4_t092", "0.92")):
            probes.append(
                {
                    "name": label,
                    "query": f"t={t_val}",
                    "size": "1100,760",
                    "budget": 1800,
                    "dump_dom": label == "cue3_t068",
                }
            )
        probes.append(
            {
                "name": "mobile_390x844",
                "query": "t=0.68&vw=390",
                "size": "390,844",
                "budget": 1800,
                "dump_dom": False,
            }
        )

    if press_seq:
        probes.append(
            {
                "name": "press_sequence",
                "query": f"free=1&xr=1&labels=1&press={press_seq}",
                "size": "900,800",
                "budget": 3200,
                "dump_dom": True,
            }
        )
    return probes


def audit_dom(dom_html: str) -> dict:
    errors_match = re.search(r'<html[^>]*\bdata-errors="([^"]*)"', dom_html, re.IGNORECASE)
    data_errors = errors_match.group(1).strip() if errors_match else ""

    # Extract all <svg ...>...</svg> blocks to check for NaN in geometry/attributes
    svg_blocks = re.findall(r"<svg\b.*?</svg>", dom_html, flags=re.DOTALL | re.IGNORECASE)
    svg_joined = "\n".join(svg_blocks)
    nan_hits = re.findall(r'(?:d|transform|x|y|x1|y1|x2|y2|cx|cy|r|rx|ry|width|height|viewBox)="[^"]*\bNaN\b[^"]*"', svg_joined)

    # Count rendered vector primitives inside SVG
    primitive_count = len(re.findall(r"<(?:path|rect|circle|ellipse|line|polygon|polyline|text)\b", svg_joined, re.IGNORECASE))
    has_fig = bool(re.search(r'<svg[^>]*\bid="fig"', dom_html, re.IGNORECASE))

    passed = (not data_errors) and (len(nan_hits) == 0) and has_fig and (primitive_count > 5)
    return {
        "passed": passed,
        "data_errors": data_errors,
        "nan_attribute_hits": nan_hits[:10],
        "svg_primitive_count": primitive_count,
        "has_fig_svg": has_fig,
    }


def run_chrome_probe(chrome_bin: str, url: str, out_png: Path, size: str, budget: int, dump_dom: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="emdash-motion-chrome-") as prof_dir:
        cmd_shot = [
            chrome_bin,
            "--headless=new",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu-sandbox",
            f"--user-data-dir={prof_dir}",
            "--force-device-scale-factor=2",
            f"--window-size={size}",
            f"--virtual-time-budget={budget}",
            f"--screenshot={out_png}",
            url,
        ]
        res_shot = subprocess.run(cmd_shot, capture_output=True, text=True, timeout=45)
        shot_ok = res_shot.returncode == 0 and out_png.is_file() and out_png.stat().st_size > 1000

    dom_audit = None
    if dump_dom:
        with tempfile.TemporaryDirectory(prefix="emdash-motion-dom-") as prof_dir2:
            cmd_dom = [
                chrome_bin,
                "--headless=new",
                "--hide-scrollbars",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-gpu-sandbox",
                f"--user-data-dir={prof_dir2}",
                f"--window-size={size}",
                f"--virtual-time-budget={budget}",
                "--dump-dom",
                url,
            ]
            res_dom = subprocess.run(cmd_dom, capture_output=True, text=True, timeout=45)
            dom_audit = audit_dom(res_dom.stdout)

    passed = shot_ok and (dom_audit["passed"] if dom_audit else True)
    return {
        "screenshot": str(out_png),
        "screenshot_bytes": out_png.stat().st_size if out_png.is_file() else 0,
        "screenshot_ok": shot_ok,
        "dom_audit": dom_audit,
        "passed": passed,
    }


def verify_target(src_file: Path, out_dir: Path, chrome_bin: str, mode_override: str | None, full_angles: bool, press_seq: str | None) -> dict:
    raw = src_file.read_text(encoding="utf-8")
    mode = mode_override or detect_mode(raw)
    stem = src_file.stem
    target_dir = out_dir / stem
    target_dir.mkdir(parents=True, exist_ok=True)

    # Build standalone HTML if not already inlined
    built_html = target_dir / f"{stem}.built.html"
    if re.search(
        r'<script\s+src=["\'][^"\']*(?:core|multiplane|choreo|tactile-audio|ephemera|dither|viewport-pool|surface-micro|three\.min)\.js["\']',
        raw,
        re.I,
    ):
        subprocess.run([sys.executable, str(BUILD_PY), str(src_file), str(built_html)], check=True)
    else:
        shutil.copyfile(src_file, built_html)

    built_text = built_html.read_text(encoding="utf-8")
    three_vendor = (HERE.parent / "assets" / "vendor" / "three.min.js").resolve()
    if re.search(r'<script\s+src=["\'][^"\']*three\.min\.js["\']', built_text, re.I) and three_vendor.is_file():
        patched = re.sub(
            r'<script\s+src=["\'][^"\']*three\.min\.js["\']\s*>\s*</script>',
            f'<script src="file://{three_vendor}"></script>',
            built_text,
            count=1,
        )
        built_html.write_text(patched, encoding="utf-8")

    meta_probes = extract_meta_probes(raw)
    if meta_probes:
        probes = meta_probes
        if press_seq:
            probes.append({
                "name": "press_sequence",
                "query": f"free=1&xr=1&labels=1&press={press_seq}",
                "size": "960,820",
                "budget": 3200,
                "dump_dom": True,
            })
    else:
        probes = default_probes(mode, full_angles=full_angles, press_seq=press_seq)
    results = []
    all_passed = True

    for p in probes:
        png_path = target_dir / f"shot-{p['name']}.png"
        url = f"file://{built_html.resolve()}?{p['query']}"
        res = run_chrome_probe(chrome_bin, url, png_path, p["size"], p["budget"], p["dump_dom"])
        res["name"] = p["name"]
        res["query"] = p["query"]
        res["size"] = p["size"]
        results.append(res)
        if not res["passed"]:
            all_passed = False

    return {
        "source": str(src_file),
        "built_html": str(built_html),
        "mode": mode,
        "passed": all_passed,
        "probes": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify emdash-motion-studio animations in headless Chrome.")
    parser.add_argument("inputs", nargs="+", help="One or more .html animation files to verify")
    parser.add_argument("--out-dir", default=".grilltrack/proof/motion", help="Directory for screenshots and proof report")
    parser.add_argument("--mode", choices=("mode-a", "mode-b", "mode-c"), default=None, help="Override auto-detected mode")
    parser.add_argument("--full-angles", action="store_true", help="Run all 7 Colorfigures camera angles for Mode A")
    parser.add_argument("--press", default=None, help="Optional ?press= button sequence (e.g. 'Push the lever@200')")
    parser.add_argument("--chrome-bin", default=None, help="Path to Chrome/Chromium binary")
    args = parser.parse_args()

    chrome_bin = find_chrome(args.chrome_bin)
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    reports = []
    overall_passed = True
    for inp in args.inputs:
        src_path = Path(inp).resolve()
        if not src_path.is_file():
            sys.exit(f"error: input file not found: {src_path}")
        rep = verify_target(src_path, out_dir, chrome_bin, args.mode, args.full_angles, args.press)
        reports.append(rep)
        if not rep["passed"]:
            overall_passed = False

    summary = {
        "overall_passed": overall_passed,
        "chrome_bin": chrome_bin,
        "targets": reports,
    }
    json_path = out_dir / "proof-report.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Write human-readable PROOF.md
    md_lines = [
        "# EmDash Motion Studio — Headless Chrome Verification Proof",
        "",
        f"- **Overall Result:** `{'PASS' if overall_passed else 'FAIL'}`",
        f"- **Targets Verified:** {len(reports)}",
        "",
    ]
    for r in reports:
        md_lines.append(f"## `{Path(r['source']).name}` (`{r['mode']}`) — `{'PASS' if r['passed'] else 'FAIL'}`")
        md_lines.append("")
        md_lines.append("| Probe | Query | Viewport | Screenshot | DOM Audit |")
        md_lines.append("| --- | --- | --- | --- | --- |")
        for p in r["probes"]:
            dom_info = "—"
            if p["dom_audit"]:
                da = p["dom_audit"]
                dom_info = f"errors=`{da['data_errors'] or 'none'}`, NaN={len(da['nan_attribute_hits'])}, svg_nodes={da['svg_primitive_count']}"
            shot_rel = Path(p["screenshot"]).relative_to(out_dir)
            md_lines.append(
                f"| `{p['name']}` | `?{p['query']}` | `{p['size']}` | `{shot_rel}` ({p['screenshot_bytes']} B) | {dom_info} |"
            )
        md_lines.append("")

    md_path = out_dir / "PROOF.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(json.dumps({"overall_passed": overall_passed, "report": str(json_path), "proof_md": str(md_path)}))
    if not overall_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
