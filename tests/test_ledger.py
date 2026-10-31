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

    def test_review_is_exact_source_adjudicated_and_repairable(self) -> None:
        self.init()
        self.focus_and_confirm()
        self.add_verified("output-001")

        self.run_cli(
            "review",
            "--id",
            "output-001",
            "--source-identity",
            "git:" + ("a" * 40),
            "--ref",
            ".grilltrack/proof/review-clean/PROOF.md",
            "--result",
            "clean",
        )
        decision = self.read_ledger()["decisions"][0]
        self.assertEqual(decision["status"], "verified")
        self.assertEqual(decision["review_result"], "clean")
        self.assertEqual(decision["review_source_identity"], "git:" + ("a" * 40))
        self.assertEqual(decision["review_classifications"], [])

        self.run_cli(
            "review",
            "--id",
            "output-001",
            "--source-identity",
            "git:" + ("a" * 40),
            "--ref",
            ".grilltrack/proof/review-findings/PROOF.md",
            "--result",
            "findings",
            "--classification",
            "required_fix",
        )
        decision = self.read_ledger()["decisions"][0]
        self.assertEqual(decision["status"], "needs_reverification")
        self.assertTrue(decision["repair_required"])
        blocked = self.run_cli(
            "verify",
            "--id",
            "output-001",
            "--ref",
            "test:cannot-bypass-fix",
            ok=False,
        )
        self.assertIn("must be implemented", blocked.stderr)

        self.run_cli(
            "implement",
            "--id",
            "output-001",
            "--ref",
            "file:repaired-output",
        )
        decision = self.read_ledger()["decisions"][0]
        self.assertIsNone(decision["review_ref"])
        self.assertFalse(decision["repair_required"])
        self.run_cli(
            "verify",
            "--id",
            "output-001",
            "--ref",
            "test:repaired-output",
        )
        self.run_cli(
            "review",
            "--id",
            "output-001",
            "--source-identity",
            "sha256:" + ("b" * 64),
            "--ref",
            ".grilltrack/proof/review-repair/PROOF.md",
            "--result",
            "clean",
        )
        decision = self.read_ledger()["decisions"][0]
        self.assertEqual(decision["status"], "verified")
        self.assertEqual(len(decision["review_history"]), 3)

        self.run_cli(
            "close",
            "--confirmed-by",
            "user",
            "--reason",
            "Cycle complete",
            "--summary",
            "Repaired output is verified and reviewed.",
        )
        closeout = self.read_ledger()["closeout"]
        self.assertEqual(closeout["reviews"][0]["decision_id"], "output-001")
        self.assertEqual(
            closeout["reviews"][0]["source_identity"],
            "sha256:" + ("b" * 64),
        )

    def test_review_rejects_mutable_source_identity(self) -> None:
        self.init()
        self.focus_and_confirm()
        self.add_verified("output-001")
        result = self.run_cli(
            "review",
            "--id",
            "output-001",
            "--source-identity",
            "git:origin/main",
            "--ref",
            ".grilltrack/proof/review/PROOF.md",
            "--result",
            "clean",
            ok=False,
        )
        self.assertIn("git:<40-lowercase-hex>", result.stderr)

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

    def test_reopen_resumes_a_paused_projection(self) -> None:
        self.init()
        self.focus_and_confirm()
        self.add_verified("output-001")
        self.run_cli(
            "pause",
            "--reason",
            "Context boundary",
            "--next-safe-action",
            "Reopen output choice",
            "--artifact-ref",
            ".grilltrack/work/context.md",
        )
        self.run_cli(
            "reopen",
            "--id",
            "output-001",
            "--reason",
            "New evidence",
        )
        ledger = self.read_ledger()
        self.assertEqual(ledger["status"], "active")
        self.assertIsNone(ledger["pause"])
        self.assertEqual(
            ledger["last_pause"]["artifact_refs"],
            [".grilltrack/work/context.md"],
        )

    def test_resume_accepts_natural_activation(self) -> None:
        self.init()
        self.run_cli(
            "pause",
            "--reason",
            "Session boundary",
            "--next-safe-action",
            "Resume naturally",
            "--artifact-ref",
            ".grilltrack/work/gates/setup.md",
        )
        paused = self.read_ledger()
        self.assertEqual(paused["status"], "paused")
        self.assertEqual(paused["pause"]["reason"], "Session boundary")
        self.assertEqual(
            paused["pause"]["artifact_refs"],
            [".grilltrack/work/gates/setup.md"],
        )
        self.run_cli("resume")
        ledger = self.read_ledger()
        self.assertEqual(ledger["status"], "active")
        self.assertEqual(ledger["last_activation"]["mechanism"], "implicit")
        self.assertIsNone(ledger["pause"])
        self.assertEqual(
            ledger["last_pause"]["artifact_refs"],
            [".grilltrack/work/gates/setup.md"],
        )
        self.assertIn("resumed_at", ledger["last_pause"])

    def test_resume_accepts_a_legacy_paused_projection(self) -> None:
        self.init()
        self.run_cli(
            "pause",
            "--reason",
            "Legacy boundary",
            "--next-safe-action",
            "Resume",
        )
        ledger = self.read_ledger()
        ledger.pop("pause")
        ledger.pop("last_pause")
        (self.project / ".grilltrack" / "ledger.json").write_text(
            json.dumps(ledger), encoding="utf-8"
        )
        self.run_cli("resume")
        resumed = self.read_ledger()
        self.assertEqual(resumed["status"], "active")
        self.assertIsNone(resumed["pause"])

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

    def test_new_rejects_non_directory_archive_entry_name(self) -> None:
        self.init()
        self.close_track()
        archive_root = self.project / ".grilltrack" / "archive"
        archive_root.mkdir(parents=True, exist_ok=True)
        (archive_root / "fixture-dir-trap").mkdir()
        (archive_root / "fixture-file-trap").write_text("trap", encoding="utf-8")
        symlink_target = self.project / ".grilltrack" / "proof" / "fixture.txt"
        symlink_target.write_text("target", encoding="utf-8")
        (archive_root / "fixture-link-trap").symlink_to(symlink_target)
        result = self.run_cli(
            "new",
            "--title",
            "Bad fixture track",
            "--track-id",
            "fixture-link-trap",
            ok=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("new track id already archived", result.stderr)

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
        rollover = (
            self.project / ".grilltrack" / "work" / "new_track_rollover.json"
        )
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
        rollover_data = json.loads(
            rollover.read_text(encoding="utf-8")
        )
        self.assertEqual(rollover_data["stage"], "archived")
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

    def test_new_recoverable_after_rollover_stage_failure(self) -> None:
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
            failpoint="after_rollover_stage",
            ok=False,
        )
        self.assertEqual(fail.returncode, 2)
        self.assertIn("simulated failure at after_rollover_stage", fail.stderr)
        ledger = self.read_ledger()
        self.assertEqual(ledger["status"], "active")
        self.assertEqual(ledger["track_id"], "fixture-track-2")
        rollover_data = json.loads(
            rollover.read_text(encoding="utf-8")
        )
        self.assertEqual(rollover_data["stage"], "ledger_written")
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

    def test_new_recovery_blocks_focus_and_validate_until_complete(self) -> None:
        self.init()
        self.close_track()
        fail = self.run_cli(
            "new",
            "--title",
            "Second fixture track",
            "--track-id",
            "fixture-track-2",
            failpoint="after_rollover_stage",
            ok=False,
        )
        self.assertEqual(fail.returncode, 2)
        self.assertIn("simulated failure at after_rollover_stage", fail.stderr)
        ledger = self.read_ledger()
        events_path = self.project / ".grilltrack" / "events.jsonl"
        before_events = events_path.read_text(encoding="utf-8")
        blocked_focus = self.run_cli(
            "focus",
            "--domain",
            "Should be blocked",
            "--cadence",
            "sequential",
            ok=False,
        )
        self.assertEqual(blocked_focus.returncode, 2)
        self.assertIn("rerun `new` to finish recovery", blocked_focus.stderr)
        self.assertEqual(ledger, self.read_ledger())
        self.assertEqual(before_events, events_path.read_text(encoding="utf-8"))
        blocked_validate = self.run_cli("validate", ok=False)
        self.assertEqual(blocked_validate.returncode, 2)
        self.assertIn("rerun `new` to finish recovery", blocked_validate.stderr)
        self.assertEqual(ledger, self.read_ledger())
        self.assertEqual(before_events, events_path.read_text(encoding="utf-8"))

        self.run_cli(
            "new",
            "--title",
            "Second fixture track",
            "--track-id",
            "fixture-track-2",
        )
        completed_events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").strip().splitlines()
        ]
        self.assertEqual([event["action"] for event in completed_events], ["track_initialized"])

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

    def test_summary_is_bounded_and_default_remains_full(self) -> None:
        self.run_cli(
            "init",
            "--title",
            "Summary fixture",
            "--track-id",
            "summary-track",
            "--output",
            "summary",
        )
        self.run_cli(
            "focus",
            "--domain",
            "Summary output",
            "--cadence",
            "sequential",
            "--summary",
            "Existing user-content input remains accepted.",
            "--output",
            "summary",
        )
        self.run_cli(
            "confirm",
            "--summary",
            "Confirm the bounded receipt.",
            "--output",
            "summary",
        )
        proposed = self.run_cli(
            "propose",
            "--id",
            "summary-001",
            "--question",
            "Which output?",
            "--choice",
            "Bounded",
            "--rationale",
            "Avoid unbounded agent output.",
            "--output",
            "summary",
        )
        receipt = json.loads(proposed.stdout)
        self.assertEqual(
            receipt,
            {
                "command": "propose",
                "decision": {"id": "summary-001", "status": "proposed"},
                "durable_paths": {
                    "ledger": str((self.project / ".grilltrack" / "ledger.json").resolve()),
                    "events": str((self.project / ".grilltrack" / "events.jsonl").resolve()),
                },
                "track": {"id": "summary-track", "status": "active"},
                "updated_at": receipt["updated_at"],
            },
        )
        self.assertNotIn("choice", receipt)
        self.assertNotIn("rationale", receipt)

        full = self.run_cli("show")
        full_data = json.loads(full.stdout)
        self.assertEqual(full_data["decisions"][0]["choice"], "Bounded")
        self.assertEqual(full_data["current_focus"]["summary"], "Confirm the bounded receipt.")
        self.assertTrue(full.stdout.startswith("{\n"))
        self.assertEqual(self.run_cli("validate").stdout.strip(), "valid")

    def test_summary_preserves_durable_semantics_and_shrinks_large_history(self) -> None:
        first = LedgerCliTests()
        first.setUp()
        second = LedgerCliTests()
        second.setUp()
        try:
            for fixture in (first, second):
                fixture.run_cli(
                    "init",
                    "--title",
                    "Equivalent fixture",
                    "--track-id",
                    "equivalent-track",
                    "--output",
                    "summary" if fixture is second else "full",
                )
                fixture.focus_and_confirm()
                for index in range(24):
                    fixture.add_verified(f"decision-{index:02d}")

            first_full = first.run_cli("focus", "--domain", "Large history", "--cadence", "sequential")
            second_summary = second.run_cli(
                "focus",
                "--domain",
                "Large history",
                "--cadence",
                "sequential",
                "--output",
                "summary",
            )
            self.assertLess(len(second_summary.stdout), len(first_full.stdout))
            self.assertLess(len(second_summary.stdout), 800)
            self.assertGreater(len(first_full.stdout), 10000)

            first_ledger = first.read_ledger()
            second_ledger = second.read_ledger()
            for ledger in (first_ledger, second_ledger):
                ledger["created_at"] = "<timestamp>"
                ledger["updated_at"] = "<timestamp>"
                ledger["last_activation"]["at"] = "<timestamp>"
                ledger["current_focus"]["started_at"] = "<timestamp>"
                ledger["current_focus"].pop("confirmed_at", None)
                for decision in ledger["decisions"]:
                    decision["created_at"] = "<timestamp>"
                    decision["updated_at"] = "<timestamp>"
                    for transition_record in decision["history"]:
                        transition_record["at"] = "<timestamp>"
            self.assertEqual(first_ledger, second_ledger)

            def event_semantics(fixture: LedgerCliTests) -> list[dict]:
                events = [
                    json.loads(line)
                    for line in (
                        fixture.project / ".grilltrack" / "events.jsonl"
                    ).read_text(encoding="utf-8").splitlines()
                ]
                for event in events:
                    event.pop("event_id", None)
                    event.pop("at", None)
                return events

            self.assertEqual(event_semantics(first), event_semantics(second))
        finally:
            first.tearDown()
            second.tearDown()

    def test_invalid_summary_transition_preserves_failure_and_durability(self) -> None:
        self.init()
        ledger_path = self.project / ".grilltrack" / "ledger.json"
        events_path = self.project / ".grilltrack" / "events.jsonl"
        before_ledger = ledger_path.read_bytes()
        before_events = events_path.read_bytes()
        result = self.run_cli(
            "lock",
            "--id",
            "missing-001",
            "--output",
            "summary",
            ok=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown decision: missing-001", result.stderr)
        self.assertEqual(ledger_path.read_bytes(), before_ledger)
        self.assertEqual(events_path.read_bytes(), before_events)

    def test_all_lifecycle_parsers_accept_output_selector(self) -> None:
        commands = (
            "init", "new", "focus", "confirm", "propose", "lock", "implement",
            "verify", "review", "reopen", "supersede", "defer", "recommend",
            "pause", "resume", "close", "compact",
        )
        for command in commands:
            result = self.run_cli(command, "--output", "summary", "--help")
            self.assertEqual(result.returncode, 0, command)
            self.assertIn("--output", result.stdout, command)

    def test_deferral_scope_requires_revisit_when_and_locks_as_deferred(self) -> None:
        self.init()
        self.focus_and_confirm()
        missing_revisit = self.run_cli(
            "propose",
            "--id",
            "webmcp-later-001",
            "--scope",
            "deferral",
            "--question",
            "Do browser agents get WebMCP tools now?",
            "--choice",
            "No. WebMCP tools wait for a later phase.",
            ok=False,
        )
        self.assertEqual(missing_revisit.returncode, 2)
        self.assertIn("revisit_when", missing_revisit.stderr)

        self.run_cli(
            "propose",
            "--id",
            "webmcp-later-001",
            "--scope",
            "deferral",
            "--revisit-when",
            "Phase 3 after first real order ships",
            "--question",
            "Do browser agents get WebMCP tools now?",
            "--choice",
            "No. WebMCP tools wait for a later phase.",
            "--rationale",
            "Wait until Phase 1 headless UCP is verified.",
        )
        self.run_cli("lock", "--id", "webmcp-later-001")
        decision = self.read_ledger()["decisions"][0]
        self.assertEqual(decision["scope"], "deferral")
        self.assertEqual(decision["status"], "deferred")
        self.assertIn("Phase 3 after first real order ships", decision["deferred_reason"])
        self.assertEqual(self.run_cli("validate").stdout.strip(), "valid")

    def test_gatekeeper_blocks_temporal_deferral_and_situational_metric_on_durable_lock(self) -> None:
        self.init()
        self.focus_and_confirm()
        self.run_cli(
            "propose",
            "--id",
            "false-ban-001",
            "--scope",
            "durable",
            "--question",
            "Do browser agents get WebMCP tools now?",
            "--choice",
            "No. WebMCP tools wait for a later phase.",
        )
        blocked_deferral = self.run_cli("lock", "--id", "false-ban-001", ok=False)
        self.assertEqual(blocked_deferral.returncode, 2)
        self.assertIn("deferral", blocked_deferral.stderr)

        self.run_cli(
            "propose",
            "--id",
            "byte-reserve-001",
            "--scope",
            "durable",
            "--question",
            "How should we handle coupons under the 128 KiB cap?",
            "--choice",
            "Park coupons and leave at least 2200 bytes of headroom under the cap.",
        )
        blocked_metric = self.run_cli(
            "lock",
            "--id",
            "byte-reserve-001",
            "--user-reply",
            "yes park coupons for now",
            "--gate",
            "heuristic",
            ok=False,
        )
        self.assertEqual(blocked_metric.returncode, 2)
        self.assertIn("situational", blocked_metric.stderr)

        # Override requires --override-reason
        missing_reason = self.run_cli(
            "lock",
            "--id",
            "byte-reserve-001",
            "--force-lock",
            ok=False,
        )
        self.assertEqual(missing_reason.returncode, 2)
        self.assertIn("override_reason", missing_reason.stderr)

        self.run_cli(
            "lock",
            "--id",
            "byte-reserve-001",
            "--force-lock",
            "--override-reason",
            "Explicitly requested temporary test fixture override",
        )
        locked = [
            item
            for item in self.read_ledger()["decisions"]
            if item["id"] == "byte-reserve-001"
        ][0]
        self.assertEqual(locked["status"], "locked")
        self.assertTrue(locked["gate_evaluation"]["overridden"])

    def test_compact_archives_superseded_and_verified_slice_decisions_preserving_dependencies(self) -> None:
        self.init()
        self.focus_and_confirm()
        # 1. Verified slice decision
        self.run_cli(
            "propose",
            "--id",
            "slice-001",
            "--scope",
            "slice",
            "--question",
            "How to stage this PR?",
            "--choice",
            "Stage in two commits.",
        )
        self.run_cli("lock", "--id", "slice-001")
        self.run_cli("implement", "--id", "slice-001", "--ref", "file:slice")
        self.run_cli("verify", "--id", "slice-001", "--ref", "test:slice")

        # 2. Old decision superseded by durable-002
        self.add_verified("old-001")
        self.run_cli(
            "propose",
            "--id",
            "durable-002",
            "--scope",
            "durable",
            "--depends-on",
            "slice-001",
            "--question",
            "Permanent architecture?",
            "--choice",
            "Use pure JSON envelope.",
        )
        self.run_cli("lock", "--id", "durable-002")
        self.run_cli(
            "supersede",
            "--id",
            "old-001",
            "--by",
            "durable-002",
            "--reason",
            "Replaced by pure JSON envelope",
        )
        self.run_cli("implement", "--id", "durable-002", "--ref", "file:durable")
        self.run_cli("verify", "--id", "durable-002", "--ref", "test:durable")

        self.run_cli("compact")
        ledger = self.read_ledger()
        active_ids = [item["id"] for item in ledger["decisions"]]
        self.assertEqual(active_ids, ["durable-002"])
        self.assertEqual(
            ledger["compacted_decision_ids"], ["old-001", "slice-001"]
        )
        self.assertEqual(len(ledger["decisions"][0]["history"]), 1)
        self.assertEqual(self.run_cli("validate").stdout.strip(), "valid")

        # Proposing a new decision that depends on a compacted decision succeeds.
        self.run_cli(
            "propose",
            "--id",
            "dependent-003",
            "--depends-on",
            "slice-001",
            "--question",
            "Follow-up?",
            "--choice",
            "Keep envelope.",
        )
        self.assertEqual(self.run_cli("validate").stdout.strip(), "valid")

        archive_file = (
            self.project
            / ".grilltrack"
            / "archive"
            / "compacted-fixture-track.json"
        )
        self.assertTrue(archive_file.is_file())
        archived_data = json.loads(archive_file.read_text(encoding="utf-8"))
        self.assertIn("slice-001", archived_data["decisions"])
        self.assertIn("old-001", archived_data["decisions"])
        self.assertIn("durable-002", archived_data["history_by_decision"])

    def test_gatekeeper_allows_contextual_confirmation_and_preserves_saved_scope_on_gate(self) -> None:
        self.init()
        self.focus_and_confirm()
        # 1. Contextual confirmation of a numeric requirement already present in the question succeeds
        #    even when digit grouping differs ('2,200 bytes' vs '2200 bytes').
        self.run_cli(
            "propose",
            "--id",
            "port-8443-durable",
            "--scope",
            "durable",
            "--question",
            "Should the public service always listen on port 8443 and leave at least 2,200 bytes?",
            "--choice",
            "Use port 8443 and leave at least 2200 bytes.",
        )
        self.run_cli(
            "lock",
            "--id",
            "port-8443-durable",
            "--user-reply",
            "yes",
            "--gate",
            "heuristic",
        )
        locked = [
            item
            for item in self.read_ledger()["decisions"]
            if item["id"] == "port-8443-durable"
        ][0]
        self.assertEqual(locked["status"], "locked")

        # 2. `gate --id <id>` preserves the saved `slice` scope when `--scope` is omitted.
        self.run_cli(
            "propose",
            "--id",
            "slice-reserve-001",
            "--scope",
            "slice",
            "--question",
            "How should we stage this PR?",
            "--choice",
            "Keep 2,200 bytes free for this slice.",
        )
        gate_out = json.loads(
            self.run_cli(
                "gate",
                "--id",
                "slice-reserve-001",
                "--gate",
                "heuristic",
            ).stdout
        )
        self.assertTrue(gate_out["passed"])
        self.assertEqual(gate_out["declared_scope"], "slice")

        # 3. `slice` scope still rejects bundled extra invariants on a brief reply.
        bundled_slice_choice = (
            "Stage the PR in two commits; also enforce a global OAuth PKCE middleware rewrite across all routes; "
            "and also require every admin view to migrate to a custom WebSocket transport before merge; "
            "and also lock a strict 15-minute session rotation policy across all environments."
        )
        self.run_cli(
            "propose",
            "--id",
            "slice-bundled-002",
            "--scope",
            "slice",
            "--question",
            "Should we stage the PR in two commits?",
            "--choice",
            bundled_slice_choice,
        )
        blocked_slice = self.run_cli(
            "lock",
            "--id",
            "slice-bundled-002",
            "--user-reply",
            "yes",
            "--gate",
            "heuristic",
            ok=False,
        )
        self.assertEqual(blocked_slice.returncode, 2)
        self.assertIn("bundled_extra_invariants", blocked_slice.stderr)


if __name__ == "__main__":
    unittest.main()
