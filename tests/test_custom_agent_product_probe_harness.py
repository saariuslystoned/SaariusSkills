from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = (
    ROOT / "plans/custom-agents/scripts/product_probe_harness.py"
)

EXPECTED_POLICY = {
    "cases": [
        {"id": "P1", "decision": "APPROVED", "receipt_type": None},
        {
            "id": "P2",
            "decision": "REQUIRES_RECEIPT",
            "receipt_type": "SCREEN_TIMEOUT_RESTORE_PLAN",
        },
        {"id": "P3", "decision": "BLOCKED", "receipt_type": None},
        {"id": "P4", "decision": "BLOCKED", "receipt_type": None},
        {"id": "P5", "decision": "APPROVED", "receipt_type": None},
        {"id": "P6", "decision": "BLOCKED", "receipt_type": None},
    ]
}

EXPECTED_FRICTION = {
    "source_event_count": 6,
    "hotspots": [
        {
            "rank": 1,
            "app_package": "com.example.beta",
            "task_stage": "search",
            "blocker_class": "target_missing",
            "event_count": 1,
            "affected_runs": 1,
            "recovered_count": 0,
            "failed_count": 1,
            "human_intervention_count": 1,
            "general_fallback_count": 0,
        },
        {
            "rank": 2,
            "app_package": "com.example.alpha",
            "task_stage": "launch",
            "blocker_class": "transport_failed",
            "event_count": 2,
            "affected_runs": 2,
            "recovered_count": 1,
            "failed_count": 1,
            "human_intervention_count": 0,
            "general_fallback_count": 1,
        },
        {
            "rank": 3,
            "app_package": "com.example.gamma",
            "task_stage": "answer",
            "blocker_class": "verification_failed",
            "event_count": 3,
            "affected_runs": 2,
            "recovered_count": 3,
            "failed_count": 0,
            "human_intervention_count": 1,
            "general_fallback_count": 2,
        },
    ],
}


