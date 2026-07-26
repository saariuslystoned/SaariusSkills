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
