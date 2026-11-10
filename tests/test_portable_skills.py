"""Portable skill packaging, privacy boundaries and synthetic helper proof."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "smoky-skill-cleaner", "smoky-behavior-validator", "smoky-cli-creator",
    "smoky-worktree", "smoky-coordinator",
    "smoky-maintainer", "smoky-portfolio-sweep",
    "smoky-deslop", "smoky-technical-documentation",
)


class PortableSkillTests(unittest.TestCase):
    def test_discovery_metadata_license_and_local_references(self) -> None:
        cursor = json.loads((ROOT / ".cursor-plugin/plugin.json").read_text())
        for manifest in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
            self.assertEqual(json.loads((ROOT / manifest).read_text())["version"], "0.7.1")
        for name in NAMES:
            directory = ROOT / "skills" / name
            body = (directory / "SKILL.md").read_text()
            self.assertIn(f"name: {name}\n", body)
            self.assertIn("optional binding", body)
            self.assertIn(f"./skills/{name}/", cursor["skills"])
            self.assertIn(f"${name}", (directory / "agents/openai.yaml").read_text())
            self.assertEqual((directory / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())
            for reference in re.findall(r"`(references/[\w./-]+)`", body):
                self.assertTrue((directory / reference).is_file(), reference)
        self.assertTrue((ROOT / "skills" / "smoky-coordinator").is_dir())
        self.assertFalse((ROOT / "skills" / "smoky-codex-coordinator").exists())
        self.assertNotIn(
            "./skills/smoky-codex-coordinator/",
            cursor["skills"],
        )

    def test_pstack_keeps_its_separate_optional_marketplace_route(self) -> None:
        market = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
        entries = {entry["name"]: entry for entry in market["plugins"]}
        self.assertEqual(entries["saarius-skills"]["source"]["path"], "./")
        self.assertEqual(entries["pstack-saarius"]["source"]["path"], "./vendor/pstack")
        pstack = json.loads((ROOT / "vendor/pstack/.codex-plugin/plugin.json").read_text())
        self.assertEqual(pstack["name"], "pstack-saarius")
        self.assertEqual(pstack["version"], "0.2.0")
        self.assertEqual(pstack["skills"], "./skills/")

    def test_public_core_contains_no_operator_bindings(self) -> None:
        # Keep the public guard generic; private operator identifiers belong in
        # a separate non-public export audit, never in this test's fixtures.
        forbidden = re.compile(r"/Users/|/home/|[A-Z]:\\\\Users\\\\|coordinator_model\s*:|deployment_host\s*:|operator_account\s*:", re.I)
        for name in NAMES:
            for path in (ROOT / "skills" / name).rglob("*"):
                if path.is_file() and path.name not in {"LICENSE", "THIRD_PARTY_NOTICES.md"}:
                    self.assertIsNone(forbidden.search(path.read_text()), str(path))

    def test_audit_fixture_is_read_only_and_reports_real_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("one", "two"):
                path = root / name
                path.mkdir()
                (path / "SKILL.md").write_text("---\nname: duplicate\ndescription: Fixture.\n---\nRead `references/missing.md`.\n")
            before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
            result = subprocess.run(["python3", str(ROOT / "skills/smoky-skill-cleaner/scripts/audit-skills"), "--root", str(root), "--json"], capture_output=True, text=True, check=True)
            report = json.loads(result.stdout)
            self.assertEqual(report["skill_count"], 2)
            self.assertEqual(report["duplicate_names"], {"duplicate": ["one", "two"]})
            self.assertEqual(report["issue_counts"]["missing-reference"], 2)
            self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()})

    def test_retired_viewer_is_not_packaged_or_discovered(self) -> None:
        retired = "smoky-session-viewer"
        self.assertFalse((ROOT / "skills" / retired).exists())
        cursor = json.loads((ROOT / ".cursor-plugin/plugin.json").read_text())
        self.assertNotIn(f"./skills/{retired}/", cursor["skills"])
        for manifest in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
            roots = json.loads((ROOT / manifest).read_text())["skills"]
            discovered = {p.name for root in roots for p in (ROOT / root).iterdir()
                          if p.is_dir() and (p / "SKILL.md").is_file()}
            self.assertNotIn(retired, discovered)


if __name__ == "__main__":
    unittest.main()
