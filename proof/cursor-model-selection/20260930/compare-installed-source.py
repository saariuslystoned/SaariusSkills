#!/usr/bin/env python3
"""Compare installed plugin source bytes to one reviewed git commit. Read-only."""

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

BASE = "cc4070ebd7861f07ca3e24f7744d779fb13a472f"
BRANCH = "codex/cursor-luna-model-selection-20260930"

MANIFEST_PATHS = [
    ".mcp.json",
    ".agents/plugins",
    ".claude-plugin",
    ".cursor-plugin",
    ".codex-plugin",
    "plugin.json",
    "bridge",
    "skills",
]

SECRET_NAMES = {".env", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}
SECRET_SUFFIXES = (".pem", ".p12", ".key")
GENERATED_PARTS = {"node_modules", "__pycache__"}


def fail(message: str) -> None:
    print(f"FAIL {message}", file=sys.stderr)
    raise SystemExit(1)


def git(worktree: Path, *args: str, text: bool = True):
    return subprocess.run(
        ["git", "-C", str(worktree), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
    )


def git_ok(worktree: Path, *args: str):
    return subprocess.run(
        ["git", "-C", str(worktree), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def is_secret(rel_path: str) -> bool:
    name = Path(rel_path).name
    return name in SECRET_NAMES or name.startswith(".env") or name.endswith(SECRET_SUFFIXES)


def is_generated(rel_path: str) -> bool:
    parts = set(Path(rel_path).parts)
    return rel_path.endswith(".pyc") or bool(parts & GENERATED_PARTS)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def contained(root: Path, relative: str) -> Path:
    current = root
    leaf = root.joinpath(*Path(relative).parts)
    for part in Path(relative).parts:
        current = current / part
        if not current.is_symlink():
            continue
        if current != leaf:
            target = Path(os.path.realpath(current))
            real_root = Path(os.path.realpath(root))
            if target != real_root and real_root not in target.parents:
                fail(f"symlink escape {relative}")
    return leaf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", required=True, help="Path to reviewed git worktree")
    parser.add_argument("--commit", required=True, help="Approved 40-hex commit hash")
    parser.add_argument("--installed", required=True, help="Path to installed plugin root")
    args = parser.parse_args()

    worktree = Path(args.worktree).resolve()
    installed = Path(args.installed).resolve()
    reviewed_commit = args.commit.strip().lower()

    if not worktree.is_dir():
        fail("reviewed worktree directory missing")
    toplevel = Path(git(worktree, "rev-parse", "--show-toplevel").stdout.strip())
    if toplevel.resolve() != worktree.resolve():
        fail("worktree argument is not the git toplevel")
    branch = git(worktree, "branch", "--show-current").stdout.strip()
    if branch != BRANCH:
        fail(f"branch {branch or '(detached)'} is not {BRANCH}")

    # 1. Require explicitly approved full 40-character lowercase hex commit hash
    if not re.fullmatch(r"[0-9a-f]{40}", reviewed_commit):
        fail("reviewed commit must be a 40-character lowercase hex digest")

    # 2. Match worktree HEAD
    head = git(worktree, "rev-parse", "HEAD").stdout.strip()
    if reviewed_commit != head:
        fail(f"accepted commit ({reviewed_commit}) is not the reviewed worktree HEAD ({head})")
    if head == BASE:
        fail("reviewed HEAD is still the base commit cc4070e")
    git(worktree, "cat-file", "-e", f"{head}^{{commit}}")
    if git_ok(worktree, "merge-base", "--is-ancestor", BASE, head).returncode != 0:
        fail("reviewed HEAD is not a descendant of the base commit")

    # 3. Check tracked plugin paths in worktree have no uncommitted changes vs HEAD
    diff_res = git_ok(worktree, "diff", "--quiet", "HEAD", "--", *MANIFEST_PATHS)
    if diff_res.returncode != 0:
        fail("worktree has uncommitted changes in tracked plugin paths vs HEAD")

    if not installed.is_dir():
        fail("installed root missing")
    if installed == worktree:
        fail("installed root is the reviewed worktree")

    # 4. List tracked plugin paths from git commit
    raw_tree = git(
        worktree, "ls-tree", "-r", "--name-only", "-z", reviewed_commit, "--", *MANIFEST_PATHS, text=False
    ).stdout
    tracked_paths = [p.decode("utf-8") for p in raw_tree.split(b"\0") if p]

    compared = 0
    failures = []

    for rel_path in tracked_paths:
        if is_generated(rel_path):
            continue
        if is_secret(rel_path):
            fail(f"secret path in tracked tree: {rel_path}")

        # Git show blob bytes from commit
        git_blob = git(worktree, "show", f"{reviewed_commit}:{rel_path}", text=False).stdout
        commit_hash = sha256_bytes(git_blob)

        target = contained(installed, rel_path)
        if not os.path.lexists(target):
            failures.append(f"missing {rel_path}")
            continue

        if target.is_symlink():
            installed_bytes = os.fsencode(os.readlink(target))
            installed_hash = sha256_bytes(installed_bytes)
        elif target.is_file():
            installed_hash = sha256_file(target)
        else:
            failures.append(f"unsupported file type {rel_path}")
            continue

        if commit_hash != installed_hash:
            failures.append(f"mismatch {rel_path} commit={commit_hash} installed={installed_hash}")
            continue

        print(f"MATCH {commit_hash} {rel_path}")
        compared += 1

    if failures:
        for item in failures:
            print(f"FAIL {item}", file=sys.stderr)
        raise SystemExit(1)
    if compared == 0:
        fail("no plugin source paths compared")

    print(f"OK {compared} paths commit={reviewed_commit} installed={installed}")


if __name__ == "__main__":
    main()
