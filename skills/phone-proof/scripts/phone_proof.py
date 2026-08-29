#!/usr/bin/env python3
"""Bounded Android display inventory and screenshot proof helper."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from typing import Any, Sequence
import xml.etree.ElementTree as ET


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CAPTURE_SCHEMA = "phone-proof.capture.v1"
TREE_SCHEMA = "phone-proof.tree.v1"
A11Y_DUMP_DEVICE_PATH = "/data/local/tmp/phone_proof_a11y.xml"
# Zero-width space (U+200B), zero-width non-joiner (U+200C), zero-width
# joiner (U+200D), and BOM / zero-width no-break space (U+FEFF). Gemini and
# other chat UIs emit these between list items and inside answer text.
ZERO_WIDTH_CODEPOINTS = (0x200B, 0x200C, 0x200D, 0xFEFF)
ZERO_WIDTH_CHARS = "".join(chr(codepoint) for codepoint in ZERO_WIDTH_CODEPOINTS)


class PhoneProofError(Exception):
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


def _adb_prefix(adb: str, serial: str | None) -> list[str]:
    prefix = [adb]
    if serial:
        prefix.extend(["-s", serial])
    return prefix


def _run(
    argv: Sequence[str],
    *,
    binary: bool = False,
) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            text=not binary,
        )
    except OSError as exc:
        raise PhoneProofError(
            "COMMAND_START_FAILED",
            "Could not start the configured ADB command.",
            details={"reason": str(exc)},
            exit_code=3,
        ) from exc


def _require_ok(
    process: subprocess.CompletedProcess[Any],
    *,
    operation: str,
) -> Any:
    if process.returncode == 0:
        return process.stdout
    stderr = process.stderr
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    raise PhoneProofError(
        "ADB_COMMAND_FAILED",
        f"ADB failed during {operation}.",
        details={
            "returncode": process.returncode,
            "stderr_present": bool(str(stderr).strip()),
        },
        exit_code=3,
    )


def parse_authorized_devices(output: str) -> list[dict[str, str]]:
    devices: list[dict[str, str]] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("List of devices"):
            continue
        parts = stripped.split()
        if len(parts) < 2 or parts[1] != "device":
            continue
        details: dict[str, str] = {"serial": parts[0]}
        for token in parts[2:]:
            if ":" in token:
                key, value = token.split(":", 1)
                details[key] = value
        devices.append(details)
    return devices


def parse_surfaceflinger_displays(output: str) -> list[dict[str, Any]]:
    displays: list[dict[str, Any]] = []
    pattern = re.compile(r'^Display\s+(\d+)\s+\(([^)]*)\):\s*(.*)$')
    for line in output.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        physical_id, kind, details = match.groups()
        virtual = "virtual display" in kind.lower()
        name_match = re.search(r'displayName="([^"]*)"', details)
        port_match = re.search(r"\bport=(\d+)", details)
        part_match = re.search(r"\bscreenPartStatus=([A-Z_]+)", details)
        displays.append(
            {
                "physical_display_id": physical_id,
                "kind": kind,
                "display_name": name_match.group(1) if name_match else None,
                "port": int(port_match.group(1)) if port_match else None,
                "screen_part_status": part_match.group(1) if part_match else None,
                "virtual": virtual,
            }
        )
    return displays


def parse_logical_viewports(output: str) -> dict[str, dict[str, Any]]:
    mappings: dict[str, dict[str, Any]] = {}
    for body in re.findall(r"DisplayViewport\{([^}]*)\}", output):
        physical = re.search(r"uniqueId='local:(\d+)'", body)
        logical = re.search(r"\bdisplayId=(-?\d+)", body)
        if not physical or not logical:
            continue
        active = re.search(r"\bisActive=(true|false)", body)
        mappings[physical.group(1)] = {
            "logical_display_id": int(logical.group(1)),
            "active": None if not active else active.group(1) == "true",
        }
    return mappings


def strip_zero_width(text: str) -> str:
    """Remove zero-width space/joiner/non-joiner and BOM characters."""
    for codepoint in ZERO_WIDTH_CODEPOINTS:
        text = text.replace(chr(codepoint), "")
    return text


_TEXT_ATTR_PATTERN = re.compile(r"""\btext=("[^"]*"|'[^']*')""")
_CONTENT_DESC_ATTR_PATTERN = re.compile(r"""\bcontent-desc=("[^"]*"|'[^']*')""")
_NODE_TAG_PATTERN = re.compile(r"<node\b")


