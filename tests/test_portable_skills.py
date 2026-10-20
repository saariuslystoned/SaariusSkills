"""Portable skill packaging, privacy boundaries and synthetic helper proof."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "smoky-skill-cleaner", "smoky-behavior-validator", "smoky-cli-creator",
    "smoky-worktree", "smoky-session-viewer", "smoky-codex-coordinator",
    "smoky-maintainer", "smoky-portfolio-sweep", "harness2",
)


class PortableSkillTests(unittest.TestCase):
    def test_discovery_metadata_license_and_local_references(self) -> None:
        cursor = json.loads((ROOT / ".cursor-plugin/plugin.json").read_text())
        for manifest in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
            self.assertEqual(json.loads((ROOT / manifest).read_text())["version"], "0.7.0")
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

    def test_pstack_keeps_its_separate_optional_marketplace_route(self) -> None:
        market = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
        entries = {entry["name"]: entry for entry in market["plugins"]}
        self.assertEqual(entries["saarius-skills"]["source"]["path"], "./")
        self.assertEqual(entries["pstack-saarius"]["source"]["path"], "./pstack")
        pstack = json.loads((ROOT / "pstack/.codex-plugin/plugin.json").read_text())
        self.assertEqual(pstack["name"], "pstack-saarius")
        self.assertEqual(pstack["version"], "0.1.0")
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

    def test_renderer_escapes_and_redacts_synthetic_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "fixture.jsonl"
            output = Path(temp) / "viewer.html"
            source.write_text(json.dumps({"role": "assistant", "content": '<script>alert("fixture")</script> token=synthetic_value_12345'}) + "\nnot json\n")
            before = source.read_bytes()
            result = self.render(source, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            html = output.read_text()
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn('<script>alert("fixture")</script>', html)
            self.assertNotIn("synthetic_value_12345", html)
            self.assertIn("warnings: 1", result.stdout)
            self.assertNotIn("<script src=", html)
            self.assertEqual(source.read_bytes(), before)
            if os.name == "posix":
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_renderer_does_not_overwrite_source_or_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "fixture.jsonl"
            source.write_text('{}\n')
            self.assertEqual(self.render(source, source, "--overwrite").returncode, 2)
            self.assertEqual(source.read_text(), '{}\n')
            output = Path(temp) / "existing.html"
            output.write_text("retain me")
            self.assertEqual(self.render(source, output).returncode, 2)
            self.assertEqual(output.read_text(), "retain me")
            self.assertEqual(self.render(source, output, "--overwrite").returncode, 0)

    def test_renderer_refuses_a_hardlink_to_its_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "fixture.jsonl"
            source.write_text('{"content":"preserve fixture"}\n')
            output = Path(temp) / "alias.html"
            os.link(source, output)
            before = source.read_bytes()
            self.assertEqual(self.render(source, output, "--overwrite").returncode, 2)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(output.read_bytes(), before)

    @staticmethod
    def render(source: Path, output: Path, *flags: str) -> subprocess.CompletedProcess:
        return subprocess.run(["python3", str(ROOT / "skills/smoky-session-viewer/scripts/render-session"), str(source), "--out", str(output), *flags], capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
