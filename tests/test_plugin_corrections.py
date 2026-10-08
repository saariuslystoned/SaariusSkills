#!/usr/bin/env python3
"""Run mock verification harness for bundled EmDash plugin corrections."""

from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "tests" / "test_plugin_corrections_mock.js"


class TestPluginCorrectionsMock(unittest.TestCase):
    def test_mock_plugin_corrections_harness(self) -> None:
        """Run Node test harness verifying route handler signatures and email transport status check."""
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("node binary not available in environment")

        res = subprocess.run(
            [node_bin, "--test", str(HARNESS_PATH)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            res.returncode,
            0,
            f"Mock plugin corrections harness failed (code {res.returncode}):\n{res.stdout}\n{res.stderr}",
        )
        self.assertIn("pass 8", res.stdout)


if __name__ == "__main__":
    unittest.main()
