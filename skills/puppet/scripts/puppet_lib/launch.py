"""Closed, value-private launch contexts for Puppet-owned target processes."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Mapping, Sequence, Tuple

from .errors import IdentityError, ValidationError
from .safety import (
    absolute_root,
    canonical_json_bytes,
    ensure_within,
    sha256_bytes,
    validate_identifier,
    validate_sha256,
)


_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_BASE_ENVIRONMENT_NAMES = frozenset(
    {
        "HOME",
        "PATH",
        "SHELL",
        "USER",
        "LOGNAME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "LC_COLLATE",
        "LC_CTYPE",
        "LC_MESSAGES",
        "LC_MONETARY",
        "LC_NUMERIC",
        "LC_TIME",
        "LC_PAPER",
        "LC_NAME",
        "LC_ADDRESS",
        "LC_TELEPHONE",
        "LC_MEASUREMENT",
        "LC_IDENTIFICATION",
        "SSH_AUTH_SOCK",
    }
)

# These are the only target-specific values Puppet may add to the closed
# baseline. Keep the registry source-owned: descriptors and callers may select
# values for these names, but cannot mint new environment authority.
TARGET_ENVIRONMENT_EXTENSIONS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "agy": frozenset(),
        "codex": frozenset({"CODEX_HOME"}),
        "claude": frozenset({"CLAUDE_CONFIG_DIR", "CLAUDE_CODE_DISABLE_AUTO_MEMORY"}),
        "cursor": frozenset(
            {
                "CURSOR_CONFIG_DIR",
                "CURSOR_DATA_DIR",
                "AGENT_CLI_CREDENTIAL_STORE",
            }
        ),
        "grok": frozenset({"GROK_HOME", "GROK_DISABLE_AUTOUPDATER"}),
    }
)

_RESTRICTED_ENVIRONMENT_NAMES = frozenset({"PWD", "OLDPWD", "TMUX", "TERM"})
_SENSITIVE_NAME_PARTS = ("SECRET", "TOKEN", "KEY", "PASSWORD")
_MAX_ENVIRONMENT_VALUE = 32768
_CONFIG_ROOT_ENVIRONMENT_NAMES = frozenset(
    {
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
        "CURSOR_CONFIG_DIR",
        "CURSOR_DATA_DIR",
        "GROK_HOME",
    }
)
_TRUE_ENVIRONMENT_NAMES = frozenset(
    {"CLAUDE_CODE_DISABLE_AUTO_MEMORY", "GROK_DISABLE_AUTOUPDATER"}
)
_FILE_CREDENTIAL_STORE_ENVIRONMENT_NAMES = frozenset({"AGENT_CLI_CREDENTIAL_STORE"})
_LAUNCH_PLAN_FIELDS = {
    "schema_version",
    "kind",
    "target",
    "session",
    "run_id",
    "cwd",
    "argv",
    "env_names",
    "env_fingerprint",
}


def _validate_environment_name(name: Any, *, allowed: frozenset[str]) -> str:
    if not isinstance(name, str) or not _ENV_NAME_RE.fullmatch(name):
        raise ValidationError("launch environment name is invalid")
    upper = name.upper()
    if (
        name in _RESTRICTED_ENVIRONMENT_NAMES
        or any(part in upper for part in _SENSITIVE_NAME_PARTS)
        or name not in allowed
    ):
        raise ValidationError("launch environment name is not allowlisted")
    return name


def _validate_environment_value(
    name: str,
    value: Any,
    *,
    admitted_lane_root: Path | None = None,
) -> str:
    if (
        not isinstance(value, str)
        or len(value) > _MAX_ENVIRONMENT_VALUE
        or any(unicodedata.category(character).startswith("C") for character in value)
    ):
        raise ValidationError("launch environment value is invalid")
    if name in _TRUE_ENVIRONMENT_NAMES and value != "true":
        raise ValidationError("launch control environment value must be exact true")
    if name in _FILE_CREDENTIAL_STORE_ENVIRONMENT_NAMES and value != "file":
        raise ValidationError(
            "launch credential-store environment value must be exact file"
        )
    if name in _CONFIG_ROOT_ENVIRONMENT_NAMES:
        if admitted_lane_root is None:
            raise ValidationError(
                "launch config root requires an explicitly admitted lane root"
            )
        lane_root = absolute_root(str(admitted_lane_root), "admitted lane root")
        config_root = absolute_root(value, "launch config root")
        return str(ensure_within(config_root, lane_root, must_exist=True))
    return value


def _allowed_environment_names(target: str | None) -> frozenset[str]:
    if target is None:
        return _BASE_ENVIRONMENT_NAMES
    try:
        extensions = TARGET_ENVIRONMENT_EXTENSIONS[target]
    except (KeyError, TypeError) as exc:
        raise ValidationError("unsupported launch target") from exc
    allowed = _BASE_ENVIRONMENT_NAMES | extensions
    for name in allowed:
        _validate_environment_name(name, allowed=allowed)
    return allowed


def _closed_environment(
    *,
    allowed: frozenset[str],
    ambient_allowed: frozenset[str],
    source_environment: Mapping[str, str],
    bindings: Mapping[str, str],
    admitted_lane_root: Path | None = None,
) -> Dict[str, str]:
    if not isinstance(source_environment, Mapping) or not isinstance(bindings, Mapping):
        raise ValidationError("launch environment source must be a mapping")
    for name in bindings:
        _validate_environment_name(name, allowed=allowed)

    selected: Dict[str, str] = {}
    for name in sorted(allowed):
        if name in bindings:
            selected[name] = _validate_environment_value(
                name,
                bindings[name],
                admitted_lane_root=admitted_lane_root,
            )
        elif name in ambient_allowed and name in source_environment:
            selected[name] = _validate_environment_value(
                name,
                source_environment[name],
                admitted_lane_root=admitted_lane_root,
            )
    return selected


def control_environment(
    source_environment: Mapping[str, str] | None = None,
) -> Dict[str, str]:
    """Return the complete closed environment for an internal tmux client."""

    source = os.environ if source_environment is None else source_environment
    return _closed_environment(
        allowed=_allowed_environment_names(None),
        ambient_allowed=_BASE_ENVIRONMENT_NAMES,
        source_environment=source,
        bindings={},
    )


def select_launch_environment(
    *,
    target: str,
    source_environment: Mapping[str, str] | None = None,
    bindings: Mapping[str, str] | None = None,
    admitted_lane_root: Path | None = None,
) -> Dict[str, str]:
    """Select one complete target environment from ambient safe names and bindings."""

    source = os.environ if source_environment is None else source_environment
    allowed = _allowed_environment_names(target)
    extensions = TARGET_ENVIRONMENT_EXTENSIONS[target]
    normalized_bindings = {} if bindings is None else bindings
    for name in normalized_bindings:
        _validate_environment_name(name, allowed=extensions)
    return _closed_environment(
        allowed=allowed,
        ambient_allowed=_BASE_ENVIRONMENT_NAMES,
        source_environment=source,
        bindings=normalized_bindings,
        admitted_lane_root=admitted_lane_root,
    )


def validate_launch_environment(
    *,
    target: str,
    environment: Mapping[str, str],
    admitted_lane_root: Path | None = None,
) -> Dict[str, str]:
    """Validate a complete environment without consulting ambient process state."""

    if not isinstance(environment, Mapping):
        raise ValidationError("launch environment must be a mapping")
    allowed = _allowed_environment_names(target)
    validated: Dict[str, str] = {}
    for name, value in environment.items():
        normalized = _validate_environment_name(name, allowed=allowed)
        validated[normalized] = _validate_environment_value(
            normalized,
            value,
            admitted_lane_root=admitted_lane_root,
        )
    return validated


def validate_subprocess_environment(
    environment: Mapping[str, str],
    *,
    admitted_lane_root: Path | None = None,
) -> Dict[str, str]:
    """Validate a closed tmux-client environment against all source-owned names."""

    if not isinstance(environment, Mapping):
        raise ValidationError("tmux client environment must be a mapping")
    allowed = _BASE_ENVIRONMENT_NAMES | frozenset().union(
        *TARGET_ENVIRONMENT_EXTENSIONS.values()
    )
    validated: Dict[str, str] = {}
    for name, value in environment.items():
        normalized = _validate_environment_name(name, allowed=allowed)
        validated[normalized] = _validate_environment_value(
            normalized,
            value,
            admitted_lane_root=admitted_lane_root,
        )
    return validated


def _validate_argv(argv: Sequence[str]) -> list[str]:
    if (
        isinstance(argv, (str, bytes, bytearray))
        or not isinstance(argv, Sequence)
        or not argv
    ):
        raise ValidationError("launch argv must be a non-empty string list")
    normalized = []
    for item in argv:
        if (
            not isinstance(item, str)
            or not item
            or len(item) > 8192
            or any(
                unicodedata.category(character).startswith("C") for character in item
            )
        ):
            raise ValidationError("launch argv must be a non-empty string list")
        normalized.append(item)
    return normalized


def validate_tmux_launch_argv(argv: Sequence[str]) -> list[str]:
    """Validate argv for tmux's direct-exec, multi-argument command form."""

    normalized = _validate_argv(argv)
    if len(normalized) < 2:
        raise ValidationError(
            "tmux launch argv must contain at least two arguments for direct exec"
        )
    return normalized


