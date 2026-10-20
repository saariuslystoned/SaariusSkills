"""Offline proof of PStack source ownership, drift checks and stable discovery."""
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
        shutil.copytree(ROOT / "pstack/custom", self.root / "pstack/custom")
        for path in ("pstack/.codex-plugin/plugin.json", ".cursor-plugin/plugin.json"):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, target)
        (self.root / "skills").mkdir()
        for name in UPSTREAM + CUSTOM:
            (self.root / "skills" / name).symlink_to(Path("../pstack/skills") / name)
        git(self.source, "init", "--quiet")
        (self.source / "pstack").mkdir()
        (self.source / "pstack/LICENSE").write_text("Fixture license\n")
        for name in UPSTREAM:
            directory = self.source / "pstack/skills" / name
            directory.mkdir(parents=True)
            (directory / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Fixture.\n---\nFirst upstream version.\n")
        # Non-selected skills and Cursor agents must not enter either output.
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

    def test_refresh_uses_committed_snapshot_and_preserves_custom_sources(self) -> None:
        before = SYNC["files"](self.root / "pstack/custom")
        first = git(self.source, "rev-parse", "HEAD")
        self.update()
        selected = self.source / "pstack/skills/how/SKILL.md"
        selected.write_text(selected.read_text().replace("First upstream", "Second upstream"))
        # A future same-name upstream skill must never replace Bobby Mode.
        (self.source / "pstack/skills/bobby-mode").mkdir()
        (self.source / "pstack/skills/bobby-mode/SKILL.md").write_text("wrong owner\n")
        second = self.commit()
        # A dirty source file is not the selected committed source.
        selected.write_text("uncommitted replacement\n")
        self.update(second)
        self.assertIn("Second upstream", (self.root / "pstack/skills/how/SKILL.md").read_text())
        self.assertEqual(SYNC["files"](self.root / "pstack/custom"), before)
        for name in CUSTOM:
            self.assertEqual((self.root / f"pstack/skills/{name}/SKILL.md").read_bytes(),
                             (self.root / f"pstack/custom/skills/{name}/SKILL.md").read_bytes())
        self.assertFalse((self.root / "vendor/pstack/agents").exists())
        self.assertFalse((self.root / "pstack/skills/unselected").exists())
        manifest = json.loads((self.root / "vendor/pstack/UPSTREAM.json").read_text())
        self.assertEqual(manifest["commit"], second)
        self.assertNotEqual(first, second)
        SYNC["package"](self.root, check_only=True)

    def test_vendor_and_package_drift_are_detected(self) -> None:
        self.update()
        vendor = self.root / "vendor/pstack/skills/how/SKILL.md"
        original = vendor.read_bytes()
        vendor.write_text("hand edited vendor\n")
        with self.assertRaisesRegex(ValueError, "vendor drift"):
            SYNC["package"](self.root, check_only=True)
        vendor.write_bytes(original)
        packaged = self.root / "pstack/skills/how/SKILL.md"
        packaged.write_text("hand edited package\n")
        with self.assertRaisesRegex(ValueError, "package drift"):
            SYNC["package"](self.root, check_only=True)

    def test_custom_edit_has_one_source_and_offline_projection(self) -> None:
        self.update()
        custom = self.root / "pstack/custom/skills/bobby-mode/SKILL.md"
        custom.write_text(custom.read_text() + "\nKeep the operator's workspace convention.\n")
        with self.assertRaisesRegex(ValueError, "package drift"):
            SYNC["package"](self.root, check_only=True)
        SYNC["package"](self.root)
        self.assertEqual((self.root / "pstack/skills/bobby-mode/SKILL.md").read_bytes(), custom.read_bytes())

    def test_refresh_refuses_to_erase_handwritten_package_changes(self) -> None:
        self.update()
        target = self.root / "pstack/skills/bobby-mode/SKILL.md"
        target.write_text(target.read_text() + "\nUnreconciled workspace customization.\n")
        before = target.read_bytes()
        vendor_before = SYNC["files"](self.root / "vendor/pstack")
        with self.assertRaisesRegex(ValueError, "package drift before upstream refresh"):
            self.update()
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(SYNC["files"](self.root / "vendor/pstack"), vendor_before)

    def test_invalid_selected_snapshot_does_not_mutate_outputs(self) -> None:
        self.update()
        before = SYNC["files"](self.root / "vendor/pstack")
        selected = self.source / "pstack/skills/how/SKILL.md"
        selected.unlink()
        selected.symlink_to("../../LICENSE")
        self.commit()
        with self.assertRaisesRegex(ValueError, "unsupported selected upstream entry"):
            self.update()
        self.assertEqual(SYNC["files"](self.root / "vendor/pstack"), before)

    def test_package_symlink_is_refused_before_refresh(self) -> None:
        self.update()
        before = SYNC["files"](self.root / "vendor/pstack")
        target = self.root / "pstack/skills/how/SKILL.md"
        target.unlink()
        target.symlink_to(self.root / "pstack/custom/LICENSE")
        with self.assertRaisesRegex(ValueError, "refusing symlink"):
            self.update()
        self.assertEqual(SYNC["files"](self.root / "vendor/pstack"), before)

    def test_real_packaging_discovery_and_local_file_provenance(self) -> None:
        SYNC["package"](ROOT, check_only=True)
        for name in CUSTOM:
            for path in (ROOT / "pstack/custom/skills" / name).rglob("*"):
                if path.is_file():
                    relative = path.relative_to(ROOT / "pstack/custom/skills" / name)
                    self.assertEqual((ROOT / "pstack/skills" / name / relative).read_bytes(), path.read_bytes())


if __name__ == "__main__":
    unittest.main()