def _parse_a11y_tree_xml(xml_text: str) -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    node_count = 0
    texts: list[str] = []
    for node in root.iter():
        if node.tag == "node":
            node_count += 1
        for attr in ("text", "content-desc"):
            value = node.get(attr)
            if not value:
                continue
            value = strip_zero_width(value)
            if value:
                texts.append(value)
    return {"parser": "xml", "node_count": node_count, "texts": texts}


def _parse_a11y_tree_regex(xml_text: str) -> dict[str, Any]:
    matches: list[tuple[int, str]] = []
    for pattern in (_TEXT_ATTR_PATTERN, _CONTENT_DESC_ATTR_PATTERN):
        for match in pattern.finditer(xml_text):
            matches.append((match.start(), match.group(1)))
    matches.sort(key=lambda item: item[0])
    texts: list[str] = []
    for _, quoted in matches:
        value = html.unescape(quoted[1:-1])
        value = strip_zero_width(value)
        if value:
            texts.append(value)
    node_count = len(_NODE_TAG_PATTERN.findall(xml_text))
    return {"parser": "regex-fallback", "node_count": node_count, "texts": texts}


def parse_a11y_tree(xml_text: str) -> dict[str, Any]:
    """Parse a uiautomator dump into node count and extracted text evidence.

    Primary parsing uses ``xml.etree.ElementTree``, a real XML parser that
    inherently handles both attribute-quote delimiters and entity
    unescaping. ``uiautomator`` switches a ``text`` attribute's delimiter
    from ``"`` to ``'`` whenever the value itself contains a double quote
    (for example a rendered answer containing an embedded quoted phrase), so
    a naive ``text="[^"]*"`` regex silently returns nothing for that node.
    Malformed XML falls back to a regex pass that explicitly accepts both
    delimiter forms.
    """
    try:
        return _parse_a11y_tree_xml(xml_text)
    except ET.ParseError:
        return _parse_a11y_tree_regex(xml_text)


def classify_device_serial(serial: str) -> str:
    """Classify a device serial as "emulator" or "physical" without echoing it."""
    return "emulator" if serial.startswith("emulator-") else "physical"


def _select_device(adb: str, serial: str | None) -> tuple[list[str], dict[str, Any]]:
    devices_process = _run([adb, "devices", "-l"])
    devices_output = _require_ok(devices_process, operation="device inventory")
    devices = parse_authorized_devices(devices_output)
    if serial:
        if not any(device["serial"] == serial for device in devices):
            raise PhoneProofError(
                "TARGET_DEVICE_UNAVAILABLE",
                "The requested device is not present and authorized.",
                details={"authorized_device_count": len(devices)},
                exit_code=3,
            )
        target_kind = "explicit-serial"
    else:
        if len(devices) != 1:
            raise PhoneProofError(
                "DEVICE_SELECTION_REQUIRED",
                "Exactly one authorized device is required unless --serial is supplied.",
                details={"authorized_device_count": len(devices)},
                exit_code=3,
            )
        serial = devices[0]["serial"]
        target_kind = "single-authorized-device"
    return _adb_prefix(adb, serial), {
        "authorized_device_count": len(devices),
        "target_kind": target_kind,
        "device_class": classify_device_serial(serial),
    }


def inventory(adb: str, serial: str | None) -> dict[str, Any]:
    if not shutil.which(adb) and not Path(adb).is_file():
        raise PhoneProofError(
            "ADB_NOT_FOUND",
            "The configured ADB executable was not found.",
            exit_code=3,
        )
    prefix, target = _select_device(adb, serial)
    model = str(
        _require_ok(
            _run([*prefix, "shell", "getprop", "ro.product.model"]),
            operation="model query",
        )
    ).strip()
    surface = str(
        _require_ok(
            _run([*prefix, "shell", "dumpsys", "SurfaceFlinger", "--display-id"]),
            operation="physical display inventory",
        )
    )
    display_service = str(
        _require_ok(
            _run([*prefix, "shell", "dumpsys", "display"]),
            operation="logical display inventory",
        )
    )
    parsed = parse_surfaceflinger_displays(surface)
    mappings = parse_logical_viewports(display_service)
    physical = [display for display in parsed if not display["virtual"]]
    for display in physical:
        display.update(
            mappings.get(
                display["physical_display_id"],
                {"logical_display_id": None, "active": None},
            )
        )
    return {
        "schema": "phone-proof.inventory.v1",
        "result": "ok",
        "target": {**target, "model": model},
        "physical_displays": physical,
        "virtual_displays_ignored": len(parsed) - len(physical),
    }


