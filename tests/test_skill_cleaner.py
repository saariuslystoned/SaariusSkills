"""Synthetic structural contracts; no claims about qualitative prose quality."""
from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HELPER = Path(__file__).resolve().parents[1] / "skills/smoky-skill-cleaner/scripts/audit-skills"
AUDIT = runpy.run_path(str(HELPER))["audit_selection"]


class SkillCleanerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.shelf = self.base / "shelf"
        self.shelf.mkdir()

    def skill(self, directory="example", name=None, description="Check example files.", body="Follow the task."):
        path = self.shelf / directory
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(
            f"---\nname: {name or directory}\ndescription: {description}\n---\n{body}\n", encoding="utf-8"
        )
        return path

    def run_cli(self, *flags):
        return subprocess.run([sys.executable, str(HELPER), *map(str, flags)], capture_output=True, text=True)

    def report(self, *flags):
        result = self.run_cli(*flags, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_selection_is_required_valid_and_unambiguous(self):
        for flags in ((), ("--root", self.base / "absent"), ("--root", HELPER),
                      ("--root", self.shelf, "--skill", self.shelf),
                      ("--root", self.shelf, "--max-description", "-1"),
                      ("--root", self.shelf, "--min-body-words", "901")):
            with self.subTest(flags=flags):
                self.assertEqual(self.run_cli(*flags).returncode, 2)
        self.assertEqual(self.report("--root", self.shelf)["skill_count"], 0)

    def test_advisories_are_not_packaging_errors_or_qualitative_verdicts(self):
        path = self.skill(description="d" * 301)
        result = self.report("--skill", path)
        skill = result["skills"][0]
        self.assertEqual(skill["packaging_errors"], [])
        self.assertEqual(set(skill["advisories"]), {"description-pressure", "body-too-thin", "missing-openai-yaml"})
        self.assertEqual(skill["unverified"], [])
        self.assertEqual(result["qualitative_assessment"], "not-performed")
        self.assertEqual(result["native_yaml_validation"], "not-performed")
        adjusted = self.report("--skill", path, "--max-description", 400, "--min-body-words", 0)
        self.assertEqual(adjusted["skills"][0]["advisories"], ["missing-openai-yaml"])
        (path / "agents").mkdir()
        (path / "agents/openai.yaml").write_text('default_prompt: "Use $example"\n')
        self.assertEqual(self.report("--skill", path, "--max-body-words", 2, "--min-body-words", 0)["skills"][0]["advisories"], ["description-pressure", "body-pressure"])

    def test_broken_packaging_and_duplicates_remain_report_data(self):
        for directory in ("one", "two"):
            path = self.skill(directory, name="duplicate", body="Read `references/missing.md` and [guide](references/present.md#section).")
            (path / "references").mkdir()
            (path / "references/present.md").write_text("# Section\n")
        result = self.report("--root", self.shelf)
        self.assertEqual(result["duplicate_names"], {"duplicate": ["one", "two"]})
        self.assertEqual(result["issue_counts"]["missing-reference"], 2)
        for skill in result["skills"]:
            self.assertEqual(set(skill["packaging_errors"]), {"name-mismatch", "missing-reference"})
            self.assertEqual(skill["missing_references"], ["references/missing.md"])

    def test_named_selection_does_not_expand_to_siblings_or_nested_shelves(self):
        selected = self.skill()
        self.skill("ignored")
        (selected / "nested").mkdir()
        (selected / "nested/SKILL.md").write_text("not part of selection")
        result = self.report("--skill", selected, "--skill", selected)
        self.assertEqual(result["skill_count"], 1)
        self.assertEqual(result["selection"], [str(selected), str(selected)])
        shelf = self.report("--root", self.shelf)
        self.assertEqual(shelf["skill_count"], 2)

    def test_two_explicit_skills_from_different_roots_compare_by_full_path(self):
        first = self.skill()
        second = self.base / "other/example"
        second.mkdir(parents=True)
        (second / "SKILL.md").write_bytes((first / "SKILL.md").read_bytes())
        result = self.report("--skill", first, "--skill", second)
        self.assertEqual(result["duplicate_names"], {"example": sorted([str(first), str(second)])})

    def test_rich_yaml_is_unverified_not_broken_or_a_false_duplicate(self):
        path = self.skill()
        for metadata in ("name: example\ndescription: >\n  A valid multiline description.",
                         "name: example\ndescription: Fine.\nmetadata:\n  source: example",
                         "name: example\nname: other\ndescription: Fine."):
            with self.subTest(metadata=metadata):
                (path / "SKILL.md").write_text(f"---\n{metadata}\n---\nFollow the task.\n")
                result = self.report("--root", self.shelf)
                self.assertEqual(result["skills"][0]["packaging_errors"], [])
                self.assertEqual(result["skills"][0]["unverified"], ["frontmatter-needs-validator"])
                self.assertEqual(result["duplicate_names"], {})

    def test_fully_unparsed_frontmatter_is_not_missing(self):
        path = self.skill()
        for metadata in ("name: >-\n  example\ndescription: >-\n  Check files.",
                         "name: &identity example\ndescription: *identity"):
            with self.subTest(metadata=metadata):
                (path / "SKILL.md").write_text(f"---\n{metadata}\n---\nRead `references/missing.md`.\n")
                skill = self.report("--skill", path)["skills"][0]
                self.assertEqual(skill["packaging_errors"], ["missing-reference"])
                self.assertEqual(skill["unverified"], ["frontmatter-needs-validator"])
                self.assertFalse(skill["metadata_verified"])

    def test_colon_without_mapping_separator_is_unverified_not_a_duplicate(self):
        for directory in ("one", "two"):
            path = self.skill(directory)
            (path / "SKILL.md").write_text("---\nname:example\ndescription:Check files.\n---\nFollow the task.\n")
        report = self.report("--root", self.shelf)
        self.assertEqual(report["duplicate_names"], {})
        for skill in report["skills"]:
            self.assertFalse(skill["metadata_verified"])
            self.assertEqual(skill["packaging_errors"], [])
            self.assertEqual(skill["unverified"], ["frontmatter-needs-validator"])

    def test_invalid_or_nonmapping_yaml_is_not_flat_metadata(self):
        path = self.skill()
        invalid_values = ("Check: files", "Check:\tfiles", "]files", "}files", "@files", "`files", "%files", "? files")
        metadata_cases = [f"name: example\ndescription: {value}" for value in invalid_values]
        metadata_cases += ["- name: example\n- description: Check files.", "[example, check]", "A scalar document"]
        for metadata in metadata_cases:
            with self.subTest(metadata=metadata):
                (path / "SKILL.md").write_text(f"---\n{metadata}\n---\nFollow the task.\n")
                skill = self.report("--skill", path)["skills"][0]
                self.assertFalse(skill["metadata_verified"])
                self.assertEqual(skill["packaging_errors"], [])
                self.assertEqual(skill["unverified"], ["frontmatter-needs-validator"])

    def test_implicit_yaml_scalar_types_are_unverified_but_quoted_strings_work(self):
        path = self.skill()
        for value in ("null", "Null", "NULL", "~", "true", "FALSE", "yes", "off", "0", "1.5", "-2", ".inf", "2026-11-05"):
            with self.subTest(value=value):
                (path / "SKILL.md").write_text(f"---\nname: example\ndescription: {value}\n---\nFollow the task.\n")
                skill = self.report("--skill", path)["skills"][0]
                self.assertFalse(skill["metadata_verified"])
                self.assertEqual(skill["packaging_errors"], [])
                self.assertEqual(skill["unverified"], ["frontmatter-needs-validator"])
        for value in ("'null'", '"false"', "'123'"):
            with self.subTest(quoted=value):
                (path / "SKILL.md").write_text(f"---\nname: example\ndescription: {value}\n---\nFollow the task.\n")
                skill = self.report("--skill", path)["skills"][0]
                self.assertTrue(skill["metadata_verified"])
                self.assertEqual(skill["packaging_errors"], [])
                self.assertEqual(skill["unverified"], [])

    def test_yaml_comment_values_are_unverified_not_certified_or_broken(self):
        path = self.skill()
        for metadata in ("name: example\ndescription: # TODO",
                         "name: example\t# identity\ndescription: Check files."):
            with self.subTest(metadata=metadata):
                (path / "SKILL.md").write_text(f"---\n{metadata}\n---\nFollow the task.\n")
                skill = self.report("--skill", path)["skills"][0]
                self.assertFalse(skill["metadata_verified"])
                self.assertEqual(skill["packaging_errors"], [])
                self.assertEqual(skill["unverified"], ["frontmatter-needs-validator"])

    def test_quoted_yaml_keys_are_unverified_not_false_packaging_errors(self):
        path = self.skill()
        (path / "SKILL.md").write_text("---\n'name': example\n\"description\": Check files.\n---\nFollow the task.\n")
        skill = self.report("--skill", path)["skills"][0]
        self.assertFalse(skill["metadata_verified"])
        self.assertEqual(skill["packaging_errors"], [])
        self.assertEqual(skill["unverified"], ["frontmatter-needs-validator"])

    def test_unreadable_optional_ui_does_not_hide_reference_errors(self):
        path = self.skill(body="Read `references/missing.md`.")
        (path / "agents").mkdir()
        (path / "agents/openai.yaml").write_bytes(b"\xff")
        skill = self.report("--skill", path)["skills"][0]
        self.assertEqual(skill["missing_references"], ["references/missing.md"])
        self.assertEqual(skill["packaging_errors"], ["missing-reference"])
        self.assertEqual(skill["unverified"], ["unreadable-openai-yaml"])
        self.assertTrue(skill["metadata_verified"])

    def test_missing_metadata_and_unreadable_files_are_distinct(self):
        path = self.skill()
        for text, expected in (("# Plain body\n", "missing-frontmatter"),
                               ("---\nname: example\n---\nBody", "missing-description")):
            (path / "SKILL.md").write_text(text)
            self.assertIn(expected, self.report("--skill", path)["skills"][0]["packaging_errors"])
        (path / "SKILL.md").write_bytes(b"\xff\xfe")
        self.assertEqual(self.report("--skill", path)["skills"][0]["unverified"], ["unreadable-skill-input"])

    def test_no_reads_through_symlinks_outside_references_or_unrelated_files(self):
        selected = self.skill(body="Read `references/../../outside.txt` and `references/link.md`.")
        outside = self.base / "outside.txt"
        outside.write_text("Synthetic sentinel, not audit evidence.")
        (selected / "references").mkdir()
        (selected / "references/link.md").symlink_to(outside)
        (selected / "agents").mkdir()
        (selected / "agents/openai.yaml").symlink_to(outside)
        linked = self.shelf / "linked"
        linked.symlink_to(self.base, target_is_directory=True)
        linked_skill = self.shelf / "linked-skill"
        linked_skill.mkdir()
        (linked_skill / "SKILL.md").symlink_to(outside)
        unrelated = self.shelf / "unrelated.jsonl"
        unrelated.write_text("Synthetic session sentinel.")
        allowed = {selected / "SKILL.md"}
        real_read = Path.read_text
        reads = []

        def guarded_read(path, *args, **kwargs):
            self.assertIn(path, allowed, f"unexpected content read: {path}")
            reads.append(path)
            return real_read(path, *args, **kwargs)

        args = argparse.Namespace(root=self.shelf, skill=None, max_description=300, max_body_words=900, min_body_words=80)
        before = self.hashes()
        with patch.object(Path, "read_text", guarded_read):
            result = AUDIT(args)
        self.assertEqual(reads, [selected / "SKILL.md"])
        self.assertEqual(result["skipped_symlinks"], [str(linked)])
        self.assertIn("reference-outside-scope-or-symlink", result["skills"][0]["unverified"])
        self.assertIn("symlink-openai-yaml", result["skills"][0]["unverified"])
        self.assertEqual(result["skills"][1]["unverified"], ["symlink-skill-md"])
        self.assertEqual(self.run_cli("--skill", linked).returncode, 2)
        self.assertEqual(before, self.hashes())

    def test_reference_presence_check_does_not_read_reference_content(self):
        path = self.skill(body="Read `references/guide.md`.")
        (path / "references").mkdir()
        (path / "references/guide.md").write_bytes(b"\xff")
        self.assertEqual(self.report("--skill", path)["skills"][0]["packaging_errors"], [])

    def test_directory_references_exist_without_expanding_or_reading_them(self):
        path = self.skill(body="[Examples](references/examples/) and [missing](references/absent/).")
        examples = path / "references/examples"
        examples.mkdir(parents=True)
        (examples / "private.jsonl").write_text("Synthetic sentinel; not audit input.")
        args = argparse.Namespace(root=None, skill=[path], max_description=300, max_body_words=900, min_body_words=80)
        real_read = Path.read_text

        def guarded_read(target, *args, **kwargs):
            self.assertEqual(target, path / "SKILL.md")
            return real_read(target, *args, **kwargs)

        before = self.hashes()
        with patch.object(Path, "read_text", guarded_read):
            skill = AUDIT(args)["skills"][0]
        self.assertEqual(skill["missing_references"], ["references/absent/"])
        self.assertEqual(skill["unverified"], [])
        self.assertEqual(before, self.hashes())

    def test_literal_reference_periods_and_traversal_are_not_stripped(self):
        path = self.skill(body="Read `references/notes.` and [more](references/more.). Also `references/..` and references/absent.md.")
        (path / "references").mkdir()
        (path / "references/notes.").write_text("Synthetic content.")
        (path / "references/more.").write_text("Synthetic content.")
        skill = self.report("--skill", path)["skills"][0]
        self.assertEqual(skill["references"], ["references/..", "references/absent.md", "references/more.", "references/notes."])
        self.assertEqual(skill["missing_references"], ["references/absent.md"])
        self.assertEqual(skill["unverified"], ["reference-outside-scope-or-symlink"])

    def test_directory_reference_symlinks_remain_unverified(self):
        path = self.skill(body="[Local](references/local/) and [outside](references/outside/).")
        (path / "references").mkdir()
        (path / "examples").mkdir()
        (path / "references/local").symlink_to(path / "examples", target_is_directory=True)
        (path / "references/outside").symlink_to(self.base, target_is_directory=True)
        skill = self.report("--skill", path)["skills"][0]
        self.assertEqual(skill["packaging_errors"], [])
        self.assertIn("reference-outside-scope-or-symlink", skill["unverified"])

    def test_realistic_source_caller_cases_only_receive_structural_assessment(self):
        fixture = HELPER.parents[3] / "proof/skill-cleaner-refine-20261105/synthetic-cases.json"
        cases = json.loads(fixture.read_text())["cases"]
        for case in cases:
            self.skill(case["directory"], case["name"], case["description"], case["body"])
        result = self.report("--root", self.shelf)
        by_dir = {skill["directory"]: skill for skill in result["skills"]}
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(by_dir[case["directory"]]["packaging_errors"], case["expected_packaging_errors"])
        self.assertEqual(result["duplicate_names"], {"artifact-check": ["private-check", "public-check"]})
        self.assertEqual(result["qualitative_assessment"], "not-performed")
        self.assertNotIn("recommendations", result)

    def hashes(self):
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.base.rglob("*") if not p.is_symlink() and p.is_file()}


if __name__ == "__main__":
    unittest.main()
