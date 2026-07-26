from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "plans/custom-agents/scripts/fanout_harness.py"


class CustomAgentFanoutHarnessTests(unittest.TestCase):
    def run_harness(
        self,
        *arguments: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        return subprocess.run(
            [sys.executable, str(HARNESS), *arguments],
            text=True,
            capture_output=True,
            env=process_env,
            check=False,
        )

    def fixture_arguments(self, workspace: Path) -> tuple[str, ...]:
        return (
            "--workspace",
            str(workspace),
            "--parent-agent",
            "saarius-i15-parenttest",
            "--parent-marker",
            "parent-marker-a1",
            "--left-agent",
            "saarius-i15-lefttest",
            "--left-marker",
            "left-marker-b2",
            "--right-agent",
            "saarius-i15-righttest",
            "--right-marker",
            "right-marker-c3",
            "--left-result",
            "left-test-a1.json",
            "--right-result",
            "right-test-b2.json",
            "--join-result",
            "join-test-c3.json",
        )

    def test_fixture_is_create_only_and_keeps_child_markers_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            fixture = self.run_harness(
                "build-fixture",
                *self.fixture_arguments(workspace),
            )
            self.assertEqual(fixture.returncode, 0, fixture.stderr)
            payload = json.loads(fixture.stdout)
            self.assertEqual(
                payload["schema"],
                "saarius.custom-agent-fanout-fixture.v1",
            )
            self.assertEqual(len(payload["profiles"]), 3)
            self.assertEqual(
                {row["agent"] for row in payload["profiles"]},
                {
                    "saarius-i15-parenttest",
                    "saarius-i15-lefttest",
                    "saarius-i15-righttest",
                },
            )

            parent = (
                workspace
                / ".agents/agents/saarius-i15-parenttest/agent.md"
            ).read_text(encoding="utf-8")
            left = (
                workspace
                / ".agents/agents/saarius-i15-lefttest/agent.md"
            ).read_text(encoding="utf-8")
            right = (
                workspace
                / ".agents/agents/saarius-i15-righttest/agent.md"
            ).read_text(encoding="utf-8")
            self.assertNotIn("left-marker-b2", parent)
            self.assertNotIn("right-marker-c3", parent)
            self.assertNotIn("left-test-a1.json", parent)
            self.assertNotIn("right-test-b2.json", parent)
            self.assertIn("saarius-i15-lefttest", parent)
            self.assertIn("saarius-i15-righttest", parent)
            self.assertNotIn("right-marker-c3", left)
            self.assertNotIn("left-marker-b2", right)
            self.assertEqual(
                (workspace / ".issue15/join").stat().st_mode & 0o777,
                0o500,
            )

            second = self.run_harness(
                "build-fixture",
                *self.fixture_arguments(workspace),
            )
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("absent or empty", second.stderr)

    def test_runner_verifier_and_postflight_are_source_blind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            controller = root / "controller"
            controller.mkdir()
            fixture = self.run_harness(
                "build-fixture",
                *self.fixture_arguments(workspace),
            )
            self.assertEqual(fixture.returncode, 0, fixture.stderr)
            fixture_payload = json.loads(fixture.stdout)
            profile_hashes = {
                row["agent"]: row["sha256"]
                for row in fixture_payload["profiles"]
            }

            fake_agy = root / "fake-agy"
            fake_agy.write_text(
                """#!/usr/bin/env python3
import json
import os
import pathlib
import re
import stat
import sys
import time

parent = os.environ["FANOUT_PARENT"]
if sys.argv[-1] == "agents":
    print("private-unrelated-agent")
    print(parent)
    print("private discovery diagnostic", file=sys.stderr)
    raise SystemExit(0)

workspace = pathlib.Path(sys.argv[sys.argv.index("--add-dir") + 1])
prompt = sys.argv[sys.argv.index("--print") + 1]
challenge = re.search(r"challenge: ([A-Za-z0-9_-]+)", prompt).group(1)
log = pathlib.Path(sys.argv[sys.argv.index("--log-file") + 1])
log.write_text("private raw fanout log", encoding="utf-8")
left = {
    "schema": "saarius.custom-agent.fanout-child.v1",
    "agent": os.environ["FANOUT_LEFT"],
    "challenge": challenge,
    "role_marker": os.environ["FANOUT_LEFT_MARKER"],
    "status": "child_ready",
}
right = {
    "schema": "saarius.custom-agent.fanout-child.v1",
    "agent": os.environ["FANOUT_RIGHT"],
    "challenge": challenge,
    "role_marker": os.environ["FANOUT_RIGHT_MARKER"],
    "status": "child_ready",
}
time.sleep(0.15)
(workspace / ".issue15/children" / os.environ["FANOUT_LEFT_RESULT"]).write_text(
    json.dumps(left),
    encoding="utf-8",
)
(workspace / ".issue15/children" / os.environ["FANOUT_RIGHT_RESULT"]).write_text(
    json.dumps(right),
    encoding="utf-8",
)
join_root = workspace / ".issue15/join"
deadline = time.monotonic() + 3
while not (stat.S_IMODE(join_root.stat().st_mode) & 0o200):
    if time.monotonic() >= deadline:
        raise SystemExit(18)
    time.sleep(0.01)
join = {
    "schema": "saarius.custom-agent.fanout-join.v1",
    "parent_agent": parent,
    "parent_marker": os.environ["FANOUT_PARENT_MARKER"],
    "challenge": challenge,
    "left": {
        "agent": os.environ["FANOUT_LEFT"],
        "role_marker": os.environ["FANOUT_LEFT_MARKER"],
    },
    "right": {
        "agent": os.environ["FANOUT_RIGHT"],
        "role_marker": os.environ["FANOUT_RIGHT_MARKER"],
    },
    "status": "joined",
}
(join_root / os.environ["FANOUT_JOIN_RESULT"]).write_text(
    json.dumps(join),
    encoding="utf-8",
)
print("private parent response")
print("private runtime diagnostic", file=sys.stderr)
""",
                encoding="utf-8",
            )
            fake_agy.chmod(0o755)
            environment = {
                "FANOUT_PARENT": "saarius-i15-parenttest",
                "FANOUT_PARENT_MARKER": "parent-marker-a1",
                "FANOUT_LEFT": "saarius-i15-lefttest",
                "FANOUT_LEFT_MARKER": "left-marker-b2",
                "FANOUT_RIGHT": "saarius-i15-righttest",
                "FANOUT_RIGHT_MARKER": "right-marker-c3",
                "FANOUT_LEFT_RESULT": "left-test-a1.json",
                "FANOUT_RIGHT_RESULT": "right-test-b2.json",
                "FANOUT_JOIN_RESULT": "join-test-c3.json",
            }

            runtime = self.run_harness(
                "run-print",
                "--agy",
                str(fake_agy),
                "--workspace",
                str(workspace),
                "--controller",
                str(controller),
                "--run-id",
                "fanout-test",
                "--parent-agent",
                "saarius-i15-parenttest",
                "--challenge",
                "fanout-challenge-d4",
                "--left-result",
                "left-test-a1.json",
                "--right-result",
                "right-test-b2.json",
                "--join-result",
                "join-test-c3.json",
                "--model",
                "test-model",
                "--effort",
                "low",
                "--discovery-timeout-seconds",
                "2",
                "--children-timeout-seconds",
                "2",
                "--timeout-seconds",
                "5",
                "--poll-ms",
                "10",
                env=environment,
            )
            self.assertEqual(runtime.returncode, 0, runtime.stderr)
            runtime_payload = json.loads(runtime.stdout)
            self.assertTrue(runtime_payload["passed"])
            self.assertTrue(runtime_payload["guard_admitted"])
            self.assertTrue(
                runtime_payload["runtime"][
                    "children_changed_before_quarantine"
                ]
            )
            self.assertTrue(
                runtime_payload["runtime"]["join_unchanged_at_release"]
            )
            self.assertTrue(
                runtime_payload["runtime"]["join_changed_after_release"]
            )
            self.assertNotIn("private-unrelated-agent", runtime.stdout)
            self.assertNotIn("private discovery diagnostic", runtime.stdout)
            self.assertNotIn("private parent response", runtime.stdout)
            self.assertNotIn("private runtime diagnostic", runtime.stdout)
            self.assertNotIn("private raw fanout log", runtime.stdout)
            for suffix in ("stdout.raw", "stderr.raw", "agy.raw"):
                self.assertFalse(
                    (controller / f"fanout-test-{suffix}").exists()
                )

            verification = self.run_harness(
                "verify",
                *self.fixture_arguments(workspace),
                "--challenge",
                "fanout-challenge-d4",
            )
            self.assertEqual(
                verification.returncode,
                0,
                verification.stderr,
            )
            self.assertTrue(json.loads(verification.stdout)["passed"])

            postflight = self.run_harness(
                "postflight",
                "--workspace",
                str(workspace),
                "--quarantine",
                str(controller / "fanout-test-agents-quarantine"),
                "--parent-agent",
                "saarius-i15-parenttest",
                "--left-agent",
                "saarius-i15-lefttest",
                "--right-agent",
                "saarius-i15-righttest",
                "--left-result",
                "left-test-a1.json",
                "--right-result",
                "right-test-b2.json",
                "--join-result",
                "join-test-c3.json",
                "--parent-profile-sha256",
                profile_hashes["saarius-i15-parenttest"],
                "--left-profile-sha256",
                profile_hashes["saarius-i15-lefttest"],
                "--right-profile-sha256",
                profile_hashes["saarius-i15-righttest"],
            )
            self.assertEqual(postflight.returncode, 0, postflight.stderr)
            self.assertTrue(json.loads(postflight.stdout)["passed"])

    def test_harness_has_no_teamwork_preview_dependency(self) -> None:
        self.assertNotIn(
            "teamwork-preview",
            HARNESS.read_text(encoding="utf-8"),
        )

    def test_runner_rejects_broken_join_gate_before_model_launch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            controller = root / "controller"
            controller.mkdir()
            fixture = self.run_harness(
                "build-fixture",
                *self.fixture_arguments(workspace),
            )
            self.assertEqual(fixture.returncode, 0, fixture.stderr)

            fake_agy = root / "fake-agy"
            fake_agy.write_text(
                "#!/bin/sh\nexit 97\n",
                encoding="utf-8",
            )
            fake_agy.chmod(0o755)
            (workspace / ".issue15/join").chmod(0o700)

            runtime = self.run_harness(
                "run-print",
                "--agy",
                str(fake_agy),
                "--workspace",
                str(workspace),
                "--controller",
                str(controller),
                "--run-id",
                "broken-gate-test",
                "--parent-agent",
                "saarius-i15-parenttest",
                "--challenge",
                "fanout-challenge-d4",
                "--left-result",
                "left-test-a1.json",
                "--right-result",
                "right-test-b2.json",
                "--join-result",
                "join-test-c3.json",
                "--model",
                "test-model",
                "--effort",
                "low",
            )
            self.assertNotEqual(runtime.returncode, 0)
            self.assertIn(
                "fan-out fixture mode or path type mismatch",
                runtime.stderr,
            )
            self.assertFalse(
                (controller / "broken-gate-test-stdout.raw").exists()
            )


if __name__ == "__main__":
    unittest.main()
