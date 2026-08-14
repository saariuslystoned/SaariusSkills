#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from herdr_puppet_lib.claude_hook_marker import validate_absent_root
from herdr_puppet_lib.claude_hooks import (
    CLAUDE_HELPER_RELATIVE_PATH,
    CLAUDE_IMPLEMENTATION_RELATIVE_PATH,
    build_runtime_claude_lifecycle_observation,
    checkpoint_lifecycle_observation,
    claude_launch_flags,
)
from herdr_puppet_lib.harness_binding import (
    HARNESS_LAUNCH_SPECS,
    ISOLATED_LAUNCH_PATH,
)


HARNESSES = {
    harness: dict(specification)
    for harness, specification in HARNESS_LAUNCH_SPECS.items()
}
HARNESSES["agy"]["status"] = ["models"]
HARNESSES["codex"]["status"] = ["login", "status"]
HARNESSES["claude"]["status"] = ["auth", "status"]
HARNESSES["grok"]["status"] = ["models"]
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
    process = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    if process.stdout is None:
        process.kill()
        process.wait()
        raise RuntimeError("census output pipe is unavailable")
    descriptor = process.stdout.fileno()
    os.set_blocking(descriptor, False)
    selector = selectors.DefaultSelector()
    selector.register(descriptor, selectors.EVENT_READ)
    output = bytearray()
    deadline = time.monotonic() + TIMEOUT_SECONDS
    eof = False
    try:
        while not eof:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, TIMEOUT_SECONDS)
            events = selector.select(min(remaining, 0.25))
            for _key, _mask in events:
                try:
                    chunk = os.read(descriptor, 8192)
                except BlockingIOError:
                    continue
                if not chunk:
                    eof = True
                    selector.unregister(descriptor)
                    break
                output.extend(chunk)
                if len(output) > MAX_OUTPUT:
                    raise RuntimeError("census output exceeds its bounded size")
            if process.poll() is not None and not events:
                try:
                    chunk = os.read(descriptor, 8192)
                except BlockingIOError:
                    continue
                if not chunk:
                    eof = True
                else:
                    output.extend(chunk)
                    if len(output) > MAX_OUTPUT:
                        raise RuntimeError(
                            "census output exceeds its bounded size"
                        )
        return process.wait(), bytes(output)
    except Exception:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        raise
    finally:
        selector.close()
        process.stdout.close()


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
    parser.add_argument("--run-id")
    parser.add_argument("--claude-hook-root")
    args = parser.parse_args(argv)
    if bool(args.output) != bool(args.checkpoint_nonce):
        raise RuntimeError(
            "--output and --checkpoint-nonce must be supplied together"
        )
    if args.checkpoint_nonce and re.fullmatch(
        r"[A-Za-z0-9._:-]{8,24}",
        args.checkpoint_nonce,
    ) is None:
        raise RuntimeError("checkpoint nonce is invalid")
    if args.harness == "claude":
        if not args.run_id or not args.claude_hook_root:
            raise RuntimeError(
                "Claude census requires --run-id and --claude-hook-root"
            )
        if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", args.run_id) is None:
            raise RuntimeError("run id is invalid")
    elif args.run_id or args.claude_hook_root:
        raise RuntimeError(
            "Claude lifecycle arguments are valid only for the Claude harness"
        )

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
    if args.harness == "claude":
        helper = (
            Path(__file__).resolve(strict=True).parent
            / "claude_hook_marker.py"
        ).resolve(strict=True)
        expected_helper = (
            worktree / CLAUDE_HELPER_RELATIVE_PATH
        )
        if helper != expected_helper or not helper.is_file() or helper.is_symlink():
            raise RuntimeError("Claude hook helper is not source-bound")
        implementation = (
            Path(__file__).resolve(strict=True).parent
            / "herdr_puppet_lib"
            / "claude_hook_marker.py"
        ).resolve(strict=True)
        expected_implementation = (
            worktree / CLAUDE_IMPLEMENTATION_RELATIVE_PATH
        )
        if (
            implementation != expected_implementation
            or not implementation.is_file()
            or implementation.is_symlink()
        ):
            raise RuntimeError(
                "Claude hook implementation is not source-bound"
            )
        interpreter = Path(sys.executable).resolve(strict=True)
        if not interpreter.is_file() or interpreter.is_symlink():
            raise RuntimeError("Python interpreter is unavailable or unsafe")
        hook_root = validate_absent_root(args.claude_hook_root)
        lifecycle_observation = build_runtime_claude_lifecycle_observation(
            run_id=args.run_id,
            marker_root=str(hook_root),
            helper_path=helper,
            implementation_path=implementation,
            interpreter_path=interpreter,
        )
    else:
        lifecycle_observation = checkpoint_lifecycle_observation()

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
    if (
        args.harness == "claude"
        and re.search(
            r"(?<![A-Za-z0-9_-])--settings(?![A-Za-z0-9_-])",
            clean_text(help_output),
        )
        is None
    ):
        raise RuntimeError("Claude executable does not advertise --settings")
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
    launch_argv = [
        str(executable),
        *(
            claude_launch_flags(lifecycle_observation)
            if args.harness == "claude"
            else mapping["flags"]
        ),
    ]
    vector = {
        "argv": launch_argv,
        "environment": launch_environment,
        "inherit_environment": False,
    }
    payload = {
        "schema": "herdr-puppet.remote-harness-census.v2",
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
        "lifecycle_observation": lifecycle_observation,
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
