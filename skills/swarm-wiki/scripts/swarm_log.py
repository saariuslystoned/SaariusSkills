#!/usr/bin/env python3
"""Append to and lint the SWARM wiki corpus.

Subcommands
-----------
append <log.md> <verb> <title> [--date YYYY-MM-DD]
    Append a log line in the contract format:  ## [2026-04-02] ingest | Title

lint <wiki-dir>
    Check the corpus for the failure modes that silently rot it.

Exit codes: 0 clean, 1 errors found, 2 usage error.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

VERBS = ("ingest", "answer", "lint", "run")

LOG_LINE = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\] (\w+) \| (.+)$")
ANY_LOG_LINE = re.compile(r"^## \[")
# A line that *means* to be a log entry but may have lost the bracket. Matching only
# `^## \[` would let `## 2026-07-25 ...` slip past the linter exactly as it slips past
# the grep contract -- the very failure this check exists to catch.
LOGLIKE = re.compile(r"^## .*(?:\d{4}-\d{2}-\d{2}|\b(?:ingest|answer|lint|run)\b)")
PAGE_HEADING = re.compile(r"^# Page: (.+)$", re.MULTILINE)
CANARY = re.compile(r"^RESYNC-CANARY-([A-Z]+): ([A-Z]+)\s*$", re.MULTILINE)
BARE_URL_LINE = re.compile(r"^\s*(?:[-*]\s*)?<?https?://\S+>?\s*$")

RELATIVE_DATES = (
    "yesterday", "today", "tomorrow", "last week", "next week",
    "last month", "next month", "recently", "a while ago", "just now",
)


def _today() -> str:
    return _dt.date.today().isoformat()


# --------------------------------------------------------------------- append
def cmd_append(args: argparse.Namespace) -> int:
    if args.verb not in VERBS:
        _emit({"result": "error", "message": f"verb must be one of {VERBS}, got {args.verb!r}"})
        return 2

    date = args.date or _today()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        _emit({"result": "error", "message": f"date must be YYYY-MM-DD, got {date!r}"})
        return 2

    title = args.title.strip()
    if not title:
        _emit({"result": "error", "message": "title must not be empty"})
        return 2
    if "\n" in title:
        _emit({"result": "error", "message": "title must be a single line"})
        return 2

    line = f"## [{date}] {args.verb} | {title}"

    path = Path(args.log)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    # Blank line before the entry keeps the markdown readable.
    if existing and not existing.endswith("\n\n"):
        existing += "\n"
    path.write_text(existing + line + "\n", encoding="utf-8")

    _emit({
        "result": "ok",
        "schema": "swarm-wiki.append.v1",
        "appended": line,
        "log": str(path),
        "entries": sum(1 for ln in path.read_text(encoding="utf-8").splitlines()
                       if ANY_LOG_LINE.match(ln)),
    })
    return 0


# ----------------------------------------------------------------------- lint
def _lint_log(text: str, rel: str, errors: list, warnings: list) -> None:
    for i, line in enumerate(text.splitlines(), 1):
        if not (ANY_LOG_LINE.match(line) or LOGLIKE.match(line)):
            continue
        m = LOG_LINE.match(line)
        if not m:
            errors.append({
                "file": rel, "line": i, "code": "malformed-log-line",
                "detail": "breaks `grep \"^## \\[\"` tail contract",
                "text": line[:120],
            })
            continue
        if m.group(2) not in VERBS:
            warnings.append({
                "file": rel, "line": i, "code": "unknown-verb",
                "detail": f"{m.group(2)!r} not in {VERBS}",
            })


def _lint_prose(text: str, rel: str, errors: list, warnings: list) -> None:
    for i, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        for phrase in RELATIVE_DATES:
            # Skip the reference docs that *name* these phrases on purpose.
            if phrase in low and "never" not in low and "relative" not in low:
                warnings.append({
                    "file": rel, "line": i, "code": "relative-date",
                    "detail": f"{phrase!r} rots silently; use absolute YYYY-MM-DD",
                })
                break
        if BARE_URL_LINE.match(line):
            warnings.append({
                "file": rel, "line": i, "code": "uncompiled-entry",
                "detail": "link-only line: compile the synthesis or delete it",
            })


def cmd_lint(args: argparse.Namespace) -> int:
    root = Path(args.wiki_dir)
    if not root.is_dir():
        _emit({"result": "error", "message": f"not a directory: {root}"})
        return 2

    errors: list = []
    warnings: list = []
    pages: dict[str, list[str]] = {}
    canaries: dict[str, str] = {}
    md_files = sorted(root.rglob("*.md"))

    if not md_files:
        _emit({"result": "error", "message": f"no markdown found under {root}"})
        return 2

    for path in md_files:
        rel = str(path.relative_to(root))
        text = path.read_text(encoding="utf-8", errors="replace")
        _lint_log(text, rel, errors, warnings)
        _lint_prose(text, rel, errors, warnings)
        for name in PAGE_HEADING.findall(text):
            pages.setdefault(name.strip(), []).append(rel)
        for kind, colour in CANARY.findall(text):
            canaries[kind] = colour

    for name, where in sorted(pages.items()):
        if len(where) > 1:
            warnings.append({
                "file": where[0], "code": "duplicate-page",
                "detail": f"page {name!r} defined in {len(where)} files: {', '.join(where)}; merge them",
            })

    # The one that is an error rather than a warning.
    if "Vocabulary" not in pages:
        errors.append({
            "file": str(root), "code": "missing-vocabulary-page",
            "detail": ("no `# Page: Vocabulary` found. The notebook does not inherit the "
                       "global custom instruction and is not source-locked, so without this "
                       "page it answers swarm questions confidently and wrongly."),
        })

    for kind in ("DOC", "SHEET", "SLIDE"):
        if kind not in canaries:
            warnings.append({
                "file": str(root), "code": "missing-canary",
                "detail": f"no RESYNC-CANARY-{kind}; staleness of that surface becomes undetectable",
            })

    _emit({
        "result": "fail" if errors else "ok",
        "schema": "swarm-wiki.lint.v1",
        "scanned": len(md_files),
        "pages": sorted(pages),
        "canaries": canaries,
        "errors": errors,
        "warnings": warnings,
    })
    return 1 if errors else 0


# ----------------------------------------------------------------------- main
def _emit(payload: dict) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swarm_log.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    ap = sub.add_parser("append", help="append a log line in the contract format")
    ap.add_argument("log")
    ap.add_argument("verb", help=f"one of {', '.join(VERBS)}")
    ap.add_argument("title")
    ap.add_argument("--date", help="YYYY-MM-DD; defaults to today")
    ap.set_defaults(func=cmd_append)

    lp = sub.add_parser("lint", help="check the corpus for silent-rot failure modes")
    lp.add_argument("wiki_dir")
    lp.set_defaults(func=cmd_lint)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
