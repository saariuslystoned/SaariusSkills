#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from herdr_puppet_lib.harness_binding import ISOLATED_LAUNCH_PATH


HARNESSES = {
    "agy": {
        "command": "agy",
        "flags": [
            "--dangerously-skip-permissions",
            "--sandbox=false",
            "--new-project",
            "--log-file",
            "/dev/null",
        ],
        "status": ["models"],
    },
    "codex": {
        "command": "codex",
        "flags": ["--dangerously-bypass-approvals-and-sandbox"],
        "status": ["login", "status"],
    },
    "claude": {
        "command": "claude",
        "flags": ["--dangerously-skip-permissions"],
        "status": ["auth", "status"],
    },
    "cursor": {
        "command": "cursor-agent",
        "flags": ["--yolo", "--sandbox", "disabled"],
    },
    "grok": {
        "command": "grok",
        "flags": ["--always-approve", "--sandbox", "off"],
        "status": ["models"],
    },
}
MAX_OUTPUT = 64 * 1024
TIMEOUT_SECONDS = 20
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def bounded(argv: list[str], env: dict[str, str]) -> tuple[int, bytes]:
    result = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=TIMEOUT_SECONDS,
        check=False,
        env=env,
    )
    return result.returncode, result.stdout[:MAX_OUTPUT]


def clean_text(value: bytes) -> str:
    return ANSI.sub("", value.decode("utf-8", errors="replace"))


def version_line(value: bytes) -> str:
    for line in clean_text(value).splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:256]
    raise RuntimeError("version output is empty")


def enrolled(harness: str, returncode: int, output: bytes) -> bool:
    if returncode != 0:
        return False
    text = clean_text(output)
    lowered = text.lower()
    if harness == "codex":
        return "logged in" in lowered or "chatgpt" in lowered
    if harness == "claude":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return "logged in" in lowered or "firstparty" in lowered
        return bool(
            payload.get("loggedIn")
            or payload.get("logged_in")
            or payload.get("authenticated")
        )
    if harness == "cursor":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return "logged in" in lowered
        return bool(
            payload.get("loggedIn")
            or payload.get("logged_in")
            or payload.get("authenticated")
        )
    return bool(text.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness", choices=sorted(HARNESSES), required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--profile-root", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--output")
    parser.add_argument("--checkpoint-nonce")
    args = parser.parse_args(argv)
    if bool(args.output) != bool(args.checkpoint_nonce):
        raise RuntimeError(
            "--output and --checkpoint-nonce must be supplied together"
        )
    if args.checkpoint_nonce and re.fullmatch(
        r"[A-Za-z0-9._:-]{8,128}",
        args.checkpoint_nonce,
    ) is None:
        raise RuntimeError("checkpoint nonce is invalid")

    mapping = HARNESSES[args.harness]
    discovered = shutil.which(mapping["command"])
    if not discovered:
        raise RuntimeError("harness executable is unavailable")
    executable = Path(discovered).resolve(strict=True)
    profile_root = Path(args.profile_root).resolve(strict=True)
    worktree = Path(args.worktree).resolve(strict=True)
    if not executable.is_file():
        raise RuntimeError("harness executable is not a regular file")
    if not profile_root.is_dir() or profile_root.stat().st_uid != os.getuid():
        raise RuntimeError("profile root is not the current dedicated user")
    if not worktree.is_dir() or worktree.stat().st_uid != os.getuid():
        raise RuntimeError("worktree is not an owned directory")

    environment = {
        "HOME": str(profile_root),
        "PATH": ISOLATED_LAUNCH_PATH,
        "LANG": "C",
        "LC_ALL": "C",
        "TERM": "xterm-256color",
    }
    version_rc, version_output = bounded(
        [str(executable), "--version"],
        environment,
    )
    help_rc, help_output = bounded(
        [str(executable), "--help"],
        environment,
    )
    if version_rc != 0 or help_rc != 0:
        raise RuntimeError("version/help census failed")
    if args.harness == "cursor":
        enrollment_state = "interactive_pending"
        status_exit = None
    else:
        status_rc, status_output = bounded(
            [str(executable), *mapping["status"]],
            environment,
        )
        enrollment_state = (
            "enrolled"
            if enrolled(args.harness, status_rc, status_output)
            else "unavailable"
        )
        status_exit = status_rc
    executable_facts = {
        "command": mapping["command"],
        "path": str(executable),
        "version": version_line(version_output),
        "sha256": sha256_file(executable),
        "version_sha256": sha256_bytes(version_output),
        "help_sha256": sha256_bytes(help_output),
    }
    executable_facts["fingerprint"] = sha256_bytes(
        canonical_bytes(executable_facts)
    )
    launch_environment = {
        "HOME": str(profile_root),
        "PATH": ISOLATED_LAUNCH_PATH,
        "LANG": "C",
        "LC_ALL": "C",
        "TERM": "xterm-256color",
    }
    launch_argv = [str(executable), *mapping["flags"]]
    vector = {
        "argv": launch_argv,
        "environment": launch_environment,
        "inherit_environment": False,
    }
    payload = {
        "schema": "herdr-puppet.remote-harness-census.v1",
        "harness": args.harness,
        "host": args.host,
        "recorded_at": now(),
        "executable": executable_facts,
        "profile": {
            "route": "dedicated_os_user_profile",
            "root": str(profile_root),
            "isolation": "dedicated_remote_user",
            "enrollment_state": enrollment_state,
            "status_exit": status_exit,
            "raw_output_retained": False,
        },
        "regular_launch": {
            **vector,
            "unrestricted": True,
            "explicit_model_selector": False,
            "vector_sha256": sha256_bytes(canonical_bytes(vector)),
        },
        "model_observation": {
            "selection": "current_default",
            "model": "unavailable",
            "effort": "unavailable",
        },
        "source": {"worktree": str(worktree)},
        "raw_output_retained": False,
    }
    serialized = canonical_bytes(payload) + b"\n"
    if args.output:
        output = Path(args.output)
        if not output.is_absolute() or output == Path("/"):
            raise RuntimeError("output must be one absolute task-owned file")
        parent = output.parent.resolve(strict=True)
        if not parent.is_dir() or parent.stat().st_uid != os.getuid():
            raise RuntimeError("output parent is not an owned directory")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(output, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        sys.stdout.write(
            f"HERDR_PUPPET_STATUS {args.checkpoint_nonce}\n"
        )
    else:
        sys.stdout.buffer.write(serialized)
    return (
        0
        if payload["profile"]["enrollment_state"]
        in {"enrolled", "interactive_pending"}
        else 3
    )


if __name__ == "__main__":
    raise SystemExit(main())
