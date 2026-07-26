from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "plans/custom-agents/scripts/fanout4_harness.py"


class CustomAgentFanout4HarnessTests(unittest.TestCase):
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

    def profile_arguments(
        self,
        workspace: Path,
        *,
        fault_child: str = "none",
    ) -> tuple[str, ...]:
        return (
            "--workspace",
            str(workspace),
            "--parent-agent",
            "saarius-i15-parent4test",
            "--parent-marker",
            "parent4-marker-a1",
            "--alpha-agent",
            "saarius-i15-alpha4test",
            "--alpha-marker",
            "alpha4-marker-b2",
            "--alpha-result",
            "alpha4-result-a1.json",
            "--beta-agent",
            "saarius-i15-beta4test",
            "--beta-marker",
            "beta4-marker-c3",
            "--beta-result",
            "beta4-result-b2.json",
            "--gamma-agent",
            "saarius-i15-gamma4test",
            "--gamma-marker",
            "gamma4-marker-d4",
            "--gamma-result",
            "gamma4-result-c3.json",
            "--delta-agent",
            "saarius-i15-delta4test",
            "--delta-marker",
            "delta4-marker-e5",
            "--delta-result",
            "delta4-result-d4.json",
            "--join-result",
            "join4-result-e5.json",
            "--fault-child",
            fault_child,
        )

    def result_arguments(self) -> tuple[str, ...]:
        return (
            "--alpha-result",
            "alpha4-result-a1.json",
            "--beta-result",
            "beta4-result-b2.json",
            "--gamma-result",
            "gamma4-result-c3.json",
            "--delta-result",
            "delta4-result-d4.json",
            "--join-result",
            "join4-result-e5.json",
        )

    def fake_environment(self, behavior: str) -> dict[str, str]:
        return {
            "FANOUT4_BEHAVIOR": behavior,
            "FANOUT4_PARENT": "saarius-i15-parent4test",
            "FANOUT4_PARENT_MARKER": "parent4-marker-a1",
            "FANOUT4_ALPHA_AGENT": "saarius-i15-alpha4test",
            "FANOUT4_ALPHA_MARKER": "alpha4-marker-b2",
            "FANOUT4_ALPHA_RESULT": "alpha4-result-a1.json",
            "FANOUT4_BETA_AGENT": "saarius-i15-beta4test",
            "FANOUT4_BETA_MARKER": "beta4-marker-c3",
            "FANOUT4_BETA_RESULT": "beta4-result-b2.json",
            "FANOUT4_GAMMA_AGENT": "saarius-i15-gamma4test",
            "FANOUT4_GAMMA_MARKER": "gamma4-marker-d4",
            "FANOUT4_GAMMA_RESULT": "gamma4-result-c3.json",
            "FANOUT4_DELTA_AGENT": "saarius-i15-delta4test",
            "FANOUT4_DELTA_MARKER": "delta4-marker-e5",
            "FANOUT4_DELTA_RESULT": "delta4-result-d4.json",
            "FANOUT4_JOIN_RESULT": "join4-result-e5.json",
        }

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

parent = os.environ["FANOUT4_PARENT"]
if sys.argv[-1] == "agents":
    print("private-unrelated-agent")
    print(parent)
    print("private discovery diagnostic", file=sys.stderr)
    raise SystemExit(0)

workspace = pathlib.Path(sys.argv[sys.argv.index("--add-dir") + 1])
prompt = sys.argv[sys.argv.index("--print") + 1]
challenge = re.search(r"challenge: ([A-Za-z0-9_-]+)", prompt).group(1)
log = pathlib.Path(sys.argv[sys.argv.index("--log-file") + 1])
log.write_text("private raw fanout4 log", encoding="utf-8")
behavior = os.environ["FANOUT4_BEHAVIOR"]
if behavior == "watchdog-timeout":
    time.sleep(5)
    raise SystemExit(0)

sides = ("ALPHA", "BETA", "GAMMA", "DELTA")
active = sides[:-1] if behavior == "child-failure" else sides
children = []
for side in active:
    child = {
        "schema": "saarius.custom-agent.fanout-child.v1",
        "agent": os.environ[f"FANOUT4_{side}_AGENT"],
        "challenge": challenge,
        "role_marker": os.environ[f"FANOUT4_{side}_MARKER"],
        "status": "child_ready",
    }
    (workspace / ".issue15/children" / os.environ[
        f"FANOUT4_{side}_RESULT"
    ]).write_text(json.dumps(child), encoding="utf-8")
    children.append(
        {
            "side": side.lower(),
            "agent": child["agent"],
            "role_marker": child["role_marker"],
        }
    )

if behavior == "success":
    join_root = workspace / ".issue15/join"
    deadline = time.monotonic() + 3
    while not (stat.S_IMODE(join_root.stat().st_mode) & 0o200):
        if time.monotonic() >= deadline:
            raise SystemExit(18)
        time.sleep(0.01)
    join = {
        "schema": "saarius.custom-agent.fanout4-join.v1",
        "parent_agent": parent,
        "parent_marker": os.environ["FANOUT4_PARENT_MARKER"],
        "challenge": challenge,
        "children": children,
        "status": "joined",
    }
    (join_root / os.environ["FANOUT4_JOIN_RESULT"]).write_text(
        json.dumps(join),
        encoding="utf-8",
    )
elif behavior == "deny-join":
    join_path = (
        workspace
        / ".issue15/join"
        / os.environ["FANOUT4_JOIN_RESULT"]
    )
    for _ in range(2):
        try:
            join_path.write_text("must-not-write", encoding="utf-8")
        except PermissionError:
            pass
        else:
            raise SystemExit(19)
        time.sleep(0.05)
else:
    time.sleep(0.15)

