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

    def test_classify_device_serial_distinguishes_emulator_and_physical(
        self,
    ) -> None:
        self.assertEqual(
            phone_proof.classify_device_serial("emulator-5554"),
            "emulator",
        )
        self.assertEqual(
            phone_proof.classify_device_serial("R58N90ABCDE"),
            "physical",
        )

    def test_parse_authorized_devices_reports_emulator_row(self) -> None:
        output = "\n".join(
            [
                "List of devices attached",
                "emulator-5554   device product:sdk_gphone64_x86_64 "
                "model:sdk_gphone64_x86_64 device:emu64x transport_id:1",
            ]
        )
        devices = phone_proof.parse_authorized_devices(output)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["serial"], "emulator-5554")
        self.assertEqual(devices[0]["model"], "sdk_gphone64_x86_64")
        self.assertEqual(
            phone_proof.classify_device_serial(devices[0]["serial"]),
            "emulator",
        )

    def test_strip_zero_width_removes_zero_width_space(self) -> None:
        polluted = "line2" + chr(0x200B) + "tail"
        self.assertEqual(phone_proof.strip_zero_width(polluted), "line2tail")

    def test_parse_a11y_tree_extracts_double_quote_delimited_text(self) -> None:
        xml_text = (
            '<hierarchy rotation="0">'
            '<node index="0" text="Hello" class="android.widget.TextView" '
            'bounds="[0,0][10,10]"/>'
            "</hierarchy>"
        )
        result = phone_proof.parse_a11y_tree(xml_text)
        self.assertEqual(result["parser"], "xml")
        self.assertEqual(result["node_count"], 1)
        self.assertEqual(result["texts"], ["Hello"])

    def test_parse_a11y_tree_preserves_inner_double_quotes_in_single_quote_delimiter(
        self,
    ) -> None:
        # uiautomator switches the text delimiter from " to ' when the
        # value itself contains a double quote (the Gemini "Worker 1"
        # shape); a real XML parser handles both delimiters natively.
        xml_text = (
            "<hierarchy rotation=\"0\">"
            "<node index=\"0\" text='He said \"Worker 1\"' "
            'class="android.widget.TextView" bounds="[0,0][10,10]"/>'
            "</hierarchy>"
        )
        result = phone_proof.parse_a11y_tree(xml_text)
        self.assertEqual(result["parser"], "xml")
        self.assertIn('He said "Worker 1"', result["texts"])

    def test_parse_a11y_tree_collects_content_desc(self) -> None:
        xml_text = (
            '<hierarchy rotation="0">'
            '<node index="0" text="" content-desc="Send message" '
            'class="android.widget.ImageButton" bounds="[0,0][10,10]"/>'
            "</hierarchy>"
        )
        result = phone_proof.parse_a11y_tree(xml_text)
        self.assertEqual(result["texts"], ["Send message"])

    def test_parse_a11y_tree_strips_zero_width_and_counts_nodes(self) -> None:
        polluted = "Worker 1" + chr(0x200B) + " ready"
        xml_text = (
            '<hierarchy rotation="0">'
            f'<node index="0" text="{polluted}" bounds="[0,0][10,10]">'
            '<node index="1" text="child" bounds="[0,0][5,5]"/>'
            "</node>"
            "</hierarchy>"
        )
        result = phone_proof.parse_a11y_tree(xml_text)
        self.assertEqual(result["node_count"], 2)
        self.assertIn("Worker 1 ready", result["texts"])
        self.assertNotIn(chr(0x200B), "".join(result["texts"]))

    def test_parse_a11y_tree_empty_hierarchy_reports_zero_nodes(self) -> None:
        result = phone_proof.parse_a11y_tree('<hierarchy rotation="0"/>')
        self.assertEqual(result["parser"], "xml")
        self.assertEqual(result["node_count"], 0)
        self.assertEqual(result["texts"], [])

    def test_parse_a11y_tree_malformed_xml_falls_back_to_regex(self) -> None:
        # Stray "<" inside an unclosed tag breaks well-formedness, forcing
        # the regex fallback. It must still extract both delimiter forms
        # and unescape "&#10;", which is common in chat UIs.
        xml_text = (
            '<hierarchy><node text="line1&#10;line2" bounds="[0,0][1,1]" '
            "<node text='single delim' bounds=\"[0,0][1,1]\"/></hierarchy>"
        )
        result = phone_proof.parse_a11y_tree(xml_text)
        self.assertEqual(result["parser"], "regex-fallback")
        self.assertEqual(result["node_count"], 2)
        self.assertIn("line1\nline2", result["texts"])
        self.assertIn("single delim", result["texts"])

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

    def test_inventory_reports_device_class_for_single_emulator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            fake_adb = temp / "adb"
            fake_adb.write_text(
                """#!/usr/bin/env python3
import sys

args = sys.argv[1:]
if args[:2] == ["-s", "emulator-5554"]:
    args = args[2:]
if args == ["devices", "-l"]:
    print("List of devices attached")
    print("emulator-5554 device product:sdk_gphone64_x86_64 model:sdk_gphone64_x86_64 device:emu64x transport_id:1")
elif args == ["shell", "getprop", "ro.product.model"]:
    print("sdk_gphone64_x86_64")
elif args == ["shell", "dumpsys", "SurfaceFlinger", "--display-id"]:
    print('Display 4619827000000000000 (HWC display 0): port=0 displayName="test"')
elif args == ["shell", "dumpsys", "display"]:
    print("DisplayViewport{type=INTERNAL, valid=true, isActive=true, displayId=0, uniqueId='local:4619827000000000000'}")
else:
    print(f"unexpected args: {args}", file=sys.stderr)
    raise SystemExit(9)
""",
                encoding="utf-8",
            )
            fake_adb.chmod(fake_adb.stat().st_mode | stat.S_IXUSR)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--adb", str(fake_adb), "inventory"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["target"]["device_class"], "emulator")
            self.assertNotIn("emulator-5554", result.stdout)

    def test_tree_cli_extracts_delimiter_safe_text_and_omits_serial(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            fake_adb = temp / "adb"
            fake_adb.write_text(
                """#!/usr/bin/env python3
import sys

DUMP_XML = '''<hierarchy rotation="0"><node index="0" text='He said "Worker 1" is ready' class="android.widget.TextView" bounds="[0,0][10,10]"/></hierarchy>'''

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
elif args == ["shell", "uiautomator", "dump", "/data/local/tmp/phone_proof_a11y.xml"]:
    print("UI hierarchy dumped to: /data/local/tmp/phone_proof_a11y.xml")
elif args == ["exec-out", "cat", "/data/local/tmp/phone_proof_a11y.xml"]:
    sys.stdout.buffer.write(DUMP_XML.encode("utf-8"))
elif args == ["shell", "rm", "-f", "/data/local/tmp/phone_proof_a11y.xml"]:
    pass
else:
    print(f"unexpected args: {args}", file=sys.stderr)
    raise SystemExit(9)
""",
                encoding="utf-8",
            )
            fake_adb.chmod(fake_adb.stat().st_mode | stat.S_IXUSR)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--adb",
                    str(fake_adb),
                    "--serial",
                    "PRIVATE-SERIAL",
                    "tree",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["schema"], "phone-proof.tree.v1")
            self.assertEqual(payload["result"], "ok")
            self.assertEqual(payload["tree"]["parser"], "xml")
            self.assertEqual(payload["tree"]["node_count"], 1)
            self.assertIn('He said "Worker 1" is ready', payload["tree"]["texts"])
            self.assertTrue(payload["tree"]["device_temp_removed"])
            self.assertNotIn("PRIVATE-SERIAL", result.stdout)

    def test_tree_cli_empty_hierarchy_fails_closed_without_allow_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            fake_adb = temp / "adb"
            fake_adb.write_text(
                """#!/usr/bin/env python3
import sys

DUMP_XML = '<hierarchy rotation="0"/>'

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
elif args == ["shell", "uiautomator", "dump", "/data/local/tmp/phone_proof_a11y.xml"]:
    print("UI hierarchy dumped to: /data/local/tmp/phone_proof_a11y.xml")
elif args == ["exec-out", "cat", "/data/local/tmp/phone_proof_a11y.xml"]:
    sys.stdout.buffer.write(DUMP_XML.encode("utf-8"))
elif args == ["shell", "rm", "-f", "/data/local/tmp/phone_proof_a11y.xml"]:
    pass
else:
    print(f"unexpected args: {args}", file=sys.stderr)
    raise SystemExit(9)
""",
                encoding="utf-8",
            )
            fake_adb.chmod(fake_adb.stat().st_mode | stat.S_IXUSR)
            base_argv = [
                sys.executable,
                str(SCRIPT),
                "--adb",
                str(fake_adb),
                "--serial",
                "PRIVATE-SERIAL",
                "tree",
            ]
            blocked = subprocess.run(
                base_argv, check=False, capture_output=True, text=True
            )
            self.assertEqual(blocked.returncode, 4, blocked.stderr)
            payload = json.loads(blocked.stdout)
            self.assertEqual(payload["result"], "empty")
            self.assertEqual(payload["tree"]["node_count"], 0)

            allowed = subprocess.run(
                [*base_argv, "--allow-empty"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            self.assertEqual(json.loads(allowed.stdout)["result"], "empty")

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
