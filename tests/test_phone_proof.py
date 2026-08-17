from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "phone-proof" / "scripts" / "phone_proof.py"
SPEC = importlib.util.spec_from_file_location("phone_proof", SCRIPT)
assert SPEC and SPEC.loader
phone_proof = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phone_proof)


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind)
    crc = zlib.crc32(payload, crc)
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", crc & 0xFFFFFFFF)
    )


def valid_png(width: int = 1080, height: int = 2400) -> bytes:
    raw = b"\x00" + (b"\x00\x00\x00" * width)
    compressed = zlib.compress(raw * height)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        phone_proof.PNG_SIGNATURE
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", compressed)
        + png_chunk(b"IEND", b"")
    )


class PhoneProofTests(unittest.TestCase):
    def test_inventory_excludes_virtual_stdout_display(self) -> None:
        output = "\n".join(
            [
                'Display 4619827000000000000 (HWC display 0): port=0 screenPartStatus=ORIGINAL displayName="inner"',
                'Display 11529215000000000000 (Virtual display): displayName="stdout" uniqueId="virtual:shell"',
            ]
        )
        displays = phone_proof.parse_surfaceflinger_displays(output)
        physical = [display for display in displays if not display["virtual"]]
        self.assertEqual(
            [display["physical_display_id"] for display in physical],
            ["4619827000000000000"],
        )
        self.assertEqual(physical[0]["display_name"], "inner")

    def test_multiple_physical_displays_require_selection(self) -> None:
        displays = [
            {"physical_display_id": "4619827000000000000"},
            {"physical_display_id": "4619827000000000001"},
        ]
        with self.assertRaises(phone_proof.PhoneProofError) as raised:
            phone_proof.select_physical_display(displays, None)
        self.assertEqual(raised.exception.code, "DISPLAY_SELECTION_REQUIRED")

    def test_physical_and_logical_ids_remain_distinct(self) -> None:
        output = (
            "mViewports=[DisplayViewport{type=INTERNAL, valid=true, "
            "isActive=true, displayId=0, "
            "uniqueId='local:4619827000000000000'}]"
        )
        mappings = phone_proof.parse_logical_viewports(output)
        self.assertEqual(
            mappings["4619827000000000000"]["logical_display_id"],
            0,
        )
        self.assertTrue(mappings["4619827000000000000"]["active"])

    def test_warning_prefixed_png_is_rejected(self) -> None:
        polluted = b"Multiple displays were found\n" + valid_png()
        with self.assertRaises(phone_proof.PhoneProofError) as raised:
            phone_proof.inspect_png(polluted)
        self.assertEqual(raised.exception.code, "CAPTURE_NOT_PNG")

    def test_valid_png_reports_dimensions_and_digest(self) -> None:
        data = valid_png(12, 34)
        report = phone_proof.inspect_png(data)
        self.assertEqual(report["width"], 12)
        self.assertEqual(report["height"], 34)
        self.assertEqual(len(report["sha256"]), 64)

    def test_capture_cli_does_not_emit_explicit_serial(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            png_path = temp / "fixture.png"
            png_path.write_bytes(valid_png())
            fake_adb = temp / "adb"
            fake_adb.write_text(
                """#!/usr/bin/env python3
import pathlib
import sys

args = sys.argv[1:]
if args[:2] == ["-s", "PRIVATE-SERIAL"]:
    args = args[2:]
if args == ["devices", "-l"]:
    print("List of devices attached")
    print("PRIVATE-SERIAL device product:test model:Pixel_Test device:test")
elif args == ["shell", "getprop", "ro.product.model"]:
    print("Pixel Test")
elif args == ["shell", "dumpsys", "SurfaceFlinger", "--display-id"]:
    print('Display 4619827000000000000 (HWC display 0): port=0 displayName="test"')
elif args == ["shell", "dumpsys", "display"]:
    print("DisplayViewport{type=INTERNAL, valid=true, isActive=true, displayId=0, uniqueId='local:4619827000000000000'}")
elif args == ["exec-out", "screencap", "-p", "-d", "4619827000000000000"]:
    sys.stdout.buffer.write(pathlib.Path(sys.argv[0]).with_name("fixture.png").read_bytes())
else:
    print(f"unexpected args: {args}", file=sys.stderr)
    raise SystemExit(9)
""",
                encoding="utf-8",
            )
            fake_adb.chmod(fake_adb.stat().st_mode | stat.S_IXUSR)
            output = temp / "capture.png"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--adb",
                    str(fake_adb),
                    "--serial",
                    "PRIVATE-SERIAL",
                    "capture",
                    "--output",
                    str(output),
                    "--min-bytes",
                    "0",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["result"], "ok")
            self.assertNotIn("PRIVATE-SERIAL", result.stdout)
            self.assertTrue(output.is_file())

    def test_adb_failure_does_not_echo_stderr(self) -> None:
        process = subprocess.CompletedProcess(
            ["adb"],
            1,
            stdout="",
            stderr="failure for PRIVATE-SERIAL",
        )
        with self.assertRaises(phone_proof.PhoneProofError) as raised:
            phone_proof._require_ok(process, operation="test")
        self.assertNotIn("PRIVATE-SERIAL", json.dumps(raised.exception.details))
        self.assertTrue(raised.exception.details["stderr_present"])


if __name__ == "__main__":
    unittest.main()