def select_physical_display(
    displays: list[dict[str, Any]],
    requested: str | None,
) -> dict[str, Any]:
    if requested:
        for display in displays:
            if display["physical_display_id"] == requested:
                return display
        raise PhoneProofError(
            "UNKNOWN_PHYSICAL_DISPLAY",
            "The requested physical display ID is not in the current inventory.",
            details={
                "available_physical_display_ids": [
                    display["physical_display_id"] for display in displays
                ]
            },
            exit_code=3,
        )
    if len(displays) != 1:
        raise PhoneProofError(
            "DISPLAY_SELECTION_REQUIRED",
            "Exactly one physical display is required unless --physical-display-id is supplied.",
            details={
                "available_physical_display_ids": [
                    display["physical_display_id"] for display in displays
                ]
            },
            exit_code=3,
        )
    return displays[0]


def inspect_png(data: bytes) -> dict[str, Any]:
    if not data.startswith(PNG_SIGNATURE):
        raise PhoneProofError(
            "CAPTURE_NOT_PNG",
            "Capture bytes do not begin with a PNG signature; a display warning may have polluted stdout.",
            exit_code=3,
        )
    if len(data) < 33 or data[12:16] != b"IHDR":
        raise PhoneProofError(
            "CAPTURE_MALFORMED_PNG",
            "Capture is missing a valid PNG IHDR chunk.",
            exit_code=3,
        )
    width, height = struct.unpack(">II", data[16:24])
    if width <= 0 or height <= 0 or b"IEND" not in data[-32:]:
        raise PhoneProofError(
            "CAPTURE_MALFORMED_PNG",
            "Capture has invalid dimensions or no terminal IEND chunk.",
            exit_code=3,
        )
    return {
        "width": width,
        "height": height,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "png_valid": True,
    }


