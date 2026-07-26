"""Allowlisted, bounded, zero-agent executable census."""

from __future__ import annotations

import datetime as dt
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .adapter_manifest import (
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    AdapterManifest,
    BEHAVIOR_CAPABILITIES,
    CURSOR_REQUIRED_PATH_TOOLS,
    build_execution_bundle,
    direct_execution_bundle,
    execution_file_identity,
    execution_file_snapshot,
    launcher_execution_identity,
)
from .agy_launch import (
    AGY_REGULAR_PERMISSION_FLAGS,
    AGY_REGULAR_PROJECT_ISOLATION_FLAGS,
    AGY_REGULAR_SANDBOX_FLAGS,
    agy_regular_launch_argv,
)
from .errors import ValidationError
from .handoffs import PROTOCOL_FINGERPRINT
from .profiles import (
    PROMPT_TRANSPORT,
    SESSION_PROFILE_COMMANDS,
    SUBMIT_SETTLE_SECONDS,
    startup_settle_seconds_for,
    session_profiles_for,
)
from .safety import canonical_json_bytes, sha256_bytes, sha256_file


MAX_OUTPUT_BYTES = 65536
TIMEOUT_SECONDS = 10
CURSOR_EXECUTION_SETTLE_SECONDS = 5.0
DIRECT_EXECUTION_SETTLE_SECONDS = 2.0
AGY_SANDBOX_DISABLE_FLAG = "--sandbox=false"
GROK_SANDBOX_DISABLE_FLAGS = ["--sandbox", "off"]
CENSUS_SCHEMA_VERSION = 2
CURSOR_STATIC_LAUNCHER_LAYOUTS = (
    b"""#!/usr/bin/env bash
set -euo pipefail
export CURSOR_INVOKED_AS="$(basename "$0")"
# Get the directory of the actual script (handles symlinks)
if command -v realpath >/dev/null 2>&1; then
  SCRIPT_DIR="$(dirname "$(realpath "$0")")"
else
  SCRIPT_DIR="$(dirname "$(readlink "$0" || echo "$0")")"
fi
NODE_BIN="$SCRIPT_DIR/node"

# Enable Node.js compile cache for faster CLI startup (requires Node.js >= 22.1.0)
# Cache is automatically invalidated when source files change
if [ -z "${NODE_COMPILE_CACHE:-}" ]; then
  if [[ "${OSTYPE:-}" == darwin* ]]; then
    export NODE_COMPILE_CACHE="$HOME/Library/Caches/cursor-compile-cache"
  else
    export NODE_COMPILE_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/cursor-compile-cache"
  fi
fi

should_skip_system_ca() {
  case "${AGENT_CLI_CREDENTIAL_STORE:-}" in
    file)
      return 0
      ;;
  esac
  return 1
}

if ! should_skip_system_ca && "$NODE_BIN" --use-system-ca --version >/dev/null 2>&1; then
  exec -a "$0" "$NODE_BIN" --use-system-ca "$SCRIPT_DIR/index.js" "$@"
fi

exec -a "$0" "$NODE_BIN" "$SCRIPT_DIR/index.js" "$@"
""",
)
CODEX_NPM_LAUNCHER_SHA256 = (
    "134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477"
)
CODEX_NPM_NATIVE_RELATIVE_PARTS = (
    "node_modules",
    "@openai",
    "codex-darwin-arm64",
    "vendor",
    "aarch64-apple-darwin",
    "bin",
    "codex",
)
COMMANDS: Dict[str, Tuple[str, ...]] = {
    "agy": ("agy",),
    "cursor": ("cursor-agent",),
    "claude": ("claude",),
    "codex": ("codex",),
    "grok": ("grok",),
}

