from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "browser"


class BrowserSkillTests(unittest.TestCase):
    def test_skill_structure_and_frontmatter(self) -> None:
        content = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = content.split("---", 2)[1]
        self.assertIn("name: browser", frontmatter)
        self.assertIn("description:", frontmatter)
        self.assertNotIn("license:", frontmatter)
        self.assertIn('"ServerName": "chrome-devtools"', content)
        self.assertIn('"ToolName": "list_pages"', content)
        self.assertIn('"Arguments": {}', content)
        self.assertIn("Run the browser objective directly", content)
        self.assertNotIn("invoke_subagent", content)
        self.assertIn("chrome-devtools", content)

    def test_browser_does_not_package_broken_custom_subagent(self) -> None:
        self.assertFalse((ROOT / "agents" / "browser-cli" / "agent.md").exists())
        protocol = (SKILL / "references" / "protocol.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("AGY CLI 1.1.12", protocol)
        self.assertIn("cannot construct its MCP tool converter", protocol)

    def test_chrome_devtools_mcp_is_packaged_and_isolated(self) -> None:
        config = json.loads((ROOT / "mcp_config.json").read_text(encoding="utf-8"))
        server = config["mcpServers"]["chrome-devtools"]
        self.assertEqual(server["command"], "npx")
        self.assertEqual(server["args"][:2], ["-y", "chrome-devtools-mcp@latest"])
        self.assertIn("--isolated", server["args"])
        self.assertIn("--no-usage-statistics", server["args"])
        self.assertNotIn("--autoConnect", server["args"])
        self.assertFalse(any("browser-url" in item for item in server["args"]))

    def test_openai_metadata_uses_explicit_skill_name(self) -> None:
        content = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("Browser Automation", content)
        self.assertIn("allow_implicit_invocation: true", content)
        self.assertIn("$browser", content)

    def test_fixture_integrity(self) -> None:
        from skills.browser.scripts.verify_browser import inspect_fixture

        report = inspect_fixture(SKILL / "fixtures" / "verification_studio.html")
        self.assertEqual(report["schema"], "browser.fixture-check/v1")
        self.assertEqual(report["scope"], "static_fixture_only")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["missing_ids"], [])
        self.assertEqual(report["missing_hooks"], [])
        self.assertFalse(report["live_browser_verified"])
        self.assertNotIn("actions", report)
        self.assertNotIn("all_passed", report)

    def test_protocol_uses_current_tool_arguments(self) -> None:
        protocol = (SKILL / "references" / "protocol.md").read_text(
            encoding="utf-8"
        )
        self.assertIn('`{"pageId":1,"bringToFront":true}`', protocol)
        self.assertIn('`{"uid":"...","value":"..."}`', protocol)
        self.assertIn('`{"text":"...","submitKey":"Enter"}`', protocol)
        self.assertNotIn("select_page` | `{\"pageIdx\"", protocol)
        self.assertNotIn("type_text` | `{\"uid\"", protocol)

    def test_static_check_is_not_described_as_live_proof(self) -> None:
        script = (SKILL / "scripts" / "verify_browser.py").read_text(
            encoding="utf-8"
        )
        suite = (SKILL / "references" / "verification_suite.md").read_text(
            encoding="utf-8"
        )
        self.assertIn('"live_browser_verified": False', script)
        self.assertNotIn('"strokes_logged": 161', script)
        self.assertIn("manual agent-driven acceptance run", suite)
        self.assertIn("not a capability pass", suite)
        self.assertIn("Do not use `--dangerously-skip-permissions`", suite)

    def test_browser_skill_relies_on_repository_license(self) -> None:
        self.assertTrue((ROOT / "LICENSE").is_file())
        self.assertFalse((SKILL / "LICENSE").exists())
        self.assertFalse((SKILL / "THIRD_PARTY_NOTICES.md").exists())


if __name__ == "__main__":
    unittest.main()