def _atomic_write(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _emit(payload: dict[str, Any], *, pretty: bool) -> None:
    print(json.dumps(payload, indent=2 if pretty else None, sort_keys=True))


def capture(args: argparse.Namespace) -> int:
    current = inventory(args.adb, args.serial)
    selected = select_physical_display(
        current["physical_displays"],
        args.physical_display_id,
    )
    prefix, _ = _select_device(args.adb, args.serial)
    process = _run(
        [
            *prefix,
            "exec-out",
            "screencap",
            "-p",
            "-d",
            selected["physical_display_id"],
        ],
        binary=True,
    )
    data = bytes(_require_ok(process, operation="physical display capture"))
    inspected = inspect_png(data)
    suspicious = inspected["bytes"] < args.min_bytes
    output = Path(args.output).expanduser().resolve()
    _atomic_write(output, data)
    payload = {
        "schema": CAPTURE_SCHEMA,
        "result": "suspicious" if suspicious else "ok",
        "target": current["target"],
        "capture": {
            **inspected,
            "physical_display_id": selected["physical_display_id"],
            "logical_display_id": selected.get("logical_display_id"),
            "display_name": selected.get("display_name"),
            "active": selected.get("active"),
            "output": str(output),
            "suspicious_low_bytes": suspicious,
            "minimum_expected_bytes": args.min_bytes,
        },
    }
    if args.manifest:
        manifest = Path(args.manifest).expanduser().resolve()
        _atomic_write(
            manifest,
            (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
    _emit(payload, pretty=args.pretty)
    return 0 if not suspicious or args.allow_suspicious else 4


def verify(args: argparse.Namespace) -> int:
    path = Path(args.image).expanduser().resolve()
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PhoneProofError(
            "IMAGE_READ_FAILED",
            "Could not read the requested image.",
            details={"reason": str(exc)},
            exit_code=3,
        ) from exc
    inspected = inspect_png(data)
    suspicious = inspected["bytes"] < args.min_bytes
    payload = {
        "schema": "phone-proof.verify.v1",
        "result": "suspicious" if suspicious else "ok",
        "image": {
            **inspected,
            "path": str(path),
            "suspicious_low_bytes": suspicious,
            "minimum_expected_bytes": args.min_bytes,
        },
    }
    _emit(payload, pretty=args.pretty)
    return 0 if not suspicious or args.allow_suspicious else 4


def tree(args: argparse.Namespace) -> int:
    current = inventory(args.adb, args.serial)
    prefix, _ = _select_device(args.adb, args.serial)
    _require_ok(
        _run([*prefix, "shell", "uiautomator", "dump", A11Y_DUMP_DEVICE_PATH]),
        operation="accessibility tree dump",
    )
    cat_process = _run(
        [*prefix, "exec-out", "cat", A11Y_DUMP_DEVICE_PATH],
        binary=True,
    )
    raw = bytes(_require_ok(cat_process, operation="accessibility tree read"))
    rm_process = _run([*prefix, "shell", "rm", "-f", A11Y_DUMP_DEVICE_PATH])
    device_temp_removed = rm_process.returncode == 0
    xml_text = raw.decode("utf-8", "replace")
    if not raw or ("<?xml" not in xml_text and "<hierarchy" not in xml_text):
        raise PhoneProofError(
            "A11Y_DUMP_EMPTY",
            "The accessibility tree dump was empty or missing expected XML content.",
            details={"bytes": len(raw), "device_temp_removed": device_temp_removed},
            exit_code=3,
        )
    parsed = parse_a11y_tree(xml_text)
    empty = parsed["node_count"] == 0
    output_path: Path | None = None
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        _atomic_write(output_path, raw)
    payload = {
        "schema": TREE_SCHEMA,
        "result": "empty" if empty else "ok",
        "target": current["target"],
        "tree": {
            "node_count": parsed["node_count"],
            "text_node_count": len(parsed["texts"]),
            "texts": parsed["texts"],
            "parser": parsed["parser"],
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "output": str(output_path) if output_path else None,
            "device_temp_removed": device_temp_removed,
        },
    }
    if args.manifest:
        manifest = Path(args.manifest).expanduser().resolve()
        _atomic_write(
            manifest,
            (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
    _emit(payload, pretty=args.pretty)
    return 0 if not empty or args.allow_empty else 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory Android displays and capture structurally valid screenshot proof."
    )
    parser.add_argument("--adb", default="adb", help="ADB executable name or path.")
    parser.add_argument(
        "--serial",
        help="Exact target serial when more than one authorized device is present; never emitted.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("inventory", help="List physical displays without exposing serials.")

    capture_parser = subparsers.add_parser(
        "capture",
        help="Capture one physical display and validate PNG structure.",
    )
    capture_parser.add_argument("--physical-display-id")
    capture_parser.add_argument("--output", required=True)
    capture_parser.add_argument("--manifest")
    capture_parser.add_argument("--min-bytes", type=int, default=20_000)
    capture_parser.add_argument("--allow-suspicious", action="store_true")

    verify_parser = subparsers.add_parser(
        "verify",
        help="Validate an existing PNG and flag unusually small captures.",
    )
    verify_parser.add_argument("--image", required=True)
    verify_parser.add_argument("--min-bytes", type=int, default=20_000)
    verify_parser.add_argument("--allow-suspicious", action="store_true")

    tree_parser = subparsers.add_parser(
        "tree",
        help="Dump the accessibility tree and extract delimiter-safe text evidence.",
    )
    tree_parser.add_argument("--output")
    tree_parser.add_argument("--manifest")
    tree_parser.add_argument("--allow-empty", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "min_bytes", 0) < 0:
        parser.error("--min-bytes must be non-negative")
    try:
        if args.command == "inventory":
            _emit(inventory(args.adb, args.serial), pretty=args.pretty)
            return 0
        if args.command == "capture":
            return capture(args)
        if args.command == "verify":
            return verify(args)
        if args.command == "tree":
            return tree(args)
        parser.error("unknown command")
    except PhoneProofError as exc:
        error = {
            "schema": "phone-proof.error.v1",
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