DECLARED_MAPPINGS: Dict[str, Dict[str, Any]] = {
    "agy": {
        # Regular launch buckets match the live-proved exact argv. The
        # parser-only --sandbox=false candidate stays out of this mapping.
        "permission_flags": list(AGY_REGULAR_PERMISSION_FLAGS),
        "project_isolation_flags": list(AGY_REGULAR_PROJECT_ISOLATION_FLAGS),
        "sandbox_flags": list(AGY_REGULAR_SANDBOX_FLAGS),
        "prompt_transport": PROMPT_TRANSPORT,
        "model_flag": "--model",
        "effort_flag": "--effort",
    },
    "cursor": {
        "permission_flags": ["--yolo"],
        "project_isolation_flags": [],
        "sandbox_flags": ["--sandbox", "disabled"],
        "prompt_transport": PROMPT_TRANSPORT,
        "model_flag": "--model",
    },
    "claude": {
        "permission_flags": ["--dangerously-skip-permissions"],
        "project_isolation_flags": [],
        "sandbox_flags": [],
        "prompt_transport": PROMPT_TRANSPORT,
        "model_flag": "--model",
        "effort_flag": "--effort",
    },
    "codex": {
        "permission_flags": ["--dangerously-bypass-approvals-and-sandbox"],
        "project_isolation_flags": [],
        "sandbox_flags": ["--dangerously-bypass-approvals-and-sandbox"],
        "prompt_transport": PROMPT_TRANSPORT,
        "model_flag": "--model",
    },
    "grok": {
        "permission_flags": ["--always-approve"],
        "project_isolation_flags": [],
        "sandbox_flags": list(GROK_SANDBOX_DISABLE_FLAGS),
        "prompt_transport": PROMPT_TRANSPORT,
        "model_flag": "--model",
        "effort_flag": "--reasoning-effort",
    },
}

ZERO_AGENT_SESSION_PROFILES = {
    target: list(session_profiles_for(target)) for target in SESSION_PROFILE_COMMANDS
}
ZERO_AGENT_SESSION_PROFILES_DECLARED = True
ZERO_AGENT_STARTUP_SETTLE_SECONDS = {
    target: startup_settle_seconds_for(target) for target in SESSION_PROFILE_COMMANDS
}


def _bounded_run_result(argv: List[str]) -> Tuple[int, bytes]:
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
    return result.returncode, output


def _bounded_run(argv: List[str]) -> bytes:
    returncode, output = _bounded_run_result(argv)
    if returncode != 0:
        raise ValidationError("bounded census command returned nonzero")
    return output


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def adapter_implementation_fingerprint(
    skill_root: Optional[Path] = None,
) -> str:
    """Bind every source and template that owns adapter/probe behavior."""
    skill_root = (
        Path(skill_root).resolve(strict=True)
        if skill_root is not None
        else Path(__file__).resolve(strict=True).parents[2]
    )
    scripts_root = skill_root / "scripts"
    sources = sorted((scripts_root / "puppet_lib").glob("*.py"))
    sources.extend(
        [
            scripts_root / "adapter_lab.py",
            scripts_root / "puppet.py",
            scripts_root / "profile_login.py",
            scripts_root / "viewer_attach.py",
        ]
    )
    instruction_root = skill_root / "templates" / "instructions"
    sources.extend(
        path for path in sorted(instruction_root.rglob("*")) if path.is_file()
    )
    rows = [
        {
            "path": path.relative_to(skill_root).as_posix(),
            "sha256": sha256_file(path),
        }
        for path in sorted(sources)
    ]
    return sha256_bytes(canonical_json_bytes(rows))


def _sandbox_disable_declared(
    target: str, mapping: Dict[str, Any], help_text: str
) -> bool:
    flags = mapping["sandbox_flags"]
    if target == "agy":
        # Regular-session mapping uses empty sandbox_flags. A claimed
        # --sandbox=false bucket is parser-oriented evidence only and must not
        # be treated as regular launch sandbox-off authority by itself.
        if flags == list(AGY_REGULAR_SANDBOX_FLAGS):
            return False
        return (
            flags == [AGY_SANDBOX_DISABLE_FLAG]
            and re.search(r"(?m)^\s*--sandbox(?:[=,\s]|$)", help_text) is not None
        )
    if target == "grok":
        # Help proves the --sandbox surface; the exact profile value "off" is the
        # declared census mapping and is not required to appear as help text.
        return (
            flags == GROK_SANDBOX_DISABLE_FLAGS
            and re.search(r"(?m)^\s*--sandbox(?:[=,\s]|$)", help_text) is not None
        )
    if flags:
        return all(flag in help_text for flag in flags)
    if target == "claude":
        return "  --sandbox" not in help_text
    return False


