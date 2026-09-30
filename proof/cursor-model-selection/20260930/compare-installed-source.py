#!/usr/bin/env python3
"""Compare installed plugin source bytes to one reviewed git commit. Read-only."""

import argparse
import copy
import hashlib
import json
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

APPROVED_LANES = ("cursor-acp", "antigravity-acp", "grok-acp")
APPROVED_ENV_KEY = "SAARIUS_ACP_PERMISSION_MODE"
APPROVED_ENV_VAL = "approve-all"


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


def parse_json_no_duplicates(raw_bytes: bytes, label: str) -> dict:
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        fail(f"malformed {label} utf-8 encoding")

    def dict_raise_on_duplicates(ordered_pairs):
        seen = set()
        out = {}
        for key, value in ordered_pairs:
            if key in seen:
                fail(f"duplicate key in {label} JSON")
            seen.add(key)
            out[key] = value
        return out

    try:
        parsed = json.loads(text, object_pairs_hook=dict_raise_on_duplicates)
    except SystemExit:
        raise
    except Exception:
        fail(f"malformed {label} JSON")

    if not isinstance(parsed, dict):
        fail(f"{label} JSON root must be an object")
    return parsed


def strict_typed_equal(a, b) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(strict_typed_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(strict_typed_equal(x, y) for x, y in zip(a, b))
    return a == b


def validate_and_load_policy(policy_path_str: str, expected_sha256: str) -> tuple[dict, str]:
    policy_path = Path(policy_path_str).resolve()
    if not policy_path.is_file():
        fail(f"approved policy file missing or not a regular file: {policy_path}")

    expected_digest = expected_sha256.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        fail("approved policy sha256 must be a 64-character lowercase hex digest")

    policy_bytes = policy_path.read_bytes()
    actual_digest = sha256_bytes(policy_bytes)
    if actual_digest != expected_digest:
        fail(f"approved policy digest mismatch expected={expected_digest} actual={actual_digest}")

    policy = parse_json_no_duplicates(policy_bytes, "approved policy")

    auth = policy.get("authorization")
    if not auth or not isinstance(auth, str) or not auth.strip():
        fail("approved policy missing or empty authorization")

    mode = policy.get("mode")
    if mode != APPROVED_ENV_VAL or type(mode) is not str:
        fail("approved policy mode mismatch")

    lanes = policy.get("lanes")
    if not isinstance(lanes, list) or len(lanes) != len(APPROVED_LANES) or tuple(lanes) != APPROVED_LANES:
        fail("approved policy lanes mismatch")

    return policy, actual_digest


def verify_mcp_json_overlay(
    commit_blob: bytes,
    installed_target: Path,
    policy_data: dict,
    policy_hash: str,
) -> tuple[str, str, str]:
    if installed_target.is_symlink() or not installed_target.is_file():
        fail("installed .mcp.json must be a regular file")

    commit_hash = sha256_bytes(commit_blob)
    installed_bytes = installed_target.read_bytes()
    installed_hash = sha256_bytes(installed_bytes)

    commit_manifest = parse_json_no_duplicates(commit_blob, "commit .mcp.json")
    installed_manifest = parse_json_no_duplicates(installed_bytes, "installed .mcp.json")

    expected_manifest = copy.deepcopy(commit_manifest)
    if "mcpServers" not in expected_manifest or not isinstance(expected_manifest["mcpServers"], dict):
        fail("commit .mcp.json missing mcpServers object")

    for lane in APPROVED_LANES:
        if lane not in expected_manifest["mcpServers"]:
            fail(f"commit .mcp.json missing server {lane}")
        server_entry = expected_manifest["mcpServers"][lane]
        if not isinstance(server_entry, dict):
            fail(f"commit .mcp.json server {lane} is not an object")
        if "env" not in server_entry:
            server_entry["env"] = {}
        elif not isinstance(server_entry["env"], dict):
            fail(f"commit .mcp.json server {lane} env is not an object")
        server_entry["env"][APPROVED_ENV_KEY] = APPROVED_ENV_VAL

    if set(installed_manifest.keys()) != set(expected_manifest.keys()):
        fail("installed .mcp.json unexpected top-level structure")

    for k, v in expected_manifest.items():
        if k != "mcpServers" and not strict_typed_equal(installed_manifest.get(k), v):
            fail(f"installed .mcp.json top-level mismatch on {k}")

    inst_servers = installed_manifest.get("mcpServers")
    if not isinstance(inst_servers, dict):
        fail("installed .mcp.json mcpServers must be an object")

    if set(inst_servers.keys()) != set(expected_manifest["mcpServers"].keys()):
        fail("installed .mcp.json mcpServers keys mismatch")

    for lane, exp_server in expected_manifest["mcpServers"].items():
        inst_server = inst_servers.get(lane)
        if not isinstance(inst_server, dict):
            fail(f"installed .mcp.json server {lane} must be an object")

        if set(inst_server.keys()) != set(exp_server.keys()):
            fail(f"installed .mcp.json server {lane} unexpected keys")

        for prop in ("command", "args", "cwd"):
            if prop in exp_server and not strict_typed_equal(inst_server.get(prop), exp_server[prop]):
                fail(f"installed .mcp.json server {lane} control mismatch: {prop}")

        exp_env = exp_server.get("env")
        inst_env = inst_server.get("env")
        if exp_env is None:
            if inst_env is not None:
                fail(f"installed .mcp.json server {lane} unexpected env")
        else:
            if not isinstance(inst_env, dict):
                fail(f"installed .mcp.json server {lane} env must be an object")
            if set(inst_env.keys()) != set(exp_env.keys()):
                fail(f"installed .mcp.json server {lane} env keys mismatch")
            for env_k, env_v in exp_env.items():
                if not strict_typed_equal(inst_env.get(env_k), env_v):
                    fail(f"installed .mcp.json server {lane} env value mismatch for {env_k}")

        for k, v in exp_server.items():
            if not strict_typed_equal(inst_server.get(k), v):
                fail(f"installed .mcp.json server {lane} property mismatch on {k}")

    canonical_expected = json.dumps(expected_manifest, sort_keys=True, separators=(",", ":"))
    canonical_installed = json.dumps(installed_manifest, sort_keys=True, separators=(",", ":"))
    if canonical_expected != canonical_installed or not strict_typed_equal(installed_manifest, expected_manifest):
        fail("installed .mcp.json does not match expected manifest")

    attestation = (
        f"MATCH_APPROVED_OVERLAY .mcp.json "
        f"commit_manifest={commit_hash} "
        f"installed_manifest={installed_hash} "
        f"policy_sha256={policy_hash} "
        f"mode={policy_data['mode']} "
        f"lanes={','.join(APPROVED_LANES)}"
    )
    return attestation, commit_hash, installed_hash


def verify(
    worktree: Path | str,
    commit: str,
    installed: Path | str,
    approved_policy: Path | str | None = None,
    approved_policy_sha256: str | None = None,
) -> int:
    worktree = Path(worktree).resolve()
    installed = Path(installed).resolve()
    reviewed_commit = str(commit).strip().lower()

    if bool(approved_policy) != bool(approved_policy_sha256):
        fail("both --approved-policy and --approved-policy-sha256 must be provided together")

    policy_data = None
    policy_hash = None
    if approved_policy and approved_policy_sha256:
        policy_data, policy_hash = validate_and_load_policy(str(approved_policy), str(approved_policy_sha256))

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

        if rel_path == ".mcp.json" and policy_data is not None:
            attestation, _, _ = verify_mcp_json_overlay(git_blob, target, policy_data, policy_hash)
            print(attestation)
            compared += 1
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

    if policy_hash:
        print(f"OK {compared} paths commit={reviewed_commit} installed={installed} approved_policy={policy_hash}")
    else:
        print(f"OK {compared} paths commit={reviewed_commit} installed={installed}")

    return compared


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", required=True, help="Path to reviewed git worktree")
    parser.add_argument("--commit", required=True, help="Approved 40-hex commit hash")
    parser.add_argument("--installed", required=True, help="Path to installed plugin root")
    parser.add_argument("--approved-policy", help="Path to approved host permission policy file")
    parser.add_argument("--approved-policy-sha256", help="Approved policy SHA256 hex digest")
    args = parser.parse_args(argv)

    if bool(args.approved_policy) != bool(args.approved_policy_sha256):
        fail("both --approved-policy and --approved-policy-sha256 must be provided together")

    return verify(
        worktree=args.worktree,
        commit=args.commit,
        installed=args.installed,
        approved_policy=args.approved_policy,
        approved_policy_sha256=args.approved_policy_sha256,
    )


if __name__ == "__main__":
    main()