print("private parent response")
print("private runtime diagnostic", file=sys.stderr)
""",
            encoding="utf-8",
        )
        path.chmod(0o755)

    def test_fixture_hides_all_child_markers_and_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            fixture = self.run_harness(
                "build-fixture",
                *self.profile_arguments(workspace),
            )
            self.assertEqual(fixture.returncode, 0, fixture.stderr)
            payload = json.loads(fixture.stdout)
            self.assertEqual(
                payload["schema"],
                "saarius.custom-agent-fanout4-fixture.v1",
            )
            self.assertEqual(len(payload["profiles"]), 5)
            parent = (
                workspace
                / ".agents/agents/saarius-i15-parent4test/agent.md"
            ).read_text(encoding="utf-8")
            for marker in (
                "alpha4-marker-b2",
                "beta4-marker-c3",
                "gamma4-marker-d4",
                "delta4-marker-e5",
            ):
                self.assertNotIn(marker, parent)
            for result in (
                "alpha4-result-a1.json",
                "beta4-result-b2.json",
                "gamma4-result-c3.json",
                "delta4-result-d4.json",
            ):
                self.assertNotIn(result, parent)
            child_expectations = {
                "alpha": ("alpha4-marker-b2", "alpha4-result-a1.json"),
                "beta": ("beta4-marker-c3", "beta4-result-b2.json"),
                "gamma": ("gamma4-marker-d4", "gamma4-result-c3.json"),
                "delta": ("delta4-marker-e5", "delta4-result-d4.json"),
            }
            for side, own_values in child_expectations.items():
                child = (
                    workspace
                    / (
                        ".agents/agents/"
                        f"saarius-i15-{side}4test/agent.md"
                    )
                ).read_text(encoding="utf-8")
                for other_side, other_values in child_expectations.items():
                    if other_side != side:
                        for value in other_values:
                            self.assertNotIn(value, child)
                self.assertNotIn("join4-result-e5.json", child)
                for own_value in own_values:
                    self.assertIn(own_value, child)
            self.assertEqual(
                (workspace / ".issue15/join").stat().st_mode & 0o777,
                0o500,
            )

    def test_success_and_containment_modes_are_source_blind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_agy = root / "fake-agy"
            self.make_fake_agy(fake_agy)
            for mode in (
                "success",
                "deny-join",
                "child-failure",
                "watchdog-timeout",
            ):
                with self.subTest(mode=mode):
                    workspace = root / f"workspace-{mode}"
                    controller = root / f"controller-{mode}"
                    controller.mkdir()
                    fault_child = (
                        "delta" if mode == "child-failure" else "none"
                    )
                    profile_args = self.profile_arguments(
                        workspace,
                        fault_child=fault_child,
                    )
                    fixture = self.run_harness(
                        "build-fixture",
                        *profile_args,
                    )
                    self.assertEqual(
                        fixture.returncode,
                        0,
                        fixture.stderr,
                    )
                    fixture_payload = json.loads(fixture.stdout)
                    hashes = {
                        row["agent"]: row["sha256"]
                        for row in fixture_payload["profiles"]
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
                        f"fanout4-{mode}",
                        "--parent-agent",
                        "saarius-i15-parent4test",
                        "--challenge",
                        f"challenge-{mode}",
                        *self.result_arguments(),
                        "--mode",
                        mode,
                        "--fault-child",
                        fault_child,
                        "--model",
                        "test-model",
                        "--effort",
                        "low",
                        "--discovery-timeout-seconds",
                        "2",
                        "--children-timeout-seconds",
                        "1" if mode == "watchdog-timeout" else "3",
                        "--timeout-seconds",
                        "6",
                        "--poll-ms",
                        "10",
                        env=self.fake_environment(mode),
                    )
                    self.assertEqual(
                        runtime.returncode,
                        0,
                        runtime.stderr,
                    )
                    runtime_payload = json.loads(runtime.stdout)
                    self.assertTrue(runtime_payload["passed"])
                    self.assertNotIn(
                        "private-unrelated-agent",
                        runtime.stdout,
                    )
                    self.assertNotIn(
                        "private raw fanout4 log",
                        runtime.stdout,
                    )

                    verification = self.run_harness(
                        "verify",
                        *profile_args,
                        "--challenge",
                        f"challenge-{mode}",
                        "--mode",
                        mode,
                    )
                    self.assertEqual(
                        verification.returncode,
                        0,
                        verification.stderr,
                    )
                    self.assertTrue(
                        json.loads(verification.stdout)["passed"]
                    )

                    postflight = self.run_harness(
                        "postflight",
                        *profile_args,
                        "--quarantine",
                        str(
                            controller
                            / f"fanout4-{mode}-agents-quarantine"
                        ),
                        "--mode",
                        mode,
                        "--parent-profile-sha256",
                        hashes["saarius-i15-parent4test"],
                        "--alpha-profile-sha256",
                        hashes["saarius-i15-alpha4test"],
                        "--beta-profile-sha256",
                        hashes["saarius-i15-beta4test"],
                        "--gamma-profile-sha256",
                        hashes["saarius-i15-gamma4test"],
                        "--delta-profile-sha256",
                        hashes["saarius-i15-delta4test"],
                    )
                    self.assertEqual(
                        postflight.returncode,
                        0,
                        postflight.stderr,
                    )
                    self.assertTrue(
                        json.loads(postflight.stdout)["passed"]
                    )
                    for suffix in (
                        "stdout.raw",
                        "stderr.raw",
                        "agy.raw",
                    ):
                        self.assertFalse(
                            (
                                controller
                                / f"fanout4-{mode}-{suffix}"
                            ).exists()
                        )

    def test_harness_has_no_teamwork_preview_dependency(self) -> None:
        self.assertNotIn(
            "teamwork-preview",
            HARNESS.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
