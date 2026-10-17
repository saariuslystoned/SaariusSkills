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
MUSE_SKILL = ROOT / "skills" / "muse-acp-delegation"
JEVSWEEPER_SKILL = ROOT / "skills" / "jevsweeper"


class PackagingTests(unittest.TestCase):
    def test_emdash_skills_discoverable_with_licenses(self) -> None:
        upstream = ("building-emdash-site", "creating-plugins", "emdash-cli", "upgrading-emdash")
        names = ("emdash-sites", "emdash-commerce", "emdash-ci-deploy", *upstream)
        cursor = json.loads((ROOT / ".cursor-plugin/plugin.json").read_text())
        codex = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
        self.assertEqual(codex["skills"], "./skills/")
        for name in names:
            self.assertTrue((ROOT / "skills" / name / "SKILL.md").is_file())
            self.assertIn(f"./skills/{name}/", cursor["skills"])
            if name in upstream:
                self.assertEqual((ROOT / "skills" / name / "LICENSE").read_bytes(),
                                 (ROOT / "vendor/emdash-skills/LICENSE").read_bytes())
                self.assertTrue((ROOT / "skills" / name / "UPSTREAM.md").is_file())

    def test_emdash_ci_deploy_resources_are_packaged(self) -> None:
        skill = ROOT / "skills" / "emdash-ci-deploy"
        for name in ("pipeline-and-targets.md", "deploy-stamp-and-verify.md", "onboard-and-troubleshoot.md"):
            self.assertTrue((skill / "references" / name).is_file())
        metadata = (skill / "agents" / "openai.yaml").read_text()
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("$emdash-ci-deploy", metadata)

    def test_emdash_commerce_resources_are_packaged(self) -> None:
        skill = ROOT / "skills" / "emdash-commerce"
        self.assertTrue((skill / "references" / "source-map.md").is_file())
        metadata = (skill / "agents" / "openai.yaml").read_text()
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("$emdash-commerce", metadata)

    def test_acp_entry_is_discoverable_on_packaged_hosts(self) -> None:
        entry = ROOT / "skills" / "acp-delegation"
        self.assertTrue((entry / "SKILL.md").is_file())
        for name in ("permissions.md", "evaluations.md"):
            self.assertTrue((entry / "references" / name).is_file())
        metadata = (entry / "agents" / "openai.yaml").read_text()
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("$acp-delegation", metadata)
        cursor = json.loads((ROOT / ".cursor-plugin" / "plugin.json").read_text())
        self.assertIn("./skills/acp-delegation/", cursor["skills"])
        # Codex/Claude/path installs discover the existing skills directory.
        for lane in ("cursor", "grok", "antigravity", "muse"):
            self.assertTrue((ROOT / "skills" / f"{lane}-acp-delegation" / "SKILL.md").is_file())

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
        self.assertEqual(plugin["version"], "0.6.0")
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

    def test_antigravity_acp_skill_is_packaged(self) -> None:
        skill = (ANTIGRAVITY_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (
            ANTIGRAVITY_SKILL / "agents" / "openai.yaml"
        ).read_text(encoding="utf-8")
        plugin = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertLessEqual(len(skill.splitlines()), 500)
        self.assertIn("$antigravity-acp-delegation", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("antigravity_acp_readiness", skill)
        self.assertIn("exact advertised", skill)
        self.assertIn("gemini-3.8-flash-high", skill)
        self.assertIn("plugin default", skill)
        self.assertIn("GEMINI_HOME", skill)
        self.assertIn("interaction_*", skill)
        self.assertIn("STEERING_UNSUPPORTED", skill)
        self.assertIn("agy-print", skill)
        self.assertIn("antigravity-acp", plugin["keywords"])
        self.assertIn("grok-acp", plugin["keywords"])
        self.assertIn("SAARIUS_ACP_HOP_ARGV", skill)
        self.assertIn("worker-absolute", skill)

    def test_cursor_plugin_manifest_packages_skills_only(self) -> None:
        cursor = json.loads(
            (ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
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

        self.assertIn(omitted, packaged)
        self.assertEqual(cursor["name"], "saarius-skills")
        self.assertEqual(cursor["skills"], expected_skills)
        self.assertNotIn(f"./skills/{omitted}/", cursor["skills"])
        self.assertIn("./skills/antigravity-acp-delegation/", cursor["skills"])
        self.assertIn("./skills/grok-acp-delegation/", cursor["skills"])
        self.assertIn("./skills/muse-acp-delegation/", cursor["skills"])
        self.assertIn("./skills/pstack-playbooks/", cursor["skills"])
        for skill in cursor["skills"]:
            self.assertTrue((ROOT / skill / "SKILL.md").is_file(), skill)
        self.assertEqual(set(cursor), {"name", "skills"})
        self.assertNotEqual(cursor, root_plugin)
        self.assertNotEqual(cursor, codex)

        self.assertEqual(
            root_plugin,
            {
                "name": "saarius-skills",
                "description": "Experimental agent skills, progressive product-decision workflows, and local ACP delegation.",
            },
        )
        self.assertEqual(codex["name"], "saarius-skills")
        self.assertEqual(codex["version"], "0.6.0")
        self.assertEqual(codex["skills"], "./skills/")
        self.assertEqual(marketplace["name"], "saarius-skills")
        self.assertEqual(marketplace["plugins"][0]["source"]["path"], "./")

    def test_plugin_ships_no_mcp_servers(self) -> None:
        # The ACP brokers and jev-decision ship in the separate ai-shed plugin
        # (saari-co/ai-shed). Declaring them here too makes both plugins
        # register the same servers and start every broker twice.
        claude = json.loads(
            (ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        codex = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        cursor = json.loads(
            (ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        metadata = {
            "name",
            "version",
            "description",
            "author",
            "homepage",
            "repository",
            "license",
            "keywords",
        }
        self.assertLessEqual(set(claude), metadata)
        self.assertLessEqual(set(codex), metadata | {"skills", "interface"})
        self.assertEqual(set(cursor), {"name", "skills"})
        self.assertFalse((ROOT / ".mcp.json").exists())
        self.assertFalse((ROOT / ".cursor-plugin" / "mcp.json").exists())
        self.assertFalse((ROOT / "bridge").exists())
        workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("node-bridges", workflow)

    def test_acp_skills_point_at_ai_shed_plugin(self) -> None:
        reference = (
            ROOT / "skills" / "acp-delegation" / "references" / "ai-shed-plugin.md"
        ).read_text(encoding="utf-8")
        self.assertIn("saari-co/ai-shed", reference)
        self.assertIn("claude plugin install ai-shed@ai-shed", reference)
        self.assertIn("mcp__plugin_ai-shed_", reference)
        self.assertIn("Do not bundle", reference)
        entry = (ROOT / "skills" / "acp-delegation" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("references/ai-shed-plugin.md", entry)
        for lane in ("cursor", "antigravity", "grok", "muse"):
            server = f"{lane}-acp"
            skill = (
                ROOT / "skills" / f"{server}-delegation" / "SKILL.md"
            ).read_text(encoding="utf-8")
            doc = (ROOT / "docs" / f"{server}-delegation.md").read_text(
                encoding="utf-8"
            )
            for text in (skill, doc):
                self.assertIn("ai-shed", text, server)
                self.assertIn(f"mcp__plugin_ai-shed_{server}__", text, server)
                self.assertNotIn("../../bridge", text, server)
                self.assertNotIn("SAARIUS_PLUGIN_ROOT", text, server)
            self.assertIn("ai-shed-plugin.md", skill, server)
        jevsweeper = (JEVSWEEPER_SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("ai-shed", jevsweeper)
        self.assertIn("mcp__plugin_ai-shed_jev-decision__decision_evaluate", jevsweeper)

    def test_grok_acp_skill_is_packaged(self) -> None:
        skill = (GROK_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (GROK_SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        plugin = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
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
        self.assertIn("grok-acp", plugin["keywords"])

    def test_muse_acp_skill_is_packaged(self) -> None:
        skill = (MUSE_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (MUSE_SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        plugin = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertLessEqual(len(skill.splitlines()), 500)
        self.assertIn("$muse-acp-delegation", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("muse_acp_readiness", skill)
        self.assertIn("muse-agent-acp", skill)
        self.assertIn("muse serve", skill)
        self.assertIn("host default", skill)
        self.assertIn("MUSE_EXECUTABLE", skill)
        self.assertIn("STEERING_UNSUPPORTED", skill)
        self.assertIn("muse-acp", plugin["keywords"])
        self.assertTrue((MUSE_SKILL / "references" / "remote-shed.md").is_file())
        self.assertTrue((ROOT / "docs" / "muse-acp-delegation.md").is_file())

    def test_claude_plugin_manifest_packages_skills(self) -> None:
        claude_text = (ROOT / ".claude-plugin" / "plugin.json").read_text(
            encoding="utf-8"
        )
        claude = json.loads(claude_text)
        market = json.loads(
            (ROOT / ".claude-plugin" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        codex = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        packaged = {
            path.name
            for path in (ROOT / "skills").iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        }

        self.assertEqual(claude["name"], "saarius-skills")
        self.assertEqual(claude["version"], codex["version"])
        # Claude Code always scans skills/; archived skills must not be there.
        self.assertNotIn("skills", claude)
        self.assertNotIn("puppet", packaged)
        self.assertNotIn("herdr-puppet", packaged)
        self.assertIn("cursor-acp-delegation", packaged)
        self.assertIn("antigravity-acp-delegation", packaged)
        self.assertIn("grok-acp-delegation", packaged)
        self.assertIn("muse-acp-delegation", packaged)
        self.assertNotIn("/Users/", claude_text)

        self.assertEqual(market["name"], "saarius-skills")
        self.assertIn("name", market["owner"])
        self.assertEqual(len(market["plugins"]), 1)
        self.assertEqual(market["plugins"][0]["name"], claude["name"])
        self.assertEqual(market["plugins"][0]["source"], "./")

    def test_jevsweeper_skill_is_packaged(self) -> None:
        skill = (JEVSWEEPER_SKILL / "SKILL.md").read_text(encoding="utf-8")
        rubric = (JEVSWEEPER_SKILL / "references" / "rubric.md").read_text(
            encoding="utf-8"
        )
        coordinator = (JEVSWEEPER_SKILL / "references" / "coordinator.md").read_text(
            encoding="utf-8"
        )
        scenarios = (JEVSWEEPER_SKILL / "references" / "scenarios.md").read_text(
            encoding="utf-8"
        )
        cursor = json.loads(
            (ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertLessEqual(len(skill), 10000)
        self.assertIn("decision_evaluate", skill)
        self.assertIn("`repair`", skill)
        self.assertIn("`owner-gate`", skill)
        self.assertIn("`do-not-patch`", skill)
        self.assertIn("Do not merge", skill)
        self.assertIn("## repair", rubric)
        self.assertIn("## owner-gate", rubric)
        self.assertIn("## do-not-patch", rubric)
        self.assertIn("./skills/jevsweeper/", cursor["skills"])
        self.assertNotIn("./skills/clawjev/", cursor["skills"])
        self.assertIn("jev-decision", skill)
        self.assertIn("Jev down never stops the rails", skill)
        self.assertIn("rubric by hand", skill)
        self.assertIn("`criteria`", rubric)
        self.assertIn("one pile never cancels another", rubric)
        self.assertIn("already authorized", skill)
        self.assertIn("Missing required proof is repair", rubric)
        self.assertIn("needs-evidence", coordinator)
        self.assertIn("waiting-on-dependency", coordinator)
        self.assertIn("headRefOid", coordinator)
        self.assertIn("needs-evidence", scenarios)
        self.assertNotIn("- `repair` if any leftover item is repair.", rubric)


if __name__ == "__main__":
    unittest.main()
