from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "grilltrack"


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
            "description": "Experimental agent orchestration and progressive product-decision workflows.",
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


if __name__ == "__main__":
    unittest.main()
