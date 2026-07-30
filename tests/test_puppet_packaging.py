from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "puppet"


class PuppetPackagingTests(unittest.TestCase):
    def test_public_puppet_plans_do_not_publish_absolute_macos_home_paths(
        self,
    ) -> None:
        plans = ROOT / "plans" / "puppet"
        for path in plans.rglob("*"):
            if not path.is_file():
                continue
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("/Users/", text)

    def test_required_package_shape(self):
        required = [
            "SKILL.md",
            "agents/openai.yaml",
            "scripts/puppet.py",
            "scripts/puppet_launch.py",
            "scripts/puppet_fanout.py",
            "scripts/viewer_attach.py",
            "scripts/profile_login.py",
            "scripts/adapter_lab.py",
            "references/operating-contract.md",
            "references/adapter-contract.md",
            "references/fast-launch-contract.md",
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
        self.assertIn("adapter_lab.py recover", text)
        self.assertIn("cooperative same-UID mechanism", text)
        self.assertIn("scripts/puppet_launch.py", text)
        self.assertIn("scripts/puppet_fanout.py", text)
        self.assertIn("runtime failures lane-local", text)
        self.assertIn("explicit `checkpoint` lifecycle", text)

    def test_fast_launch_reference_declares_one_request_boundary(self):
        text = (SKILL / "references" / "fast-launch-contract.md").read_text(
            encoding="utf-8"
        )
        for marker in (
            "puppet_launch.py catalog-init",
            "puppet_launch.py prepare",
            "puppet_launch.py run",
            "puppet_launch.py status",
            "puppet_launch.py attach",
            "puppet_launch.py view",
            "puppet_launch.py checkpoint",
            "puppet_launch.py halt",
            "--timeout",
            "--allow-live-launch",
            "serialized",
            "concurrently",
            "create-only",
            "automatic_cleanup",
            "never invokes census",
            "auth-store read",
            "never reads a pane",
            "never an automatic part of",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

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
        forbidden = [
            "capture-" + "pane",
            "pipe-" + "pane",
            "git " + "push",
            "gh " + "pr",
        ]
        for marker in forbidden:
            self.assertNotIn(marker, sources)

    def test_human_native_live_view_is_an_explicit_baseline_gate(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        campaign = (
            ROOT / "plans" / "puppet" / "codex-goal-regular-qualification.md"
        ).read_text(encoding="utf-8")
        amendment = (
            ROOT / "plans" / "puppet" / "instruction-qualification.md"
        ).read_text(encoding="utf-8")

        self.assertIn("native, unfiltered live TUI", skill)
        self.assertIn("human may attach and detach", skill)
        self.assertIn("human-only read-only attach command", campaign)
        self.assertIn("controller remains transcript-blind", campaign)
        self.assertIn("human-only read-only attach/detach", amendment)
        for text in (skill, campaign, amendment):
            self.assertIn("capture", text)
            self.assertIn("controller", text)

    def test_package_template_layer_shapes_are_declared(self):
        catalog = json.loads(
            (SKILL / "templates" / "instructions" / "catalog.json").read_text(
                encoding="utf-8",
            )
        )
        shipped = catalog.get("shipped_layers")
        self.assertIsInstance(shipped, dict)

        declared = {"catalog.json"}
        declared.add(str(shipped["universal"]["path"]))
        declared.add(str(shipped["model"]["path"]))
        declared.add(str(shipped["lifecycle"]["regular"]))
        declared.update(str(path) for path in shipped["harnesses"].values())

        declared = {str(Path("instructions") / item) for item in declared}
        declared.add("instructions/catalog.json")

        actual = {
            str(Path(path.relative_to(SKILL / "templates")).as_posix())
            for path in (SKILL / "templates" / "instructions").rglob("*")
            if path.is_file()
        }
        self.assertEqual(declared, actual)


if __name__ == "__main__":
    unittest.main()
