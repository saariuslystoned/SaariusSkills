from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "swarm-wiki"
SCRIPT = SKILL / "scripts" / "swarm_log.py"


def run(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, check=False,
    )
    return proc.returncode, json.loads(proc.stdout)


VOCAB = "# Page: Vocabulary\nHosts are cp-1, spark-1.\n"
CANARIES = (
    "RESYNC-CANARY-DOC: ORANGE\n"
    "RESYNC-CANARY-SHEET: ORANGE\n"
    "RESYNC-CANARY-SLIDE: ORANGE\n"
)


class SkillPackagingTests(unittest.TestCase):
    def test_skill_files_present(self) -> None:
        for rel in ("SKILL.md", "LICENSE", "agents/openai.yaml",
                    "references/notebook.md", "references/layout.md",
                    "references/log-format.md", "references/drive-cli.md",
                    "scripts/swarm_log.py"):
            self.assertTrue((SKILL / rel).is_file(), f"missing {rel}")

    def test_frontmatter_declares_name_and_license(self) -> None:
        head = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        self.assertIn("name: swarm-wiki", head)
        self.assertIn("license: MIT", head)

    def test_agent_manifest_allows_implicit_invocation(self) -> None:
        text = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("allow_implicit_invocation: true", text)


class AppendTests(unittest.TestCase):
    def test_appends_in_contract_format(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "log.md"
            code, out = run("append", str(log), "ingest", "Some Title", "--date", "2026-04-02")
            self.assertEqual(code, 0)
            self.assertEqual(out["appended"], "## [2026-04-02] ingest | Some Title")
            self.assertIn("## [2026-04-02] ingest | Some Title",
                          log.read_text(encoding="utf-8"))

    def test_appended_line_satisfies_the_grep_contract(self) -> None:
        """The format exists so `grep "^## \\[" | tail` keeps working."""
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "log.md"
            for i in range(3):
                run("append", str(log), "run", f"Task {i}", "--date", "2026-04-02")
            lines = [ln for ln in log.read_text(encoding="utf-8").splitlines()
                     if ln.startswith("## [")]
            self.assertEqual(len(lines), 3)

    def test_rejects_unknown_verb_and_bad_date(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "log.md"
            self.assertEqual(run("append", str(log), "nope", "T")[0], 2)
            self.assertEqual(run("append", str(log), "ingest", "T", "--date", "April 2")[0], 2)
            self.assertFalse(log.exists(), "nothing should be written on rejection")


class LintTests(unittest.TestCase):
    def _wiki(self, td: str, body: str) -> str:
        (Path(td) / "wiki.md").write_text(CANARIES + VOCAB + body, encoding="utf-8")
        return td

    def test_clean_corpus_passes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            code, out = run("lint", self._wiki(td, "\n# Page: Notes\nCompiled on 2026-04-02.\n"))
            self.assertEqual(code, 0)
            self.assertEqual(out["result"], "ok")
            self.assertEqual(out["errors"], [])

    def test_missing_vocabulary_page_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "wiki.md").write_text(CANARIES + "# Page: Notes\nx\n", encoding="utf-8")
            code, out = run("lint", td)
            self.assertEqual(code, 1)
            self.assertEqual(out["result"], "fail")
            self.assertIn("missing-vocabulary-page", [e["code"] for e in out["errors"]])

    def test_bracketless_log_line_is_caught(self) -> None:
        """It slips past the grep contract, so it must not slip past the linter."""
        with tempfile.TemporaryDirectory() as td:
            self._wiki(td, "\n## 2026-04-02 ingest without brackets\n")
            _, out = run("lint", td)
            self.assertIn("malformed-log-line", [e["code"] for e in out["errors"]])

    def test_relative_date_and_link_only_entry_warn(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self._wiki(td, "\n# Page: Notes\nWe did this yesterday.\nhttps://example.com/a\n")
            _, out = run("lint", td)
            codes = [w["code"] for w in out["warnings"]]
            self.assertIn("relative-date", codes)
            self.assertIn("uncompiled-entry", codes)

    def test_missing_canary_warns_per_surface(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "wiki.md").write_text(
                "RESYNC-CANARY-DOC: ORANGE\n" + VOCAB, encoding="utf-8")
            _, out = run("lint", td)
            details = " ".join(w["detail"] for w in out["warnings"])
            self.assertIn("RESYNC-CANARY-SHEET", details)
            self.assertIn("RESYNC-CANARY-SLIDE", details)

    def test_duplicate_page_warns(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            self._wiki(td, "")
            (Path(td) / "other.md").write_text("# Page: Vocabulary\ndupe\n", encoding="utf-8")
            _, out = run("lint", td)
            self.assertIn("duplicate-page", [w["code"] for w in out["warnings"]])


if __name__ == "__main__":
    unittest.main()
