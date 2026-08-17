from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "browser"


class BrowserSkillTests(unittest.TestCase):
    def test_skill_structure_and_frontmatter(self) -> None:
        self.assertTrue(SKILL.exists())
        self.assertTrue((SKILL / "SKILL.md").exists())
        content = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: browser", content)
        self.assertIn("license: MIT", content)
        self.assertIn("invoke_subagent", content)
        self.assertIn("chrome_devtools", content)

    def test_agents_metadata(self) -> None:
        yaml_path = SKILL / "agents" / "openai.yaml"
        self.assertTrue(yaml_path.exists())
        content = yaml_path.read_text(encoding="utf-8")
        self.assertIn("Browser Automation", content)
        self.assertIn("allow_implicit_invocation: true", content)

    def test_fixture_integrity(self) -> None:
        fixture_path = SKILL / "fixtures" / "verification_studio.html"
        self.assertTrue(fixture_path.exists())
        html = fixture_path.read_text(encoding="utf-8")
        self.assertIn('id="agent-codename"', html)
        self.assertIn('id="agent-email"', html)
        self.assertIn('id="canvas-studio"', html)
        self.assertIn('id="drop-zone"', html)
        self.assertIn('id="telemetry-log"', html)

    def test_verification_script(self) -> None:
        sys_path = SKILL / "scripts" / "verify_browser.py"
        self.assertTrue(sys_path.exists())
        from skills.browser.scripts.verify_browser import simulate_interaction_suite

        report = simulate_interaction_suite(SKILL / "fixtures" / "verification_studio.html")
        self.assertTrue(report["all_passed"])
        self.assertEqual(len(report["actions"]), 6)
        self.assertEqual(report["actions"]["typing"]["status"], "PASS")
        self.assertEqual(report["actions"]["checkboxes_and_radios"]["status"], "PASS")
        self.assertEqual(report["actions"]["clicks"]["status"], "PASS")
        self.assertEqual(report["actions"]["drag_and_drop"]["status"], "PASS")
        self.assertEqual(report["actions"]["canvas_drawing"]["status"], "PASS")
        self.assertEqual(report["actions"]["proof_capture"]["status"], "PASS")

    def test_legal_copies_match(self) -> None:
        self.assertEqual(
            (ROOT / "LICENSE").read_text(encoding="utf-8"),
            (SKILL / "LICENSE").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8"),
            (SKILL / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