def _agy_sandbox_false_parser_proved(command_prefix: List[str]) -> bool:
    """Prove the exact negative boolean form without launching a model.

    This is parser-only evidence. It must never be copied into the regular
    launch sandbox_flags bucket or launch argv.
    """

    accepted, _accepted_output = _bounded_run_result(
        command_prefix + [AGY_SANDBOX_DISABLE_FLAG, "help"]
    )
    rejected, _rejected_output = _bounded_run_result(
        command_prefix + ["--sandbox=puppet-invalid", "help"]
    )
    return accepted == 0 and rejected != 0


def _project_isolation_declared(mapping: Dict[str, Any], help_text: str) -> bool:
    if not mapping["project_isolation_flags"]:
        return False
    return all(
        re.search(r"(?m)^\s*" + re.escape(flag) + r"(?:[=,\s]|$)", help_text)
        is not None
        for flag in mapping["project_isolation_flags"]
    )


def _launch_flags(mapping: Dict[str, Any]) -> List[str]:
    """Combine declared flag groups without repeating an identical switch."""
    combined: List[str] = []
    for flag in (
        mapping["permission_flags"]
        + mapping["sandbox_flags"]
        + mapping["project_isolation_flags"]
    ):
        if flag not in combined:
            combined.append(flag)
    return combined


def _regular_launch_argv(target: str, resolved_path: str, mapping: Dict[str, Any]) -> List[str]:
    """Build the target's regular census launch argv from declared buckets."""

    if target == "agy":
        return agy_regular_launch_argv(resolved_path)
    return [resolved_path] + _launch_flags(mapping)


def _cursor_execution_bundle(
    launcher_path: Path, launcher: Dict[str, Any]
) -> Dict[str, Any]:
    """Resolve only Cursor's exact observed shell-launcher execution layout."""

    observed_launcher, raw = execution_file_snapshot(launcher_path, max_bytes=8192)
    if observed_launcher != launcher_execution_identity(launcher):
        raise ValidationError("cursor launcher changed during static validation")
    if raw not in CURSOR_STATIC_LAUNCHER_LAYOUTS:
        raise ValidationError("cursor launcher is not the recognized shell layout")
    directory = launcher_path.parent
    runtime = execution_file_identity(directory / "node")
    entrypoint = execution_file_identity(directory / "index.js")
    env_path = Path("/usr/bin/env")
    path_value = os.environ.get("PATH")
    if not isinstance(path_value, str) or not path_value:
        raise ValidationError("cursor launcher PATH is unavailable")
    path_entries = path_value.split(os.pathsep)
    if any(not item or not Path(item).is_absolute() for item in path_entries):
        raise ValidationError("cursor launcher PATH is cwd-dependent")
    transient_paths = [env_path]
    for tool in CURSOR_REQUIRED_PATH_TOOLS:
        discovered = shutil.which(tool, path=path_value)
        if not discovered:
            raise ValidationError("cursor launcher %s is unavailable" % tool)
        transient_paths.append(Path(discovered).resolve(strict=True))
    transients = sorted(
        [execution_file_identity(path) for path in transient_paths],
        key=lambda item: item["path"],
    )
    return build_execution_bundle(
        launcher=launcher_execution_identity(launcher),
        transition="same_pid_exec",
        runtime_executable=runtime,
        transient_executables=transients,
        support_files=[entrypoint],
        settle_timeout_seconds=CURSOR_EXECUTION_SETTLE_SECONDS,
    )


