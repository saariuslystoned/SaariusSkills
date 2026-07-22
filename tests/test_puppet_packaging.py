from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "puppet"


class PuppetPackagingTests(unittest.TestCase):
    def test_required_package_shape(self):
        required = [
            "SKILL.md",
            "agents/openai.yaml",
            "scripts/puppet.py",
            "scripts/adapter_lab.py",
            "references/operating-contract.md",
            "references/adapter-contract.md",
            "references/prompt-patterns.md",
            "references/proof-provenance.md",
            "references/yolo-contract.md",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
        ]
        for relative in required:
            with self.subTest(path=relative):
                self.assertTrue((SKILL / relative).is_file())
        self.assertFalse((SKILL / "README.md").exists())

    def test_skill_is_concise_and_warns_about_yolo(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(text.splitlines()), 500)
        self.assertIn("live execution is YOLO-only", text)
        self.assertIn("A target cannot review or accept itself", text)
        self.assertIn("Never inspect `.env`", text)

    def test_metadata_supports_natural_and_explicit_invocation(self):
        metadata = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("$puppet", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)

    def test_legal_copy_and_clean_room_notice(self):
        self.assertEqual(
            (ROOT / "LICENSE").read_text(encoding="utf-8"),
            (SKILL / "LICENSE").read_text(encoding="utf-8"),
        )
        notices = (SKILL / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("clean-room implementation", notices)
        self.assertIn("does not vendor", notices)

    def test_no_capture_pane_or_delivery_commands(self):
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (SKILL / "scripts").rglob("*.py")
        )
        forbidden = ["capture-" + "pane", "pipe-" + "pane", "git " + "push", "gh " + "pr"]
        for marker in forbidden:
            self.assertNotIn(marker, sources)


if __name__ == "__main__":
    unittest.main()
