from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "skills" / "smoky-ci-performance" / "scripts" / "capture.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("ci_capture", HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError("capture helper could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPER_MODULE = load_helper()


class CaptureHelperTests(unittest.TestCase):
    def run_capture(self, out: Path, command: list[str]) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, str(HELPER), "--out", str(out), "--", *command],
            check=False,
            capture_output=True,
        )

    def test_help_warns_without_running_a_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "not-created"
            result = subprocess.run(
                [sys.executable, str(HELPER), "--help"],
                check=False,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, b"")
            self.assertIn(b"--out", result.stdout)
            self.assertIn(b"secrets", result.stdout)
            self.assertFalse(missing.exists())

    def test_success_and_exit_seven_split_streams(self) -> None:
        cases = (
            (0, "raise SystemExit(0)"),
            (7, "raise SystemExit(7)"),
        )
        script = (
            "import sys\n"
            "sys.stdout.write('OUT\\n')\n"
            "sys.stdout.flush()\n"
            "sys.stderr.write('ERR\\n')\n"
            "sys.stderr.flush()\n"
            "sys.stdout.write('STDIN:' + sys.stdin.read())\n"
            "sys.stdout.flush()\n"
            "{exit_line}\n"
        )
        for expected, exit_line in cases:
            with self.subTest(expected=expected):
                with tempfile.TemporaryDirectory() as directory:
                    out = Path(directory) / "cap"
                    if expected == 7:
                        out.mkdir()
                    result = self.run_capture(
                        out,
                        [sys.executable, "-c", script.format(exit_line=exit_line)],
                    )
                    self.assertEqual(result.returncode, expected)
                    self.assertEqual((out / "stdout.txt").read_bytes(), b"OUT\nSTDIN:")
                    self.assertEqual((out / "stderr.txt").read_bytes(), b"ERR\n")
                    self.assertTrue(result.stdout.startswith(b"{"))
                    self.assertNotIn(b"ERR\n", result.stderr)
                    record = json.loads((out / "capture.json").read_text(encoding="utf-8"))
                    self.assertEqual(result.stdout, (out / "capture.json").read_bytes())
                    self.assertEqual(record["classification"], "complete")
                    self.assertEqual(record["exit"]["raw"], expected)
                    self.assertEqual(record["exit"]["normalized"], expected)
                    self.assertIsNone(record["exit"]["signal"])
                    self.assertIsInstance(record["wall_seconds"], float)
                    self.assertEqual(record["cost"], "unknown")
                    again = self.run_capture(out, [sys.executable, "-c", "raise SystemExit(0)"])
                    self.assertEqual(again.returncode, 2)
                    self.assertIn(b"classification=incomplete", again.stderr)
                    self.assertEqual((out / "stdout.txt").read_bytes(), b"OUT\nSTDIN:")

    def test_literal_argv_is_not_interpolated(self) -> None:
        dollar = "$HOME"
        quoted = 'say "hi"'
        spaced = "a b"
        script = "import sys\nprint(sys.argv[1])\nprint(sys.argv[2])\nprint(sys.argv[3])\n"
        command = [sys.executable, "-c", script, dollar, quoted, spaced]
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "cap"
            result = self.run_capture(out, command)
            self.assertEqual(result.returncode, 0)
            record = json.loads((out / "capture.json").read_text(encoding="utf-8"))
            self.assertEqual(record["argv"], command)
            self.assertEqual(
                (out / "stdout.txt").read_text(encoding="utf-8"),
                f"{dollar}\n{quoted}\n{spaced}\n",
            )

    def test_existing_output_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            occupied = root / "occupied"
            occupied.mkdir()
            kept = occupied / "keep.txt"
            kept.write_text("keep", encoding="utf-8")
            refused = self.run_capture(occupied, [sys.executable, "-c", "print('no')"])
            self.assertEqual(refused.returncode, 2)
            self.assertIn(b"classification=incomplete", refused.stderr)
            self.assertEqual(refused.stdout, b"")
            self.assertEqual(kept.read_text(encoding="utf-8"), "keep")
            self.assertFalse((occupied / "capture.json").exists())

            blocked = root / "blocked.txt"
            blocked.write_text("file", encoding="utf-8")
            file_result = self.run_capture(blocked, [sys.executable, "-c", "print('no')"])
            self.assertEqual(file_result.returncode, 2)
            self.assertEqual(blocked.read_text(encoding="utf-8"), "file")
            self.assertFalse((root / "capture.json").exists())

    def test_missing_executable_has_no_fake_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "cap"
            result = self.run_capture(out, ["/no/such/capture-command"])
            self.assertEqual(result.returncode, 127)
            record = json.loads(result.stdout.decode("utf-8"))
            self.assertEqual(record, json.loads((out / "capture.json").read_text(encoding="utf-8")))
            self.assertEqual(record["classification"], "failure")
            self.assertEqual(record["error"]["code"], "executable-not-found")
            self.assertIsNone(record["exit"]["raw"])
            self.assertIsNone(record["exit"]["normalized"])
            self.assertIsNone(record["wall_seconds"])
            self.assertFalse(record["metrics_supported"])
            for key in ("user_seconds", "system_seconds", "max_rss", "max_rss_unit"):
                self.assertIsNone(record["resources"][key])
            self.assertEqual(record["cost"], "unknown")
            summary = (out / "summary.md").read_text(encoding="utf-8").strip()
            self.assertIn("max_rss=null", summary)
            self.assertNotIn("max_rss=0", summary)
            self.assertNotIn("classification=complete", summary)

    def test_receipt_json_matches_summary_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "cap"
            result = self.run_capture(out, [sys.executable, "-c", "print('ok')"])
            self.assertEqual(result.returncode, 0)
            text = (out / "capture.json").read_text(encoding="utf-8")
            self.assertNotRegex(text, r"\b(True|False|None)\b")
            record = json.loads(text)
            self.assertIs(record["metrics_supported"], True)
            self.assertEqual(record["resources"]["aggregation"], "waited-children")
            if sys.platform == "darwin":
                self.assertEqual(record["resources"]["max_rss_unit"], "bytes")
            elif sys.platform.startswith("linux"):
                self.assertEqual(record["resources"]["max_rss_unit"], "KiB")
            self.assertIsInstance(record["resources"]["max_rss"], int)
            parsed = {}
            for token in (out / "summary.md").read_text(encoding="utf-8").split():
                key, raw = token.split("=", 1)
                parsed[key] = json.loads(raw)
            self.assertEqual(parsed["classification"], record["classification"])
            self.assertEqual(parsed["raw_exit"], record["exit"]["raw"])
            self.assertEqual(parsed["normalized_exit"], record["exit"]["normalized"])
            self.assertEqual(parsed["signal"], record["exit"]["signal"])
            self.assertEqual(parsed["wall_seconds"], record["wall_seconds"])
            self.assertEqual(parsed["user_seconds"], record["resources"]["user_seconds"])
            self.assertEqual(parsed["system_seconds"], record["resources"]["system_seconds"])
            self.assertEqual(parsed["max_rss"], record["resources"]["max_rss"])
            self.assertEqual(parsed["max_rss_unit"], record["resources"]["max_rss_unit"])
            self.assertEqual(parsed["cost"], "unknown")

    def test_signal_meaning_is_preserved(self) -> None:
        script = "import os, signal\nos.kill(os.getpid(), signal.SIGTERM)\n"
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "cap"
            result = self.run_capture(out, [sys.executable, "-c", script])
            record = json.loads((out / "capture.json").read_text(encoding="utf-8"))
            self.assertEqual(record["classification"], "complete")
            self.assertEqual(record["exit"]["raw"], -15)
            self.assertEqual(record["exit"]["signal"], 15)
            self.assertEqual(record["exit"]["normalized"], 143)
            self.assertEqual(result.returncode, 143)

    def test_unsupported_metric_is_null_not_zero(self) -> None:
        sample = type("Sample", (), {"ru_utime": 0.0, "ru_stime": 1.5, "ru_maxrss": 0})()
        unknown = HELPER_MODULE.interpret_resources(sample, "freebsd")
        self.assertEqual(unknown["user_seconds"], 0.0)
        self.assertEqual(unknown["system_seconds"], 1.5)
        self.assertIsNone(unknown["max_rss"])
        self.assertIsNone(unknown["max_rss_unit"])
        self.assertEqual(unknown["aggregation"], "waited-children")
        missing = HELPER_MODULE.interpret_resources(None, "darwin")
        self.assertIsNone(missing["user_seconds"])
        self.assertIsNone(missing["system_seconds"])
        self.assertIsNone(missing["max_rss"])
        self.assertIsNone(missing["max_rss_unit"])
        self.assertIsNone(missing["aggregation"])
        measured = HELPER_MODULE.interpret_resources(sample, "linux")
        self.assertEqual(measured["max_rss"], 0)
        self.assertEqual(measured["max_rss_unit"], "KiB")

    def test_helper_is_executable(self) -> None:
        mode = HELPER.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)
