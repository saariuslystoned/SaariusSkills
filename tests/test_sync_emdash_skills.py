#!/usr/bin/env python3
"""Isolated stdlib regression tests for scripts/sync-emdash-skills.

Verifies:
- Attribute-free Git plumbing extraction:
  - export-ignore in uncommitted .git/info/attributes does not omit committed files.
  - export-ignore in committed .gitattributes does not omit committed files.
  - export-subst does not alter committed bytes (verbatim placeholders preserved).
  - Meaningful modes (e.g. executable 0o755) are preserved.
  - Unsupported symlink entries are rejected before target mutation.
- Overlap guard protection:
  - Target descendant of source is rejected and source working tree preserved.
  - Target ancestor of source is rejected.
  - Target identical to source or repository root is rejected.
- Network-fetch (source=None) path with temporary local Git upstream via imported script:
  - Full commit SHA resolution and materialization.
  - Branch ref resolution.
  - Annotated tag resolution and tag peeling.
  - Unresolved ref handling without target directory mutation.
- Local source (source=<dir>) path:
  - SHA pinning and provenance, proving git clone --branch <sha> fails.
  - Dirty file modifications and untracked files in source repo are ignored without mutating source.
  - Explicit ref selection with --source.
  - Manifest verification (--check) and drift detection on modifications/additions/deletions.
  - Failure before mutation on unresolved ref or missing skill.
- Security and interface boundaries:
  - Removal of destructive --target CLI flag.
  - Default CLI check execution.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = REPO_ROOT / "scripts" / "sync-emdash-skills"

loader = SourceFileLoader("sync_emdash_skills", str(SYNC_SCRIPT))
spec = spec_from_loader(loader.name, loader)
sync_mod = module_from_spec(spec)
loader.exec_module(sync_mod)


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def create_fixture_repo(repo_dir: Path) -> dict[str, str]:
    """Create a local Git repository fixture with standard skills, branches, tags, and commits."""
    run_git(["init", "--quiet"], repo_dir)
    run_git(["branch", "-M", "main"], repo_dir)
    run_git(["config", "user.name", "Test Committer"], repo_dir)
    run_git(["config", "user.email", "test@example.com"], repo_dir)

    skills = ["building-emdash-site", "creating-plugins", "emdash-cli", "upgrading-emdash"]
    for skill in skills:
        skill_dir = repo_dir / "skills" / skill
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(f"# {skill} v1\nInitial content\n", encoding="utf-8")

    (repo_dir / "LICENSE").write_text("MIT License fixture\n", encoding="utf-8")

    run_git(["add", "."], repo_dir)
    run_git(["commit", "-m", "feat: initial skills release v1.0.0"], repo_dir)
    c1 = run_git(["rev-parse", "HEAD"], repo_dir).stdout.strip()

    # Create annotated tag pointing to c1
    run_git(["tag", "-a", "v1.0.0", "-m", "release tag v1.0.0"], repo_dir)

    # Commit 2: update emdash-cli on main
    (repo_dir / "skills" / "emdash-cli" / "SKILL.md").write_text(
        "# emdash-cli v2\nUpdated committed content on main\n", encoding="utf-8"
    )
    run_git(["add", "."], repo_dir)
    run_git(["commit", "-m", "chore: update emdash-cli to v2"], repo_dir)
    c2 = run_git(["rev-parse", "HEAD"], repo_dir).stdout.strip()

    # Commit 3 on a separate branch 'feature-v3'
    run_git(["checkout", "-b", "feature-v3"], repo_dir)
    (repo_dir / "skills" / "emdash-cli" / "SKILL.md").write_text(
        "# emdash-cli v3\nBranch content on feature-v3\n", encoding="utf-8"
    )
    run_git(["add", "."], repo_dir)
    run_git(["commit", "-m", "feat: emdash-cli v3 on branch"], repo_dir)
    c3 = run_git(["rev-parse", "HEAD"], repo_dir).stdout.strip()

    # Switch back to main
    run_git(["checkout", "main"], repo_dir)

    return {"c1": c1, "c2": c2, "c3": c3}


class TestSyncEmdashSkills(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="emdash-test-")
        self.tmp_path = Path(self.tmp.name)
        self.fixture_repo = self.tmp_path / "upstream-fixture"
        self.fixture_repo.mkdir()
        self.commits = create_fixture_repo(self.fixture_repo)
        self.target_dir = self.tmp_path / "target-vendor"
        self.orig_upstream_repo = sync_mod.UPSTREAM_REPO

    def tearDown(self) -> None:
        sync_mod.UPSTREAM_REPO = self.orig_upstream_repo
        self.tmp.cleanup()

    def update_sync(
        self,
        ref: str | None = None,
        source: Path | None = None,
        skills: list[str] | None = None,
        verbose: bool = False,
        target: Path | None = None,
    ) -> int:
        if skills is None:
            skills = list(sync_mod.DEFAULT_SKILLS)
        if target is None:
            target = self.target_dir
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return sync_mod.update(
                ref=ref,
                source=source,
                skills=skills,
                verbose=verbose,
                target=target,
            )

    def check_sync(self, verbose: bool = False, target: Path | None = None) -> int:
        if target is None:
            target = self.target_dir
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return sync_mod.check(verbose=verbose, target=target)

    # -------------------------------------------------------------------------
    # Attribute-free Git plumbing extraction tests
    # -------------------------------------------------------------------------

    def test_export_ignore_in_info_attributes_does_not_omit_files(self) -> None:
        """Prove export-ignore in uncommitted .git/info/attributes cannot omit committed files."""
        ref_file = self.fixture_repo / "skills" / "emdash-cli" / "reference.md"
        ref_content = "# emdash-cli Reference Guide\nCommitted reference content\n"
        ref_file.write_text(ref_content, encoding="utf-8")
        run_git(["add", "skills/emdash-cli/reference.md"], self.fixture_repo)
        run_git(["commit", "-m", "feat: add reference guide"], self.fixture_repo)

        info_attr = self.fixture_repo / ".git" / "info" / "attributes"
        info_attr.parent.mkdir(parents=True, exist_ok=True)
        info_attr.write_text("skills/emdash-cli/reference.md export-ignore\n", encoding="utf-8")

        ret = self.update_sync(ref=None, source=self.fixture_repo)
        self.assertEqual(ret, 0, "update should succeed")

        target_ref = self.target_dir / "skills" / "emdash-cli" / "reference.md"
        self.assertTrue(target_ref.is_file(), "reference.md must not be omitted despite export-ignore")
        self.assertEqual(target_ref.read_text(encoding="utf-8"), ref_content)

        manifest = json.loads((self.target_dir / "UPSTREAM.json").read_text(encoding="utf-8"))
        self.assertIn("skills/emdash-cli/reference.md", manifest.get("files", {}))

        chk = self.check_sync()
        self.assertEqual(chk, 0, "check should pass with all committed files recorded")

    def test_export_ignore_in_committed_attributes_does_not_omit_files(self) -> None:
        """Prove export-ignore in committed .gitattributes cannot omit committed files."""
        ref_file = self.fixture_repo / "skills" / "emdash-cli" / "reference.md"
        ref_content = "# emdash-cli Reference Guide\nCommitted reference content\n"
        ref_file.write_text(ref_content, encoding="utf-8")
        gitattr = self.fixture_repo / ".gitattributes"
        gitattr.write_text("skills/emdash-cli/reference.md export-ignore\n", encoding="utf-8")
        run_git(["add", "."], self.fixture_repo)
        run_git(["commit", "-m", "feat: commit reference and .gitattributes"], self.fixture_repo)

        ret = self.update_sync(ref=None, source=self.fixture_repo)
        self.assertEqual(ret, 0, "update should succeed")

        target_ref = self.target_dir / "skills" / "emdash-cli" / "reference.md"
        self.assertTrue(target_ref.is_file(), "reference.md must not be omitted despite committed export-ignore")
        self.assertEqual(target_ref.read_text(encoding="utf-8"), ref_content)

        chk = self.check_sync()
        self.assertEqual(chk, 0)

    def test_export_subst_does_not_alter_committed_bytes(self) -> None:
        """Prove export-subst cannot alter raw committed bytes during snapshot extraction."""
        subst_file = self.fixture_repo / "skills" / "emdash-cli" / "subst.md"
        raw_content = "Committed raw format placeholder: $Format:%H$\n"
        subst_file.write_text(raw_content, encoding="utf-8")
        gitattr = self.fixture_repo / ".gitattributes"
        gitattr.write_text("skills/emdash-cli/subst.md export-subst\n", encoding="utf-8")
        run_git(["add", "."], self.fixture_repo)
        run_git(["commit", "-m", "feat: commit file with export-subst"], self.fixture_repo)

        ret = self.update_sync(ref=None, source=self.fixture_repo)
        self.assertEqual(ret, 0, "update should succeed")

        target_subst = self.target_dir / "skills" / "emdash-cli" / "subst.md"
        self.assertTrue(target_subst.is_file())
        self.assertEqual(
            target_subst.read_text(encoding="utf-8"),
            raw_content,
            "export-subst must not alter raw committed file bytes",
        )

        chk = self.check_sync()
        self.assertEqual(chk, 0)

    def test_unsupported_symlink_rejected_before_target_mutation(self) -> None:
        """Prove symlinks in commit are rejected before target mutation rather than followed."""
        link_target = self.fixture_repo / "skills" / "emdash-cli" / "symlink_escape"
        link_target.symlink_to("../../LICENSE")
        run_git(["add", "skills/emdash-cli/symlink_escape"], self.fixture_repo)
        run_git(["commit", "-m", "add symlink"], self.fixture_repo)

        self.target_dir.mkdir(parents=True, exist_ok=True)
        sentinel = self.target_dir / "SENTINEL.txt"
        sentinel.write_text("keep intact\n", encoding="utf-8")

        ret = self.update_sync(ref=None, source=self.fixture_repo)
        self.assertEqual(ret, 2, "symlinks must be rejected with exit code 2")

        self.assertTrue(sentinel.is_file())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep intact\n")
        self.assertFalse((self.target_dir / "UPSTREAM.json").exists())

    def test_meaningful_modes_preserved(self) -> None:
        """Prove meaningful file modes (e.g. executable 0o755) are preserved during extraction."""
        exec_file = self.fixture_repo / "skills" / "emdash-cli" / "run.sh"
        exec_file.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
        exec_file.chmod(0o755)
        run_git(["add", "skills/emdash-cli/run.sh"], self.fixture_repo)
        run_git(["commit", "-m", "add executable script"], self.fixture_repo)

        ret = self.update_sync(ref=None, source=self.fixture_repo)
        self.assertEqual(ret, 0)

        target_exec = self.target_dir / "skills" / "emdash-cli" / "run.sh"
        self.assertTrue(target_exec.is_file())
        self.assertTrue(target_exec.stat().st_mode & 0o111 != 0, "executable bit must be preserved")

    # -------------------------------------------------------------------------
    # Overlap guard tests
    # -------------------------------------------------------------------------

    def test_descendant_overlap_rejected_and_preserves_source_tree(self) -> None:
        """Prove target beneath source is rejected and source working tree is preserved."""
        descendant_target = self.fixture_repo / "vendor" / "emdash-skills"
        descendant_target.mkdir(parents=True, exist_ok=True)
        sentinel = descendant_target / "local-work.txt"
        sentinel_content = "precious uncommitted local work\n"
        sentinel.write_text(sentinel_content, encoding="utf-8")

        ret = self.update_sync(ref=None, source=self.fixture_repo, target=descendant_target)
        self.assertEqual(ret, 2, "descendant target must be rejected with exit code 2")

        # Sentinel must be completely preserved
        self.assertTrue(sentinel.is_file(), "sentinel file in source must be preserved")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), sentinel_content)

        # Target directory must NOT have been converted to mirror
        self.assertFalse((descendant_target / "UPSTREAM.json").exists())

    def test_ancestor_and_repo_root_overlap_rejected(self) -> None:
        """Prove target as ancestor of source or repository root is rejected."""
        # Ancestor of source
        ret_ancestor = self.update_sync(ref=None, source=self.fixture_repo, target=self.fixture_repo.parent)
        self.assertEqual(ret_ancestor, 2)

        # Same as source
        ret_same = self.update_sync(ref=None, source=self.fixture_repo, target=self.fixture_repo)
        self.assertEqual(ret_same, 2)

        # Repo root
        ret_root = self.update_sync(ref=None, source=self.fixture_repo, target=REPO_ROOT)
        self.assertEqual(ret_root, 2)

    # -------------------------------------------------------------------------
    # Network-fetch (source=None) tests with local Git upstream override
    # -------------------------------------------------------------------------

    def test_network_fetch_full_sha(self) -> None:
        """Prove network-fetch path (source=None) fetches and pins an exact full commit SHA."""
        sync_mod.UPSTREAM_REPO = str(self.fixture_repo)
        sha = self.commits["c1"]

        ret = self.update_sync(ref=sha, source=None)
        self.assertEqual(ret, 0, "network-fetch update for full SHA should return 0")

        # Verify target contains content from commit 1
        cli_skill = self.target_dir / "skills" / "emdash-cli" / "SKILL.md"
        self.assertTrue(cli_skill.is_file())
        self.assertIn("# emdash-cli v1", cli_skill.read_text(encoding="utf-8"))

        # Verify manifest provenance
        manifest_path = self.target_dir / "UPSTREAM.json"
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["commit"], sha)
        self.assertEqual(manifest["ref"], sha)

        # Verify manifest integrity check passes
        chk = self.check_sync()
        self.assertEqual(chk, 0)

    def test_network_fetch_branch(self) -> None:
        """Prove network-fetch path (source=None) resolves and materializes a branch ref."""
        sync_mod.UPSTREAM_REPO = str(self.fixture_repo)

        ret = self.update_sync(ref="feature-v3", source=None)
        self.assertEqual(ret, 0, "network-fetch update for branch should return 0")

        cli_skill = self.target_dir / "skills" / "emdash-cli" / "SKILL.md"
        self.assertIn("# emdash-cli v3", cli_skill.read_text(encoding="utf-8"))

        manifest = json.loads((self.target_dir / "UPSTREAM.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["commit"], self.commits["c3"])
        self.assertEqual(manifest["ref"], "feature-v3")

        chk = self.check_sync()
        self.assertEqual(chk, 0)

    def test_network_fetch_annotated_tag(self) -> None:
        """Prove network-fetch path (source=None) resolves annotated tag and peels to commit."""
        sync_mod.UPSTREAM_REPO = str(self.fixture_repo)

        ret = self.update_sync(ref="v1.0.0", source=None)
        self.assertEqual(ret, 0, "network-fetch update for annotated tag should return 0")

        cli_skill = self.target_dir / "skills" / "emdash-cli" / "SKILL.md"
        self.assertIn("# emdash-cli v1", cli_skill.read_text(encoding="utf-8"))

        manifest = json.loads((self.target_dir / "UPSTREAM.json").read_text(encoding="utf-8"))
        # Commit must be the peeled commit SHA, not the tag object SHA
        self.assertEqual(manifest["commit"], self.commits["c1"])
        self.assertEqual(manifest["ref"], "v1.0.0")

        chk = self.check_sync()
        self.assertEqual(chk, 0)

    def test_network_fetch_unresolved_ref_preserves_target(self) -> None:
        """Prove network-fetch path fails on unresolved ref without modifying pre-existing target."""
        sync_mod.UPSTREAM_REPO = str(self.fixture_repo)
        self.target_dir.mkdir(parents=True, exist_ok=True)
        sentinel = self.target_dir / "PRESERVE_ME.txt"
        sentinel.write_text("existing pre-mutation content\n", encoding="utf-8")

        ret = self.update_sync(ref="nonexistent-branch-or-tag-9999", source=None)
        self.assertEqual(ret, 2, "unresolved ref must return exit code 2")

        # Verify target was untouched
        self.assertTrue(sentinel.is_file())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "existing pre-mutation content\n")
        self.assertFalse((self.target_dir / "UPSTREAM.json").exists())
        self.assertFalse((self.target_dir / "skills").exists())

    # -------------------------------------------------------------------------
    # Local source (source=<dir>) tests
    # -------------------------------------------------------------------------

    def test_sha_pinning_and_provenance(self) -> None:
        """Prove that commit SHAs can be pinned and materialized, unlike clone --branch."""
        sha = self.commits["c1"]

        # 1. Prove that git clone --branch <sha> would fail
        clone_dest = self.tmp_path / "clone-fail-dest"
        failed_clone = subprocess.run(
            ["git", "clone", "--quiet", "--branch", sha, str(self.fixture_repo), str(clone_dest)],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(failed_clone.returncode, 0, "git clone --branch <sha> should fail")

        # 2. Prove update with source=<dir> and ref=<sha> succeeds
        ret = self.update_sync(ref=sha, source=self.fixture_repo)
        self.assertEqual(ret, 0, "sync update should succeed")

        # Verify target has commit 1 content
        cli_skill = self.target_dir / "skills" / "emdash-cli" / "SKILL.md"
        self.assertTrue(cli_skill.is_file())
        self.assertIn("# emdash-cli v1", cli_skill.read_text(encoding="utf-8"))

        # Verify UPSTREAM.json provenance
        manifest_file = self.target_dir / "UPSTREAM.json"
        self.assertTrue(manifest_file.is_file())
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        self.assertEqual(manifest["commit"], sha)
        self.assertEqual(manifest["ref"], sha)

        # Verify check passes
        chk = self.check_sync()
        self.assertEqual(chk, 0)

    def test_dirty_and_untracked_source_handling(self) -> None:
        """Prove that dirty edits and untracked files in source are not copied and source is not mutated."""
        cli_skill_source = self.fixture_repo / "skills" / "emdash-cli" / "SKILL.md"
        untracked_file = self.fixture_repo / "skills" / "emdash-cli" / "UNTRACKED_DIRTY.txt"

        # Dirty existing file and create untracked file in working tree
        cli_skill_source.write_text("DIRTY MUTATION IN WORKING TREE\n", encoding="utf-8")
        untracked_file.write_text("UNTRACKED DIRTY FILE\n", encoding="utf-8")

        ret = self.update_sync(ref=None, source=self.fixture_repo)
        self.assertEqual(ret, 0)

        # Target must contain the committed bytes (Commit 2: v2 on main), NOT the dirty working bytes
        target_cli = self.target_dir / "skills" / "emdash-cli" / "SKILL.md"
        self.assertIn("# emdash-cli v2", target_cli.read_text(encoding="utf-8"))
        self.assertNotIn("DIRTY MUTATION", target_cli.read_text(encoding="utf-8"))

        # Target must not contain untracked files
        target_untracked = self.target_dir / "skills" / "emdash-cli" / "UNTRACKED_DIRTY.txt"
        self.assertFalse(target_untracked.exists(), "untracked file must not be copied")

        # Source repo working tree must not be mutated
        status = run_git(["status", "--porcelain"], self.fixture_repo).stdout
        self.assertIn(" M skills/emdash-cli/SKILL.md", status)
        self.assertIn("?? skills/emdash-cli/UNTRACKED_DIRTY.txt", status)

        # Check passes cleanly against manifest
        chk = self.check_sync()
        self.assertEqual(chk, 0)

    def test_explicit_source_ref_selection(self) -> None:
        """Prove that explicit ref selection with source respects the specified ref over working HEAD."""
        # Working tree HEAD is at commit 2 on main
        head_commit = run_git(["rev-parse", "HEAD"], self.fixture_repo).stdout.strip()
        self.assertEqual(head_commit, self.commits["c2"])

        # Sync specifying ref=v1.0.0 (the tag pointing to commit 1)
        ret = self.update_sync(ref="v1.0.0", source=self.fixture_repo)
        self.assertEqual(ret, 0)

        manifest = json.loads((self.target_dir / "UPSTREAM.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["ref"], "v1.0.0")
        self.assertEqual(manifest["commit"], self.commits["c1"])

        cli_skill = self.target_dir / "skills" / "emdash-cli" / "SKILL.md"
        self.assertIn("# emdash-cli v1", cli_skill.read_text(encoding="utf-8"))

        chk = self.check_sync()
        self.assertEqual(chk, 0)

    def test_check_after_update_and_drift_detection(self) -> None:
        """Prove that check succeeds after update and detects any subsequent file drift."""
        ret = self.update_sync(ref=None, source=self.fixture_repo)
        self.assertEqual(ret, 0)

        # Initial check must be clean
        chk = self.check_sync()
        self.assertEqual(chk, 0)

        # 1. Modify a tracked file
        license_file = self.target_dir / "LICENSE"
        orig_content = license_file.read_text(encoding="utf-8")
        license_file.write_text(orig_content + "TAMPERED\n", encoding="utf-8")
        self.assertEqual(self.check_sync(), 1)

        # Restore file
        license_file.write_text(orig_content, encoding="utf-8")
        self.assertEqual(self.check_sync(), 0)

        # 2. Add an extra file
        extra = self.target_dir / "EXTRA_FILE.txt"
        extra.write_text("extra", encoding="utf-8")
        self.assertEqual(self.check_sync(), 1)
        extra.unlink()
        self.assertEqual(self.check_sync(), 0)

        # 3. Missing file
        license_file.unlink()
        self.assertEqual(self.check_sync(), 1)

    def test_failure_before_target_mutation_for_unresolved_ref(self) -> None:
        """Prove that unresolved refs fail before mutating or creating the target directory."""
        self.target_dir.mkdir(parents=True, exist_ok=True)
        sentinel = self.target_dir / "DO_NOT_TOUCH.txt"
        sentinel.write_text("immutable baseline\n", encoding="utf-8")

        ret = self.update_sync(ref="nonexistent-sha-99999", source=self.fixture_repo)
        self.assertEqual(ret, 2)

        # Ensure sentinel is preserved and target was NOT cleared or mutated
        self.assertTrue(sentinel.is_file())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "immutable baseline\n")
        self.assertFalse((self.target_dir / "UPSTREAM.json").exists())

    def test_failure_before_target_mutation_for_missing_skill(self) -> None:
        """Prove that missing valid skills fail validation before touching target or mutating source."""
        self.target_dir.mkdir(parents=True, exist_ok=True)
        target_sentinel = self.target_dir / "DO_NOT_TOUCH.txt"
        target_sentinel.write_text("immutable baseline\n", encoding="utf-8")

        source_sentinel = self.fixture_repo / "SOURCE_SENTINEL.txt"
        source_sentinel.write_text("source untouched\n", encoding="utf-8")

        ret = self.update_sync(
            ref=None,
            source=self.fixture_repo,
            skills=["building-emdash-site", "nonexistent-custom-skill"],
        )
        self.assertEqual(ret, 2)

        # Target untouched
        self.assertTrue(target_sentinel.is_file())
        self.assertEqual(target_sentinel.read_text(encoding="utf-8"), "immutable baseline\n")
        self.assertFalse((self.target_dir / "UPSTREAM.json").exists())

        # Source untouched
        self.assertTrue(source_sentinel.is_file())
        self.assertEqual(source_sentinel.read_text(encoding="utf-8"), "source untouched\n")

    # -------------------------------------------------------------------------
    # Skill directory name and containment validation regression tests
    # -------------------------------------------------------------------------

    def test_skills_absolute_path_outside_fixture_rejected(self) -> None:
        """Prove absolute path to outside directory with SKILL.md is rejected and target/source are untouched."""
        outside_skill = self.tmp_path / "outside-installed-skill"
        outside_skill.mkdir(parents=True, exist_ok=True)
        (outside_skill / "SKILL.md").write_text("# outside skill\n", encoding="utf-8")

        self.target_dir.mkdir(parents=True, exist_ok=True)
        target_sentinel = self.target_dir / "TARGET_SENTINEL.txt"
        target_sentinel.write_text("sentinel target untouched\n", encoding="utf-8")

        source_sentinel = self.fixture_repo / "SOURCE_SENTINEL.txt"
        source_sentinel.write_text("sentinel source untouched\n", encoding="utf-8")

        ret = self.update_sync(
            ref=None,
            source=self.fixture_repo,
            skills=[str(outside_skill)],
        )
        self.assertEqual(ret, 2, "absolute path in skills must be rejected with exit code 2")

        # Sentinel target untouched, no UPSTREAM.json or skills directory created
        self.assertTrue(target_sentinel.is_file())
        self.assertEqual(target_sentinel.read_text(encoding="utf-8"), "sentinel target untouched\n")
        self.assertFalse((self.target_dir / "UPSTREAM.json").exists())
        self.assertFalse((self.target_dir / "skills").exists())

        # Source untouched
        self.assertTrue(source_sentinel.is_file())
        self.assertEqual(source_sentinel.read_text(encoding="utf-8"), "sentinel source untouched\n")

    def test_skills_traversal_paths_rejected(self) -> None:
        """Prove relative traversal paths (e.g. ../ or ../../) are rejected and target/source are untouched."""
        self.target_dir.mkdir(parents=True, exist_ok=True)
        target_sentinel = self.target_dir / "TARGET_SENTINEL.txt"
        target_sentinel.write_text("sentinel target untouched\n", encoding="utf-8")

        source_sentinel = self.fixture_repo / "SOURCE_SENTINEL.txt"
        source_sentinel.write_text("sentinel source untouched\n", encoding="utf-8")

        for bad_traversal in ["../outside", "../../skills/emdash-cli", "skills/../emdash-cli", "./emdash-cli"]:
            with self.subTest(traversal=bad_traversal):
                ret = self.update_sync(
                    ref=None,
                    source=self.fixture_repo,
                    skills=[bad_traversal],
                )
                self.assertEqual(ret, 2, f"traversal path '{bad_traversal}' must return 2")
                self.assertTrue(target_sentinel.is_file())
                self.assertEqual(target_sentinel.read_text(encoding="utf-8"), "sentinel target untouched\n")
                self.assertFalse((self.target_dir / "UPSTREAM.json").exists())
                self.assertTrue(source_sentinel.is_file())
                self.assertEqual(source_sentinel.read_text(encoding="utf-8"), "sentinel source untouched\n")

    def test_skills_invalid_names_rejected(self) -> None:
        """Prove invalid skill names (slashes, backslashes, empty, dot, dotdot) are rejected."""
        self.target_dir.mkdir(parents=True, exist_ok=True)
        target_sentinel = self.target_dir / "TARGET_SENTINEL.txt"
        target_sentinel.write_text("sentinel target untouched\n", encoding="utf-8")

        source_sentinel = self.fixture_repo / "SOURCE_SENTINEL.txt"
        source_sentinel.write_text("sentinel source untouched\n", encoding="utf-8")

        for bad_name in [".", "..", "foo/bar", "foo\\bar", "", "  ", "emdash/cli"]:
            with self.subTest(name=bad_name):
                ret = self.update_sync(
                    ref=None,
                    source=self.fixture_repo,
                    skills=[bad_name],
                )
                self.assertEqual(ret, 2, f"invalid skill name '{bad_name}' must return 2")
                self.assertTrue(target_sentinel.is_file())
                self.assertEqual(target_sentinel.read_text(encoding="utf-8"), "sentinel target untouched\n")
                self.assertFalse((self.target_dir / "UPSTREAM.json").exists())
                self.assertTrue(source_sentinel.is_file())
                self.assertEqual(source_sentinel.read_text(encoding="utf-8"), "sentinel source untouched\n")

    # -------------------------------------------------------------------------
    # Security and CLI surface tests
    # -------------------------------------------------------------------------

    def test_cli_interface_and_default_semantics(self) -> None:
        """Prove default CLI semantics: --check passes on mirror, and --target CLI flag is removed."""
        # Default CLI --check must pass
        res = subprocess.run([sys.executable, str(SYNC_SCRIPT), "--check"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"default CLI --check failed: {res.stderr}")
        self.assertIn("emdash skills mirror clean", res.stdout)

        # CLI flag --target must not exist (unrecognized arguments error code 2)
        res_target = subprocess.run(
            [sys.executable, str(SYNC_SCRIPT), "--check", "--target", str(self.target_dir)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_target.returncode, 2)
        self.assertIn("unrecognized arguments: --target", res_target.stderr)


class PackagedProjectionTests(unittest.TestCase):
    def test_packaged_drift_is_detected_and_repaired_without_touching_other_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            other = root / "unrelated"
            other.mkdir()
            sentinel = other / "SKILL.md"
            sentinel.write_text("untouched")
            self.assertEqual(sync_mod.package_skills(False, package_root=root), 0)
            self.assertEqual(sync_mod.package_skills(True, package_root=root), 0)
            entry = root / "emdash-cli" / "SKILL.md"
            entry.write_text("modified")
            self.assertEqual(sync_mod.package_skills(True, package_root=root), 1)
            self.assertEqual(sync_mod.package_skills(False, package_root=root), 0)
            self.assertEqual(sync_mod.package_skills(True, package_root=root), 0)
            self.assertEqual(sentinel.read_text(), "untouched")

    def test_packaged_symlink_refused_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            (outside / "SKILL.md").write_text("untouched")
            packages = root / "packages"
            packages.mkdir()
            (packages / "upgrading-emdash").symlink_to(outside, target_is_directory=True)
            self.assertEqual(sync_mod.package_skills(False, package_root=packages), 2)
            self.assertFalse((packages / "building-emdash-site").exists())
            self.assertEqual((outside / "SKILL.md").read_text(), "untouched")


if __name__ == "__main__":
    unittest.main()
