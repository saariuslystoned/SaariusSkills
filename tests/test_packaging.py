from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "grilltrack"
PHONE_PROOF_SKILL = ROOT / "skills" / "phone-proof"
ANTIGRAVITY_SKILL = ROOT / "skills" / "antigravity-acp-delegation"
GROK_SKILL = ROOT / "skills" / "grok-acp-delegation"
MUSE_SKILL = ROOT / "skills" / "muse-acp-delegation"
JEVSWEEPER_SKILL = ROOT / "skills" / "jevsweeper"
DINKUSKIT_LIVE_TEST_SKILL = ROOT / "skills" / "dinkuskit-live-test"
DINKUS_SWEEP_SKILL = ROOT / "skills" / "dinkus-sweep"
HARNESS2_SKILL = ROOT / "skills" / "harness2"
PERFORMANCE_SKILL = ROOT / "skills" / "smoky-performance"
CHARACTER_STUDIO_SKILL = ROOT / "skills" / "smoky-character-studio"
GITHUB_DESIGN_SKILL = ROOT / "skills" / "smoky-github-design"
LABEL_DIELINE_SKILL = ROOT / "skills" / "smoky-label-dieline"
AGY_SIDEBAR_SESSION_SKILL = ROOT / "skills" / "agy-sidebar-session"