def public_launch_identity(
    *,
    repo: Path,
    argv: Sequence[str],
    environment: Mapping[str, str],
    admitted_lane_root: Path | None = None,
) -> Dict[str, Any]:
    """Return value-free public identity for one already-closed launch context."""

    cwd = str(Path(repo).resolve(strict=True))
    normalized_argv = _validate_argv(argv)
    closed_environment = validate_subprocess_environment(
        environment,
        admitted_lane_root=admitted_lane_root,
    )
    environment_names = sorted(closed_environment)
    return {
        "cwd": cwd,
        "argv_sha256": sha256_bytes(canonical_json_bytes(normalized_argv)),
        "env_names": environment_names,
        "env_fingerprint": sha256_bytes(
            canonical_json_bytes(
                [(name, closed_environment[name]) for name in environment_names]
            )
        ),
    }


def validate_public_launch_identity(value: Any, *, target: str) -> Dict[str, Any]:
    """Validate the value-free identity admitted to journals and proof."""

    if not isinstance(value, Mapping) or set(value) != {
        "cwd",
        "argv_sha256",
        "env_names",
        "env_fingerprint",
    }:
        raise ValidationError("launch identity fields are invalid")
    cwd = value.get("cwd")
    if (
        not isinstance(cwd, str)
        or not cwd
        or len(cwd) > 4096
        or not Path(cwd).is_absolute()
        or any(unicodedata.category(character).startswith("C") for character in cwd)
    ):
        raise ValidationError("launch identity cwd is invalid")
    names = value.get("env_names")
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ValidationError("launch identity environment names are invalid")
    if names != sorted(set(names)):
        raise ValidationError("launch identity environment names are invalid")
    allowed = _allowed_environment_names(target)
    for name in names:
        _validate_environment_name(name, allowed=allowed)
    return {
        "cwd": cwd,
        "argv_sha256": validate_sha256(
            value.get("argv_sha256"), "launch identity argv_sha256"
        ),
        "env_names": names,
        "env_fingerprint": validate_sha256(
            value.get("env_fingerprint"), "launch identity env_fingerprint"
        ),
    }


