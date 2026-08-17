from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "grilltrack"
HERDR_SKILL = ROOT / "skills" / "herdr-puppet"
PHONE_DOGFOOD_SKILL = ROOT / "skills" / "phone-dogfood"


class PackagingTests(unittest.TestCase):
    def test_plugin_and_marketplace_identity(self) -> None:
        plugin = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        root_plugin = json.loads(
            (ROOT / "plugin.json").read_text(encoding="utf-8")
        )
        expected_root = {
            "name": "saarius-skills",
            "description": "Experimental agent supervision, Herdr transport, and progressive product-decision workflows.",
        }
        market = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(root_plugin, expected_root)
        self.assertEqual(plugin["name"], "saarius-skills")
        self.assertEqual(plugin["version"], "0.2.0")
        self.assertEqual(plugin["skills"], "./skills/")
        self.assertNotEqual(plugin, root_plugin)
        self.assertEqual(plugin["name"], root_plugin["name"])
        self.assertEqual(market["name"], "saarius-skills")
        self.assertEqual(market["plugins"][0]["name"], plugin["name"])
        self.assertEqual(market["plugins"][0]["source"]["path"], "./")

    def test_intent_aware_activation_metadata(self) -> None:
        metadata = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("$grilltrack", metadata)
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Do not make the user repeat a canned prompt", skill)
        self.assertIn("casual mention", skill)
        self.assertLessEqual(len(skill.splitlines()), 500)

    def test_greenfield_design_contract_is_packaged(self) -> None:
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        frontend = (
            SKILL / "references" / "grill-frontend" / "README.md"
        ).read_text(encoding="utf-8")
        contract = (
            SKILL / "references" / "grill-frontend" / "design-contract.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Default to root `design.md`", skill)
        self.assertIn("[design-contract.md](design-contract.md)", frontend)
        self.assertIn("# Greenfield design contract", contract)
        self.assertIn("Do not cleanly close", contract)
        self.assertIn("Do not impose this requirement", contract)

    def test_font_system_grill_is_packaged(self) -> None:
        frontend = (
            SKILL / "references" / "grill-frontend" / "README.md"
        ).read_text(encoding="utf-8")
        typography = (
            SKILL / "references" / "grill-frontend" / "typography.md"
        ).read_text(encoding="utf-8")
        contract = (
            SKILL / "references" / "grill-frontend" / "design-contract.md"
        ).read_text(encoding="utf-8")

        self.assertIn("[typography.md](typography.md)", frontend)
        self.assertIn("# Typography and fonts", typography)
        self.assertIn("five complete typographic systems", typography)
        self.assertIn("real weights", typography)
        self.assertIn("runtime font requests", typography)
        self.assertIn("exact families and real", contract)

    def test_legal_copies_match(self) -> None:
        self.assertEqual(
            (ROOT / "LICENSE").read_text(encoding="utf-8"),
            (SKILL / "LICENSE").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8"),
            (SKILL / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8"),
        )

    def test_no_placeholders(self) -> None:
        placeholder = "[" + "TODO:"
        for path in ROOT.rglob("*"):
            if not path.is_file() or {
                ".git",
                ".ruff_cache",
                "__pycache__",
            }.intersection(path.parts):
                continue
            if path.suffix not in {".md", ".json", ".yaml", ".py", ""}:
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(placeholder, text, str(path))

    def test_ledger_has_no_delivery_runner(self) -> None:
        source = (
            SKILL / "scripts" / "grilltrack_ledger.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import subprocess", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("git push", source)
        self.assertNotIn("gh pr", source)

    def test_herdr_puppet_skill_is_packaged_and_bounded(self) -> None:
        skill = (HERDR_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (HERDR_SKILL / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        client = (
            HERDR_SKILL
            / "scripts"
            / "herdr_puppet_lib"
            / "herdr_client.py"
        ).read_text(encoding="utf-8")
        cli = (
            HERDR_SKILL
            / "scripts"
            / "herdr_puppet_lib"
            / "cli.py"
        ).read_text(encoding="utf-8")
        compact_client = " ".join(client.split())
        self.assertLessEqual(len(skill.splitlines()), 500)
        self.assertIn("$herdr-puppet", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("transcript-blind", skill)
        self.assertIn("Never inject `/teamwork-preview` automatically", skill)
        self.assertIn("lease-preserve", skill)
        self.assertIn("cleanup-preserved-tab", skill)
        self.assertIn("lease-migrate-v1", skill)
        self.assertIn("qualification-harness-ready", skill)
        self.assertIn("operator_observed_ready_input", skill)
        self.assertIn("remote-task-file-register", skill)
        self.assertIn("--timeout-ms 480000", skill)
        self.assertIn("--timeout-seconds 510", skill)
        self.assertIn("status --lease-json", skill)
        self.assertIn("must not be rewritten as a", skill)
        self.assertIn('"method": "pane.send_input"', compact_client)
        self.assertIn('selected_keys = ["enter"]', compact_client)
        self.assertIn('"keys": selected_keys', compact_client)
        self.assertIn('"pane", "run"', compact_client)
        self.assertIn('"<redacted-command>"', compact_client)
        self.assertIn("socket.AF_UNIX", client)
        self.assertNotIn('add_argument("--text")', cli)
        self.assertNotIn('add_argument("--command")', cli)
        self.assertIn('"qualification-run"', cli)
        self.assertIn('add_argument("--stdin"', cli)
        self.assertIn('"wait", "output"', compact_client)
        self.assertIn('"api", "snapshot"', compact_client)
        self.assertNotIn('"pane", "read"', compact_client)
        self.assertNotIn('"send-text"', compact_client)
        self.assertNotIn('"send-keys"', compact_client)
        self.assertNotIn('"server", "stop"', compact_client)
        self.assertNotIn('"session", "stop"', compact_client)
        self.assertNotIn('"workspace", "close"', compact_client)
        self.assertIn('"tab", "close"', compact_client)
        self.assertNotIn('"pane", "close"', compact_client)
        self.assertNotIn("SIGTERM", client)
        self.assertNotIn("SIGKILL", client)
        self.assertIn('add_argument("--confirm-tab-id"', cli)
        self.assertIn('add_argument("--allow-live-cleanup"', cli)
        self.assertIn('"qualification-harness-ready"', cli)
        self.assertIn('"qualification-harness-launch"', cli)
        self.assertIn('"qualification-startup-gate"', cli)
        self.assertIn('"qualification-view-begin"', cli)
        self.assertIn('"qualification-view-complete"', cli)
        self.assertIn('"harness-census-verify"', cli)
        self.assertIn('"instruction-wrapper-create"', cli)
        self.assertIn('"remote-task-file-register"', cli)
        self.assertIn('"lease-migrate"', cli)
        self.assertIn('"lease-migrate-v1"', cli)
        self.assertIn('add_argument("--checkpoint-nonce")', cli)
        self.assertTrue(
            (HERDR_SKILL / "scripts" / "harness_census.py").is_file()
        )
        self.assertTrue(
            (
                HERDR_SKILL
                / "templates"
                / "instructions"
                / "catalog.json"
            ).is_file()
        )

    def test_herdr_puppet_schemas_parse(self) -> None:
        references = HERDR_SKILL / "references"
        for name in (
            "plan.schema.json",
            "plan-v1.schema.json",
            "lease.schema.json",
            "lease-v2.schema.json",
            "lease-v1.schema.json",
            "event.schema.json",
            "destination-catalog.schema.json",
            "harness-binding.schema.json",
            "harness-binding-v2.schema.json",
            "harness-binding-v1.schema.json",
            "remote-harness-census.schema.json",
            "remote-harness-census-v2.schema.json",
        ):
            schema = json.loads((references / name).read_text(encoding="utf-8"))
            self.assertEqual(
                schema["$schema"],
                "https://json-schema.org/draft/2020-12/schema",
            )
        lease_schema = json.loads(
            (references / "lease.schema.json").read_text(encoding="utf-8")
        )
        plan_schema = json.loads(
            (references / "plan.schema.json").read_text(encoding="utf-8")
        )
        historical_plan_schema = json.loads(
            (references / "plan-v1.schema.json").read_text(encoding="utf-8")
        )
        previous_lease_schema = json.loads(
            (references / "lease-v2.schema.json").read_text(encoding="utf-8")
        )
        historical_lease_schema = json.loads(
            (references / "lease-v1.schema.json").read_text(encoding="utf-8")
        )
        frozen_schema_digests = {
            "plan-v1.schema.json": (
                historical_plan_schema,
                "19159fe3c798e49ed9774f3c3b7732f2048ce9874373a1da5d8a59f6222d2c56",
            ),
            "lease-v2.schema.json": (
                previous_lease_schema,
                "b144118a1680389c0cf9a233d55e9cac924e6904798b34d02bda33ee55ff6736",
            ),
            "lease-v1.schema.json": (
                historical_lease_schema,
                "c0e39e58591c7ab3cb1926fd7051c51bed987f2c54fd8967a92d74ca3fbd4715",
            ),
        }
        for name, (schema, expected_digest) in frozen_schema_digests.items():
            with self.subTest(frozen_schema=name):
                canonical = json.dumps(
                    schema,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                self.assertEqual(
                    hashlib.sha256(canonical).hexdigest(),
                    expected_digest,
                )
        event_schema = json.loads(
            (references / "event.schema.json").read_text(encoding="utf-8")
        )
        binding_schema = json.loads(
            (references / "harness-binding.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            binding_schema["properties"]["profile"]["properties"][
                "enrollment_state"
            ]["enum"],
            ["enrolled", "interactive_pending"],
        )
        self.assertIn("allOf", binding_schema)
        self.assertEqual(
            binding_schema["properties"]["schema"]["const"],
            "herdr-puppet.harness-binding.v3",
        )
        required_agy_argv = [
            "--model",
            "gemini-3.7-flash-high",
            "--dangerously-skip-permissions",
            "--sandbox=false",
            "--new-project",
            "--log-file",
            "/dev/null",
        ]
        binding_agy_argv = binding_schema["allOf"][2]["then"][
            "properties"
        ]["regular_launch"]["properties"]["argv"]["prefixItems"]
        self.assertEqual(
            [item["const"] for item in binding_agy_argv[1:]],
            required_agy_argv,
        )
        frozen_binding = json.loads(
            (references / "harness-binding-v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            frozen_binding["properties"]["schema"]["const"],
            "herdr-puppet.harness-binding.v2",
        )
        census_schema = json.loads(
            (references / "remote-harness-census.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            census_schema["properties"]["schema"]["const"],
            "herdr-puppet.remote-harness-census.v3",
        )
        self.assertIn("runtime validate_remote_census", census_schema["$comment"])
        self.assertEqual(
            census_schema["$defs"]["checkpointLifecycle"]["properties"][
                "strategy"
            ]["const"],
            "strict_checkpoint_only",
        )
        self.assertEqual(
            census_schema["$defs"]["claudeLifecycle"]["properties"][
                "strategy"
            ]["const"],
            "claude_native_hook_markers",
        )
        census_conditions = json.dumps(census_schema["allOf"], sort_keys=True)
        self.assertIn("interactive_pending", json.dumps(census_schema))
        self.assertIn("claudeLifecycle", census_conditions)
        self.assertIn('"status_exit": {"const": 0}', census_conditions)
        census_agy_argv = census_schema["allOf"][0]["then"][
            "properties"
        ]["regular_launch"]["properties"]["argv"]["prefixItems"]
        self.assertEqual(
            [item["const"] for item in census_agy_argv[1:]],
            required_agy_argv,
        )
        destination_schema = json.loads(
            (references / "destination-catalog.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            set(
                destination_schema["properties"]["profiles"]["items"][
                    "required"
                ]
            ),
            {"name", "workspace_label", "ssh_target"},
        )
        self.assertFalse(
            destination_schema["properties"]["profiles"]["items"][
                "additionalProperties"
            ]
        )
        self.assertTrue(
            destination_schema["properties"]["profiles"]["uniqueItems"]
        )
        self.assertEqual(
            plan_schema["properties"]["schema"]["const"],
            "herdr-puppet.plan.v2",
        )
        self.assertIn("selected_authority_sha256", plan_schema["required"])
        self.assertEqual(
            lease_schema["properties"]["schema"]["const"],
            "herdr-puppet.lease.v3",
        )
        self.assertEqual(
            previous_lease_schema["properties"]["schema"]["const"],
            "herdr-puppet.lease.v2",
        )
        self.assertTrue(
            previous_lease_schema["$id"].endswith("/lease-v2.schema.json")
        )
        self.assertEqual(
            historical_plan_schema["properties"]["schema"]["const"],
            "herdr-puppet.plan.v1",
        )
        self.assertTrue(
            historical_plan_schema["$id"].endswith("/plan-v1.schema.json")
        )
        self.assertNotIn(
            "destination_selection",
            historical_plan_schema["properties"],
        )
        self.assertEqual(
            historical_plan_schema["properties"]["harness_binding"]["oneOf"],
            [
                {"$ref": "harness-binding-v2.schema.json"},
                {"$ref": "harness-binding-v1.schema.json"},
            ],
        )
        self.assertEqual(
            historical_lease_schema["properties"]["schema"]["const"],
            "herdr-puppet.lease.v1",
        )
        self.assertTrue(
            historical_lease_schema["$id"].endswith("/lease-v1.schema.json")
        )
        self.assertNotIn(
            "destination_selection",
            historical_lease_schema["properties"],
        )
        self.assertEqual(
            historical_lease_schema["properties"]["harness_binding"]["oneOf"],
            [
                {"$ref": "harness-binding-v2.schema.json"},
                {"$ref": "harness-binding-v1.schema.json"},
            ],
        )
        lease_cross_fields = json.dumps(
            lease_schema["allOf"],
            sort_keys=True,
        )
        self.assertIn("workspace_trust", lease_cross_fields)
        self.assertIn("security_acknowledgement", lease_cross_fields)
        self.assertIn("permission_bypass_confirmation", lease_cross_fields)
        self.assertIn('\"agy\", \"grok\"', lease_cross_fields)
        self.assertIn('\"accept\", \"not_present\"', lease_cross_fields)
        self.assertIn('\"phase\": {\"const\": \"steering\"}', lease_cross_fields)
        self.assertIn("minContains", lease_cross_fields)
        self.assertEqual(
            lease_schema["properties"]["harness_readiness"]["enum"],
            [
                "unverified",
                "operator_verified",
                "checkpoint_pending",
                "checkpoint_verified",
            ],
        )
        self.assertEqual(
            lease_schema["properties"]["shell_readiness"]["enum"],
            ["unverified", "status_verified"],
        )
        self.assertIn("caller_text_files", lease_schema["properties"])
        self.assertIn("caller_text_files_removed", lease_schema["properties"])
        self.assertIn("remote_task_files", lease_schema["properties"])
        self.assertIn("harness_readiness_submission_seq", lease_schema["properties"])
        self.assertIn("harness_readiness_nonce_sha256", lease_schema["properties"])
        transport_adapter = (
            HERDR_SKILL / "scripts" / "herdr_puppet_lib" / "harness_binding.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"references/lease-v2.schema.json"', transport_adapter)
        self.assertEqual(
            set(lease_schema["required"]),
            {
                "schema",
                "state",
                "run_id",
                "harness",
                "session",
                "workspace",
                "destination_selection",
                "selected_authority_sha256",
                "owned_label",
                "tab_id",
                "pane_id",
                "terminal_id",
                "ssh",
                "next_seq",
                "shell_readiness",
                "harness_readiness",
                "source",
                "harness_binding",
                "startup_gate_operations",
                "proof_root",
                "caller_text_files",
                "caller_text_files_removed",
                "remote_task_files",
                "interactive_sends",
                "pending_interactive_send",
                "pending_sequence_operation",
            },
        )
        readiness_rule = lease_schema["allOf"][0]
        self.assertEqual(
            readiness_rule["then"]["required"],
            [
                "harness_launch",
                "harness_readiness_evidence",
                "harness_readiness_operator",
                "harness_readiness_verified_at",
            ],
        )
        self.assertEqual(
            readiness_rule["then"]["properties"]["shell_readiness"]["const"],
            "status_verified",
        )
        self.assertEqual(
            readiness_rule["then"]["properties"]["harness"]["enum"],
            ["codex", "claude", "cursor", "grok"],
        )
        self.assertIn("command_sha256", event_schema["properties"])

    def test_herdr_puppet_packages_bounded_peekaboo_fallback(self) -> None:
        skill = (HERDR_SKILL / "SKILL.md").read_text(encoding="utf-8")
        fallback = (
            HERDR_SKILL
            / "references"
            / "desktop-observation-fallback.md"
        ).read_text(encoding="utf-8")
        self.assertIn("desktop-observation-fallback.md", skill)
        self.assertIn("Computer Use", skill)
        self.assertIn("peekaboo permissions --json", fallback)
        self.assertIn("peekaboo image --mode screen", fallback)
        self.assertIn('peekaboo list windows --app "Screen Sharing"', fallback)
        self.assertIn("Control Screen", fallback)
        self.assertIn("negative bounds", fallback)
        self.assertIn("infer an authentication gate", fallback)
        self.assertIn("Use Pixel Use MCP for phone semantics", fallback)
        self.assertIn("Never enter or retrieve a password", fallback)

    def test_phone_dogfood_skill_is_packaged_and_bounded(self) -> None:
        skill = (PHONE_DOGFOOD_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (
            PHONE_DOGFOOD_SKILL / "agents" / "openai.yaml"
        ).read_text(encoding="utf-8")
        helper = (
            PHONE_DOGFOOD_SKILL / "scripts" / "phone_dogfood.py"
        ).read_text(encoding="utf-8")
        self.assertLessEqual(len(skill.splitlines()), 500)
        self.assertIn("$phone-dogfood", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("Actually inspect the image", skill)
        self.assertIn("physical screenshot ID", skill)
        self.assertNotIn("shell=True", helper)
        self.assertNotIn("os.system", helper)
        self.assertNotIn('"serial": serial', helper)


if __name__ == "__main__":
    unittest.main()
