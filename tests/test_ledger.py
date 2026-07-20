from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "skills" / "grilltrack" / "scripts" / "grilltrack_ledger.py"


class LedgerCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(LEDGER), "--project", str(self.project), *args],
            check=False,
            capture_output=True,
            text=True,
        )
        if ok and result.returncode != 0:
            self.fail(f"command failed: {args}\nstdout={result.stdout}\nstderr={result.stderr}")
        return result

    def read_ledger(self) -> dict:
        return json.loads(
            (self.project / ".grilltrack" / "ledger.json").read_text(
                encoding="utf-8"
            )
        )

    def init(self) -> None:
        self.run_cli(
            "init",
            "--activation",
            "$grilltrack",
            "--title",
            "Fixture track",
            "--track-id",
            "fixture-track",
        )

    def focus_and_confirm(self) -> None:
        self.run_cli(
            "focus",
            "--domain",
            "CLI output",
            "--cadence",
            "sequential",
        )
        self.run_cli(
            "confirm",
            "--summary",
            "Implement and verify the chosen status output.",
        )

    def add_verified(
        self, decision_id: str, *, depends_on: str | None = None
    ) -> None:
        args = [
            "propose",
            "--id",
            decision_id,
            "--question",
            f"Choose {decision_id}",
            "--choice",
            f"value-{decision_id}",
        ]
        if depends_on:
            args.extend(["--depends-on", depends_on])
        self.run_cli(*args)
        self.run_cli("lock", "--id", decision_id)
        self.run_cli(
            "implement", "--id", decision_id, "--ref", f"file:{decision_id}"
        )
        self.run_cli("verify", "--id", decision_id, "--ref", f"test:{decision_id}")

    def test_init_requires_exact_activation(self) -> None:
        result = self.run_cli(
            "init",
            "--activation",
            "GrillTrack",
            "--title",
            "No",
            ok=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("explicit activation required", result.stderr)
        self.assertFalse((self.project / ".grilltrack").exists())

    def test_full_cycle_is_durable_and_valid(self) -> None:
        self.init()
        self.focus_and_confirm()
        self.add_verified("output-001")
        valid = self.run_cli("validate")
        self.assertEqual(valid.stdout.strip(), "valid")
        ledger = self.read_ledger()
        self.assertEqual(ledger["decisions"][0]["status"], "verified")
        self.assertTrue((self.project / ".grilltrack" / "events.jsonl").is_file())
        self.assertEqual(
            (self.project / ".grilltrack" / ".gitignore").read_text(
                encoding="utf-8"
            ),
            "work/\n",
        )

    def test_implementation_requires_confirmation(self) -> None:
        self.init()
        self.run_cli(
            "focus",
            "--domain",
            "CLI output",
            "--cadence",
            "sequential",
        )
        self.run_cli(
            "propose",
            "--id",
            "output-001",
            "--question",
            "Which output?",
            "--choice",
            "Compact",
        )
        self.run_cli("lock", "--id", "output-001")
        result = self.run_cli(
            "implement",
            "--id",
            "output-001",
            "--ref",
            "file:status_cli.py",
            ok=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("shared understanding", result.stderr)

    def test_reopen_marks_transitive_dependents(self) -> None:
        self.init()
        self.focus_and_confirm()
        self.add_verified("base-001")
        self.add_verified("child-001", depends_on="base-001")
        self.run_cli(
            "reopen",
            "--activation",
            "$grilltrack",
            "--id",
            "base-001",
            "--reason",
            "New evidence",
        )
        decisions = {item["id"]: item for item in self.read_ledger()["decisions"]}
        self.assertEqual(decisions["base-001"]["status"], "reopened")
        self.assertEqual(
            decisions["child-001"]["status"], "needs_reverification"
        )
        self.assertEqual(
            decisions["base-001"]["history"][-1]["choice"], "value-base-001"
        )

    def test_reopen_leaves_unlocked_proposals_proposed(self) -> None:
        self.init()
        self.focus_and_confirm()
        self.add_verified("base-001")
        self.run_cli(
            "propose",
            "--id",
            "draft-001",
            "--question",
            "Draft dependent choice",
            "--choice",
            "Still under discussion",
            "--depends-on",
            "base-001",
        )
        self.run_cli(
            "reopen",
            "--activation",
            "$grilltrack",
            "--id",
            "base-001",
            "--reason",
            "New evidence",
        )
        decisions = {item["id"]: item for item in self.read_ledger()["decisions"]}
        self.assertEqual(decisions["draft-001"]["status"], "proposed")

    def test_resume_requires_exact_activation(self) -> None:
        self.init()
        self.run_cli(
            "pause",
            "--reason",
            "Session boundary",
            "--next-safe-action",
            "Resume explicitly",
        )
        denied = self.run_cli(
            "resume", "--activation", "grilltrack", ok=False
        )
        self.assertEqual(denied.returncode, 2)
        self.run_cli("resume", "--activation", "$grilltrack")
        self.assertEqual(self.read_ledger()["status"], "active")

    def test_close_rejects_unresolved_then_accepts_deferred(self) -> None:
        self.init()
        self.focus_and_confirm()
        self.run_cli(
            "propose",
            "--id",
            "output-001",
            "--question",
            "Which output?",
            "--choice",
            "Compact",
        )
        self.run_cli("lock", "--id", "output-001")
        denied = self.run_cli(
            "close",
            "--confirmed-by",
            "user",
            "--reason",
            "Done",
            "--summary",
            "Not actually done",
            ok=False,
        )
        self.assertEqual(denied.returncode, 2)
        self.run_cli(
            "defer",
            "--id",
            "output-001",
            "--reason",
            "User accepted the remaining risk",
        )
        self.run_cli(
            "close",
            "--confirmed-by",
            "user",
            "--reason",
            "No meaningful next grill",
            "--summary",
            "Deferred output choice is recorded.",
        )
        self.assertEqual(self.read_ledger()["status"], "closed")

    def test_dependency_cycle_is_rejected(self) -> None:
        self.init()
        self.focus_and_confirm()
        self.add_verified("base-001")
        self.add_verified("child-001", depends_on="base-001")
        ledger = self.read_ledger()
        ledger["decisions"][0]["dependencies"] = ["child-001"]
        (self.project / ".grilltrack" / "ledger.json").write_text(
            json.dumps(ledger), encoding="utf-8"
        )
        result = self.run_cli("validate", ok=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("dependency cycle", result.stderr)


if __name__ == "__main__":
    unittest.main()
