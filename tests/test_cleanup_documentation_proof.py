"""The bounded proof must fail closed, including under Python optimization."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "proof/smoky-deslop-docs-20261105/use_cases.py"
MODES = (((), None), (("-O",), None), (("-OO",), None), ((), "1"))


class CleanupDocumentationProofTests(unittest.TestCase):
    def run_proof(self, flags: tuple[str, ...], optimization: str | None,
                  mutation: str = "") -> subprocess.CompletedProcess:
        # Load only the trusted synthetic fixture; no gated operation exists.
        driver = (
            "import runpy\n"
            f"fixture = runpy.run_path({str(PROOF)!r})\n"
            "scope = fixture['main'].__globals__\n"
            f"{mutation}\n"
            "fixture['main']()\n"
        )
        env = os.environ.copy()
        env.pop("PYTHONOPTIMIZE", None)
        if optimization is not None:
            env["PYTHONOPTIMIZE"] = optimization
        return subprocess.run([sys.executable, *flags, "-c", driver],
                              env=env, text=True, capture_output=True, timeout=10)

    def test_safe_examples_pass_in_all_optimization_modes(self) -> None:
        for flags, optimization in MODES:
            with self.subTest(flags=flags, optimization=optimization):
                result = self.run_proof(flags, optimization)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("PASS cleanup:", result.stdout)
                self.assertIn("PASS docs:", result.stdout)

    def test_unsafe_edits_and_broken_negative_controls_fail_in_all_modes(self) -> None:
        cases = (
            ("scope['AFTER'] = scope['UNSAFE']", "cleanup changed handler behavior", "cleanup"),
            ("scope['UNSAFE'] = scope['AFTER']", "guard-removal negative control must differ", "cleanup"),
            ("scope['REWRITE'] = scope['UNSAFE_DOC']", "rewrite must preserve literal parser mode", "docs"),
            ("scope['UNSAFE_DOC'] = scope['ORIGINAL_DOC']", "dropped-preview negative control must differ", "docs"),
            ("scope['REWRITE'] = scope['REWRITE'].replace('tool export', 'other export')", "documented executable must be tool", "docs"),
        )
        for flags, optimization in MODES:
            for mutation, reason, stage in cases:
                with self.subTest(flags=flags, optimization=optimization, mutation=mutation):
                    result = self.run_proof(flags, optimization, mutation)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn(f"FAIL: {reason}", result.stderr)
                    self.assertNotIn(f"PASS {stage}:", result.stdout)


if __name__ == "__main__":
    unittest.main()