class PackagingTests(unittest.TestCase):
    def test_simplification_and_performance_cores_are_discoverable_and_attributed(self) -> None:
        import re

        names = ("smoky-pr-simplify", "smoky-performance")
        cursor = json.loads((ROOT / ".cursor-plugin/plugin.json").read_text())
        self.assertFalse((ROOT / "skills/smoky-ci-performance").exists())
        self.assertNotIn("./skills/smoky-ci-performance/", cursor["skills"])
        for name in names:
            directory = ROOT / "skills" / name
            for manifest in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
                roots = json.loads((ROOT / manifest).read_text())["skills"]
                discovered = [p.name for root in roots for p in (ROOT / root).iterdir()
                              if p.is_dir() and (p / "SKILL.md").is_file()]
                self.assertEqual(discovered.count(name), 1, manifest)
            self.assertEqual(cursor["skills"].count(f"./skills/{name}/"), 1)
            self.assertIn(f"name: {name}\n", (directory / "SKILL.md").read_text())
            metadata = (directory / "agents/openai.yaml").read_text()
            self.assertIn(f"${name}", metadata)
            self.assertIn("allow_implicit_invocation: true", metadata)
            self.assertEqual((directory / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())
            notice = (directory / "THIRD_PARTY_NOTICES.md").read_text()
            upstream_license = (ROOT / "LICENSE").read_text().replace("Bobby Bones", "OpenClaw Foundation")
            self.assertIn(upstream_license.strip(), notice)
            self.assertIn("85c39026a90f58164595249f69c311ed71b44df8", notice)
            for document in directory.rglob("*.md"):
                for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
                    if "://" not in target and not target.startswith("#"):
                        self.assertTrue((document.parent / target.split("#")[0]).is_file(), target)
            for catalog in ("README.md", "docs/portable-skills.md"):
                self.assertIn(f"skills/{name}/SKILL.md", (ROOT / catalog).read_text())

    def test_cleanup_and_documentation_cores_are_discoverable_and_attributed(self) -> None:
        import re

        names = ("smoky-deslop", "smoky-technical-documentation")
        cursor = json.loads((ROOT / ".cursor-plugin/plugin.json").read_text())
        for name in names:
            directory = ROOT / "skills" / name
            for manifest in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
                roots = json.loads((ROOT / manifest).read_text())["skills"]
                discovered = [p.name for root in roots for p in (ROOT / root).iterdir()
                              if p.is_dir() and (p / "SKILL.md").is_file()]
                self.assertEqual(discovered.count(name), 1, manifest)
            self.assertEqual(cursor["skills"].count(f"./skills/{name}/"), 1)
            # AGY/path installs use root skills; root plugin has no path list.
            self.assertTrue((directory / "SKILL.md").is_file())
            self.assertEqual((directory / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())
            notice = (directory / "THIRD_PARTY_NOTICES.md").read_text()
            self.assertIn("Copyright (c) 2026 Vincent Koc", notice)
            upstream_license = (ROOT / "LICENSE").read_text().replace("Bobby Bones", "Vincent Koc")
            self.assertIn(upstream_license.strip(), notice)
            self.assertIn("c9ca51e3a4e93fe10266d78e430c6575a5b19d30", notice)
            self.assertIn(f"${name}", (directory / "agents/openai.yaml").read_text())
            for document in directory.rglob("*.md"):
                for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
                    if "://" not in target and not target.startswith("#"):
                        self.assertTrue((document.parent / target.split("#")[0]).is_file(), target)
            for catalog in ("README.md", "docs/portable-skills.md"):
                self.assertIn(f"skills/{name}/SKILL.md", (ROOT / catalog).read_text())

    def test_ryan_mode_is_discoverable_without_an_obsolete_alias(self) -> None:
        skill = ROOT / "skills" / "ryan-mode"
        for filename in ("SKILL.md", "SOURCE.md", "LICENSE"):
            self.assertTrue((skill / filename).is_file(), filename)
        self.assertFalse((ROOT / "skills" / "bobby-mode").exists())
        self.assertFalse((ROOT / "skills" / "bobby-mode").is_symlink())
        cursor = json.loads((ROOT / ".cursor-plugin/plugin.json").read_text())
        self.assertEqual(cursor["skills"].count("./skills/ryan-mode/"), 1)
        self.assertNotIn("./skills/bobby-mode/", cursor["skills"])
        for relative in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
            manifest = json.loads((ROOT / relative).read_text())
            discovered = [
                child.name
                for path in manifest["skills"]
                for child in (ROOT / path).iterdir()
                if child.is_dir() and (child / "SKILL.md").is_file()
            ]
            self.assertEqual(discovered.count("ryan-mode"), 1, relative)
            self.assertNotIn("bobby-mode", discovered, relative)

    def test_smoky_coordinator_is_canonical_and_legacy_package_is_absent(self) -> None:
        cursor = json.loads((ROOT / ".cursor-plugin/plugin.json").read_text())
        codex = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
        claude = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        skill = ROOT / "skills" / "smoky-coordinator"
        self.assertTrue((skill / "SKILL.md").is_file())
        self.assertTrue((skill / "agents/openai.yaml").is_file())
        self.assertTrue((skill / "LICENSE").is_file())
        self.assertIn("$smoky-coordinator", (skill / "agents/openai.yaml").read_text())
        self.assertFalse((ROOT / "skills" / "smoky-codex-coordinator").exists())
        canonical = (ROOT / "skills/smoky-coordinator/SKILL.md").read_text()
        self.assertIn("name: smoky-coordinator\n", canonical)
        self.assertIn("./skills/smoky-coordinator/", cursor["skills"])
        self.assertNotIn("./skills/smoky-codex-coordinator/", cursor["skills"])
        self.assertEqual(codex["skills"], ["./skills/", "./vendor/pstack/skills/"])
        self.assertEqual(claude["skills"], ["./skills/", "./vendor/pstack/skills/"])
        self.assertIn("./skills/acp-delegation/", cursor["skills"])

    def test_emdash_skills_discoverable_with_licenses(self) -> None:
        upstream = ("building-emdash-site", "creating-plugins", "emdash-cli", "upgrading-emdash")
        names = ("emdash-sites", "emdash-commerce", "emdash-ci-deploy", "emdash-stitch-design", "emdash-surface-fx", *upstream)
        cursor = json.loads((ROOT / ".cursor-plugin/plugin.json").read_text())
        codex = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
        self.assertEqual(codex["skills"], ["./skills/", "./vendor/pstack/skills/"])
        for name in names:
            self.assertTrue((ROOT / "skills" / name / "SKILL.md").is_file())
            self.assertIn(f"./skills/{name}/", cursor["skills"])
            if name in upstream:
                self.assertEqual((ROOT / "skills" / name / "LICENSE").read_bytes(),
                                 (ROOT / "vendor/emdash-skills/LICENSE").read_bytes())
                self.assertTrue((ROOT / "skills" / name / "UPSTREAM.md").is_file())

    def test_emdash_surface_fx_resources_are_packaged(self) -> None:
        import re

        skill = ROOT / "skills" / "emdash-surface-fx"
        self.assertTrue((skill / "SKILL.md").is_file())
        self.assertTrue((skill / "LICENSE").is_file())
        self.assertTrue((skill / "agents" / "openai.yaml").is_file())
        self.assertTrue((skill / "references" / "teknium-catalog-and-astro-recipes.md").is_file())
        showcase = skill / "assets" / "examples" / "dinkuskit-surface-fx-showcase.html"
        self.assertTrue(showcase.is_file())
        showcase_text = showcase.read_text(encoding="utf-8")
        self.assertIn('<script src="../ephemera.js"></script>', showcase_text)
        self.assertNotIn("emdash-motion-studio/assets/tactile-audio.js", showcase_text)
        self.assertIsNone(re.search(r"\bany\b", showcase_text))

        for sfx_eng in ("dither.js", "viewport-pool.js", "surface-micro.js", "ephemera.js"):
            p = skill / "assets" / sfx_eng
            self.assertTrue(p.is_file(), sfx_eng)
            self.assertIsNone(re.search(r"\bany\b", p.read_text(encoding="utf-8")), sfx_eng)

        surface_micro_text = (skill / "assets" / "surface-micro.js").read_text(encoding="utf-8")
        self.assertIn("data-rough-path", surface_micro_text)
        self.assertIn("getTotalLength", surface_micro_text)

        ephemera_text = (skill / "assets" / "ephemera.js").read_text(encoding="utf-8")
        self.assertIn("function mountReceipt(", ephemera_text)
        self.assertIn("function renderBarcodeSvg(", ephemera_text)
        self.assertIn("function mountRubberStamp(", ephemera_text)

        sfx_meta = (skill / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: true", sfx_meta)
        self.assertIn("$emdash-surface-fx", sfx_meta)

        skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("High-Leverage Website Placement Guide (Strong Defaults + Open Experimentation)", skill_text)
        self.assertIn("purely reveals the coupon code + copies it to clipboard", skill_text)
        self.assertIn("mountHoverTilt", skill_text)
        self.assertIn("@chenglou/pretext", skill_text)
        self.assertIn("editorial lookbooks / magazine-style story pages", skill_text)
        self.assertIn("assets/ephemera.js", skill_text)

        ref_text = (skill / "references" / "teknium-catalog-and-astro-recipes.md").read_text(encoding="utf-8")
        self.assertIn("assets/ephemera.js", ref_text)

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
        self.assertTrue((skill / "references" / "rea-strategy.md").is_file())
        metadata = (skill / "agents" / "openai.yaml").read_text()
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("$emdash-commerce", metadata)

    def test_emdash_stitch_sites_and_deploy_hardenings_are_packaged(self) -> None:
        import re

        stitch_skill = ROOT / "skills" / "emdash-stitch-design"
        sites_skill = ROOT / "skills" / "emdash-sites"
        deploy_skill = ROOT / "skills" / "emdash-ci-deploy"
        surface_skill = ROOT / "skills" / "emdash-surface-fx"

        for folder in (stitch_skill, sites_skill, deploy_skill, surface_skill):
            skill_doc = (folder / "SKILL.md").read_text(encoding="utf-8")
            self.assertLessEqual(len(skill_doc.splitlines()), 500, folder.name)
            for doc in folder.rglob("*.md"):
                text = doc.read_text(encoding="utf-8")
                self.assertNotIn("/Users/", text, str(doc))
                self.assertNotIn("/home/", text, str(doc))
                for target in re.findall(r"\]\(([^)]+)\)", text):
                    if "://" not in target and not target.startswith("#"):
                        self.assertTrue(
                            (doc.parent / target.split("#")[0]).is_file(),
                            f"{doc}: {target}",
                        )

        visual_cycle = (
            stitch_skill / "references" / "grilltrack-visual-cycle.md"
        ).read_text(encoding="utf-8")
        taste = (stitch_skill / "references" / "taste-and-prompts.md").read_text(
            encoding="utf-8"
        )
        stitch_main = (stitch_skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("NSWindow", visual_cycle)
        self.assertIn("Emulation.setDeviceMetricsOverride", visual_cycle)
        self.assertIn("window.innerWidth === 390", visual_cycle)
        self.assertIn("faux-CAD blueprint cosplay", taste)
        self.assertIn("DATUM_A", taste)
        self.assertIn("Discord, GitHub, and social", stitch_main)

        cf_hosting = (
            sites_skill / "references" / "cloudflare-hosting.md"
        ).read_text(encoding="utf-8")
        plugin_surfaces = (
            sites_skill / "references" / "plugin-surfaces.md"
        ).read_text(encoding="utf-8")
        scenarios = (
            sites_skill / "references" / "scenario-checks.md"
        ).read_text(encoding="utf-8")
        self.assertIn("playgroundDatabase", cf_hosting)
        self.assertIn("EmDashPreviewDB", cf_hosting)
        self.assertIn("56px", cf_hosting)
        self.assertIn("039", cf_hosting)
        self.assertIn("globalThis.fetch", plugin_surfaces)
        self.assertIn('exports["./native"].workerd', plugin_surfaces)
        self.assertIn("PLAYGROUND_LOCK=1", plugin_surfaces)
        self.assertIn("EmDashPreviewDB", scenarios)

        deploy_main = (deploy_skill / "SKILL.md").read_text(encoding="utf-8")
        deploy_trouble = (
            deploy_skill / "references" / "onboard-and-troubleshoot.md"
        ).read_text(encoding="utf-8")
        self.assertIn("wrangler d1 execute --remote", deploy_main)
        self.assertIn("Cold D1 first request fails mid-migration", deploy_trouble)

        surface_main = (surface_skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Surface Restraint: Craft Replaces Telemetry Clutter", surface_main)
        self.assertIn("chrome: 'stage-only'", surface_main)

    def test_harness2_skill_contract_and_metadata_are_packaged(self) -> None:
        skill_path = HARNESS2_SKILL / "SKILL.md"
        contract_path = HARNESS2_SKILL / "references" / "experiment-contract.md"
        metadata_path = HARNESS2_SKILL / "agents" / "openai.yaml"
        cursor = json.loads((ROOT / ".cursor-plugin" / "plugin.json").read_text())

        self.assertTrue(skill_path.is_file())
        self.assertTrue(contract_path.is_file())
        self.assertTrue(metadata_path.is_file())
        self.assertIn("./skills/harness2/", cursor["skills"])
        metadata = metadata_path.read_text(encoding="utf-8")
        self.assertIn("name: harness2", skill_path.read_text(encoding="utf-8"))
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("$harness2", metadata)
        self.assertEqual(
            (HARNESS2_SKILL / "LICENSE").read_bytes(),
            (ROOT / "LICENSE").read_bytes(),
        )

    def test_performance_skill_retains_ci_contract_and_resources(self) -> None:
        skill = (PERFORMANCE_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (PERFORMANCE_SKILL / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        cursor = json.loads((ROOT / ".cursor-plugin" / "plugin.json").read_text())
        self.assertIn("name: smoky-performance\n", skill)
        self.assertIn("./skills/smoky-performance/", cursor["skills"])
        self.assertIn("$smoky-performance", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertTrue(
            (PERFORMANCE_SKILL / "references" / "benchmark-protocol.md").is_file()
        )
        self.assertTrue(
            (PERFORMANCE_SKILL / "references" / "ci-efficiency.md").is_file()
        )
        protocol = (
            PERFORMANCE_SKILL / "references" / "benchmark-protocol.md"
        ).read_text(encoding="utf-8")
        self.assertIn("macOS:", protocol)
        self.assertIn("Linux:", protocol)
        self.assertIn("/usr/bin/time -l", protocol)
        self.assertIn("/usr/bin/time -v", protocol)
        self.assertIn("exit-code.txt", protocol)
        self.assertIn("Never delete shared caches", protocol)
        self.assertIn("Missing REQUIRED execution evidence", protocol)
        self.assertIn("OpenClaw", protocol)
        self.assertEqual(
            (PERFORMANCE_SKILL / "LICENSE").read_bytes(),
            (ROOT / "LICENSE").read_bytes(),
        )
        helper = PERFORMANCE_SKILL / "scripts" / "capture.py"
        self.assertTrue(helper.is_file())
        self.assertTrue(helper.stat().st_mode & 0o111)
        self.assertTrue(
            (PERFORMANCE_SKILL / "references" / "capture-contract.md").is_file()
        )
        self.assertTrue(
            (PERFORMANCE_SKILL / "references" / "test-and-ci.md").is_file()
        )

    def test_ci_performance_capture_recipe_preserves_status_and_streams(self) -> None:
        protocol_path = PERFORMANCE_SKILL / "references" / "benchmark-protocol.md"
        protocol = protocol_path.read_text(encoding="utf-8")
        recipes = {}
        for heading in ("macOS:", "Linux:"):
            recipe_section = protocol.split(heading, 1)[1]
            recipe = recipe_section.split("```", 2)[1].removeprefix("sh\n")
            recipes[heading] = recipe
            syntax = subprocess.run(
                ["sh", "-n"],
                input=recipe,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(syntax.returncode, 0, syntax.stderr)

        if sys.platform == "darwin":
            heading = "macOS:"
            time_command = "/usr/bin/time -l"
        elif sys.platform.startswith("linux"):
            heading = "Linux:"
            time_command = "/usr/bin/time -v"
        else:
            self.skipTest("capture recipe is specified only for macOS and Linux")

        recipe = recipes[heading]
        self.assertIn(time_command, recipe)
        self.assertIn('exit "$exit_code"', recipe)
        self.assertEqual(recipe.count("<repo-command> [args...]"), 1)
        self.assertIn('printf \'%s\\000\' "$@" >argv.nul', recipe)
        self.assertNotIn("<<'EOF'", recipe)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "fixture.sh"
            fixture.write_text(
                """#!/bin/sh
printf 'fixture stdout\n'
printf 'fixture stderr\n' >&2
printf '%s\n' "$@" > args.txt
exit "$1"
""",
                encoding="utf-8",
            )
            fixture.chmod(0o755)

            for expected_status in (0, 7):
                with self.subTest(expected_status=expected_status):
                    output = root / str(expected_status)
                    output.mkdir()
                    fixture_relative = Path("fixture.sh")
                    (output / fixture_relative).write_text(
                        fixture.read_text(encoding="utf-8"), encoding="utf-8"
                    )
                    (output / fixture_relative).chmod(0o755)
                    arguments = [
                        str(expected_status),
                        "argument with spaces",
                        "embedded 'single' and \"double\" quotes",
                        "line one\nEOF\nline three",
                        "$(printf inert)",
                        "(inert); printf should-not-run",
                    ]
                    command = shlex.join([f"./{fixture_relative}", *arguments])
                    wrapper = recipe.replace(
                        "<repo-command> [args...]", command
                    )
                    result = subprocess.run(
                        ["sh", "-c", wrapper],
                        cwd=output,
                        capture_output=True,
                        text=True,
                        check=False,
                    )

                    self.assertEqual(result.returncode, expected_status)
                    self.assertEqual(
                        (output / "argv.nul").read_bytes(),
                        b"".join(
                            argument.encode("utf-8") + b"\0"
                            for argument in [f"./{fixture_relative}", *arguments]
                        ),
                    )
                    self.assertEqual(
                        (output / "args.txt").read_text(encoding="utf-8"),
                        "".join(f"{argument}\n" for argument in arguments),
                    )
                    self.assertEqual(
                        (output / "exit-code.txt").read_text(encoding="utf-8"),
                        f"{expected_status}\n",
                    )
                    self.assertEqual(
                        (output / "stdout.txt").read_text(encoding="utf-8"),
                        "fixture stdout\n",
                    )
                    self.assertEqual(
                        (output / "stderr.txt").read_text(encoding="utf-8"),
                        "fixture stderr\n",
                    )
                    metrics = (output / "metrics.txt").read_text(encoding="utf-8")
                    self.assertTrue(metrics)
                    self.assertNotIn("fixture stdout", metrics)
                    self.assertNotIn("fixture stderr", metrics)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(result.stderr, "")

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
            "$schema": "https://antigravity.google/schemas/v1/plugin.json",
            "name": "saarius-skills",
            "displayName": "Saarius Skills",
            "version": "0.7.1",
            "description": "Experimental agent skills, progressive product-decision workflows, and local ACP delegation.",
        }
        market = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(root_plugin, expected_root)
        self.assertEqual(plugin["name"], "saarius-skills")
        self.assertEqual(plugin["version"], "0.7.1")
        self.assertEqual(root_plugin["version"], plugin["version"])
        self.assertEqual(plugin["skills"], ["./skills/", "./vendor/pstack/skills/"])
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

    def test_dinkuskit_live_test_points_at_live_journeys(self) -> None:
        skill = (DINKUSKIT_LIVE_TEST_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (
            DINKUSKIT_LIVE_TEST_SKILL / "agents" / "openai.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("$dinkuskit-live-test", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)
        # The journeys, runner and workflow live in dinkuskit/live-journeys; only the pointer stays here.
        self.assertIn("https://github.com/dinkuskit/live-journeys/blob/main/SKILL.md", skill)
        self.assertIn("\ndescription: ", skill.split("\n---\n", 1)[0])
        for rule in ("4242 4242 4242 4242", "Never pay twice", "read-only", "Never record Ship's print link"):
            self.assertIn(rule, skill)
        self.assertFalse((DINKUSKIT_LIVE_TEST_SKILL / "runner").exists())
        self.assertFalse((DINKUSKIT_LIVE_TEST_SKILL / "references").exists())
        self.assertFalse((ROOT / ".github" / "workflows" / "live-journeys.yml").exists())

    def test_dinkus_sweep_is_a_profile_of_the_portfolio_sweep(self) -> None:
        skill = (DINKUS_SWEEP_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (DINKUS_SWEEP_SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        cursor = json.loads((ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertIn("\nname: dinkus-sweep\n", skill.split("\n---\n", 1)[0])
        self.assertIn("$dinkus-sweep", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("./skills/dinkus-sweep/", cursor["skills"])
        self.assertEqual(
            (DINKUS_SWEEP_SKILL / "LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes()
        )
        # A profile layered on the portable core, never a second copy of it.
        self.assertIn("`smoky-portfolio-sweep`", skill)
        self.assertIn("grants no authority", skill)
        self.assertTrue((DINKUS_SWEEP_SKILL / "references" / "dinkus-rails.md").is_file())
        for repo in ("commerce", "payments", "ship", "template-store", "dinkuskit",
                     "live-journeys", "coupons", "inventory", "books"):
            self.assertIn(f"`dinkuskit/{repo}`", skill)
        for rule in ("Override?", "Never override on your own", "never\nrebase or force-push",
                     "agentic commerce", "expected head\nSHA"):
            self.assertIn(rule, skill)
        self.assertLessEqual(len(skill.splitlines()), 500)

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
        expected_skills += [
            f"./vendor/pstack/skills/{path.name}/"
            for path in (ROOT / "vendor/pstack/skills").iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        ]
        expected_skills.sort(key=lambda path: path.rstrip("/").rsplit("/", 1)[-1])
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
                "$schema": "https://antigravity.google/schemas/v1/plugin.json",
                "name": "saarius-skills",
                "displayName": "Saarius Skills",
                "version": "0.7.1",
                "description": "Experimental agent skills, progressive product-decision workflows, and local ACP delegation.",
            },
        )
        self.assertEqual(codex["name"], "saarius-skills")
        self.assertEqual(codex["version"], "0.7.1")
        self.assertEqual(codex["skills"], ["./skills/", "./vendor/pstack/skills/"])
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
        self.assertLessEqual(set(claude), metadata | {"skills"})
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
        # Both roots are explicit so custom-path replacement and additive loaders work.
        self.assertEqual(claude["skills"], ["./skills/", "./vendor/pstack/skills/"])
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

    def test_smoky_character_studio_skill_is_packaged(self) -> None:
        skill = (CHARACTER_STUDIO_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (
            CHARACTER_STUDIO_SKILL / "agents" / "openai.yaml"
        ).read_text(encoding="utf-8")
        contract = (
            CHARACTER_STUDIO_SKILL / "references" / "sprite-v2-contract.md"
        ).read_text(encoding="utf-8")
        helper = CHARACTER_STUDIO_SKILL / "scripts" / "compile_pet_atlas.py"
        cursor = json.loads(
            (ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertLessEqual(len(skill.splitlines()), 500)
        self.assertIn("name: smoky-character-studio\n", skill)
        self.assertIn("$smoky-character-studio", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("./skills/smoky-character-studio/", cursor["skills"])
        self.assertEqual(
            (CHARACTER_STUDIO_SKILL / "LICENSE").read_bytes(),
            (ROOT / "LICENSE").read_bytes(),
        )
        self.assertIn("#FF00FF", skill)
        self.assertIn("sprite_version: 2", skill)
        self.assertIn("1536×2288", contract)
        self.assertIn("Clank", contract)
        self.assertIn("Bobby Bones", contract)
        self.assertIn("Blaze", contract)
        self.assertTrue(helper.is_file())
        self.assertTrue(helper.stat().st_mode & 0o111)
        spec_run = subprocess.run(
            [sys.executable, str(helper), "spec"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(spec_run.returncode, 0, spec_run.stderr)
        spec_payload = json.loads(spec_run.stdout)
        self.assertEqual(spec_payload["populated_frames"], 73)
        self.assertEqual(spec_payload["unused_cells"], 15)

    def test_agy_sidebar_session_skill_is_packaged(self) -> None:
        skill = (AGY_SIDEBAR_SESSION_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (
            AGY_SIDEBAR_SESSION_SKILL / "agents" / "openai.yaml"
        ).read_text(encoding="utf-8")
        catalog = (
            AGY_SIDEBAR_SESSION_SKILL / "references" / "language-server-rpcs.md"
        ).read_text(encoding="utf-8")
        helper = AGY_SIDEBAR_SESSION_SKILL / "scripts" / "agy-session.py"
        cursor = json.loads(
            (ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertLessEqual(len(skill.splitlines()), 500)
        self.assertIn("name: agy-sidebar-session\n", skill)
        self.assertIn("$agy-sidebar-session", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("./skills/agy-sidebar-session/", cursor["skills"])
        self.assertEqual(
            (AGY_SIDEBAR_SESSION_SKILL / "LICENSE").read_bytes(),
            (ROOT / "LICENSE").read_bytes(),
        )
        self.assertIn("agentapi new-conversation", skill)
        self.assertIn("LanguageServerService", catalog)
        self.assertIn("WaitForConversationFullyIdle", catalog)
        self.assertTrue(helper.is_file())
        self.assertTrue(helper.stat().st_mode & 0o111)
        help_run = subprocess.run(
            [sys.executable, str(helper), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(help_run.returncode, 0, help_run.stderr)
        self.assertIn("export-md", help_run.stdout)

    def test_smoky_github_design_skill_is_packaged_and_verifies_assets(self) -> None:
        skill = (GITHUB_DESIGN_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (
            GITHUB_DESIGN_SKILL / "agents" / "openai.yaml"
        ).read_text(encoding="utf-8")
        anatomy = (
            GITHUB_DESIGN_SKILL / "references" / "top10-github-anatomy.md"
        ).read_text(encoding="utf-8")
        recipes = (
            GITHUB_DESIGN_SKILL / "references" / "style-recipes-and-shelf-hygiene.md"
        ).read_text(encoding="utf-8")
        helper = GITHUB_DESIGN_SKILL / "scripts" / "verify_github_assets.py"
        cursor = json.loads(
            (ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertLessEqual(len(skill.splitlines()), 500)
        self.assertIn("name: smoky-github-design\n", skill)
        self.assertIn("$smoky-github-design", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("./skills/smoky-github-design/", cursor["skills"])
        self.assertEqual(
            (GITHUB_DESIGN_SKILL / "LICENSE").read_bytes(),
            (ROOT / "LICENSE").read_bytes(),
        )
        self.assertIn("prefers-color-scheme", skill)
        self.assertIn("1280×640", skill)
        self.assertIn("smoky-character-studio", skill)
        self.assertIn("openclaw/openclaw", anatomy)
        self.assertIn("morluto/rea", anatomy)
        self.assertIn("Character-Mark", recipes)
        self.assertTrue(helper.is_file())
        self.assertTrue(helper.stat().st_mode & 0o111)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            svg_mark = tmp_root / "mark.svg"
            svg_mark.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/></svg>',
                encoding="utf-8",
            )
            readme = tmp_root / "README.md"
            readme.write_text(
                '<picture>\n'
                '  <source media="(prefers-color-scheme: dark)" srcset="docs/banner-dark.jpg">\n'
                '  <source media="(prefers-color-scheme: light)" srcset="docs/banner-light.jpg">\n'
                '  <img alt="Demo Banner" src="docs/banner-dark.jpg">\n'
                '</picture>\n\n'
                'Inline code docs like `Use an <img> element` or '
                '`<img src="https://github.com/example/private-shelf/releases/download/v1/x.png">` '
                'must not be treated as live HTML.\n\n'
                '    <img src="https://github.com/example/private-shelf/releases/download/v1/indented.png">\n\n'
                '- ~~~sh\n'
                '  > /tmp/out\n'
                '  <img src="https://github.com/example/private-shelf/releases/download/v1/list-fence.png">\n'
                '  ~~~\n'
                '-     <img src="https://github.com/example/private-shelf/releases/download/v1/list-indented.png">\n',
                encoding="utf-8",
            )
            ok_run = subprocess.run(
                [
                    sys.executable,
                    str(helper),
                    "--mark",
                    str(svg_mark),
                    "--readme",
                    str(readme),
                    "--repo-visibility",
                    "PUBLIC",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(ok_run.returncode, 0, ok_run.stderr)
            payload = json.loads(ok_run.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["assets"][0]["width"], 24)
            self.assertTrue(payload["readme"]["has_picture"])

            bad_readme = tmp_root / "README-bad.md"
            bad_readme.write_text(
                "![Broken](https://github.com/example/private-shelf/releases/download/v1/banner.jpg)\n",
                encoding="utf-8",
            )
            # Fails closed in PUBLIC mode even without --forbid-in-public
            default_bad_run = subprocess.run(
                [
                    sys.executable,
                    str(helper),
                    "--readme",
                    str(bad_readme),
                    "--repo-visibility",
                    "PUBLIC",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(default_bad_run.returncode, 1)
            self.assertIn("unverified GitHub asset shelf", default_bad_run.stdout)

            # Passes when explicitly verified as a public shelf, unless also forbidden
            public_readme = tmp_root / "README-public-shelf.md"
            public_readme.write_text(
                "![Public](https://github.com/example/public-shelf/releases/download/v1/banner.jpg)\n",
                encoding="utf-8",
            )
            allowed_run = subprocess.run(
                [
                    sys.executable,
                    str(helper),
                    "--readme",
                    str(public_readme),
                    "--repo-visibility",
                    "PUBLIC",
                    "--allow-public-shelf",
                    "example/public-shelf",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(allowed_run.returncode, 0, allowed_run.stderr)

            forbidden_run = subprocess.run(
                [
                    sys.executable,
                    str(helper),
                    "--readme",
                    str(public_readme),
                    "--repo-visibility",
                    "PUBLIC",
                    "--allow-public-shelf",
                    "example/public-shelf",
                    "--forbid-in-public",
                    "example/public-shelf",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(forbidden_run.returncode, 1)

            # Reference-style Markdown images and /releases/latest/download/ URLs fail closed too
            ref_readme = tmp_root / "README-ref-latest.md"
            ref_readme.write_text(
                "![Banner][hero]\n"
                "![latest][]\n\n"
                "[hero]: https://github.com/example/private-shelf/releases/download/v1/banner.png\n"
                "[latest]: https://github.com/example/latest-shelf/releases/latest/download/banner.png\n",
                encoding="utf-8",
            )
            ref_bad_run = subprocess.run(
                [
                    sys.executable,
                    str(helper),
                    "--readme",
                    str(ref_readme),
                    "--repo-visibility",
                    "PUBLIC",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(ref_bad_run.returncode, 1)
            self.assertIn("example/private-shelf", ref_bad_run.stdout)
            self.assertIn("example/latest-shelf", ref_bad_run.stdout)

            # PRIVATE README rejects embedded GitHub release URLs (Camo auth failure)
            priv_release_run = subprocess.run(
                [
                    sys.executable,
                    str(helper),
                    "--readme",
                    str(bad_readme),
                    "--repo-visibility",
                    "PRIVATE",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(priv_release_run.returncode, 1)
            self.assertIn("Camo", priv_release_run.stdout)

            # Content AFTER a list-item fence (- ~~~sh ... ~~~) is still inspected
            after_list_fence = tmp_root / "README-after-list-fence.md"
            after_list_fence.write_text(
                "- ~~~sh\n"
                "  echo ok\n"
                "  ~~~\n\n"
                "![After](https://github.com/example/private-shelf/releases/download/v1/after.png)\n",
                encoding="utf-8",
            )
            after_list_run = subprocess.run(
                [
                    sys.executable,
                    str(helper),
                    "--readme",
                    str(after_list_fence),
                    "--repo-visibility",
                    "PUBLIC",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(after_list_run.returncode, 1)
            self.assertIn("example/private-shelf", after_list_run.stdout)

            zero_mark = tmp_root / "zero.svg"
            zero_mark.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 0 0"></svg>',
                encoding="utf-8",
            )
            zero_run = subprocess.run(
                [sys.executable, str(helper), "--mark", str(zero_mark)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(zero_run.returncode, 1)

            # Social preview rejects 1280x640 SVG/WebP and accepts 1280x640 PNG
            bad_social_svg = tmp_root / "social.svg"
            bad_social_svg.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 640"><rect width="1280" height="640"/></svg>',
                encoding="utf-8",
            )
            bad_social_run = subprocess.run(
                [sys.executable, str(helper), "--social", str(bad_social_svg)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bad_social_run.returncode, 1)
            self.assertIn("must be PNG, JPEG, or GIF", bad_social_run.stdout)

            bad_social_webp = tmp_root / "social.webp"
            bad_social_webp.write_bytes(
                b"RIFF"
                + (22).to_bytes(4, "little")
                + b"WEBP"
                + b"VP8X"
                + (10).to_bytes(4, "little")
                + b"\x00\x00\x00\x00"
                + (1279).to_bytes(3, "little")
                + (639).to_bytes(3, "little")
            )
            bad_webp_run = subprocess.run(
                [sys.executable, str(helper), "--social", str(bad_social_webp)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bad_webp_run.returncode, 1)
            self.assertIn("must be PNG, JPEG, or GIF", bad_webp_run.stdout)

            import struct
            import zlib

            ihdr = struct.pack(">IIBBBBB", 1280, 640, 8, 2, 0, 0, 0)
            valid_png = (
                b"\x89PNG\r\n\x1a\n"
                + struct.pack(">I", 13)
                + b"IHDR"
                + ihdr
                + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
                + struct.pack(">I", 0)
                + b"IEND"
                + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
            )
            good_social_png = tmp_root / "social.png"
            good_social_png.write_bytes(valid_png)
            good_social_run = subprocess.run(
                [sys.executable, str(helper), "--social", str(good_social_png)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(good_social_run.returncode, 0, good_social_run.stderr)

    def test_smoky_label_dieline_skill_is_packaged_and_verifies_prepress_contracts(self) -> None:
        import math
        import re
        import zlib

        skill = (LABEL_DIELINE_SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = (
            LABEL_DIELINE_SKILL / "agents" / "openai.yaml"
        ).read_text(encoding="utf-8")
        prepress_ref = (
            LABEL_DIELINE_SKILL / "references" / "prepress-and-container-specs.md"
        ).read_text(encoding="utf-8")
        brand_vecs = json.loads(
            (LABEL_DIELINE_SKILL / "assets" / "brand_vectors.json").read_text(encoding="utf-8")
        )
        helper = LABEL_DIELINE_SKILL / "scripts" / "dieline_engine.py"
        cursor = json.loads(
            (ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
        )

        self.assertLessEqual(len(skill.splitlines()), 500)
        self.assertIn("name: smoky-label-dieline\n", skill)
        self.assertIn("$smoky-label-dieline", metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)
        self.assertIn("./skills/smoky-label-dieline/", cursor["skills"])
        self.assertEqual(
            (LABEL_DIELINE_SKILL / "LICENSE").read_bytes(),
            (ROOT / "LICENSE").read_bytes(),
        )
        for catalog in ("README.md", "docs/portable-skills.md"):
            self.assertIn(
                "skills/smoky-label-dieline/SKILL.md",
                (ROOT / catalog).read_text(encoding="utf-8"),
            )
        for doc in LABEL_DIELINE_SKILL.rglob("*.md"):
            text = doc.read_text(encoding="utf-8")
            self.assertNotIn("/Users/", text, str(doc))
            self.assertNotIn("/home/", text, str(doc))
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if "://" not in target and not target.startswith("#"):
                    self.assertTrue(
                        (doc.parent / target.split("#")[0]).is_file(),
                        f"{doc}: {target}",
                    )
        self.assertNotIn("/Users/", helper.read_text(encoding="utf-8"))
        self.assertNotIn("/home/", helper.read_text(encoding="utf-8"))
        self.assertIn("Die Line", skill)
        self.assertIn("TAC", prepress_ref)
        self.assertIn("smoky_co", brand_vecs)
        self.assertIn("smcbd", brand_vecs)
        self.assertTrue(helper.is_file())
        self.assertTrue(helper.stat().st_mode & 0o111)

        # 1. Hermetic --help smoke
        help_run = subprocess.run(
            [sys.executable, str(helper), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(help_run.returncode, 0, help_run.stderr)
        self.assertIn("--calc-container", help_run.stdout)

        # 2. Container-to-dieline dimensional math across cylinder, tapered cone, pouch, and carton
        cyl_run = subprocess.run(
            [
                sys.executable,
                str(helper),
                "--calc-container",
                json.dumps(
                    {
                        "type": "cylinder",
                        "diameter_in": 2.0865,
                        "straight_height_in": 1.815,
                        "lid_recess_in": 2.5625,
                    }
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(cyl_run.returncode, 0, cyl_run.stderr)
        cyl_payload = json.loads(cyl_run.stdout)
        self.assertEqual(len(cyl_payload["panels"]), 2)
        self.assertAlmostEqual(cyl_payload["panels"][0]["width_in"], 2.5, places=3)
        self.assertAlmostEqual(cyl_payload["panels"][1]["width_in"], 6.4299, places=3)
        self.assertAlmostEqual(cyl_payload["panels"][1]["height_in"], 1.69, places=3)

        carton_run = subprocess.run(
            [
                sys.executable,
                str(helper),
                "--calc-container",
                json.dumps(
                    {"type": "carton", "width_in": 2.0, "depth_in": 1.5, "height_in": 4.0}
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(carton_run.returncode, 0, carton_run.stderr)
        carton_panel = json.loads(carton_run.stdout)["panels"][0]
        self.assertEqual(carton_panel["width_in"], 7.5)
        self.assertEqual(carton_panel["height_in"], 8.25)
        self.assertEqual(len(carton_panel["carton_net"]["fold_lines_in"]), 12)
        self.assertEqual(len(carton_panel["carton_net"]["flap_slits_in"]), 3)

        cone_run = subprocess.run(
            [
                sys.executable,
                str(helper),
                "--calc-container",
                json.dumps(
                    {
                        "type": "tapered",
                        "bottom_diameter_in": 2.0,
                        "top_diameter_in": 3.0,
                        "vertical_height_in": 4.0,
                    }
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(cone_run.returncode, 0, cone_run.stderr)
        cone_panel = json.loads(cone_run.stdout)["panels"][0]
        self.assertEqual(cone_panel["shape"], "conical_wrap")
        self.assertAlmostEqual(cone_panel["inner_radius_in"], 8.125, places=3)
        self.assertAlmostEqual(cone_panel["outer_radius_in"], 12.0311, places=3)
        self.assertGreater(cone_panel["sector_angle_deg"], 43.0)

        # Long (> 300-byte) inline JSON `--calc-container` must parse directly without ENAMETOOLONG filesystem stat
        long_inline_json = json.dumps(
            {
                "container_type": "cylinder",
                "diameter_in": 2.125,
                "straight_height_in": 2.0,
                "seam_gap_in": 0.25,
                "height_clearance_in": 0.3125,
                "corner_radius_in": 0.1092,
                "lid_recess_in": 2.50,
                "lid_clearance_in": 0.0,
                "bleed_in": 0.125,
                "safety_in": 0.0625,
                "notes": "x" * 180,
            }
        )
        self.assertGreater(len(long_inline_json.encode("utf-8")), 300)
        long_calc_run = subprocess.run(
            [sys.executable, str(helper), "--calc-container", long_inline_json],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(long_calc_run.returncode, 0, long_calc_run.stderr)
        self.assertEqual(len(json.loads(long_calc_run.stdout)["panels"]), 2)

        # 3. UPC-A Modulo-10 encoder & bad check-digit rejection
        upc_ok = subprocess.run(
            [sys.executable, str(helper), "--encode-upca", "85004341302"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(upc_ok.returncode, 0, upc_ok.stderr)
        upc_data = json.loads(upc_ok.stdout)
        self.assertEqual(upc_data["upc12"], "850043413028")
        self.assertEqual(upc_data["modules"], 95)

        upc_bad = subprocess.run(
            [sys.executable, str(helper), "--encode-upca", "850043413029"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(upc_bad.returncode, 0)

        # 4. GS1 retail UPC-A sizing, 4-module QR quiet zone, and conical annular sector normal-offset verification
        import importlib.util

        spec_mod = importlib.util.spec_from_file_location("dieline_engine", helper)
        assert spec_mod and spec_mod.loader
        mod = importlib.util.module_from_spec(spec_mod)
        spec_mod.loader.exec_module(mod)

        # GS1 retail UPC-A minimum & fixed aspect-ratio bar-height enforcement (bar_h >= 69.23X)
        valid_upc = mod.validate_upca_box(86.0, 62.0, bg_pad=2.0)
        self.assertGreaterEqual(valid_upc["mod_w_pt"] / 72.0, 0.0104)
        self.assertGreaterEqual(valid_upc["short_bar_h_pt"], valid_upc["mod_w_pt"] * mod.GS1_UPCA_BAR_HEIGHT_MODULES - 1e-6)
        with self.assertRaises(ValueError):
            mod.validate_upca_box(70.0, 36.25, bg_pad=2.0)
        with self.assertRaises(ValueError):
            # 104pt width (X=0.01278") requires >= 0.885" (63.7pt) bars, so 62pt outer box is truncated and rejected!
            mod.validate_upca_box(104.0, 62.0, bg_pad=2.0)
        wide_upc_panel = mod.DielinePanel("wide_upc", "rect", cx=400.0, cy=300.0, width_in=7.5, height_in=3.0)
        wide_upc_plan = mod.plan_panel_artwork_layout(wide_upc_panel, {"product_name": "WIDE WRAP", "upc": "850043413028"})
        w_ux, w_uy, w_uw, w_uh = wide_upc_plan["upc_rect"]
        wide_upc_metrics = mod.validate_upca_box(w_uw, w_uh, bg_pad=2.0)
        self.assertGreaterEqual(wide_upc_metrics["short_bar_h_pt"], wide_upc_metrics["mod_w_pt"] * mod.GS1_UPCA_BAR_HEIGHT_MODULES - 1e-6)

        # ISO/IEC 18004 4-module QR quiet zone
        qr_layout = mod.compute_qr_layout(40.0, 25, quiet_modules=4.0)
        self.assertAlmostEqual(qr_layout["quiet_pad_pt"] / qr_layout["cell_pt"], 4.0, places=6)
        with self.assertRaises(ValueError):
            mod.compute_qr_layout(40.0, 25, quiet_modules=2.0)

        # Conical annular sector perpendicular normal offset (+0.125" = 9.0 pt)
        cp = mod.DielinePanel(
            "cone",
            "conical_wrap",
            cx=300.0,
            cy=300.0,
            width_in=cone_panel["width_in"],
            height_in=cone_panel["height_in"],
            inner_radius_in=cone_panel["inner_radius_in"],
            outer_radius_in=cone_panel["outer_radius_in"],
            sector_angle_deg=cone_panel["sector_angle_deg"],
            apex_down=True,
        )
        pts_0 = cp.annular_sector_points(0.0, arc_steps=64)
        pts_b = cp.annular_sector_points(9.0, arc_steps=64)
        # Midpoint of outer arc is at index 32; midpoint of inner arc is at index 65 + 32 = 97
        self.assertAlmostEqual(pts_b[32][1] - pts_0[32][1], 9.0, places=5)
        self.assertAlmostEqual(pts_0[97][1] - pts_b[97][1], 9.0, places=5)
        cbx0, cby0, cbw, cbh = cp.offset_bbox(9.0)
        self.assertGreater(cbw, cp.w + 18.0 + 2.0)  # acute radial miter corners protrude past trim_w + 2*bleed
        for px, py in pts_b:
            self.assertGreaterEqual(px, cbx0 - 1e-6)
            self.assertLessEqual(px, cbx0 + cbw + 1e-6)
            self.assertGreaterEqual(py, cby0 - 1e-6)
            self.assertLessEqual(py, cby0 + cbh + 1e-6)

        # Flat prism trapezoid normal offset
        tp = mod.DielinePanel(
            "prism",
            "flat_trapezoid",
            cx=200.0,
            cy=200.0,
            width_in=2.0,
            top_width_in=3.0,
            height_in=4.0,
        )
        v0 = tp.trapezoid_vertices(0.0)
        vb = tp.trapezoid_vertices(9.0)
        dx, dy = v0[2][0] - v0[1][0], v0[2][1] - v0[1][1]
        edge_len = math.hypot(dx, dy)
        nx, ny = dy / edge_len, -dx / edge_len
        perp_dist = (vb[1][0] - v0[1][0]) * nx + (vb[1][1] - v0[1][1]) * ny
        self.assertAlmostEqual(perp_dist, 9.0, places=5)
        tbx0, tby0, tbw, tbh = tp.offset_bbox(9.0)
        self.assertGreater(tbw, max(tp.w, tp.top_w) + 18.0 + 1.0)
        for px, py in vb:
            self.assertGreaterEqual(px, tbx0 - 1e-6)
            self.assertLessEqual(px, tbx0 + tbw + 1e-6)
            self.assertGreaterEqual(py, tby0 - 1e-6)
            self.assertLessEqual(py, tby0 + tbh + 1e-6)

        # Square `rect` vs `rounded_rect` corner defaults
        sq_rect = mod.DielinePanel("sq", "rect", cx=200.0, cy=200.0, width_in=4.0, height_in=2.0)
        rd_rect = mod.DielinePanel("rd", "rounded_rect", cx=200.0, cy=200.0, width_in=4.0, height_in=2.0)
        self.assertEqual(sq_rect.corner_r, 0.0)
        self.assertGreater(rd_rect.corner_r, 0.0)

        # Folded carton & sleeve barcode stays strictly inside one flat body panel (never crosses fold scores),
        # and omitting 'upc' or 'qr_url' never fabricates another SKU's GTIN or URL.
        carton_dp = mod.DielinePanel(
            "carton_rte",
            "tuck_box",
            cx=400.0,
            cy=400.0,
            width_in=carton_panel["width_in"],
            height_in=carton_panel["height_in"],
            carton_net=carton_panel["carton_net"],
        )
        carton_no_upc = mod.plan_panel_artwork_layout(carton_dp, {"product_name": "ROASTED COFFEE"})
        self.assertIsNone(carton_no_upc["upc_rect"])
        self.assertIsNone(carton_no_upc["qr_zone"]["qr_rect"])

        carton_plan = mod.plan_panel_artwork_layout(
            carton_dp,
            {
                "product_name": "RELIEF TINCTURE",
                "upc": "850043413028",
                "qr_url": "https://example.com/coa",
            },
        )
        ux, uy, uw, uh = carton_plan["upc_rect"]
        upc_face = carton_plan["upc_face"]
        self.assertGreaterEqual(ux, upc_face["x0"] + carton_dp.safety)
        self.assertLessEqual(ux + uw, upc_face["x1"] - carton_dp.safety)
        for fx1, fy1, fx2, fy2 in carton_dp.fold_segments():
            if abs(fx1 - fx2) < 1e-6:  # vertical fold score
                self.assertFalse(ux < fx1 < ux + uw, f"Barcode {ux}..{ux+uw} crossed vertical fold at {fx1}")

        # Standalone circular labels preserve requested qr_url/disclaimer, and small 2"x2" flat labels
        # omit unused optional columns instead of failing on empty side-column reservations.
        standalone_circle = mod.DielinePanel("seal", "circle", cx=200.0, cy=200.0, width_in=3.0, height_in=3.0)
        circle_qr_plan = mod.plan_panel_artwork_layout(
            standalone_circle,
            {"product_name": "BATCH SEAL", "qr_url": "https://example.com/batch", "disclaimer": "KEEP REFRIGERATED."},
        )
        self.assertEqual(circle_qr_plan["mode"], "flat_3zone")
        self.assertIsNotNone(circle_qr_plan["qr_zone"]["qr_rect"])
        self.assertGreater(len(circle_qr_plan["qr_zone"]["fda_layout"]["lines"]), 0)

        small_flat = mod.DielinePanel("small_2x2", "rect", cx=200.0, cy=200.0, width_in=2.0, height_in=2.0)
        small_plan = mod.plan_panel_artwork_layout(small_flat, {"product_name": "COFFEE"})
        self.assertIsNone(small_plan["qr_zone"])
        self.assertIsNone(small_plan["upc_zone"])
        self.assertFalse(small_plan["draw_dividers"])

        # 3"x3" rectangular panel with brand + qr_url where narrow QR column cannot fit a side vector logo
        # must preserve brand identification in the hero header instead of hiding both!
        rect_3x3 = mod.DielinePanel("rect_3x3", "rect", cx=200.0, cy=200.0, width_in=3.0, height_in=3.0)
        rect_3x3_plan = mod.plan_panel_artwork_layout(
            rect_3x3,
            {"brand": "SMOKY MOUNTAIN CBD", "product_name": "BALM", "qr_url": "https://example.com/coa"},
        )
        self.assertIsNone(rect_3x3_plan["qr_zone"]["vec_box"])
        self.assertIsNotNone(rect_3x3_plan["hero"]["brand_header"])

        # Open sleeve with wide glue_flap_in > 0.85" excludes the leading glue flap from printable faces
        wide_sleeve_calc = mod.calculate_container_dieline(
            {"type": "sleeve", "width_in": 2.0, "depth_in": 1.5, "height_in": 4.0, "glue_flap_in": 1.0}
        )
        sp_cfg = wide_sleeve_calc["panels"][0]
        self.assertTrue(sp_cfg["has_leading_glue_flap"])
        sleeve_dp = mod.DielinePanel(
            sp_cfg["panel_id"],
            sp_cfg["shape"],
            cx=400.0,
            cy=300.0,
            width_in=sp_cfg["width_in"],
            height_in=sp_cfg["height_in"],
            fold_offsets_in=sp_cfg["fold_offsets_in"],
            has_leading_glue_flap=sp_cfg["has_leading_glue_flap"],
        )
        sleeve_plan = mod.plan_panel_artwork_layout(sleeve_dp, {"product_name": "TEA SLEEVE"})
        glue_right_edge = sleeve_dp.x0 + mod.inch(1.0)
        self.assertGreater(sleeve_plan["hero"]["x0"], glue_right_edge)

        # Custom palette CMYK channel bounds and <= 300% TAC enforcement
        valid_pal = mod.validate_palette_cmyk({"bg": [70, 40, 50, 30]})
        self.assertEqual(sum(valid_pal["bg"]), 190.0)
        with self.assertRaises(ValueError):
            mod.validate_palette_cmyk({"bg": [100, 100, 100, 100]})
        with self.assertRaises(ValueError):
            mod.validate_palette_cmyk({"bg": [-5, 10, 10, 10]})
        with self.assertRaises(ValueError):
            mod.plan_panel_artwork_layout(
                sq_rect,
                {"product_name": "INK OVERLOAD", "palette_cmyk": {"bg": [100, 100, 100, 100]}},
            )

        # Overflowing directions/ingredients copy is rejected rather than silently dropped
        short_rect = mod.DielinePanel("short", "rect", cx=200.0, cy=200.0, width_in=3.0, height_in=1.1)
        with self.assertRaises(ValueError):
            mod.plan_panel_artwork_layout(
                short_rect,
                {
                    "product_name": "MINI BALM",
                    "directions": "Apply liberally to clean dry skin up to four times daily.",
                    "ingredients": "Octyldodecanol, Squalane, Menthol, Camphor, Hemp Extract.",
                    "upc": "850043413028",
                },
            )
        tall_rect = mod.DielinePanel("tall", "rounded_rect", cx=300.0, cy=200.0, width_in=6.43, height_in=1.69)
        with self.assertRaises(ValueError):
            mod.plan_panel_artwork_layout(
                tall_rect,
                {
                    "product_name": "BALANCE BALM",
                    "ingredients": " ".join(["Organic Botanical Extract,"] * 180),
                },
            )

        # 5. Stdlib PDF preflight check (passes CMYK + Spot + non-printing tech OCG + Overprint; fails on RGB or missing PrintState OFF)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            stream_body = zlib.compress(
                b"q /OC /LayerArtwork BDC 0.5 0.4 0.4 0.9 k /GSOverprint gs EMC Q\n"
            )
            good_pdf = tmp_root / "good.pdf"
            good_pdf.write_bytes(
                b"%PDF-1.7\n"
                b"1 0 obj << /Type /Catalog /OCProperties << /OCGs [2 0 R 3 0 R 4 0 R 5 0 R 6 0 R 7 0 R] "
                b"/D << /AS [ << /Event /Print /Category [/Print] /OCGs [2 0 R 3 0 R 4 0 R 5 0 R 6 0 R 7 0 R] >> ] >> >> >> endobj\n"
                b"2 0 obj << /Type /OCG /Name (Artwork) /Usage << /Print << /PrintState /ON >> >> >> endobj\n"
                b"3 0 obj << /Type /OCG /Name (Diecut) /Usage << /Print << /PrintState /OFF >> >> >> endobj\n"
                b"4 0 obj << /Type /OCG /Name (Safety) /Usage << /Print << /PrintState /OFF >> >> >> endobj\n"
                b"5 0 obj << /Type /OCG /Name (Bleed) /Usage << /Print << /PrintState /OFF >> >> >> endobj\n"
                b"6 0 obj << /Type /OCG /Name (Dimensions) /Usage << /Print << /PrintState /OFF >> >> >> endobj\n"
                b"7 0 obj << /Type /OCG /Name (Die Template) /Usage << /Print << /PrintState /OFF >> >> >> endobj\n"
                b"8 0 obj [ /Separation /Die#20Line /DeviceCMYK << >> ] endobj\n"
                b"9 0 obj [ /Separation /Safety#20Line /DeviceCMYK << >> ] endobj\n"
                b"10 0 obj [ /Separation /Bleed#20Line /DeviceCMYK << >> ] endobj\n"
                b"11 0 obj << /GSOverprint << /Type /ExtGState /OP true /op true /OPM 1 >> >> endobj\n"
                b"12 0 obj << /Filter /FlateDecode >>\nstream\n"
                + stream_body
                + b"\nendstream\nendobj\n%%EOF\n"
            )
            rep_ok = mod._extract_pdf_text_and_content_streams(good_pdf.read_bytes())
            self.assertIn(b"/GSOverprint gs", rep_ok)
            orig_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

            def _stdlib_only_imports(name, *a, **kw):
                if name in ("pymupdf", "pikepdf"):
                    raise ImportError("mocked stdlib-only mode")
                return orig_import(name, *a, **kw)

            import builtins

            old_imp = builtins.__import__
            try:
                builtins.__import__ = _stdlib_only_imports
                good_rep = mod.verify_dieline_pdf(good_pdf)
                self.assertTrue(good_rep["preflight_pass"])
                self.assertTrue(good_rep["cmyk_only_no_rgb"])
                self.assertTrue(good_rep["tac_within_limit"])
                self.assertTrue(good_rep["non_printing_tech_layers"])

                no_printstate_pdf = tmp_root / "missing_printstate.pdf"
                no_printstate_pdf.write_bytes(good_pdf.read_bytes().replace(b"/PrintState /OFF", b"/PrintState /ON"))
                self.assertFalse(mod.verify_dieline_pdf(no_printstate_pdf)["preflight_pass"])

                # Changing JUST Diecut to PrintState ON while Safety/Bleed stay OFF must fail stdlib preflight!
                diecut_on_pdf = tmp_root / "diecut_print_on.pdf"
                diecut_on_pdf.write_bytes(
                    good_pdf.read_bytes().replace(
                        b"3 0 obj << /Type /OCG /Name (Diecut) /Usage << /Print << /PrintState /OFF >> >> >> endobj",
                        b"3 0 obj << /Type /OCG /Name (Diecut) /Usage << /Print << /PrintState /ON >> >> >> endobj",
                    )
                )
                diecut_on_rep = mod.verify_dieline_pdf(diecut_on_pdf)
                self.assertFalse(diecut_on_rep["preflight_pass"])
                self.assertFalse(diecut_on_rep["non_printing_tech_layers"])

                over_tac_stream = zlib.compress(
                    b"q /OC /LayerArtwork BDC 1.0 1.0 1.0 1.0 k /GSOverprint gs EMC Q\n"
                )
                over_tac_pdf = tmp_root / "over_tac.pdf"
                over_tac_pdf.write_bytes(good_pdf.read_bytes().replace(stream_body, over_tac_stream))
                tac_rep = mod.verify_dieline_pdf(over_tac_pdf)
                self.assertFalse(tac_rep["preflight_pass"])
                self.assertFalse(tac_rep["tac_within_limit"])
                self.assertAlmostEqual(tac_rep["max_tac_pct"], 400.0, places=2)

                rgb_pdf = tmp_root / "bad_rgb.pdf"
                rgb_pdf.write_bytes(good_pdf.read_bytes() + b"\n13 0 obj /DeviceRGB endobj\n")
                bad_rep = mod.verify_dieline_pdf(rgb_pdf)
                self.assertFalse(bad_rep["preflight_pass"])
                self.assertFalse(bad_rep["cmyk_only_no_rgb"])

                # Uncompressed (unfiltered) page streams must still be inspected for RGB and >300% CMYK TAC
                uncompressed_rgb_pdf = tmp_root / "uncompressed_rgb.pdf"
                uncompressed_rgb_pdf.write_bytes(
                    good_pdf.read_bytes().replace(
                        b"12 0 obj << /Filter /FlateDecode >>\nstream\n" + stream_body + b"\nendstream",
                        b"12 0 obj << /Length 58 >>\nstream\nq /OC /LayerArtwork BDC 0.2 0.4 0.8 rg /GSOverprint gs EMC Q\nendstream",
                    )
                )
                unc_rgb_rep = mod.verify_dieline_pdf(uncompressed_rgb_pdf)
                self.assertFalse(unc_rgb_rep["preflight_pass"])
                self.assertFalse(unc_rgb_rep["cmyk_only_no_rgb"])

                uncompressed_tac_pdf = tmp_root / "uncompressed_tac.pdf"
                uncompressed_tac_pdf.write_bytes(
                    good_pdf.read_bytes().replace(
                        b"12 0 obj << /Filter /FlateDecode >>\nstream\n" + stream_body + b"\nendstream",
                        b"12 0 obj << /Length 63 >>\nstream\nq /OC /LayerArtwork BDC 1.0 1.0 1.0 1.0 k /GSOverprint gs EMC Q\nendstream",
                    )
                )
                unc_tac_rep = mod.verify_dieline_pdf(uncompressed_tac_pdf)
                self.assertFalse(unc_tac_rep["preflight_pass"])
                self.assertFalse(unc_tac_rep["tac_within_limit"])
                self.assertAlmostEqual(unc_tac_rep["max_tac_pct"], 400.0, places=2)

                # Unknown or corrupt stream filters must fail closed rather than silently passing preflight
                unknown_filter_pdf = tmp_root / "unknown_filter.pdf"
                unknown_filter_pdf.write_bytes(
                    good_pdf.read_bytes().replace(b"/Filter /FlateDecode", b"/Filter /LZWDecode")
                )
                unk_rep = mod.verify_dieline_pdf(unknown_filter_pdf)
                self.assertFalse(unk_rep["preflight_pass"])
                self.assertFalse(unk_rep["streams_decoded_ok"])

                # Overprint check must require `/OP true` (not just `/OPM 1` with `/OP false`)
                op_false_pdf = tmp_root / "op_false.pdf"
                op_false_pdf.write_bytes(
                    good_pdf.read_bytes().replace(
                        b"/OP true /op true /OPM 1",
                        b"/OP false /op false /OPM 1",
                    )
                )
                op_false_rep = mod.verify_dieline_pdf(op_false_pdf)
                self.assertFalse(op_false_rep["preflight_pass"])
                self.assertFalse(op_false_rep["overprint_enabled"])

                # 3-component `/ICCBased` RGB profile (without `/DeviceRGB` or `rg`) must fail RGB check!
                icc_rgb_pdf = tmp_root / "icc_rgb.pdf"
                icc_rgb_pdf.write_bytes(
                    good_pdf.read_bytes().replace(
                        b"%%EOF\n",
                        b"13 0 obj [ /ICCBased 14 0 R ] endobj\n"
                        b"14 0 obj << /N 3 /Length 4 >>\nstream\nICCP\nendstream\nendobj\n%%EOF\n",
                    )
                )
                icc_rgb_rep = mod.verify_dieline_pdf(icc_rgb_pdf)
                self.assertFalse(icc_rgb_rep["preflight_pass"])
                self.assertFalse(icc_rgb_rep["cmyk_only_no_rgb"])

                # Alternate CMYK operators (`/DeviceCMYK cs 1 1 1 1 sc` and `CS` + `SCN`) must enforce TAC <= 300%!
                alt_cmyk_sc_stream = zlib.compress(
                    b"q /OC /LayerArtwork BDC /DeviceCMYK cs 1 1 1 1 sc /GSOverprint gs EMC Q\n"
                )
                alt_cmyk_sc_pdf = tmp_root / "alt_cmyk_sc.pdf"
                alt_cmyk_sc_pdf.write_bytes(good_pdf.read_bytes().replace(stream_body, alt_cmyk_sc_stream))
                alt_sc_rep = mod.verify_dieline_pdf(alt_cmyk_sc_pdf)
                self.assertFalse(alt_sc_rep["preflight_pass"])
                self.assertFalse(alt_sc_rep["tac_within_limit"])
                self.assertAlmostEqual(alt_sc_rep["max_tac_pct"], 400.0, places=2)

                alt_cmyk_scn_stream = zlib.compress(
                    b"q /OC /LayerArtwork BDC /DeviceCMYK CS 0.9 0.9 0.9 0.9 SCN /GSOverprint gs EMC Q\n"
                )
                alt_cmyk_scn_pdf = tmp_root / "alt_cmyk_scn.pdf"
                alt_cmyk_scn_pdf.write_bytes(good_pdf.read_bytes().replace(stream_body, alt_cmyk_scn_stream))
                alt_scn_rep = mod.verify_dieline_pdf(alt_cmyk_scn_pdf)
                self.assertFalse(alt_scn_rep["preflight_pass"])
                self.assertFalse(alt_scn_rep["tac_within_limit"])
                self.assertAlmostEqual(alt_scn_rep["max_tac_pct"], 360.0, places=2)

                # Unresolved multi-ink color space (`/UnknownCS cs 1 1 1 1 scn`) must fail closed!
                unknown_cs_stream = zlib.compress(
                    b"q /OC /LayerArtwork BDC /UnknownCS cs 1 1 1 1 scn /GSOverprint gs EMC Q\n"
                )
                unknown_cs_pdf = tmp_root / "unknown_cs_scn.pdf"
                unknown_cs_pdf.write_bytes(good_pdf.read_bytes().replace(stream_body, unknown_cs_stream))
                unknown_cs_rep = mod.verify_dieline_pdf(unknown_cs_pdf)
                self.assertFalse(unknown_cs_rep["preflight_pass"])
                self.assertFalse(unknown_cs_rep["tac_within_limit"])

                # CMYK `/Shading` gradient stops (`/FunctionType 2` / `3`) exceeding 300% TAC must fail!
                grad_over_pdf = tmp_root / "grad_over_tac.pdf"
                grad_over_pdf.write_bytes(
                    good_pdf.read_bytes().replace(
                        b"%%EOF\n",
                        b"13 0 obj << /ShadingType 2 /ColorSpace /DeviceCMYK /Coords [0 0 100 100] /Function 14 0 R >> endobj\n"
                        b"14 0 obj << /FunctionType 2 /Domain [0 1] /C0 [0.1 0.2 0.3 0.4] /C1 [1 1 1 1] /N 1 >> endobj\n%%EOF\n",
                    )
                )
                grad_over_rep = mod.verify_dieline_pdf(grad_over_pdf)
                self.assertFalse(grad_over_rep["preflight_pass"])
                self.assertFalse(grad_over_rep["tac_within_limit"])
                self.assertAlmostEqual(grad_over_rep["max_tac_pct"], 400.0, places=2)

                # Uninspectable mesh `/ShadingType 4` in CMYK must fail closed!
                mesh_sh_pdf = tmp_root / "mesh_shading.pdf"
                mesh_sh_pdf.write_bytes(
                    good_pdf.read_bytes().replace(
                        b"%%EOF\n",
                        b"13 0 obj << /ShadingType 4 /ColorSpace /DeviceCMYK /BitsPerCoordinate 16 >> endobj\n%%EOF\n",
                    )
                )
                mesh_sh_rep = mod.verify_dieline_pdf(mesh_sh_pdf)
                self.assertFalse(mesh_sh_rep["preflight_pass"])
                self.assertFalse(mesh_sh_rep["tac_within_limit"])
            finally:
                builtins.__import__ = old_imp


if __name__ == "__main__":
    unittest.main()
