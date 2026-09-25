from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "grilltrack"
PHONE_PROOF_SKILL = ROOT / "skills" / "phone-proof"
ANTIGRAVITY_SKILL = ROOT / "skills" / "antigravity-acp-delegation"
GROK_SKILL = ROOT / "skills" / "grok-acp-delegation"


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
            "description": "Experimental agent skills, progressive product-decision workflows, and local ACP delegation.",
        }
        market = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(root_plugin, expected_root)
        self.assertEqual(plugin["name"], "saarius-skills")
        self.assertEqual(plugin["version"], "0.4.0")
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

    def test_typed_artifact_graph_review_and_human_gate_are_packaged(self) -> None:
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        workflow = (SKILL / "references" / "workflow-contract.md").read_text(
            encoding="utf-8"
        )
        human_gates = (SKILL / "references" / "human-gates.md").read_text(
            encoding="utf-8"
        )
        protocol = (SKILL / "references" / "protocol.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("[references/workflow-contract.md]", skill)
        self.assertIn("review the verified result separately", skill)
        self.assertIn("## Artifact graph", workflow)
        self.assertIn("**Allowed mode:**", workflow)
        self.assertIn("Cross it with durable artifacts", workflow)
        self.assertIn("# Human-guided gates", human_gates)
        self.assertIn("Never ask the user to paste a secret", human_gates)
        self.assertIn("**Standards:**", protocol)
        self.assertIn("**Source intent:**", protocol)

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
                "node_modules",
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

    def test_phone_proof_skill_is_packaged_and_bounded(self) -> None:
        skill = (PHONE_PROOF_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (
            PHONE_PROOF_SKILL / "agents" / "openai.yaml"
        ).read_text(encoding="utf-8")
        helper = (
            PHONE_PROOF_SKILL / "scripts" / "phone_proof.py"
        ).read_text(encoding="utf-8")
        self.assertLessEqual(len(skill.splitlines()), 500)
        self.assertIn("$phone-proof", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("Actually inspect the image", skill)
        self.assertIn("physical screenshot ID", skill)
        self.assertIn("Android Studio", skill)
        self.assertIn("Running Devices", skill)
        self.assertIn("device_class", helper)
        self.assertIn("Accessibility tree", skill)
        self.assertIn("phone-proof.tree.v1", helper)
        self.assertNotIn("shell=True", helper)
        self.assertNotIn("os.system", helper)
        self.assertNotIn('"serial": serial', helper)

    def test_antigravity_acp_skill_and_mcp_server_are_packaged(self) -> None:
        skill = (ANTIGRAVITY_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (
            ANTIGRAVITY_SKILL / "agents" / "openai.yaml"
        ).read_text(encoding="utf-8")
        plugin = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        mcp = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        self.assertLessEqual(len(skill.splitlines()), 500)
        self.assertIn("$antigravity-acp-delegation", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("antigravity_acp_readiness", skill)
        self.assertIn("exact advertised", skill)
        self.assertIn("gemini-3.8-flash-high", skill)
        self.assertIn("plugin default", skill)
        self.assertIn("GEMINI_HOME", skill)
        contract = (ROOT / "bridge" / "antigravity-acp" / "contract.mjs").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'PREFERRED_DEFAULT_MODEL_ID = "gemini-3.8-flash-high"',
            contract,
        )
        cursor_mcp = (ROOT / ".cursor-plugin" / "mcp.json").read_text(encoding="utf-8")
        self.assertNotIn("GEMINI_HOME", cursor_mcp)
        self.assertNotIn("gemini-3.8-flash-high", cursor_mcp)
        self.assertIn("interaction_*", skill)
        self.assertIn("STEERING_UNSUPPORTED", skill)
        self.assertIn("agy-print", skill)
        self.assertIn("antigravity-acp", plugin["keywords"])
        self.assertIn("antigravity-acp", mcp["mcpServers"])
        self.assertIn("cursor-acp", mcp["mcpServers"])
        self.assertIn("grok-acp", mcp["mcpServers"])
        self.assertIn("grok-acp", plugin["keywords"])
        acp_runtime = ROOT / "bridge" / "acp-runtime"
        self.assertTrue((acp_runtime / "launcher.mjs").is_file())
        self.assertTrue((acp_runtime / "hop.mjs").is_file())
        self.assertTrue((acp_runtime / "prepare.mjs").is_file())
        self.assertTrue((acp_runtime / "runtime-store.mjs").is_file())
        self.assertIn("SAARIUS_ACP_HOP_ARGV", skill)
        self.assertIn("worker-absolute", skill)
        self.assertEqual(
            mcp["mcpServers"]["antigravity-acp"]["args"],
            ["bridge/acp-runtime/launcher.mjs", "antigravity-acp"],
        )
        self.assertEqual(
            mcp["mcpServers"]["cursor-acp"]["args"],
            ["bridge/acp-runtime/launcher.mjs", "cursor-acp"],
        )
        self.assertEqual(
            mcp["mcpServers"]["grok-acp"]["args"],
            ["bridge/acp-runtime/launcher.mjs", "grok-acp"],
        )
        cursor_broker = (ROOT / "bridge" / "cursor-acp" / "broker.mjs").read_text(
            encoding="utf-8"
        )
        cursor_recovery_tests = (
            ROOT / "bridge" / "cursor-acp" / "test" / "recovery.test.mjs"
        ).read_text(encoding="utf-8")
        self.assertIn('schema: "saarius.cursor-acp.owner.v1"', cursor_broker)
        self.assertIn("startTime", cursor_broker)
        self.assertIn("recoverStaleJobs", cursor_broker)
        self.assertIn("live owner", cursor_recovery_tests)

    def test_cursor_plugin_manifest_packages_skills_and_antigravity_mcp(
        self,
    ) -> None:
        cursor = json.loads(
            (ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        cursor_mcp_text = (ROOT / ".cursor-plugin" / "mcp.json").read_text(
            encoding="utf-8"
        )
        cursor_mcp = json.loads(cursor_mcp_text)
        packaged = {
            path.name
            for path in (ROOT / "skills").iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        }
        omitted = "cursor-acp-delegation"
        expected_skills = [
            f"./skills/{name}/"
            for name in sorted(packaged - {omitted})
        ]
        codex = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        root_plugin = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        codex_mcp = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))

        self.assertIn(omitted, packaged)
        self.assertEqual(cursor["name"], "saarius-skills")
        self.assertEqual(cursor["skills"], expected_skills)
        self.assertNotIn(f"./skills/{omitted}/", cursor["skills"])
        self.assertIn("./skills/antigravity-acp-delegation/", cursor["skills"])
        self.assertIn("./skills/grok-acp-delegation/", cursor["skills"])
        self.assertIn("./skills/pstack-playbooks/", cursor["skills"])
        for skill in cursor["skills"]:
            self.assertTrue((ROOT / skill / "SKILL.md").is_file(), skill)
        self.assertEqual(cursor["mcpServers"], "./.cursor-plugin/mcp.json")
        self.assertNotEqual(cursor, root_plugin)
        self.assertNotEqual(cursor, codex)

        self.assertEqual(set(cursor_mcp["mcpServers"]), {"antigravity-acp", "grok-acp"})
        server = cursor_mcp["mcpServers"]["antigravity-acp"]
        self.assertEqual(server["command"], "node")
        self.assertEqual(
            server["args"],
            ["${CURSOR_PLUGIN_ROOT}/bridge/acp-runtime/launcher.mjs", "antigravity-acp"],
        )
        grok_server = cursor_mcp["mcpServers"]["grok-acp"]
        self.assertEqual(grok_server["command"], "node")
        self.assertEqual(
            grok_server["args"],
            ["${CURSOR_PLUGIN_ROOT}/bridge/acp-runtime/launcher.mjs", "grok-acp"],
        )
        self.assertNotIn("env", server)
        self.assertNotIn("env", grok_server)
        self.assertNotIn("GEMINI_HOME", cursor_mcp_text)
        self.assertNotIn("CURSOR_AGENT_EXECUTABLE", cursor_mcp_text)
        self.assertNotIn("GROK_EXECUTABLE", cursor_mcp_text)
        self.assertNotIn("/Users/", cursor_mcp_text)
        self.assertNotIn("${PLUGIN_ROOT}", cursor_mcp_text)
        self.assertNotIn("cursor-acp", cursor_mcp["mcpServers"])

        self.assertEqual(
            root_plugin,
            {
                "name": "saarius-skills",
                "description": "Experimental agent skills, progressive product-decision workflows, and local ACP delegation.",
            },
        )
        self.assertEqual(codex["name"], "saarius-skills")
        self.assertEqual(codex["version"], "0.4.0")
        self.assertEqual(codex["skills"], "./skills/")
        self.assertEqual(codex["mcpServers"], "./.mcp.json")
        self.assertEqual(marketplace["name"], "saarius-skills")
        self.assertEqual(marketplace["plugins"][0]["source"]["path"], "./")
        self.assertEqual(
            codex_mcp["mcpServers"]["antigravity-acp"]["args"],
            ["bridge/acp-runtime/launcher.mjs", "antigravity-acp"],
        )
        self.assertEqual(
            codex_mcp["mcpServers"]["cursor-acp"]["args"],
            ["bridge/acp-runtime/launcher.mjs", "cursor-acp"],
        )
        self.assertEqual(
            codex_mcp["mcpServers"]["grok-acp"]["args"],
            ["bridge/acp-runtime/launcher.mjs", "grok-acp"],
        )
        self.assertNotIn("GROK_EXECUTABLE", json.dumps(codex_mcp["mcpServers"]["grok-acp"]))

    def test_grok_acp_skill_and_mcp_server_are_packaged(self) -> None:
        skill = (GROK_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (GROK_SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        plugin = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        mcp = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        broker = (ROOT / "bridge" / "grok-acp" / "broker.mjs").read_text(
            encoding="utf-8"
        )
        self.assertLessEqual(len(skill.splitlines()), 500)
        self.assertIn("$grok-acp-delegation", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("grok_acp_readiness", skill)
        self.assertIn("grok agent stdio", skill)
        self.assertIn("grok-build", skill)
        self.assertIn("grok-4.7", skill)
        self.assertIn("plugin default", skill)
        self.assertIn("GROK_EXECUTABLE", skill)
        self.assertIn("STEERING_UNSUPPORTED", skill)
        self.assertIn("cursor-agent acp", skill)
        self.assertIn("Grok Bot", skill)
        self.assertIn('DEFAULT_GROK_MODEL = "grok-4.7"', broker)
        self.assertIn('ACPX_GROK_AGENT = "grok-build"', broker)
        self.assertNotIn("/Users/bobbybones", broker)
        self.assertIn("grok-acp", plugin["keywords"])
        self.assertIn("grok-acp", mcp["mcpServers"])
        self.assertNotIn("GROK_EXECUTABLE", json.dumps(mcp["mcpServers"]["grok-acp"]))
        self.assertNotIn("/Users/", json.dumps(mcp["mcpServers"]["grok-acp"]))


if __name__ == "__main__":
    unittest.main()
