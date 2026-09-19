from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "puppet" / "scripts"
CLI = SCRIPTS / "puppet.py"

sys.path.insert(0, str(SCRIPTS))
from puppet import build_parser  # noqa: E402


class PuppetCLITests(unittest.TestCase):
    def setUp(self):
        self.parser = build_parser()

    def _run_cli(self, arguments):
        return subprocess.run(
            [sys.executable, str(CLI), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def test_help_output_exposes_global_json_and_bootstrap_forms(self):
        result = self._run_cli(["--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--json", result.stdout)
        result = self._run_cli(["send", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--message-file", result.stdout)
        self.assertIn("--stdin", result.stdout)
        result = self._run_cli(["wait", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--until", result.stdout)
        self.assertIn("beacon", result.stdout)
        result = self._run_cli(["open-view", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--terminal", result.stdout)
        self.assertIn("--dry-run", result.stdout)
        result = self._run_cli(["profile-init", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--profile-root", result.stdout)
        self.assertIn("--executable", result.stdout)
        result = self._run_cli(["profile-status", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--profile-root", result.stdout)
        result = self._run_cli(["onboard", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--profile-shelf", result.stdout)
        self.assertIn("TARGET=/ABSOLUTE/PATH", result.stdout)
        result = self._run_cli(["reconcile-grok-dead-lease", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--state-root", result.stdout)
        self.assertIn("--session", result.stdout)
        self.assertIn("proven-dead launch-incomplete", result.stdout)
        self.assertIn("Grok session", result.stdout)
        for command in ("doctor", "launch"):
            result = self._run_cli([command, "--help"])
            self.assertEqual(result.returncode, 0)
            self.assertIn("--profile-root", result.stdout)
            self.assertIn("--transport", result.stdout)
        result = self._run_cli(["plan", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--transport", result.stdout)

    def test_promote_and_close_remain_unsupported(self):
        for command in ("promote", "close"):
            result = self._run_cli([command])
            self.assertEqual(result.returncode, 3)
            self.assertIn('"error": "unsupported"', result.stderr)

    def test_send_requires_exactly_one_message_input(self):
        with self.assertRaises(SystemExit):
            self.parser.parse_args(
                [
                    "send",
                    "--state-root",
                    "state",
                    "--session",
                    "session",
                    "--request-id",
                    "request",
                ]
            )
        with self.assertRaises(SystemExit):
            self.parser.parse_args(
                [
                    "send",
                    "--state-root",
                    "state",
                    "--session",
                    "session",
                    "--request-id",
                    "request",
                    "--message-file",
                    "message.txt",
                    "--stdin",
                ]
            )
        self.parser.parse_args(
            [
                "send",
                "--state-root",
                "state",
                "--session",
                "session",
                "--request-id",
                "request",
                "--message-file",
                "message.txt",
            ]
        )
        self.parser.parse_args(
            [
                "send",
                "--state-root",
                "state",
                "--session",
                "session",
                "--request-id",
                "request",
                "--stdin",
            ]
        )

    def test_wait_accepts_beacon_condition_and_optional_after_marker(self):
        base = [
            "wait",
            "--state-root",
            "state",
            "--session",
            "session",
            "--until",
            "beacon",
            "--timeout",
            "1.0",
        ]
        args = self.parser.parse_args(base)
        self.assertEqual(args.until, "beacon")
        self.assertEqual(args.timeout, 1.0)
        self.assertIsNone(args.after)
        args = self.parser.parse_args([*base, "--after", "3"])
        self.assertEqual(args.after, "3")

    def test_wait_and_halt_reject_non_finite_timeouts_at_parse_time(self):
        # Issue #28: float("nan") passes every range comparison, so the parser
        # must refuse it before wait_for's bounds are ever consulted.
        for command, extra in (("wait", ["--until", "checkpoint"]), ("halt", [])):
            # A bare "-inf" is parsed as an option flag; the "=" form reaches
            # the type check like every other value.
            for timeout in (
                ["--timeout", "nan"],
                ["--timeout", "NaN"],
                ["--timeout", "inf"],
                ["--timeout", "Infinity"],
                ["--timeout=-inf"],
                ["--timeout", "abc"],
            ):
                with self.subTest(command=command, timeout=timeout):
                    with (
                        contextlib.redirect_stderr(io.StringIO()) as stderr,
                        self.assertRaises(SystemExit) as raised,
                    ):
                        self.parser.parse_args(
                            [
                                command,
                                "--state-root",
                                "state",
                                "--session",
                                "session",
                                *extra,
                                *timeout,
                            ]
                        )
                    self.assertEqual(raised.exception.code, 2)
                    self.assertIn(
                        "must be a finite number of seconds", stderr.getvalue()
                    )
        result = self._run_cli(
            [
                "wait",
                "--state-root",
                "state",
                "--session",
                "session",
                "--until",
                "checkpoint",
                "--timeout",
                "nan",
            ]
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be a finite number of seconds", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_launch_accepts_optional_finite_deadline(self):
        base = [
            "launch",
            "--session",
            "session",
            "--contract",
            "contract.json",
            "--manifest",
            "manifest.json",
            "--authorization",
            "authorization.json",
            "--proof-root",
            "proof",
            "--state-root",
            "state",
            "--prompt-file",
            "prompt.txt",
        ]
        self.assertIsNone(self.parser.parse_args(base).deadline_seconds)
        self.assertEqual(
            self.parser.parse_args(
                [*base, "--deadline-seconds", "3600"]
            ).deadline_seconds,
            3600.0,
        )
        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            self.parser.parse_args([*base, "--deadline-seconds", "nan"])

    def test_review_and_accept_require_explicit_checkpoint(self):
        review_base = [
            "review",
            "--state-root",
            "state",
            "--session",
            "session",
            "--actor",
            "controller",
            "--verdict",
            "block",
            "--evidence",
            "evidence.json",
        ]
        with self.assertRaises(SystemExit):
            self.parser.parse_args(review_base)
        review_args = self.parser.parse_args(
            [*review_base, "--checkpoint", "checkpoint-id"]
        )
        self.assertEqual(review_args.checkpoint, "checkpoint-id")

        accept_base = [
            "accept",
            "--state-root",
            "state",
            "--session",
            "session",
            "--actor",
            "controller",
            "--evidence",
            "evidence.json",
        ]
        with self.assertRaises(SystemExit):
            self.parser.parse_args(accept_base)
        accept_args = self.parser.parse_args(
            [*accept_base, "--checkpoint", "checkpoint-id"]
        )
        self.assertEqual(accept_args.checkpoint, "checkpoint-id")

    def test_global_json_flag_is_accepted(self):
        args = self.parser.parse_args(["--json", "promote"])
        self.assertTrue(args.json)

    def test_profile_init_advertises_private_profile_targets(self):
        common = [
            "profile-init",
            "--profile-root",
            "/tmp/profile",
            "--executable",
            "/tmp/executable",
        ]
        with self.assertRaises(SystemExit):
            self.parser.parse_args([*common, "--target", "agy"])
        for target in ("codex", "claude", "cursor", "grok"):
            with self.subTest(target=target):
                args = self.parser.parse_args([*common, "--target", target])
                self.assertEqual(args.target, target)

    def test_onboard_requires_absolute_unique_allowlisted_manifests(self):
        common = ["onboard", "--profile-shelf", "/tmp/profiles"]
        args = self.parser.parse_args(
            [
                *common,
                "--manifest",
                "grok=/tmp/grok.json",
                "--manifest",
                "codex=/tmp/codex.json",
            ]
        )
        self.assertEqual(
            args.manifest,
            [
                ("grok", Path("/tmp/grok.json")),
                ("codex", Path("/tmp/codex.json")),
            ],
        )
        for invalid in (
            "other=/tmp/other.json",
            "grok=relative.json",
            "grok",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(SystemExit):
                self.parser.parse_args([*common, "--manifest", invalid])

    def test_onboard_rejects_duplicate_manifest_target_as_conflict(self):
        result = self._run_cli(
            [
                "onboard",
                "--profile-shelf",
                "/tmp/profiles",
                "--manifest",
                "grok=/tmp/grok-a.json",
                "--manifest",
                "grok=/tmp/grok-b.json",
            ]
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn('"error": "conflict"', result.stderr)
        self.assertIn("duplicate onboarding target", result.stderr)
        self.assertNotIn("NameError", result.stderr)

    def test_message_and_evidence_bodies_are_not_command_argv(self):
        with self.assertRaises(SystemExit):
            self.parser.parse_args(
                [
                    "send",
                    "--state-root",
                    "state",
                    "--session",
                    "session",
                    "--request-id",
                    "request",
                    "--stdin",
                    "--message",
                    "message body",
                ]
            )
        with self.assertRaises(SystemExit):
            self.parser.parse_args(
                [
                    "review",
                    "--state-root",
                    "state",
                    "--session",
                    "session",
                    "--actor",
                    "controller",
                    "--checkpoint",
                    "checkpoint-id",
                    "--verdict",
                    "block",
                    "--evidence",
                    "evidence.json",
                    "--evidence-text",
                    "oops",
                ]
            )


if __name__ == "__main__":
    unittest.main()
