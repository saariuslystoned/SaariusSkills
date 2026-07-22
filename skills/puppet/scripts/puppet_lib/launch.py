"""Closed, value-private launch contexts for Puppet-owned target processes."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Mapping, Sequence, Tuple

from .errors import ValidationError
from .safety import canonical_json_bytes, sha256_bytes, validate_sha256


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
        "cursor": frozenset(),
        "grok": frozenset({"GROK_HOME", "GROK_DISABLE_AUTOUPDATER"}),
    }
)

_RESTRICTED_ENVIRONMENT_NAMES = frozenset({"PWD", "OLDPWD", "TMUX", "TERM"})
_SENSITIVE_NAME_PARTS = ("SECRET", "TOKEN", "KEY", "PASSWORD")
_MAX_ENVIRONMENT_VALUE = 32768


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


def _validate_environment_value(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) > _MAX_ENVIRONMENT_VALUE
        or any(unicodedata.category(character) == "Cc" for character in value)
    ):
        raise ValidationError("launch environment value is invalid")
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
    source_environment: Mapping[str, str],
    bindings: Mapping[str, str],
) -> Dict[str, str]:
    if not isinstance(source_environment, Mapping) or not isinstance(bindings, Mapping):
        raise ValidationError("launch environment source must be a mapping")
    for name in bindings:
        _validate_environment_name(name, allowed=allowed)

    selected: Dict[str, str] = {}
    for name in sorted(allowed):
        if name in bindings:
            selected[name] = _validate_environment_value(bindings[name])
        elif name in source_environment:
            selected[name] = _validate_environment_value(source_environment[name])
    return selected


def control_environment(
    source_environment: Mapping[str, str] | None = None,
) -> Dict[str, str]:
    """Return the complete closed environment for an internal tmux client."""

    source = os.environ if source_environment is None else source_environment
    return _closed_environment(
        allowed=_allowed_environment_names(None),
        source_environment=source,
        bindings={},
    )


def select_launch_environment(
    *,
    target: str,
    source_environment: Mapping[str, str] | None = None,
    bindings: Mapping[str, str] | None = None,
) -> Dict[str, str]:
    """Select one complete target environment from ambient safe names and bindings."""

    source = os.environ if source_environment is None else source_environment
    return _closed_environment(
        allowed=_allowed_environment_names(target),
        source_environment=source,
        bindings={} if bindings is None else bindings,
    )


def validate_launch_environment(
    *, target: str, environment: Mapping[str, str]
) -> Dict[str, str]:
    """Validate a complete environment without consulting ambient process state."""

    if not isinstance(environment, Mapping):
        raise ValidationError("launch environment must be a mapping")
    allowed = _allowed_environment_names(target)
    validated: Dict[str, str] = {}
    for name, value in environment.items():
        normalized = _validate_environment_name(name, allowed=allowed)
        validated[normalized] = _validate_environment_value(value)
    return validated


def validate_subprocess_environment(
    environment: Mapping[str, str],
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
        validated[normalized] = _validate_environment_value(value)
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
            or any(unicodedata.category(character) == "Cc" for character in item)
        ):
            raise ValidationError("launch argv must be a non-empty string list")
        normalized.append(item)
    return normalized


def public_launch_identity(
    *, repo: Path, argv: Sequence[str], environment: Mapping[str, str]
) -> Dict[str, Any]:
    """Return value-free public identity for one already-closed launch context."""

    cwd = str(Path(repo).resolve(strict=True))
    normalized_argv = _validate_argv(argv)
    closed_environment = validate_subprocess_environment(environment)
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
        or any(unicodedata.category(character) == "Cc" for character in cwd)
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
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Build private launch values and their separate value-free public identity."""

    environment = select_launch_environment(
        target=target,
        source_environment=source_environment,
        bindings=bindings,
    )
    return environment, public_launch_identity(
        repo=repo,
        argv=argv,
        environment=environment,
    )