class CustomAgentProductProbeHarnessTests(unittest.TestCase):
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

    def single_arguments(self, workspace: Path) -> tuple[str, ...]:
        return (
            "--workspace",
            str(workspace),
            "--agent",
            "saarius-i15-pixel-single",
            "--marker",
            "single-marker-a1",
            "--result",
            "single-result-a1.json",
        )

    def custom_arguments(self, workspace: Path) -> tuple[str, ...]:
        return (
            "--workspace",
            str(workspace),
            "--parent-agent",
            "saarius-i15-pixel-parent",
            "--parent-marker",
            "parent-marker-a1",
            "--policy-agent",
            "saarius-i15-pixel-policy",
            "--policy-marker",
            "policy-marker-b2",
            "--policy-result",
            "policy-result-b2.json",
            "--friction-agent",
            "saarius-i15-pixel-friction",
            "--friction-marker",
            "friction-marker-c3",
            "--friction-result",
            "friction-result-c3.json",
            "--join-result",
            "custom-result-d4.json",
        )

    def make_fake_agy(self, path: Path) -> None:
        path.write_text(
            """#!/usr/bin/env python3
import json
import os
import pathlib
import re
import stat
import sys
import time

if sys.argv[-1] == "agents":
    print("private-unrelated-agent")
    print(os.environ["PROBE_DISCOVERY_AGENT"])
    print("private discovery diagnostic", file=sys.stderr)
    raise SystemExit(0)

workspace = pathlib.Path(sys.argv[sys.argv.index("--add-dir") + 1])
agent = sys.argv[sys.argv.index("--agent") + 1]
prompt = sys.argv[sys.argv.index("--print") + 1]
challenge = re.search(r"challenge: ([A-Za-z0-9_-]+)", prompt).group(1)
log = pathlib.Path(sys.argv[sys.argv.index("--log-file") + 1])
log.write_text("private product probe log", encoding="utf-8")
policy = json.loads(os.environ["PROBE_POLICY"])
friction = json.loads(os.environ["PROBE_FRICTION"])

if agent == os.environ.get("PROBE_SINGLE"):
    time.sleep(0.55)
    value = {
        "schema": "saarius.pixel-use-single-probe.v1",
        "agent": agent,
        "marker": os.environ["PROBE_SINGLE_MARKER"],
        "challenge": challenge,
        "policy": policy,
        "friction": friction,
        "status": "complete",
    }
    (
        workspace
        / ".issue15/result"
        / os.environ["PROBE_SINGLE_RESULT"]
    ).write_text(json.dumps(value), encoding="utf-8")
else:
    policy_value = {
        "schema": "saarius.pixel-use-policy-branch.v1",
        "agent": os.environ["PROBE_POLICY_AGENT"],
        "branch_marker": os.environ["PROBE_POLICY_MARKER"],
        "challenge": challenge,
        "policy": policy,
        "status": "complete",
    }
    friction_value = {
        "schema": "saarius.pixel-use-friction-branch.v1",
        "agent": os.environ["PROBE_FRICTION_AGENT"],
        "branch_marker": os.environ["PROBE_FRICTION_MARKER"],
        "challenge": challenge,
        "friction": friction,
        "status": "complete",
    }
    (
        workspace
        / ".issue15/branches"
        / os.environ["PROBE_POLICY_RESULT"]
    ).write_text(json.dumps(policy_value), encoding="utf-8")
    (
        workspace
        / ".issue15/branches"
        / os.environ["PROBE_FRICTION_RESULT"]
    ).write_text(json.dumps(friction_value), encoding="utf-8")
    join_root = workspace / ".issue15/join"
    deadline = time.monotonic() + 3
    while not (stat.S_IMODE(join_root.stat().st_mode) & 0o200):
        if time.monotonic() >= deadline:
            raise SystemExit(18)
        time.sleep(0.01)
    join = {
        "schema": "saarius.pixel-use-custom-probe.v1",
        "parent_agent": agent,
        "parent_marker": os.environ["PROBE_PARENT_MARKER"],
        "challenge": challenge,
        "policy_branch": {
            "agent": os.environ["PROBE_POLICY_AGENT"],
            "branch_marker": os.environ["PROBE_POLICY_MARKER"],
        },
        "friction_branch": {
            "agent": os.environ["PROBE_FRICTION_AGENT"],
            "branch_marker": os.environ["PROBE_FRICTION_MARKER"],
        },
        "policy": policy,
        "friction": friction,
        "status": "complete",
    }
    (
        join_root / os.environ["PROBE_JOIN_RESULT"]
    ).write_text(json.dumps(join), encoding="utf-8")

print("private parent response")
print("private runtime diagnostic", file=sys.stderr)
""",
            encoding="utf-8",
        )
        path.chmod(0o755)

    def common_environment(self) -> dict[str, str]:
        return {
            "PROBE_POLICY": json.dumps(EXPECTED_POLICY),
            "PROBE_FRICTION": json.dumps(EXPECTED_FRICTION),
            "PROBE_SINGLE": "saarius-i15-pixel-single",
            "PROBE_SINGLE_MARKER": "single-marker-a1",
            "PROBE_SINGLE_RESULT": "single-result-a1.json",
            "PROBE_PARENT_MARKER": "parent-marker-a1",
            "PROBE_POLICY_AGENT": "saarius-i15-pixel-policy",
            "PROBE_POLICY_MARKER": "policy-marker-b2",
            "PROBE_POLICY_RESULT": "policy-result-b2.json",
            "PROBE_FRICTION_AGENT": "saarius-i15-pixel-friction",
            "PROBE_FRICTION_MARKER": "friction-marker-c3",
            "PROBE_FRICTION_RESULT": "friction-result-c3.json",
            "PROBE_JOIN_RESULT": "custom-result-d4.json",
        }

    def test_fixtures_preserve_branch_source_blindness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            single_workspace = root / "single"
            custom_workspace = root / "custom"
            single = self.run_harness(
                "build-single",
                *self.single_arguments(single_workspace),
            )
            custom = self.run_harness(
                "build-custom",
                *self.custom_arguments(custom_workspace),
            )
            self.assertEqual(single.returncode, 0, single.stderr)
            self.assertEqual(custom.returncode, 0, custom.stderr)

            single_profile = (
                single_workspace
                / ".agents/agents/saarius-i15-pixel-single/agent.md"
            ).read_text(encoding="utf-8")
            parent = (
                custom_workspace
                / ".agents/agents/saarius-i15-pixel-parent/agent.md"
            ).read_text(encoding="utf-8")
            policy = (
                custom_workspace
                / ".agents/agents/saarius-i15-pixel-policy/agent.md"
            ).read_text(encoding="utf-8")
            friction = (
                custom_workspace
                / ".agents/agents/saarius-i15-pixel-friction/agent.md"
            ).read_text(encoding="utf-8")

            self.assertIn("sys.setting.dark_theme", single_profile)
            self.assertIn("com.example.alpha", single_profile)
            self.assertNotIn("sys.setting.dark_theme", parent)
            self.assertNotIn("com.example.alpha", parent)
            self.assertNotIn("policy-marker-b2", parent)
            self.assertNotIn("friction-marker-c3", parent)
            self.assertNotIn("policy-result-b2.json", parent)
            self.assertNotIn("friction-result-c3.json", parent)
            self.assertIn("sys.setting.dark_theme", policy)
            self.assertNotIn("com.example.alpha", policy)
            self.assertIn("com.example.alpha", friction)
            self.assertNotIn("sys.setting.dark_theme", friction)
            self.assertNotIn("friction-marker-c3", policy)
            self.assertNotIn("policy-marker-b2", friction)
            self.assertNotIn("custom-result-d4.json", policy)
            self.assertNotIn("custom-result-d4.json", friction)
            self.assertNotIn("teamwork-preview", HARNESS.read_text())

    def test_single_and_custom_runners_verify_and_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_agy = root / "fake-agy"
            self.make_fake_agy(fake_agy)
            environment = self.common_environment()

            single_workspace = root / "single"
            single_controller = root / "single-controller"
            single_controller.mkdir()
            single_fixture = self.run_harness(
                "build-single",
                *self.single_arguments(single_workspace),
            )
            self.assertEqual(
                single_fixture.returncode,
                0,
                single_fixture.stderr,
            )
            single_hash = json.loads(single_fixture.stdout)["profiles"][0][
                "sha256"
            ]
            environment["PROBE_DISCOVERY_AGENT"] = (
                "saarius-i15-pixel-single"
            )
            single_run = self.run_harness(
                "run-single",
                "--agy",
                str(fake_agy),
                "--workspace",
                str(single_workspace),
                "--controller",
                str(single_controller),
                "--run-id",
                "single-test-a1",
                "--challenge",
                "pixel-probe-a1",
                "--model",
                "test-model",
                "--effort",
                "low",
                "--agent",
                "saarius-i15-pixel-single",
                "--result",
                "single-result-a1.json",
                "--discovery-timeout-seconds",
                "2",
                "--timeout-seconds",
                "5",
                env=environment,
            )
            self.assertEqual(single_run.returncode, 0, single_run.stderr)
            single_payload = json.loads(single_run.stdout)
            self.assertTrue(single_payload["passed"])
            self.assertTrue(
                single_payload["runtime"][
                    "result_changed_after_quarantine"
                ]
            )
            self.assertNotIn("private", single_run.stdout)
            single_verify = self.run_harness(
                "verify-single",
                *self.single_arguments(single_workspace),
                "--challenge",
                "pixel-probe-a1",
            )
            self.assertEqual(single_verify.returncode, 0)
            self.assertTrue(json.loads(single_verify.stdout)["passed"])
            single_post = self.run_harness(
                "postflight",
                "--arm",
                "single",
                "--workspace",
                str(single_workspace),
                "--quarantine",
                str(single_controller / "single-test-a1-agents-quarantine"),
                "--agent",
                "saarius-i15-pixel-single",
                "--result",
                "single-result-a1.json",
                "--agent-profile-sha256",
                single_hash,
            )
            self.assertEqual(single_post.returncode, 0, single_post.stderr)

            custom_workspace = root / "custom"
            custom_controller = root / "custom-controller"
            custom_controller.mkdir()
            custom_fixture = self.run_harness(
                "build-custom",
                *self.custom_arguments(custom_workspace),
            )
            self.assertEqual(
                custom_fixture.returncode,
                0,
                custom_fixture.stderr,
            )
            custom_hashes = {
                row["agent"]: row["sha256"]
                for row in json.loads(custom_fixture.stdout)["profiles"]
            }
            environment["PROBE_DISCOVERY_AGENT"] = (
                "saarius-i15-pixel-parent"
            )
            custom_run = self.run_harness(
                "run-custom",
                "--agy",
                str(fake_agy),
                "--workspace",
                str(custom_workspace),
                "--controller",
                str(custom_controller),
                "--run-id",
                "custom-test-a1",
                "--challenge",
                "pixel-probe-a1",
                "--model",
                "test-model",
                "--effort",
                "low",
                "--parent-agent",
                "saarius-i15-pixel-parent",
                "--policy-result",
                "policy-result-b2.json",
                "--friction-result",
                "friction-result-c3.json",
                "--join-result",
                "custom-result-d4.json",
                "--discovery-timeout-seconds",
                "2",
                "--children-timeout-seconds",
                "2",
                "--timeout-seconds",
                "5",
                env=environment,
            )
            self.assertEqual(custom_run.returncode, 0, custom_run.stderr)
            custom_payload = json.loads(custom_run.stdout)
            self.assertTrue(custom_payload["passed"])
            self.assertTrue(
                custom_payload["runtime"][
                    "children_changed_before_quarantine"
                ]
            )
            self.assertTrue(
                custom_payload["runtime"]["join_changed_after_release"]
            )
            self.assertNotIn("private", custom_run.stdout)
            custom_verify = self.run_harness(
                "verify-custom",
                *self.custom_arguments(custom_workspace),
                "--challenge",
                "pixel-probe-a1",
            )
            self.assertEqual(custom_verify.returncode, 0)
            self.assertTrue(json.loads(custom_verify.stdout)["passed"])
            custom_post = self.run_harness(
                "postflight",
                "--arm",
                "custom",
                "--workspace",
                str(custom_workspace),
                "--quarantine",
                str(custom_controller / "custom-test-a1-agents-quarantine"),
                "--parent-agent",
                "saarius-i15-pixel-parent",
                "--policy-agent",
                "saarius-i15-pixel-policy",
                "--friction-agent",
                "saarius-i15-pixel-friction",
                "--policy-result",
                "policy-result-b2.json",
                "--friction-result",
                "friction-result-c3.json",
                "--join-result",
                "custom-result-d4.json",
                "--parent-profile-sha256",
                custom_hashes["saarius-i15-pixel-parent"],
                "--policy-profile-sha256",
                custom_hashes["saarius-i15-pixel-policy"],
                "--friction-profile-sha256",
                custom_hashes["saarius-i15-pixel-friction"],
            )
            self.assertEqual(custom_post.returncode, 0, custom_post.stderr)
            self.assertTrue(json.loads(custom_post.stdout)["passed"])

            for controller, run_id in (
                (single_controller, "single-test-a1"),
                (custom_controller, "custom-test-a1"),
            ):
                for suffix in ("stdout.raw", "stderr.raw", "agy.raw"):
                    self.assertFalse(
                        (controller / f"{run_id}-{suffix}").exists()
                    )

    def test_custom_runner_rejects_broken_join_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "custom"
            controller = root / "controller"
            controller.mkdir()
            fixture = self.run_harness(
                "build-custom",
                *self.custom_arguments(workspace),
            )
            self.assertEqual(fixture.returncode, 0, fixture.stderr)
            (workspace / ".issue15/join").chmod(0o700)
            fake_agy = root / "fake-agy"
            fake_agy.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
            fake_agy.chmod(0o755)
            runtime = self.run_harness(
                "run-custom",
                "--agy",
                str(fake_agy),
                "--workspace",
                str(workspace),
                "--controller",
                str(controller),
                "--run-id",
                "broken-gate-a1",
                "--challenge",
                "pixel-probe-a1",
                "--model",
                "test-model",
                "--effort",
                "low",
                "--parent-agent",
                "saarius-i15-pixel-parent",
                "--policy-result",
                "policy-result-b2.json",
                "--friction-result",
                "friction-result-c3.json",
                "--join-result",
                "custom-result-d4.json",
            )
            self.assertNotEqual(runtime.returncode, 0)
            self.assertIn(
                "custom product fixture mode or path type mismatch",
                runtime.stderr,
            )
            self.assertFalse(
                (controller / "broken-gate-a1-stdout.raw").exists()
            )


if __name__ == "__main__":
    unittest.main()
