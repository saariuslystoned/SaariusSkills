from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "grilltrack"
HERDR_SKILL = ROOT / "skills" / "herdr-puppet"


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
            "description": "Experimental agent workflows and Herdr transport tools.",
        }
        market = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(root_plugin, expected_root)
        self.assertEqual(plugin["name"], "saarius-skills")
        self.assertEqual(plugin["version"], "0.1.0")
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
            if not path.is_file() or ".git" in path.parts:
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
        self.assertIn("unique task-owned readiness artifact", skill)
        self.assertIn("status --lease-json", skill)
        self.assertIn("must not be rewritten as a", skill)
        self.assertIn('"method": "pane.send_input"', compact_client)
        self.assertIn('"keys": ["enter"]', compact_client)
        self.assertIn("socket.AF_UNIX", client)
        self.assertNotIn('add_argument("--text")', cli)
        self.assertIn('add_argument("--stdin"', cli)
        self.assertIn('"wait", "output"', compact_client)
        self.assertIn('"api", "snapshot"', compact_client)
        self.assertNotIn('"pane", "read"', compact_client)
        self.assertNotIn('"send-text"', compact_client)
        self.assertNotIn('"send-keys"', compact_client)
        self.assertNotIn('"pane", "run"', compact_client)
        self.assertNotIn('"server", "stop"', compact_client)
        self.assertNotIn('"session", "stop"', compact_client)
        self.assertNotIn('"workspace", "close"', compact_client)
        self.assertIn('"tab", "close"', compact_client)
        self.assertNotIn('"pane", "close"', compact_client)
        self.assertNotIn("SIGTERM", client)
        self.assertNotIn("SIGKILL", client)
        self.assertIn('add_argument("--confirm-tab-id"', cli)
        self.assertIn('add_argument("--allow-live-cleanup"', cli)

    def test_herdr_puppet_schemas_parse(self) -> None:
        references = HERDR_SKILL / "references"
        for name in ("plan.schema.json", "lease.schema.json", "event.schema.json"):
            schema = json.loads((references / name).read_text(encoding="utf-8"))
            self.assertEqual(
                schema["$schema"],
                "https://json-schema.org/draft/2020-12/schema",
            )
        lease_schema = json.loads(
            (references / "lease.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            lease_schema["properties"]["harness_readiness"]["enum"],
            ["unverified", "status_verified"],
        )
        self.assertIn("caller_text_files", lease_schema["properties"])
        self.assertIn("caller_text_files_removed", lease_schema["properties"])


if __name__ == "__main__":
    unittest.main()