def build_launch_identity(
    *,
    target: str,
    repo: Path,
    argv: Sequence[str],
    source_environment: Mapping[str, str] | None = None,
    bindings: Mapping[str, str] | None = None,
    admitted_lane_root: Path | None = None,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Build private launch values and their separate value-free public identity."""

    normalized_argv = validate_tmux_launch_argv(argv)
    environment = select_launch_environment(
        target=target,
        source_environment=source_environment,
        bindings=bindings,
        admitted_lane_root=admitted_lane_root,
    )
    return environment, public_launch_identity(
        repo=repo,
        argv=normalized_argv,
        environment=environment,
        admitted_lane_root=admitted_lane_root,
    )


def build_admitted_launch_plan(
    *,
    target: str,
    session: str,
    run_id: str,
    repo: Path,
    argv: Sequence[str],
    environment: Mapping[str, str],
    admitted_lane_root: Path | None = None,
) -> Dict[str, Any]:
    """Build the value-private plan that must exist before lease admission."""

    _allowed_environment_names(target)
    validate_identifier(session, "launch plan session")
    validate_identifier(run_id, "launch plan run id")
    normalized_argv = validate_tmux_launch_argv(argv)
    normalized_environment = validate_launch_environment(
        target=target,
        environment=environment,
        admitted_lane_root=admitted_lane_root,
    )
    identity = public_launch_identity(
        repo=repo,
        argv=normalized_argv,
        environment=normalized_environment,
        admitted_lane_root=admitted_lane_root,
    )
    return {
        "schema_version": 1,
        "kind": "puppet.admitted-launch-plan/v1",
        "target": target,
        "session": session,
        "run_id": run_id,
        "cwd": identity["cwd"],
        "argv": normalized_argv,
        "env_names": identity["env_names"],
        "env_fingerprint": identity["env_fingerprint"],
    }


def validate_admitted_launch_plan(
    value: Any,
    *,
    expected_target: str | None = None,
    expected_session: str | None = None,
    expected_run_id: str | None = None,
) -> Dict[str, Any]:
    """Validate an admitted plan and derive its exact public launch identity."""

    if (
        not isinstance(value, Mapping)
        or set(value) != _LAUNCH_PLAN_FIELDS
        or value.get("schema_version") != 1
        or value.get("kind") != "puppet.admitted-launch-plan/v1"
    ):
        raise ValidationError("admitted launch plan fields are invalid")
    target = value.get("target")
    _allowed_environment_names(target)
    session = validate_identifier(value.get("session"), "launch plan session")
    run_id = validate_identifier(value.get("run_id"), "launch plan run id")
    if expected_target is not None and target != expected_target:
        raise IdentityError("admitted launch plan target is unexpected")
    if expected_session is not None and session != expected_session:
        raise IdentityError("admitted launch plan session is unexpected")
    if expected_run_id is not None and run_id != expected_run_id:
        raise IdentityError("admitted launch plan run id is unexpected")
    cwd_value = value.get("cwd")
    cwd = absolute_root(cwd_value, "admitted launch plan cwd")
    argv = validate_tmux_launch_argv(value.get("argv"))
    names = value.get("env_names")
    if (
        not isinstance(names, list)
        or not all(isinstance(name, str) for name in names)
        or names != sorted(set(names))
    ):
        raise ValidationError("admitted launch plan environment names are invalid")
    allowed = _allowed_environment_names(target)
    for name in names:
        _validate_environment_name(name, allowed=allowed)
    fingerprint = validate_sha256(
        value.get("env_fingerprint"),
        "admitted launch plan environment fingerprint",
    )
    plan = dict(value)
    plan["cwd"] = str(cwd)
    plan["argv"] = argv
    plan["env_names"] = names
    plan["env_fingerprint"] = fingerprint
    plan["launch_identity"] = {
        "cwd": str(cwd),
        "argv_sha256": sha256_bytes(canonical_json_bytes(argv)),
        "env_names": names,
        "env_fingerprint": fingerprint,
    }
    return plan
