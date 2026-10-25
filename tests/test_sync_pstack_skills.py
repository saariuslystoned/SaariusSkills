"""Offline proof of PStack's single vendor source and direct discovery."""
from __future__ import annotations

import json
import runpy
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC = runpy.run_path(str(ROOT / "scripts/sync-pstack-skills"))
UPSTREAM = SYNC["UPSTREAM_SKILLS"]
CUSTOM = SYNC["CUSTOM_SKILLS"]


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, text=True, capture_output=True).stdout.strip()


class PstackSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="pstack-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "package"
        self.source = Path(self.temp.name) / "upstream"
        self.root.mkdir()
        self.source.mkdir()
        for name in CUSTOM:
            shutil.copytree(ROOT / "skills" / name, self.root / "skills" / name)
        for path in (
            "vendor/pstack/.codex-plugin/plugin.json", "vendor/pstack/plugin.json",
            "vendor/pstack/README.md", ".cursor-plugin/plugin.json",
            ".codex-plugin/plugin.json", ".claude-plugin/plugin.json",
            ".agents/plugins/marketplace.json",
        ):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, target)
        git(self.source, "init", "--quiet")
        (self.source / "pstack").mkdir()
        (self.source / "pstack/LICENSE").write_text("Fixture license\n")
        for name in UPSTREAM:
            directory = self.source / "pstack/skills" / name
            directory.mkdir(parents=True)
            (directory / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Fixture.\n---\nFirst upstream version.\n")
        (self.source / "pstack/skills/unselected").mkdir()
        (self.source / "pstack/skills/unselected/SKILL.md").write_text("not selected\n")
        (self.source / "pstack/agents").mkdir()
        (self.source / "pstack/agents/agent.md").write_text("not selected\n")
        self.commit()

    def commit(self) -> str:
        git(self.source, "add", ".")
        git(self.source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "fixture")
        return git(self.source, "rev-parse", "HEAD")

    def update(self, ref: str = "HEAD") -> None:
        SYNC["update"](self.source, ref, self.root)

    def test_refresh_uses_committed_snapshot_and_preserves_local_sources(self) -> None:
        before = SYNC["files"](self.root / "skills")
        metadata = {p: (self.root / "vendor/pstack" / p).read_bytes() for p in SYNC["LOCAL_METADATA"]}
        first = git(self.source, "rev-parse", "HEAD")
        self.update()
        selected = self.source / "pstack/skills/how/SKILL.md"
        selected.write_text(selected.read_text().replace("First upstream", "Second upstream"))
        # A future same-name upstream skill must never replace Bobby Mode.
        (self.source / "pstack/skills/bobby-mode").mkdir()
        (self.source / "pstack/skills/bobby-mode/SKILL.md").write_text("wrong owner\n")
        second = self.commit()
        selected.write_text("uncommitted replacement\n")
        self.update(second)
        self.assertIn("Second upstream", (self.root / "vendor/pstack/skills/how/SKILL.md").read_text())
        self.assertEqual(SYNC["files"](self.root / "skills"), before)
        self.assertEqual({p: (self.root / "vendor/pstack" / p).read_bytes() for p in metadata}, metadata)
        self.assertFalse((self.root / "vendor/pstack/agents").exists())
        self.assertFalse((self.root / "vendor/pstack/skills/unselected").exists())
        self.assertFalse((self.root / "pstack").exists())
        for name in UPSTREAM:
            self.assertFalse((self.root / "skills" / name).exists())
        manifest = json.loads((self.root / "vendor/pstack/UPSTREAM.json").read_text())
        self.assertEqual(manifest["commit"], second)
        self.assertNotEqual(first, second)
        SYNC["check"](self.root)

    def test_vendor_drift_refuses_check_and_update_without_writes(self) -> None:
        self.update()
        (self.root / "vendor/pstack/skills/how/SKILL.md").write_text("hand edited vendor\n")
        before = SYNC["files"](self.root)
        with self.assertRaisesRegex(ValueError, "vendor drift"):
            SYNC["check"](self.root)
        with self.assertRaisesRegex(ValueError, "vendor drift"):
            self.update()
        self.assertEqual(SYNC["files"](self.root), before)

    def test_local_edit_needs_no_projection_and_survives_refresh(self) -> None:
        self.update()
        custom = self.root / "skills/bobby-mode/SKILL.md"
        custom.write_text(custom.read_text() + "\nKeep the operator's workspace convention.\n")
        before = SYNC["files"](self.root / "skills")
        SYNC["check"](self.root)
        self.update()
        self.assertEqual(SYNC["files"](self.root / "skills"), before)

    def test_obsolete_alias_and_root_package_are_rejected(self) -> None:
        self.update()
        alias = self.root / "skills/how"
        alias.symlink_to("../vendor/pstack/skills/how")
        before = SYNC["files"](self.root / "vendor/pstack")
        with self.assertRaisesRegex(ValueError, "only in vendor/pstack"):
            self.update()
        self.assertEqual(SYNC["files"](self.root / "vendor/pstack"), before)
        alias.unlink()
        (self.root / "pstack").mkdir()
        with self.assertRaisesRegex(ValueError, "obsolete root pstack"):
            SYNC["check"](self.root)

    def test_untracked_vendor_content_is_not_exempted_from_hashes(self) -> None:
        self.update()
        (self.root / "vendor/pstack/unexpected.md").write_text("not in the snapshot\n")
        with self.assertRaisesRegex(ValueError, "vendor drift"):
            SYNC["check"](self.root)

    def test_invalid_selected_snapshot_does_not_mutate_outputs(self) -> None:
        self.update()
        before = SYNC["files"](self.root)
        selected = self.source / "pstack/skills/how/SKILL.md"
        selected.unlink()
        selected.symlink_to("../../LICENSE")
        self.commit()
        with self.assertRaisesRegex(ValueError, "unsupported selected upstream entry"):
            self.update()
        self.assertEqual(SYNC["files"](self.root), before)

    def test_vendor_symlink_is_refused_before_refresh(self) -> None:
        self.update()
        target = self.root / "vendor/pstack/skills/how/SKILL.md"
        target.unlink()
        target.symlink_to(self.root / "skills/bobby-mode/SKILL.md")
        before = SYNC["files"](self.root / "skills")
        with self.assertRaisesRegex(ValueError, "refusing symlink"):
            self.update()
        self.assertTrue(target.is_symlink())
        self.assertEqual(SYNC["files"](self.root / "skills"), before)

    def test_real_discovery_has_one_physical_source_per_skill(self) -> None:
        SYNC["check"](ROOT)
        self.assertFalse((ROOT / "pstack").exists())
        for name in UPSTREAM:
            self.assertFalse((ROOT / "skills" / name).exists())
            self.assertFalse((ROOT / "skills" / name).is_symlink())
            self.assertTrue((ROOT / "vendor/pstack/skills" / name / "SKILL.md").is_file())
        for name in CUSTOM:
            self.assertFalse((ROOT / "skills" / name).is_symlink())
            self.assertTrue((ROOT / "skills" / name / "SKILL.md").is_file())

    def test_main_manifests_discover_each_skill_once(self) -> None:
        for relative in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
            manifest = json.loads((ROOT / relative).read_text())
            names = [
                child.name
                for path in manifest["skills"]
                for child in (ROOT / path).iterdir()
                if child.is_dir() and (child / "SKILL.md").is_file()
            ]
            self.assertEqual(len(names), len(set(names)), relative)
            self.assertTrue(set(UPSTREAM + CUSTOM) <= set(names), relative)

    def test_package_compatibility_flag_is_read_only(self) -> None:
        before = SYNC["files"](ROOT / "vendor/pstack")
        result = subprocess.run(["python3", str(ROOT / "scripts/sync-pstack-skills"), "--package"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(SYNC["files"](ROOT / "vendor/pstack"), before)
        self.assertFalse((ROOT / "pstack").exists())


if __name__ == "__main__":
    unittest.main()