def _codex_npm_execution_bundle(
    launcher_path: Path, launcher: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Resolve the exact 0.145.0 npm launcher to its bundled native CLI."""

    observed_launcher, _raw = execution_file_snapshot(
        launcher_path, max_bytes=16384
    )
    if observed_launcher != launcher_execution_identity(launcher):
        raise ValidationError("codex npm launcher changed during static validation")
    if (
        observed_launcher["sha256"] != CODEX_NPM_LAUNCHER_SHA256
        or launcher_path.name != "codex.js"
        or launcher_path.parent.name != "bin"
        or launcher_path.parent.parent.name != "codex"
        or launcher_path.parent.parent.parent.name != "@openai"
    ):
        raise ValidationError("codex npm launcher is not the recognized layout")
    package_root = launcher_path.parent.parent
    runtime = execution_file_identity(
        package_root.joinpath(*CODEX_NPM_NATIVE_RELATIVE_PARTS)
    )
    execution = build_execution_bundle(
        launcher=runtime,
        transition="direct_with_support",
        runtime_executable=runtime,
        transient_executables=[],
        support_files=[observed_launcher],
        settle_timeout_seconds=DIRECT_EXECUTION_SETTLE_SECONDS,
    )
    return runtime, execution


def _execution_bundle(
    target: str, launcher_path: Path, launcher: Dict[str, Any]
) -> Dict[str, Any]:
    with launcher_path.open("rb") as handle:
        prefix = handle.read(2)
    if target == "cursor":
        return _cursor_execution_bundle(launcher_path, launcher)
    if prefix == b"#!":
        raise ValidationError(
            "%s shell or script launcher has no exact runtime resolver" % target
        )
    return direct_execution_bundle(
        launcher, settle_timeout_seconds=DIRECT_EXECUTION_SETTLE_SECONDS
    )


def _census_command_prefix(
    target: str, resolved_path: Path, execution: Dict[str, Any]
) -> List[str]:
    """Avoid executing Cursor's shell wrapper during zero-agent inspection."""

    if target != "cursor":
        return [str(resolved_path)] + list(COMMANDS[target][1:])
    support = execution["support_files"]
    if len(support) != 1 or Path(support[0]["path"]).name != "index.js":
        raise ValidationError("cursor entrypoint layout is invalid")
    return [execution["runtime_executable"]["path"], support[0]["path"]]


def census_target(target: str, adapter_fingerprint: str) -> AdapterManifest:
    if target not in COMMANDS:
        raise ValidationError("target is not on the census allowlist")
    requested = COMMANDS[target][0]
    discovered = shutil.which(requested)
    if not discovered:
        raise ValidationError("target executable is unavailable")
    requested_path = Path(discovered)
    requested_resolved_path = requested_path.resolve(strict=True)
    if not requested_resolved_path.is_file():
        raise ValidationError("resolved executable is not a regular file")
    requested_launcher = execution_file_identity(requested_resolved_path)
    requested_executable = {
        "requested_path": str(requested_path),
        "resolved_path": requested_launcher["path"],
        "device": requested_launcher["device"],
        "inode": requested_launcher["inode"],
        "size": requested_launcher["size"],
        "mtime_ns": requested_launcher["mtime_ns"],
        "sha256": requested_launcher["sha256"],
    }
    with requested_resolved_path.open("rb") as handle:
        prefix = handle.read(2)
    if target == "codex" and prefix == b"#!":
        runtime, execution = _codex_npm_execution_bundle(
            requested_resolved_path, requested_executable
        )
        executable = {
            "requested_path": str(requested_path),
            "resolved_path": runtime["path"],
            "device": runtime["device"],
            "inode": runtime["inode"],
            "size": runtime["size"],
            "mtime_ns": runtime["mtime_ns"],
            "sha256": runtime["sha256"],
        }
        resolved_path = Path(runtime["path"])
    else:
        executable = requested_executable
        resolved_path = requested_resolved_path
        execution = _execution_bundle(target, resolved_path, executable)
    command_prefix = _census_command_prefix(target, resolved_path, execution)
    version = _bounded_run(command_prefix + ["--version"])
    help_output = _bounded_run(command_prefix + ["--help"])
    if requested_path.resolve(strict=True) != requested_resolved_path:
        raise ValidationError("target requested executable changed during bounded census")
    if target == "codex" and prefix == b"#!":
        current_launcher = {
            "requested_path": str(requested_path),
            "resolved_path": requested_launcher["path"],
            "device": requested_launcher["device"],
            "inode": requested_launcher["inode"],
            "size": requested_launcher["size"],
            "mtime_ns": requested_launcher["mtime_ns"],
            "sha256": requested_launcher["sha256"],
        }
        current_runtime, current_execution = _codex_npm_execution_bundle(
            requested_resolved_path, current_launcher
        )
        if current_runtime != runtime or current_execution != execution:
            raise ValidationError(
                "target runtime layout changed during bounded census"
            )
    else:
        if execution_file_identity(resolved_path) != requested_launcher:
            raise ValidationError("target launcher changed during bounded census")
        if _execution_bundle(target, resolved_path, executable) != execution:
            raise ValidationError(
                "target runtime layout changed during bounded census"
            )
    mapping = dict(DECLARED_MAPPINGS[target])
    help_text = help_output.decode("utf-8", errors="replace")
    permission_declared = all(flag in help_text for flag in mapping["permission_flags"])
    if target == "agy":
        # Keep the parser-only --sandbox=false sweep available as evidence, but
        # never promote it into regular launch sandbox_flags, launch argv, or
        # sandbox-off authority for the complete YOLO mapping.
        if not isinstance(_agy_sandbox_false_parser_proved(command_prefix), bool):
            raise ValidationError("agy sandbox parser probe is invalid")
        sandbox_declared = False
    else:
        sandbox_declared = _sandbox_disable_declared(target, mapping, help_text)
    isolation_declared = _project_isolation_declared(mapping, help_text)
    prompt_declared = mapping["prompt_transport"].endswith("_declared")
    session_profiles = session_profiles_for(target)
    session_profiles_declared = bool(session_profiles)
    startup_settle_seconds = startup_settle_seconds_for(target)
    complete = (
        permission_declared
        and sandbox_declared
        and isolation_declared
        and prompt_declared
        and session_profiles_declared
        and startup_settle_seconds > 0
    )
    mapping.update(
        {
            "complete": complete,
            "permission_declared": permission_declared,
            "sandbox_disable_declared": sandbox_declared,
            "project_isolation_declared": isolation_declared,
            "prompt_transport_declared": prompt_declared,
            "session_profiles": session_profiles,
            "session_profiles_declared": session_profiles_declared,
            "startup_settle_seconds": startup_settle_seconds,
            "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
            "launch_argv": _regular_launch_argv(
                target, executable["resolved_path"], mapping
            ),
        }
    )
    executable.update(
        version_sha256=sha256_bytes(version),
        help_sha256=sha256_bytes(help_output),
    )
    raw = {
        "schema_version": ADAPTER_MANIFEST_SCHEMA_VERSION,
        "target": target,
        "generated_at": _utc_now(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "executable": executable,
        "execution": execution,
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
    if set(targets) - set(COMMANDS):
        raise ValidationError("target is not on the census allowlist")
    return {
        "schema_version": CENSUS_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "zero_agent": True,
        "session_profiles": {
            target: list(ZERO_AGENT_SESSION_PROFILES[target]) for target in targets
        },
        "session_profiles_declared": ZERO_AGENT_SESSION_PROFILES_DECLARED,
        "startup_settle_seconds": {
            target: ZERO_AGENT_STARTUP_SETTLE_SECONDS[target] for target in targets
        },
        "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
        "manifests": {
            target: census_target(target, adapter_fingerprint).raw for target in targets
        },
    }
