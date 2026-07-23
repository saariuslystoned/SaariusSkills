from __future__ import annotations

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

    def test_wait_accepts_beacon_condition(self):
        args = self.parser.parse_args(
            [
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
        )
        self.assertEqual(args.until, "beacon")
        self.assertEqual(args.timeout, 1.0)

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
