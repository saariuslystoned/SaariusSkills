from __future__ import annotations

import os
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

    def run_cli(
        self,
        *args: str,
        ok: bool = True,
        failpoint: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        if failpoint is not None:
            env["GRILLTRACK_TEST_FAILPOINT"] = failpoint
        else:
            env.pop("GRILLTRACK_TEST_FAILPOINT", None)
        result = subprocess.run(
            [sys.executable, str(LEDGER), "--project", str(self.project), *args],
            check=False,
            capture_output=True,
            text=True,
            env=env,
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

    def close_track(self, summary: str = "Verified fixture output.") -> None:
        proof = self.project / ".grilltrack" / "proof" / "fixture.txt"
        proof.write_text("retained proof\n", encoding="utf-8")
        self.run_cli(
            "close",
            "--confirmed-by",
            "user",
            "--reason",
            "Cycle complete",
            "--summary",
            summary,
            "--proof-ref",
            ".grilltrack/proof/fixture.txt",
        )

    def test_init_accepts_natural_activation(self) -> None:
        self.init()
        self.assertEqual(
            self.read_ledger()["last_activation"]["mechanism"], "implicit"
        )

    def test_explicit_activation_remains_supported(self) -> None:
        self.run_cli(
            "init",
            "--activation",
            "$grilltrack",
            "--title",
            "Explicit track",
            "--track-id",
            "explicit-track",
        )
        self.assertEqual(
            self.read_ledger()["last_activation"]["mechanism"], "$grilltrack"
        )

    def test_invalid_activation_is_rejected(self) -> None:
        result = self.run_cli(
            "init",
            "--activation",
            "GrillTrack",
            "--title",
            "No",
            ok=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("activation must be implicit or $grilltrack", result.stderr)
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
            "--id",
            "base-001",
            "--reason",
            "New evidence",
        )
        decisions = {item["id"]: item for item in self.read_ledger()["decisions"]}
        self.assertEqual(decisions["draft-001"]["status"], "proposed")

    def test_resume_accepts_natural_activation(self) -> None:
        self.init()
        self.run_cli(
            "pause",
            "--reason",
            "Session boundary",
            "--next-safe-action", "Resume naturally",
        )
        self.run_cli("resume")
        ledger = self.read_ledger()
        self.assertEqual(ledger["status"], "active")
        self.assertEqual(ledger["last_activation"]["mechanism"], "implicit")

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

    def test_new_preserves_closed_track_and_starts_successor(self) -> None:
        self.init()
        self.focus_and_confirm()
        self.add_verified("output-001")
        proof = self.project / ".grilltrack" / "proof" / "fixture.txt"
        proof.write_text("retained proof\n", encoding="utf-8")
        self.run_cli(
            "close",
            "--confirmed-by", "user",
            "--reason", "Cycle complete",
            "--summary", "Verified fixture output.",
            "--proof-ref", ".grilltrack/proof/fixture.txt",
        )
        closed_ledger = self.read_ledger()
        closed_events = (
            self.project / ".grilltrack" / "events.jsonl"
        ).read_text(encoding="utf-8")

        self.run_cli(
            "new",
            "--title", "Next fixture track",
            "--track-id", "fixture-track-2",
        )

        ledger = self.read_ledger()
        archive = (
            self.project / ".grilltrack" / "archive" / "fixture-track"
        )
        self.assertEqual(ledger["status"], "active")
        self.assertEqual(ledger["predecessor_track_id"], "fixture-track")
        self.assertEqual(ledger["last_activation"]["mechanism"], "implicit")
        self.assertEqual(
            json.loads((archive / "ledger.json").read_text(encoding="utf-8")),
            closed_ledger,
        )
        self.assertEqual(
            (archive / "events.jsonl").read_text(encoding="utf-8"),
            closed_events,
        )
        self.assertEqual(proof.read_text(encoding="utf-8"), "retained proof\n")
        events = [
            json.loads(line)
            for line in (
                self.project / ".grilltrack" / "events.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual([event["action"] for event in events], ["track_initialized"])
        self.assertEqual(
            events[0]["data"]["archive_ref"],
            ".grilltrack/archive/fixture-track",
        )

    def test_new_rejects_predecessor_or_archived_track_id(self) -> None:
        self.init()
        self.close_track()
        self.run_cli(
            "new",
            "--title",
            "Second fixture track",
            "--track-id",
            "fixture-track-2",
        )
        self.close_track(summary="Second track complete.")
        result = self.run_cli(
            "new",
            "--title",
            "Third fixture track",
            "--track-id",
            "fixture-track",
            ok=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("already archived", result.stderr)
        self.assertEqual(self.read_ledger()["track_id"], "fixture-track-2")

    def test_new_recoverable_after_archive_failure(self) -> None:
        self.init()
        self.close_track()
        rollover = (
            self.project / ".grilltrack" / "work" / "new_track_rollover.json"
        )
        fail = self.run_cli(
            "new",
            "--title",
            "Second fixture track",
            "--track-id",
            "fixture-track-2",
            failpoint="after_archive",
            ok=False,
        )
        self.assertEqual(fail.returncode, 2)
        self.assertIn("simulated failure at after_archive", fail.stderr)
        self.assertEqual(self.read_ledger()["status"], "closed")
        self.assertTrue(rollover.is_file())
        self.run_cli(
            "new",
            "--title",
            "Second fixture track",
            "--track-id",
            "fixture-track-2",
        )
        ledger = self.read_ledger()
        self.assertEqual(ledger["status"], "active")
        self.assertEqual(ledger["track_id"], "fixture-track-2")
        self.assertEqual(rollover.exists(), False)

    def test_new_recoverable_after_ledger_failure(self) -> None:
        self.init()
        self.close_track()
        fail = self.run_cli(
            "new",
            "--title",
            "Second fixture track",
            "--track-id",
            "fixture-track-2",
            failpoint="after_ledger",
            ok=False,
        )
        self.assertEqual(fail.returncode, 2)
        self.assertIn("simulated failure at after_ledger", fail.stderr)
        ledger = self.read_ledger()
        self.assertEqual(ledger["status"], "active")
        self.assertEqual(ledger["track_id"], "fixture-track-2")
        self.assertEqual(
            (self.project / ".grilltrack" / "work" / "new_track_rollover.json").is_file(),
            True,
        )
        self.run_cli(
            "new",
            "--title",
            "Second fixture track",
            "--track-id",
            "fixture-track-2",
        )
        events = [
            json.loads(line)
            for line in (
                self.project / ".grilltrack" / "events.jsonl"
            ).read_text(encoding="utf-8")
            .strip()
            .splitlines()
        ]
        self.assertEqual([event["action"] for event in events], ["track_initialized"])

    def test_new_rejects_an_active_track(self) -> None:
        self.init()
        result = self.run_cli(
            "new", "--title", "Too soon", ok=False
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("only after the current track is closed", result.stderr)

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
