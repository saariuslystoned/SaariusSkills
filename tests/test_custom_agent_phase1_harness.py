from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "plans/custom-agents/scripts/phase1_harness.py"
MANIFEST = ROOT / "fixtures/custom-agents/phase1/manifest.json"


class CustomAgentPhase1HarnessTests(unittest.TestCase):
    def run_harness(
        self,
        *arguments: str,
        stdin: str = "",
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        return subprocess.run(
            [sys.executable, str(HARNESS), *arguments],
            input=stdin,
            text=True,
            capture_output=True,
            env=process_env,
            check=False,
        )

    def test_materialize_is_create_only_and_hashes_files(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            workspace = Path(parent) / "workspace"
            result = self.run_harness(
                "materialize",
                "--workspace",
                str(workspace),
                "--init-git",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(
                payload["schema"], "saarius.custom-agent-materialization.v1"
            )
            self.assertEqual(payload["file_count"], 6)
            self.assertTrue((workspace / ".git").is_dir())
            self.assertTrue(
                (workspace / ".issue15/phase1_harness.py").is_file()
            )

            second = self.run_harness(
                "materialize",
                "--workspace",
                str(workspace),
            )
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("absent or empty", second.stderr)

    def test_inventory_retains_only_expected_names_and_digest(self) -> None:
        raw = "\n".join(
            [
                "default",
                "private-unrelated-name",
                "saarius-issue15-recon-v1",
                "saarius-issue15-implementation-v1",
                "saarius-issue15-verification-v1",
                "saarius-issue15-proof-v1",
            ]
        )
        result = self.run_harness("inventory", stdin=raw)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["expected_found_count"], 4)
        self.assertNotIn("private-unrelated-name", result.stdout)

    def test_plugin_inventory_retains_only_expected_name_and_digest(self) -> None:
        raw = "\n".join(
            [
                "private-unrelated-plugin",
                "saarius-issue15-observer",
                "private@example.test",
            ]
        )
        result = self.run_harness(
            "plugin-inventory",
            "--name",
            "saarius-issue15-observer",
            stdin=raw,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["expected_found"])
        self.assertNotIn("private-unrelated-plugin", result.stdout)
        self.assertNotIn("private@example.test", result.stdout)

    def test_materialize_phase1b_uses_workspace_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            workspace = Path(parent) / "workspace"
            result = self.run_harness(
                "materialize",
                "--workspace",
                str(workspace),
                "--fixture-set",
                "phase1b",
                "--init-git",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["file_count"], 7)
            plugin_root = (
                workspace
                / ".agents/plugins/saarius-issue15-observer"
            )
            self.assertTrue((plugin_root / "plugin.json").is_file())
            self.assertTrue((plugin_root / "hooks.json").is_file())
            self.assertFalse((workspace / ".agents/hooks.json").exists())

    def test_runtime_fixture_print_run_and_postflight_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            controller = root / "controller"
            controller.mkdir()
            agent = "saarius-i15-testagent"
            marker = "test-marker"
            challenge = "test-challenge"
            fixture = self.run_harness(
                "build-runtime-fixture",
                "--workspace",
                str(workspace),
                "--agent",
                agent,
                "--role",
                "reconnaissance",
                "--role-marker",
                marker,
            )
            self.assertEqual(fixture.returncode, 0, fixture.stderr)
            fixture_payload = json.loads(fixture.stdout)

            fake_agy = root / "fake-agy"
            fake_agy.write_text(
                """#!/usr/bin/env python3
import json
import pathlib
import re
import sys
import time

prompt = sys.argv[sys.argv.index("--print") + 1]
challenge = re.search(r"challenge: ([A-Za-z0-9_-]+)", prompt).group(1)
workspace = pathlib.Path(sys.argv[sys.argv.index("--add-dir") + 1])
agent = sys.argv[sys.argv.index("--agent") + 1]
log = pathlib.Path(sys.argv[sys.argv.index("--log-file") + 1])
log.write_text("private raw log", encoding="utf-8")
time.sleep(0.25)
(workspace / ".issue15/result.json").write_text(
    json.dumps(
        {
            "schema": "saarius.custom-agent.identity.v1",
            "agent": agent,
            "challenge": challenge,
            "role_marker": "test-marker",
            "status": "identity_ready",
        }
    ),
    encoding="utf-8",
)
print("private model response")
print("private diagnostic", file=sys.stderr)
""",
                encoding="utf-8",
            )
            fake_agy.chmod(0o755)

            runtime = self.run_harness(
                "run-print",
                "--agy",
                str(fake_agy),
                "--workspace",
                str(workspace),
                "--controller",
                str(controller),
                "--run-id",
                "runtime-test",
                "--agent",
                agent,
                "--challenge",
                challenge,
                "--model",
                "test-model",
                "--effort",
                "low",
                "--quarantine-delay-ms",
                "100",
                "--timeout-seconds",
                "3",
            )
            self.assertEqual(runtime.returncode, 0, runtime.stderr)
            runtime_payload = json.loads(runtime.stdout)
            self.assertEqual(runtime_payload["process_exit"], 0)
            self.assertTrue(runtime_payload["result_changed_after_quarantine"])
            self.assertFalse(runtime_payload["raw_artifacts_retained"])
            self.assertNotIn("private model response", runtime.stdout)
            self.assertNotIn("private diagnostic", runtime.stdout)
            self.assertNotIn("private raw log", runtime.stdout)
            for suffix in ("stdout.raw", "stderr.raw", "agy.raw"):
                self.assertFalse((controller / f"runtime-test-{suffix}").exists())

            verification = self.run_harness(
                "verify-result",
                "--result",
                str(workspace / ".issue15/result.json"),
                "--agent",
                agent,
                "--challenge",
                challenge,
                "--role-marker",
                marker,
            )
            self.assertEqual(verification.returncode, 0, verification.stderr)
            self.assertTrue(json.loads(verification.stdout)["passed"])

            postflight = self.run_harness(
                "runtime-postflight",
                "--workspace",
                str(workspace),
                "--quarantine",
                str(controller / "runtime-test-agents-quarantine"),
                "--agent",
                agent,
                "--expected-profile-sha256",
                fixture_payload["profile_sha256"],
            )
            self.assertEqual(postflight.returncode, 0, postflight.stderr)
            self.assertTrue(json.loads(postflight.stdout)["passed"])

    def test_runtime_negative_postflight_accepts_unchanged_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            controller = root / "controller"
            controller.mkdir()
            profile_agent = "saarius-i15-decoyagent"
            launched_agent = "saarius-i15-unknownagent"
            fixture = self.run_harness(
                "build-runtime-fixture",
                "--workspace",
                str(workspace),
                "--agent",
                profile_agent,
                "--role",
                "verification",
                "--role-marker",
                "negative-marker",
            )
            self.assertEqual(fixture.returncode, 0, fixture.stderr)
            fixture_payload = json.loads(fixture.stdout)
            quarantine = controller / "negative-agents-quarantine"
            (workspace / ".agents").rename(quarantine)

            postflight = self.run_harness(
                "runtime-postflight",
                "--workspace",
                str(workspace),
                "--quarantine",
                str(quarantine),
                "--agent",
                launched_agent,
                "--profile-agent",
                profile_agent,
                "--expected-profile-sha256",
                fixture_payload["profile_sha256"],
                "--result-state",
                "unchanged",
            )
            self.assertEqual(postflight.returncode, 0, postflight.stderr)
            self.assertTrue(json.loads(postflight.stdout)["passed"])

    def test_guarded_run_rejects_absent_and_duplicate_before_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            controller = root / "controller"
            controller.mkdir()
            agent = "saarius-i15-guardtest"
            fixture = self.run_harness(
                "build-runtime-fixture",
                "--workspace",
                str(workspace),
                "--agent",
                agent,
                "--role",
                "reconnaissance",
                "--role-marker",
                "guard-marker",
            )
            self.assertEqual(fixture.returncode, 0, fixture.stderr)

            fake_agy = root / "fake-agy"
            fake_agy.write_text(
                """#!/usr/bin/env python3
import os
import pathlib
import sys

agent = os.environ["FAKE_AGENT"]
mode = os.environ["FAKE_DISCOVERY_MODE"]
if sys.argv[-1] == "agents":
    print("private-unrelated-agent")
    if mode == "exact":
        print(agent)
    elif mode == "duplicate":
        print(agent)
        print(agent)
    raise SystemExit(0)

pathlib.Path(os.environ["FAKE_MODEL_SENTINEL"]).write_text(
    "model-started",
    encoding="utf-8",
)
raise SystemExit(17)
""",
                encoding="utf-8",
            )
            fake_agy.chmod(0o755)
            sentinel = root / "model-started"
            common = (
                "guarded-run-print",
                "--agy",
                str(fake_agy),
                "--workspace",
                str(workspace),
                "--controller",
                str(controller),
                "--agent",
                agent,
                "--challenge",
                "guard-challenge",
                "--model",
                "test-model",
                "--effort",
                "low",
                "--timeout-seconds",
                "3",
                "--discovery-timeout-seconds",
                "2",
            )
            common_env = {
                "FAKE_AGENT": agent,
                "FAKE_MODEL_SENTINEL": str(sentinel),
            }

            absent = self.run_harness(
                *common,
                "--run-id",
                "guard-absent",
                env={**common_env, "FAKE_DISCOVERY_MODE": "absent"},
            )
            self.assertEqual(absent.returncode, 2, absent.stderr)
            absent_payload = json.loads(absent.stdout)
            self.assertFalse(absent_payload["admitted"])
            self.assertEqual(absent_payload["gate_reason"], "agent_absent")
            self.assertEqual(
                absent_payload["discovery"]["exact_name_occurrences"],
                0,
            )
            self.assertFalse(absent_payload["model_launch_started"])
            self.assertFalse(sentinel.exists())
            self.assertNotIn("private-unrelated-agent", absent.stdout)

            duplicate = self.run_harness(
                *common,
                "--run-id",
                "guard-duplicate",
                env={**common_env, "FAKE_DISCOVERY_MODE": "duplicate"},
            )
            self.assertEqual(duplicate.returncode, 2, duplicate.stderr)
            duplicate_payload = json.loads(duplicate.stdout)
            self.assertFalse(duplicate_payload["admitted"])
            self.assertEqual(
                duplicate_payload["gate_reason"],
                "agent_ambiguous",
            )
            self.assertEqual(
                duplicate_payload["discovery"]["exact_name_occurrences"],
                2,
            )
            self.assertFalse(duplicate_payload["model_launch_started"])
            self.assertFalse(
                duplicate_payload["discovery"]["raw_retained"]
            )
            self.assertFalse(sentinel.exists())
            self.assertNotIn("private-unrelated-agent", duplicate.stdout)

    def test_guarded_run_admits_exact_name_and_preserves_oracle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            controller = root / "controller"
            controller.mkdir()
            agent = "saarius-i15-guardpositive"
            marker = "guard-positive-marker"
            challenge = "guard-positive-challenge"
            fixture = self.run_harness(
                "build-runtime-fixture",
                "--workspace",
                str(workspace),
                "--agent",
                agent,
                "--role",
                "verification",
                "--role-marker",
                marker,
            )
            self.assertEqual(fixture.returncode, 0, fixture.stderr)
            fixture_payload = json.loads(fixture.stdout)

            fake_agy = root / "fake-agy"
            fake_agy.write_text(
                """#!/usr/bin/env python3
import json
import os
import pathlib
import re
import sys
import time

agent = os.environ["FAKE_AGENT"]
if sys.argv[-1] == "agents":
    print("private-unrelated-agent")
    print(agent)
    print("private discovery diagnostic", file=sys.stderr)
    raise SystemExit(0)

pathlib.Path(os.environ["FAKE_MODEL_SENTINEL"]).write_text(
    "model-started",
    encoding="utf-8",
)
prompt = sys.argv[sys.argv.index("--print") + 1]
challenge = re.search(r"challenge: ([A-Za-z0-9_-]+)", prompt).group(1)
workspace = pathlib.Path(sys.argv[sys.argv.index("--add-dir") + 1])
log = pathlib.Path(sys.argv[sys.argv.index("--log-file") + 1])
log.write_text("private raw log", encoding="utf-8")
time.sleep(0.25)
(workspace / ".issue15/result.json").write_text(
    json.dumps(
        {
            "schema": "saarius.custom-agent.identity.v1",
            "agent": agent,
            "challenge": challenge,
            "role_marker": "guard-positive-marker",
            "status": "identity_ready",
        }
    ),
    encoding="utf-8",
)
print("private model response")
""",
                encoding="utf-8",
            )
            fake_agy.chmod(0o755)
            sentinel = root / "model-started"

            guarded = self.run_harness(
                "guarded-run-print",
                "--agy",
                str(fake_agy),
                "--workspace",
                str(workspace),
                "--controller",
                str(controller),
                "--run-id",
                "guard-positive",
                "--agent",
                agent,
                "--challenge",
                challenge,
                "--model",
                "test-model",
                "--effort",
                "low",
                "--quarantine-delay-ms",
                "100",
                "--timeout-seconds",
                "3",
                "--discovery-timeout-seconds",
                "2",
                env={
                    "FAKE_AGENT": agent,
                    "FAKE_MODEL_SENTINEL": str(sentinel),
                },
            )
            self.assertEqual(guarded.returncode, 0, guarded.stderr)
            guarded_payload = json.loads(guarded.stdout)
            self.assertTrue(guarded_payload["admitted"])
            self.assertEqual(guarded_payload["gate_reason"], "exactly_one")
            self.assertEqual(
                guarded_payload["discovery"]["exact_name_occurrences"],
                1,
            )
            self.assertTrue(guarded_payload["model_launch_started"])
            self.assertTrue(
                guarded_payload["runtime"][
                    "result_changed_after_quarantine"
                ]
            )
            self.assertTrue(sentinel.is_file())
            self.assertNotIn("private-unrelated-agent", guarded.stdout)
            self.assertNotIn("private discovery diagnostic", guarded.stdout)
            self.assertNotIn("private model response", guarded.stdout)

            verification = self.run_harness(
                "verify-result",
                "--result",
                str(workspace / ".issue15/result.json"),
                "--agent",
                agent,
                "--challenge",
                challenge,
                "--role-marker",
                marker,
            )
            self.assertEqual(verification.returncode, 0, verification.stderr)
            self.assertTrue(json.loads(verification.stdout)["passed"])

            postflight = self.run_harness(
                "runtime-postflight",
                "--workspace",
                str(workspace),
                "--quarantine",
                str(controller / "guard-positive-agents-quarantine"),
                "--agent",
                agent,
                "--expected-profile-sha256",
                fixture_payload["profile_sha256"],
            )
            self.assertEqual(postflight.returncode, 0, postflight.stderr)
            self.assertTrue(json.loads(postflight.stdout)["passed"])

    def test_hook_denies_reads_and_redacts_sensitive_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event_log = root / "events.jsonl"
            sentinel = root / "write.sentinel"
            env = {
                "ISSUE15_EVENT_LOG": str(event_log),
                "ISSUE15_RUN_SALT": "test-salt",
                "ISSUE15_WRITE_SENTINEL": str(sentinel),
                "ISSUE15_WORKSPACE": str(root),
                "ISSUE15_RESULT_FILE": str(root / ".issue15/result.json"),
                "ISSUE15_ALLOW_ONE_WRITE": "1",
            }
            payload = {
                "conversationId": "private-conversation-id",
                "workspacePaths": ["/private/workspace/path"],
                "transcriptPath": "/private/transcript.jsonl",
                "artifactDirectoryPath": "/private/artifacts",
                "stepIdx": 2,
                "toolCall": {
                    "name": "view_file",
                    "args": {
                        "AbsolutePath": "/private/secret.txt",
                        "UntrustedValue": "credential-shaped-private-value",
                    },
                },
            }
            result = self.run_harness(
                "hook",
                "PreToolUse",
                stdin=json.dumps(payload),
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["decision"], "deny")
            retained = event_log.read_text(encoding="utf-8")
            self.assertNotIn("private-conversation-id", retained)
            self.assertNotIn("/private/workspace/path", retained)
            self.assertNotIn("/private/transcript.jsonl", retained)
            self.assertNotIn("credential-shaped-private-value", retained)
            event = json.loads(retained)
            self.assertEqual(event["tool_name"], "view_file")
            self.assertEqual(
                event["tool_arg_keys"], ["AbsolutePath", "UntrustedValue"]
            )
            self.assertFalse(event["exact_result_target"])

    def test_hook_allows_exactly_one_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".issue15").mkdir()
            env = {
                "ISSUE15_EVENT_LOG": str(root / "events.jsonl"),
                "ISSUE15_RUN_SALT": "test-salt",
                "ISSUE15_WRITE_SENTINEL": str(root / "write.sentinel"),
                "ISSUE15_WORKSPACE": str(root),
                "ISSUE15_RESULT_FILE": str(root / ".issue15/result.json"),
                "ISSUE15_ALLOW_ONE_WRITE": "1",
            }
            payload = {
                "conversationId": "actor",
                "workspacePaths": ["/workspace"],
                "stepIdx": 1,
                "toolCall": {
                    "name": "write_to_file",
                    "args": {
                        "TargetFile": ".issue15/result.json",
                        "CodeContent": "{}",
                    },
                },
            }
            wrong_payload = json.loads(json.dumps(payload))
            wrong_payload["toolCall"]["args"]["TargetFile"] = "wrong.json"
            wrong = self.run_harness(
                "hook",
                "PreToolUse",
                stdin=json.dumps(wrong_payload),
                env=env,
            )
            first = self.run_harness(
                "hook",
                "PreToolUse",
                stdin=json.dumps(payload),
                env=env,
            )
            second = self.run_harness(
                "hook",
                "PreToolUse",
                stdin=json.dumps(payload),
                env=env,
            )
            self.assertEqual(json.loads(wrong.stdout)["decision"], "deny")
            self.assertEqual(json.loads(first.stdout)["decision"], "allow")
            self.assertEqual(json.loads(second.stdout)["decision"], "deny")

    def test_log_sanitizer_emits_only_expected_agent_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_log = root / "raw.jsonl"
            sanitized = root / "sanitized.json"
            raw_log.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "agent": {
                                    "name": "saarius-issue15-recon-v1"
                                },
                                "prompt": "private prompt",
                                "email": "private@example.test",
                            }
                        ),
                        json.dumps(
                            {
                                "message": "private model response",
                                "profile": {"name": "unrelated-agent"},
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            result = self.run_harness(
                "sanitize-log",
                "--input",
                str(raw_log),
                "--output",
                str(sanitized),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            retained = sanitized.read_text(encoding="utf-8")
            self.assertIn("saarius-issue15-recon-v1", retained)
            self.assertNotIn("private prompt", retained)
            self.assertNotIn("private@example.test", retained)
            self.assertNotIn("private model response", retained)
            self.assertNotIn("unrelated-agent", retained)

    def test_result_verifier_requires_exact_bounded_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result_path = Path(directory) / "result.json"
            result_path.write_text(
                json.dumps(
                    {
                        "schema": "saarius.custom-agent.identity.v1",
                        "agent": "saarius-issue15-proof-v1",
                        "challenge": "challenge-123",
                        "role_marker": "proof-e84a1c39",
                        "status": "identity_ready",
                    }
                ),
                encoding="utf-8",
            )
            passed = self.run_harness(
                "verify-result",
                "--result",
                str(result_path),
                "--agent",
                "saarius-issue15-proof-v1",
                "--challenge",
                "challenge-123",
            )
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertTrue(json.loads(passed.stdout)["passed"])

            value = json.loads(result_path.read_text(encoding="utf-8"))
            value["extra"] = "not allowed"
            result_path.write_text(json.dumps(value), encoding="utf-8")
            failed = self.run_harness(
                "verify-result",
                "--result",
                str(result_path),
                "--agent",
                "saarius-issue15-proof-v1",
                "--challenge",
                "challenge-123",
            )
            self.assertEqual(failed.returncode, 2)
            self.assertIn("field_set_mismatch", failed.stdout)

    def test_manifest_and_schemas_are_bounded(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["agents"]), 4)
        self.assertEqual(len({row["name"] for row in manifest["agents"]}), 4)
        for row in manifest["agents"]:
            self.assertTrue(row["main_agent"])
            self.assertTrue(row["subagent"])

        for relative in [
            "plans/custom-agents/capability-fingerprint.schema.json",
            "plans/custom-agents/behavior-report.schema.json",
        ]:
            schema = json.loads((ROOT / relative).read_text(encoding="utf-8"))
            self.assertFalse(schema["additionalProperties"])

    def test_no_teamwork_preview_dependency_in_harness_or_fixtures(self) -> None:
        paths = [HARNESS, MANIFEST]
        for fixture_set in ("phase1", "phase1b"):
            paths.extend(
                (
                    ROOT
                    / "fixtures/custom-agents"
                    / fixture_set
                    / "workspace"
                ).rglob("*")
            )
        for path in paths:
            if path.is_file():
                self.assertNotIn(
                    "teamwork-preview",
                    path.read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
