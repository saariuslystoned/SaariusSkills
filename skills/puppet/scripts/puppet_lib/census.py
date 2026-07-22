"""Allowlisted, bounded, zero-agent executable census."""

from __future__ import annotations

import datetime as dt
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .adapter_manifest import AdapterManifest, BEHAVIOR_CAPABILITIES
from .errors import ValidationError
from .safety import sha256_bytes, sha256_file


MAX_OUTPUT_BYTES = 65536
TIMEOUT_SECONDS = 10
PROTOCOL_FINGERPRINT = sha256_bytes(b"PUPPET_CONFORMANCE_V1")


COMMANDS: Dict[str, Tuple[str, ...]] = {
    "agy": ("agy",),
    "cursor": ("cursor-agent",),
    "claude": ("claude",),
    "codex": ("codex",),
    "grok": ("grok",),
}

DECLARED_MAPPINGS: Dict[str, Dict[str, Any]] = {
    "agy": {
        "permission_flags": ["--dangerously-skip-permissions"],
        "sandbox_flags": ["--sandbox=false"],
        "prompt_transport": "interactive_tmux_buffer_unproved",
    },
    "cursor": {
        "permission_flags": ["--yolo"],
        "sandbox_flags": ["--sandbox", "disabled"],
        "prompt_transport": "interactive_tmux_buffer_unproved",
    },
    "claude": {
        "permission_flags": ["--dangerously-skip-permissions"],
        "sandbox_flags": [],
        "prompt_transport": "stdin_print_declared",
    },
    "codex": {
        "permission_flags": ["--dangerously-bypass-approvals-and-sandbox"],
        "sandbox_flags": ["--dangerously-bypass-approvals-and-sandbox"],
        "prompt_transport": "stdin_exec_declared",
    },
    "grok": {
        "permission_flags": ["--always-approve"],
        "sandbox_flags": [],
        "prompt_transport": "prompt_file_declared",
    },
}


def _bounded_run(argv: List[str]) -> bytes:
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C",
        "LC_ALL": "C",
    }
    if os.environ.get("HOME"):
        # Preserve the caller's home for wrapper path resolution; never inspect
        # or copy any configuration below it.
        environment["HOME"] = os.environ["HOME"]
    try:
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=TIMEOUT_SECONDS,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError("bounded census command failed") from exc
    output = result.stdout
    if len(output) > MAX_OUTPUT_BYTES:
        raise ValidationError("bounded census output exceeds the cap")
    if result.returncode != 0:
        raise ValidationError("bounded census command returned nonzero")
    return output


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def census_target(target: str, adapter_fingerprint: str) -> AdapterManifest:
    if target not in COMMANDS:
        raise ValidationError("target is not on the census allowlist")
    requested = COMMANDS[target][0]
    discovered = shutil.which(requested)
    if not discovered:
        raise ValidationError("target executable is unavailable")
    requested_path = Path(discovered)
    resolved_path = requested_path.resolve(strict=True)
    if not resolved_path.is_file():
        raise ValidationError("resolved executable is not a regular file")
    command_prefix = [str(resolved_path)] + list(COMMANDS[target][1:])
    version = _bounded_run(command_prefix + ["--version"])
    help_output = _bounded_run(command_prefix + ["--help"])
    mapping = dict(DECLARED_MAPPINGS[target])
    help_text = help_output.decode("utf-8", errors="replace")
    permission_declared = all(flag in help_text for flag in mapping["permission_flags"][:1])
    sandbox_declared = bool(mapping["sandbox_flags"]) and mapping["sandbox_flags"][0] in help_text
    prompt_declared = mapping["prompt_transport"].endswith("_declared")
    complete = permission_declared and sandbox_declared and prompt_declared
    mapping.update(
        {
            "complete": complete,
            "permission_declared": permission_declared,
            "sandbox_disable_declared": sandbox_declared,
            "prompt_transport_declared": prompt_declared,
            "launch_argv": [str(resolved_path)] + mapping["permission_flags"] + mapping["sandbox_flags"],
        }
    )
    stat_result = resolved_path.stat()
    raw = {
        "schema_version": 1,
        "target": target,
        "generated_at": _utc_now(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "executable": {
            "requested_path": str(requested_path),
            "resolved_path": str(resolved_path),
            "device": stat_result.st_dev,
            "inode": stat_result.st_ino,
            "size": stat_result.st_size,
            "mtime_ns": stat_result.st_mtime_ns,
            "sha256": sha256_file(resolved_path),
            "version_sha256": sha256_bytes(version),
            "help_sha256": sha256_bytes(help_output),
        },
        "adapter_fingerprint": adapter_fingerprint,
        "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        "yolo_mapping": mapping,
        "capabilities": {name: "declared" for name in BEHAVIOR_CAPABILITIES},
        "doctor_only": True,
        "qualification": None,
    }
    return AdapterManifest.from_dict(raw)


def census_many(targets: List[str], adapter_fingerprint: str) -> Dict[str, Any]:
    if len(set(targets)) != len(targets):
        raise ValidationError("duplicate census targets")
    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "zero_agent": True,
        "manifests": {target: census_target(target, adapter_fingerprint).raw for target in targets},
    }
