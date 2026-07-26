"""Private subscription-profile bootstrap and body-free auth census.

Puppet never copies an existing credential or performs login on behalf of the
operator. It creates a namespaced profile and emits an execution-time-validated
helper command that the human may choose to run.
"""

from __future__ import annotations

import json
import os
import pwd
import selectors
import shlex
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from .adapter_manifest import (
    execution_file_identity,
    validate_execution_file_identity,
)
from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .safety import (
    canonical_json_bytes,
    exclusive_lock,
    read_json,
    sha256_bytes,
    validate_identifier,
)


PROFILE_SCHEMA = "puppet.subscription-profile/v1"
STATUS_SCHEMA = "puppet.subscription-profile-status/v1"
PROFILE_REUSE_SCOPE = "durable_cross_run"
PROFILE_STATUS_POLICY = "silent_before_each_launch"
PROFILE_HUMAN_LOGIN_POLICY = "initial_enrollment_or_provider_invalidation_only"
PROFILE_OPERATOR_GLOBAL_ADOPTION = "not_yet_qualified"
MAX_STATUS_OUTPUT_BYTES = 16384
STATUS_TIMEOUT_SECONDS = 20
LAUNCH_BINDING_SCHEMA = "puppet.subscription-launch-binding/v1"
CLAUDE_NATIVE_KEYRING_AUTH_ROUTE = "operating_system_native_keyring"
SYNTHETIC_PROFILE_HOME_AUTH_ROUTE = "synthetic_profile_home"
CLAUDE_LEGACY_PROFILE_MIGRATION_BLOCKER = (
    "claude_synthetic_home_profile_migration_required"
)

_BASE_LAUNCH_ENVIRONMENT_NAMES = frozenset({"HOME", "TMPDIR", "PATH", "LANG", "LC_ALL"})
_LOGIN_ONLY_ENVIRONMENT_NAMES = frozenset({"NO_OPEN_BROWSER"})
_DIRECTORY_IDENTITY_FIELDS = {"path", "device", "inode", "uid", "mode"}
_PUBLIC_BINDING_FIELDS = {
    "schema",
    "target",
    "profile_root",
    "root_identity",
    "directory_identities",
    "real_home_identity",
    "auth_route",
    "manifest_path",
    "manifest_sha256",
    "executable",
    "launch_env_names",
    "login_only_env_names",
    "status",
}

_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "target",
        "root",
        "directories",
        "requested_executable",
        "executable",
        "helper",
        "interpreter",
        "library",
        "env_executable",
        "bindings",
        "commands",
        "auth_route",
        "real_home",
    }
)
_LEGACY_MANIFEST_FIELDS = _MANIFEST_FIELDS - {"auth_route", "real_home"}

_PROFILE_LAYOUTS: Mapping[str, tuple[str, ...]] = {
    "codex": ("home", "config", "tmp"),
    "claude": ("home", "config", "tmp"),
    "cursor": ("home", "config", "data", "tmp"),
    "grok": ("home", "config", "tmp"),
}


@dataclass(frozen=True)
class SubscriptionLaunchContext:
    """Exact private profile values separated from body-free public binding."""

    target: str
    profile_root: Path
    manifest_path: Path
    manifest_sha256: str
    executable: Mapping[str, Any]
    source_environment: Mapping[str, str] = field(repr=False)
    bindings: Mapping[str, str] = field(repr=False)
    public_binding: Mapping[str, Any]


def _private_directory(path: Path, *, label: str, create: bool) -> Dict[str, Any]:
    path = Path(path)
    if not path.is_absolute():
        raise ValidationError("%s must be absolute" % label)
    if path.exists() and path.is_symlink():
        raise ValidationError("%s must not be a symlink" % label)
    if not path.exists():
        if not create:
            raise ValidationError("%s does not exist" % label)
        try:
            path.mkdir(mode=0o700)
            os.chmod(path, 0o700)
        except FileExistsError as exc:
            raise ConflictError("%s creation raced" % label) from exc
        except OSError as exc:
            raise ValidationError("unable to create %s" % label) from exc
    try:
        resolved = path.resolve(strict=True)
        details = resolved.stat()
    except OSError as exc:
        raise ValidationError("unable to inspect %s" % label) from exc
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) != 0o700
    ):
        raise ValidationError("%s is not a user-owned mode-0700 directory" % label)
    return {
        "path": str(resolved),
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "mode": stat.S_IMODE(details.st_mode),
    }


def _resolve_executable(path: Path) -> tuple[str, Dict[str, Any]]:
    requested = Path(path)
    if not requested.is_absolute():
        raise ValidationError("profile executable must be absolute")
    try:
        resolved = requested.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValidationError("profile executable is unavailable") from exc
    return str(requested), execution_file_identity(resolved)


def _auth_route_for_target(target: str) -> str:
    if target == "claude":
        return CLAUDE_NATIVE_KEYRING_AUTH_ROUTE
    return SYNTHETIC_PROFILE_HOME_AUTH_ROUTE


def _real_user_home_identity(*, label: str) -> Dict[str, Any]:
    entry = pwd.getpwuid(os.getuid())
    path = Path(entry.pw_dir)
    if not path.is_absolute():
        raise ValidationError("%s must be absolute" % label)
    if path.is_symlink():
        raise ValidationError("%s must not be a symlink" % label)
    try:
        resolved = path.resolve(strict=True)
        details = resolved.stat()
    except OSError as exc:
        raise ValidationError("unable to inspect %s" % label) from exc
    if not stat.S_ISDIR(details.st_mode):
        raise ValidationError("%s is not a directory" % label)
    if details.st_uid != os.getuid():
        raise ValidationError("%s is not owned by the current user" % label)
    return {
        "path": str(resolved),
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "mode": stat.S_IMODE(details.st_mode),
    }


def _expected_real_home_identity(
    target: str, directories: Mapping[str, Dict[str, Any]]
) -> Dict[str, Any]:
    if target == "claude":
        return _real_user_home_identity(label="real user home")
    return dict(directories["home"])


def _is_legacy_claude_manifest(value: Mapping[str, Any]) -> bool:
    if value.get("target") != "claude":
        return False
    keys = set(value)
    if keys == _LEGACY_MANIFEST_FIELDS:
        return True
    if keys != _MANIFEST_FIELDS:
        return False
    if value.get("auth_route") != CLAUDE_NATIVE_KEYRING_AUTH_ROUTE:
        return True
    bindings = value.get("bindings")
    directories = value.get("directories")
    if not isinstance(bindings, Mapping) or not isinstance(directories, Mapping):
        return False
    home_dir = directories.get("home")
    if isinstance(home_dir, Mapping) and bindings.get("HOME") == home_dir.get("path"):
        return True
    real_home = value.get("real_home")
    if isinstance(real_home, Mapping) and isinstance(home_dir, Mapping):
        if real_home.get("path") == home_dir.get("path"):
            return True
    return False


def _coerce_manifest(
    value: Any, *, allow_legacy_claude_refresh: bool = False
) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("subscription profile manifest fields are invalid")
    keys = set(value)
    if keys == _MANIFEST_FIELDS:
        return dict(value)
    if keys != _LEGACY_MANIFEST_FIELDS:
        raise ValidationError("subscription profile manifest fields are invalid")
    target = validate_identifier(value.get("target"), "profile target")
    if target == "claude":
        if allow_legacy_claude_refresh:
            return dict(value)
        raise UnsupportedError(CLAUDE_LEGACY_PROFILE_MIGRATION_BLOCKER)
    directories = value.get("directories")
    if not isinstance(directories, dict) or "home" not in directories:
        raise ValidationError("subscription profile directory map is invalid")
    home = directories.get("home")
    if not isinstance(home, dict):
        raise ValidationError("subscription profile directory identity is invalid")
    return {
        **dict(value),
        "auth_route": SYNTHETIC_PROFILE_HOME_AUTH_ROUTE,
        "real_home": dict(home),
    }


def _profile_environment(
    target: str,
    directories: Mapping[str, Dict[str, Any]],
    *,
    real_home: Mapping[str, Any],
) -> Dict[str, str]:
    values = {
        "HOME": str(real_home["path"]),
        "TMPDIR": directories["tmp"]["path"],
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
    }
    if target == "codex":
        values["CODEX_HOME"] = directories["config"]["path"]
    elif target == "claude":
        values["CLAUDE_CONFIG_DIR"] = directories["config"]["path"]
        values["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    elif target == "cursor":
        values["CURSOR_CONFIG_DIR"] = directories["config"]["path"]
        values["CURSOR_DATA_DIR"] = directories["data"]["path"]
        values["AGENT_CLI_CREDENTIAL_STORE"] = "file"
        values["NO_OPEN_BROWSER"] = "1"
    elif target == "grok":
        values["GROK_HOME"] = directories["config"]["path"]
        values["GROK_DISABLE_AUTOUPDATER"] = "true"
    else:  # pragma: no cover - target validation owns this branch
        raise UnsupportedError("subscription profile target is unsupported")
    return values


def _profile_commands(target: str, executable: str) -> Dict[str, list[str]]:
    if target == "codex":
        return {
            "login": [executable, "login", "--device-auth"],
            "status": [executable, "login", "status"],
        }
    if target == "claude":
        return {
            "login": [executable, "auth", "login"],
            "status": [executable, "auth", "status"],
        }
    if target == "cursor":
        return {
            "login": [executable, "login"],
            "status": [executable, "status", "--format", "json"],
        }
    if target == "grok":
        return {
            "login": [executable, "login", "--device-auth"],
            "status": [executable, "models"],
        }
    raise UnsupportedError("subscription profile target is unsupported")


def _default_login_helper() -> Path:
    return Path(__file__).resolve(strict=True).parents[1] / "profile_login.py"


def _manifest_public(value: Mapping[str, Any]) -> Dict[str, Any]:
    clean_helper_environment = [
        "HOME=" + value["bindings"]["HOME"],
        "TMPDIR=" + value["bindings"]["TMPDIR"],
        "PATH=/usr/bin:/bin",
        "LANG=C",
        "LC_ALL=C",
    ]
    return {
        **dict(value),
        "login_command": shlex.join(
            [
                value["env_executable"]["path"],
                "-i",
                *clean_helper_environment,
                value["interpreter"]["path"],
                "-E",
                "-s",
                "-S",
                "-B",
                value["helper"]["path"],
                "--profile-root",
                value["root"]["path"],
            ]
        ),
        "manifest_sha256": sha256_bytes(canonical_json_bytes(value)),
        "reuse_scope": PROFILE_REUSE_SCOPE,
        "status_policy": PROFILE_STATUS_POLICY,
        "human_login_policy": PROFILE_HUMAN_LOGIN_POLICY,
        "operator_global_adoption": PROFILE_OPERATOR_GLOBAL_ADOPTION,
        "login_performed": False,
        "account_change_authorized": False,
    }


def _validate_manifest(
    value: Any,
    *,
    verify_current: bool = True,
    allow_stale_launch_authority: bool = False,
    allow_legacy_claude_refresh: bool = False,
) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("subscription profile manifest fields are invalid")
    if allow_legacy_claude_refresh and _is_legacy_claude_manifest(value):
        return _validate_legacy_claude_manifest(
            value,
            verify_current=verify_current,
            allow_stale_launch_authority=allow_stale_launch_authority,
        )
    value = _coerce_manifest(
        value, allow_legacy_claude_refresh=allow_legacy_claude_refresh
    )
    if set(value) != _MANIFEST_FIELDS:
        raise ValidationError("subscription profile manifest fields are invalid")
    if value.get("schema") != PROFILE_SCHEMA:
        raise ValidationError("subscription profile schema is unsupported")
    target = validate_identifier(value.get("target"), "profile target")
    if target not in _PROFILE_LAYOUTS:
        raise UnsupportedError("subscription profile target is unsupported")

    recorded_root = value.get("root")
    if not isinstance(recorded_root, dict):
        raise ValidationError("subscription profile root identity is invalid")
    root = _private_directory(
        Path(recorded_root.get("path", "")), label="profile root", create=False
    )
    if root != recorded_root:
        raise IdentityError("subscription profile root identity changed")

    directories = value.get("directories")
    if not isinstance(directories, dict) or set(directories) != set(
        _PROFILE_LAYOUTS[target]
    ):
        raise ValidationError("subscription profile directory map is invalid")
    checked_directories: Dict[str, Dict[str, Any]] = {}
    for name in _PROFILE_LAYOUTS[target]:
        recorded = directories.get(name)
        if not isinstance(recorded, dict):
            raise ValidationError("subscription profile directory identity is invalid")
        current = _private_directory(
            Path(recorded.get("path", "")),
            label="profile %s directory" % name,
            create=False,
        )
        if current != recorded:
            raise IdentityError("subscription profile directory identity changed")
        if Path(current["path"]) != Path(root["path"]) / name:
            raise IdentityError("subscription profile directory path changed")
        checked_directories[name] = current

    executable = validate_execution_file_identity(
        value.get("executable"), "profile executable", verify_current=verify_current
    )
    requested = value.get("requested_executable")
    if (
        not isinstance(requested, str)
        or not requested
        or not Path(requested).is_absolute()
    ):
        raise ValidationError("subscription profile requested executable is invalid")
    if not allow_stale_launch_authority:
        try:
            if Path(requested).resolve(strict=True) != Path(executable["path"]):
                raise IdentityError("subscription profile executable path changed")
        except (OSError, RuntimeError) as exc:
            raise IdentityError(
                "subscription profile executable is unavailable"
            ) from exc

    helper = validate_execution_file_identity(
        value.get("helper"), "profile login helper", verify_current=verify_current
    )
    interpreter = validate_execution_file_identity(
        value.get("interpreter"),
        "profile login interpreter",
        verify_current=verify_current,
    )
    library = validate_execution_file_identity(
        value.get("library"), "profile login library", verify_current=verify_current
    )
    env_executable = validate_execution_file_identity(
        value.get("env_executable"),
        "profile login environment executable",
        verify_current=verify_current,
    )
    auth_route = value.get("auth_route")
    expected_auth_route = _auth_route_for_target(target)
    if auth_route != expected_auth_route:
        raise IdentityError("subscription profile auth route changed")
    recorded_real_home = value.get("real_home")
    if not isinstance(recorded_real_home, dict):
        raise ValidationError("subscription profile real home identity is invalid")
    real_home = _validate_recorded_real_home(
        recorded_real_home, label="subscription profile real home"
    )
    expected_real_home = _expected_real_home_identity(target, checked_directories)
    if real_home != expected_real_home:
        raise IdentityError("subscription profile real home identity changed")
    if target == "claude" and real_home["path"] == checked_directories["home"]["path"]:
        raise UnsupportedError(CLAUDE_LEGACY_PROFILE_MIGRATION_BLOCKER)
    bindings = _profile_environment(
        target, checked_directories, real_home=real_home
    )
    if value.get("bindings") != bindings:
        raise IdentityError("subscription profile bindings changed")
    commands = _profile_commands(target, executable["path"])
    if value.get("commands") != commands:
        raise IdentityError("subscription profile commands changed")
    return {
        **dict(value),
        "root": root,
        "directories": checked_directories,
        "executable": executable,
        "helper": helper,
        "interpreter": interpreter,
        "library": library,
        "env_executable": env_executable,
        "auth_route": auth_route,
        "real_home": real_home,
    }


def _validate_legacy_claude_manifest(
    value: Mapping[str, Any],
    *,
    verify_current: bool = True,
    allow_stale_launch_authority: bool = False,
) -> Dict[str, Any]:
    if not _is_legacy_claude_manifest(value):
        raise ValidationError("subscription profile manifest fields are invalid")
    target = validate_identifier(value.get("target"), "profile target")
    if target != "claude":
        raise ValidationError("subscription profile manifest fields are invalid")

    recorded_root = value.get("root")
    if not isinstance(recorded_root, dict):
        raise ValidationError("subscription profile root identity is invalid")
    root = _private_directory(
        Path(recorded_root.get("path", "")), label="profile root", create=False
    )
    if root != recorded_root:
        raise IdentityError("subscription profile root identity changed")

    directories = value.get("directories")
    if not isinstance(directories, dict) or set(directories) != set(
        _PROFILE_LAYOUTS[target]
    ):
        raise ValidationError("subscription profile directory map is invalid")
    checked_directories: Dict[str, Dict[str, Any]] = {}
    for name in _PROFILE_LAYOUTS[target]:
        recorded = directories.get(name)
        if not isinstance(recorded, dict):
            raise ValidationError("subscription profile directory identity is invalid")
        current = _private_directory(
            Path(recorded.get("path", "")),
            label="profile %s directory" % name,
            create=False,
        )
        if current != recorded:
            raise IdentityError("subscription profile directory identity changed")
        if Path(current["path"]) != Path(root["path"]) / name:
            raise IdentityError("subscription profile directory path changed")
        checked_directories[name] = current

    executable = validate_execution_file_identity(
        value.get("executable"), "profile executable", verify_current=verify_current
    )
    requested = value.get("requested_executable")
    if (
        not isinstance(requested, str)
        or not requested
        or not Path(requested).is_absolute()
    ):
        raise ValidationError("subscription profile requested executable is invalid")
    if not allow_stale_launch_authority:
        try:
            if Path(requested).resolve(strict=True) != Path(executable["path"]):
                raise IdentityError("subscription profile executable path changed")
        except (OSError, RuntimeError) as exc:
            raise IdentityError(
                "subscription profile executable is unavailable"
            ) from exc

    helper = validate_execution_file_identity(
        value.get("helper"), "profile login helper", verify_current=verify_current
    )
    interpreter = validate_execution_file_identity(
        value.get("interpreter"),
        "profile login interpreter",
        verify_current=verify_current,
    )
    library = validate_execution_file_identity(
        value.get("library"), "profile login library", verify_current=verify_current
    )
    env_executable = validate_execution_file_identity(
        value.get("env_executable"),
        "profile login environment executable",
        verify_current=verify_current,
    )
    commands = _profile_commands(target, executable["path"])
    if value.get("commands") != commands:
        raise IdentityError("subscription profile commands changed")
    return {
        **dict(value),
        "root": root,
        "directories": checked_directories,
        "executable": executable,
        "helper": helper,
        "interpreter": interpreter,
        "library": library,
        "env_executable": env_executable,
    }


def _write_create_only(path: Path, value: Dict[str, Any]) -> None:
    """Publish a fully durable manifest atomically without overwriting."""

    payload = canonical_json_bytes(value) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".%s." % path.name, dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        try:
            os.fchmod(descriptor, 0o600)
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise OSError("short subscription profile manifest write")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        details = temporary.stat()
        if (
            not stat.S_ISREG(details.st_mode)
            or stat.S_IMODE(details.st_mode) != 0o600
            or details.st_nlink != 1
        ):
            raise IdentityError("subscription profile temporary manifest is invalid")
        try:
            os.link(str(temporary), str(path), follow_symlinks=False)
        except FileExistsError as exc:
            raise ConflictError("subscription profile manifest already exists") from exc
        parent_descriptor = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _write_replace(path: Path, value: Dict[str, Any]) -> None:
    """Atomically refresh non-secret launch authority for an owned profile."""

    payload = canonical_json_bytes(value) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".%s." % path.name, dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        try:
            os.fchmod(descriptor, 0o600)
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise OSError("short subscription profile manifest write")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        details = temporary.stat()
        if (
            not stat.S_ISREG(details.st_mode)
            or stat.S_IMODE(details.st_mode) != 0o600
            or details.st_nlink != 1
        ):
            raise IdentityError("subscription profile temporary manifest is invalid")
        os.replace(str(temporary), str(path))
        parent_descriptor = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _new_profile_root(path: Path) -> Dict[str, Any]:
    if not path.is_absolute():
        raise ValidationError("profile root must be absolute")
    if not path.parent.is_dir():
        raise ValidationError("profile root parent must exist")
    if path.exists() or path.is_symlink():
        raise ConflictError("subscription profile root already exists")
    return _private_directory(path, label="profile root", create=True)


def initialize_subscription_profile(
    *,
    target: str,
    profile_root: Path | str,
    executable_path: Path | str,
    helper_path: Path | str | None = None,
    interpreter_path: Path | str | None = None,
) -> Dict[str, Any]:
    """Create or rejoin one private profile without performing login."""

    target = validate_identifier(target, "profile target")
    if target == "agy":
        raise UnsupportedError(
            "AGY exposes no proved authentication-preserving private config-root selector"
        )
    if target not in _PROFILE_LAYOUTS:
        raise UnsupportedError("subscription profile target is unsupported")
    root_path = Path(profile_root)
    if not root_path.is_absolute() or not root_path.parent.is_dir():
        raise ValidationError("profile root must be absolute with an existing parent")

    requested, executable = _resolve_executable(Path(executable_path))
    helper = execution_file_identity(
        Path(_default_login_helper() if helper_path is None else helper_path).resolve(
            strict=True
        )
    )
    interpreter = execution_file_identity(
        Path(sys.executable if interpreter_path is None else interpreter_path).resolve(
            strict=True
        )
    )
    library = execution_file_identity(Path(__file__).resolve(strict=True))
    env_executable = execution_file_identity(Path("/usr/bin/env"))
    manifest_path = root_path / "profile.json"
    if root_path.exists():
        # Validate ownership before creating even a lock file. Empty or
        # malformed pre-existing roots are never implicitly adopted.
        if root_path.is_symlink() or not manifest_path.is_file():
            raise ConflictError("pre-existing subscription profile is not owned")
        preflight = _validate_manifest(
            read_json(manifest_path),
            verify_current=False,
            allow_stale_launch_authority=True,
            allow_legacy_claude_refresh=True,
        )
        root_path = Path(preflight["root"]["path"])
        manifest_path = root_path / "profile.json"
    else:
        root = _new_profile_root(root_path)
        root_path = Path(root["path"])
        manifest_path = root_path / "profile.json"

    lock_path = root_path / ".profile-init.lock"
    with exclusive_lock(lock_path):
        if manifest_path.exists():
            previous = _validate_manifest(
                read_json(manifest_path),
                verify_current=False,
                allow_stale_launch_authority=True,
                allow_legacy_claude_refresh=True,
            )
            if previous["target"] != target:
                raise ConflictError("subscription profile belongs to another target")
            root = previous["root"]
            directories = previous["directories"]
        else:
            previous = None
            if any(entry.name != lock_path.name for entry in root_path.iterdir()):
                raise ConflictError(
                    "unowned content exists in subscription profile root"
                )
            directories = {
                name: _private_directory(
                    root_path / name,
                    label="profile %s directory" % name,
                    create=True,
                )
                for name in _PROFILE_LAYOUTS[target]
            }
        bindings = _profile_environment(
            target,
            directories,
            real_home=_expected_real_home_identity(target, directories),
        )
        manifest = {
            "schema": PROFILE_SCHEMA,
            "target": target,
            "root": root,
            "directories": directories,
            "requested_executable": requested,
            "executable": executable,
            "helper": helper,
            "interpreter": interpreter,
            "library": library,
            "env_executable": env_executable,
            "bindings": bindings,
            "commands": _profile_commands(target, executable["path"]),
            "auth_route": _auth_route_for_target(target),
            "real_home": _expected_real_home_identity(target, directories),
        }
        if previous is None:
            _write_create_only(manifest_path, manifest)
        elif manifest != previous:
            _write_replace(manifest_path, manifest)
        manifest = _validate_manifest(manifest, verify_current=True)
        return _manifest_public(manifest)


def _bounded_status_run(
    argv: Sequence[str], *, environment: Mapping[str, str], cwd: Path
) -> subprocess.CompletedProcess[bytes]:
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    output = bytearray()
    try:
        process = subprocess.Popen(
            list(argv),
            cwd=str(cwd),
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if process.stdout is None:  # pragma: no cover - PIPE guarantees this
            raise ValidationError("subscription profile status pipe is unavailable")
        os.set_blocking(process.stdout.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + STATUS_TIMEOUT_SECONDS
        eof = False
        while not eof:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(list(argv), STATUS_TIMEOUT_SECONDS)
            ready = selector.select(min(remaining, 0.25))
            if not ready and process.poll() is not None:
                ready = selector.select(0)
                if not ready:
                    break
            for key, _mask in ready:
                try:
                    block = os.read(key.fileobj.fileno(), 4096)
                except BlockingIOError:
                    continue
                if not block:
                    eof = True
                    break
                output.extend(block)
                if len(output) > MAX_STATUS_OUTPUT_BYTES:
                    raise ValidationError(
                        "subscription profile status output exceeds the cap"
                    )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(list(argv), STATUS_TIMEOUT_SECONDS)
        returncode = process.wait(timeout=remaining)
        return subprocess.CompletedProcess(
            list(argv), returncode, stdout=bytes(output), stderr=None
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError("subscription profile status command failed") from exc
    finally:
        if selector is not None:
            selector.close()
        if process is not None:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdout is not None:
                process.stdout.close()


def _parse_status(
    target: str, result: subprocess.CompletedProcess[bytes]
) -> Dict[str, Any]:
    try:
        text = result.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(
            "subscription profile status output is not UTF-8"
        ) from exc
    normalized = text.strip()
    if target == "codex":
        lines = {line.strip() for line in normalized.splitlines()}
        if result.returncode == 0 and "Logged in using ChatGPT" in lines:
            return {"login_state": "logged_in", "method": "chatgpt"}
        if "Not logged in" in lines:
            return {"login_state": "logged_out", "method": "none"}
    elif target == "claude":
        try:
            value = json.loads(normalized)
        except json.JSONDecodeError:
            value = None
        if (
            isinstance(value, dict)
            and set(value) == {"loggedIn", "authMethod", "apiProvider"}
            and isinstance(value.get("loggedIn"), bool)
        ):
            method = value.get("authMethod")
            provider = value.get("apiProvider")
            return {
                "login_state": (
                    "logged_in"
                    if value["loggedIn"] and result.returncode == 0
                    else "logged_out"
                    if not value["loggedIn"]
                    else "unknown"
                ),
                "method": method if method in {"claude.ai", "none"} else "other",
                "provider": provider if provider in {"firstParty"} else "other",
            }
    elif target == "cursor":
        try:
            value = json.loads(normalized)
        except json.JSONDecodeError:
            value = None
        if (
            isinstance(value, dict)
            and isinstance(value.get("isAuthenticated"), bool)
            and value.get("status") in {"authenticated", "unauthenticated"}
        ):
            return {
                "login_state": (
                    "logged_in"
                    if value["isAuthenticated"] and result.returncode == 0
                    else "logged_out"
                    if not value["isAuthenticated"]
                    else "unknown"
                ),
                "method": "private_file_store",
            }
    elif target == "grok":
        state = (
            "logged_out"
            if "You are not authenticated" in normalized
            or "No auth credentials" in normalized
            else "logged_in"
            if result.returncode == 0 and "Available models:" in normalized
            else "unknown"
        )
        default_model = (
            "grok-4.5" if "Default model: grok-4.5" in normalized else "unknown"
        )
        return {
            "login_state": state,
            "method": "private_grok_home",
            "default_model": default_model,
        }
    return {"login_state": "unknown", "method": "unknown"}


def subscription_profile_status(*, profile_root: Path | str) -> Dict[str, Any]:
    """Run one target-native status command and discard its raw output."""

    root = _private_directory(Path(profile_root), label="profile root", create=False)
    manifest_path = Path(root["path"]) / "profile.json"
    manifest = _validate_manifest(read_json(manifest_path), verify_current=True)
    lock_path = Path(manifest["root"]["path"]) / ".profile-init.lock"
    with exclusive_lock(lock_path):
        manifest = _validate_manifest(read_json(manifest_path), verify_current=True)
        result = _bounded_status_run(
            manifest["commands"]["status"],
            environment=manifest["bindings"],
            cwd=Path(manifest["root"]["path"]),
        )
    return _public_status(manifest, result)


def _public_status(
    manifest: Mapping[str, Any], result: subprocess.CompletedProcess[bytes]
) -> Dict[str, Any]:
    """Reduce native status output to the allowlisted body-free schema."""

    parsed = _parse_status(manifest["target"], result)
    return {
        "schema": STATUS_SCHEMA,
        "target": manifest["target"],
        "profile_root": manifest["root"]["path"],
        "executable": manifest["executable"],
        "auth_route": manifest["auth_route"],
        "login_state": parsed["login_state"],
        "method": parsed["method"],
        **({"provider": parsed["provider"]} if "provider" in parsed else {}),
        **(
            {"default_model": parsed["default_model"]}
            if "default_model" in parsed
            else {}
        ),
        "status_exit": result.returncode,
        "reuse_scope": PROFILE_REUSE_SCOPE,
        "status_policy": PROFILE_STATUS_POLICY,
        "human_login_policy": PROFILE_HUMAN_LOGIN_POLICY,
        "raw_output_retained": False,
        "login_performed": False,
        "model_launched": False,
    }


def _launch_context_from_manifest(
    *,
    manifest: Dict[str, Any],
    manifest_path: Path,
    expected_target: str,
    expected_executable_path: Path | str,
) -> SubscriptionLaunchContext:
    if manifest["target"] != expected_target:
        raise IdentityError("subscription profile target does not match adapter")
    try:
        resolved_expected_executable = Path(expected_executable_path).resolve(
            strict=True
        )
    except (OSError, RuntimeError) as exc:
        raise ValidationError(
            "expected subscription profile executable is unavailable"
        ) from exc
    expected_executable = execution_file_identity(resolved_expected_executable)
    if manifest["executable"] != expected_executable:
        raise IdentityError("subscription profile executable does not match adapter")
    manifest_sha256 = sha256_bytes(canonical_json_bytes(manifest))
    source_environment = {
        name: manifest["bindings"][name]
        for name in sorted(_BASE_LAUNCH_ENVIRONMENT_NAMES)
    }
    bindings = {
        name: value
        for name, value in manifest["bindings"].items()
        if name not in _BASE_LAUNCH_ENVIRONMENT_NAMES
        and name not in _LOGIN_ONLY_ENVIRONMENT_NAMES
    }
    public_binding = {
        "schema": LAUNCH_BINDING_SCHEMA,
        "target": manifest["target"],
        "profile_root": manifest["root"]["path"],
        "root_identity": manifest["root"],
        "directory_identities": manifest["directories"],
        "real_home_identity": manifest["real_home"],
        "auth_route": manifest["auth_route"],
        "manifest_path": str(manifest_path.resolve(strict=True)),
        "manifest_sha256": manifest_sha256,
        "executable": manifest["executable"],
        "launch_env_names": sorted([*source_environment.keys(), *bindings.keys()]),
        "login_only_env_names": sorted(
            name
            for name in manifest["bindings"]
            if name in _LOGIN_ONLY_ENVIRONMENT_NAMES
        ),
    }
    return SubscriptionLaunchContext(
        target=manifest["target"],
        profile_root=Path(manifest["root"]["path"]),
        manifest_path=manifest_path.resolve(strict=True),
        manifest_sha256=manifest_sha256,
        executable=manifest["executable"],
        source_environment=source_environment,
        bindings=bindings,
        public_binding=public_binding,
    )


def subscription_profile_launch_context(
    *,
    profile_root: Path | str,
    expected_target: str,
    expected_executable_path: Path | str,
) -> SubscriptionLaunchContext:
    """Revalidate one profile and return its exact closed launch context."""

    expected_target = validate_identifier(expected_target, "profile target")
    root = _private_directory(Path(profile_root), label="profile root", create=False)
    manifest_path = Path(root["path"]) / "profile.json"
    lock_path = Path(root["path"]) / ".profile-init.lock"
    with exclusive_lock(lock_path):
        manifest = _validate_manifest(read_json(manifest_path), verify_current=True)
        return _launch_context_from_manifest(
            manifest=manifest,
            manifest_path=manifest_path,
            expected_target=expected_target,
            expected_executable_path=expected_executable_path,
        )


def subscription_profile_preflight(
    *,
    profile_root: Path | str,
    expected_target: str,
    expected_executable_path: Path | str,
) -> tuple[SubscriptionLaunchContext, Dict[str, Any]]:
    """Atomically bind one launch context to its native auth status sample."""

    expected_target = validate_identifier(expected_target, "profile target")
    root = _private_directory(Path(profile_root), label="profile root", create=False)
    manifest_path = Path(root["path"]) / "profile.json"
    lock_path = Path(root["path"]) / ".profile-init.lock"
    with exclusive_lock(lock_path):
        manifest = _validate_manifest(read_json(manifest_path), verify_current=True)
        context = _launch_context_from_manifest(
            manifest=manifest,
            manifest_path=manifest_path,
            expected_target=expected_target,
            expected_executable_path=expected_executable_path,
        )
        result = _bounded_status_run(
            manifest["commands"]["status"],
            environment=manifest["bindings"],
            cwd=Path(manifest["root"]["path"]),
        )
        return context, _public_status(manifest, result)


def build_subscription_launch_binding(
    context: SubscriptionLaunchContext, status: Mapping[str, Any]
) -> Dict[str, Any]:
    """Build the body-free proof binding for one sampled launch preflight."""

    public_status = {
        name: status[name]
        for name in (
            "schema",
            "target",
            "profile_root",
            "auth_route",
            "login_state",
            "method",
            "provider",
            "default_model",
            "status_exit",
            "raw_output_retained",
            "login_performed",
            "model_launched",
        )
        if name in status
    }
    if "auth_route" not in public_status:
        public_status["auth_route"] = context.public_binding["auth_route"]
    return {**dict(context.public_binding), "status": public_status}


def _validate_recorded_real_home(value: Any, *, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _DIRECTORY_IDENTITY_FIELDS:
        raise ValidationError("%s identity fields are invalid" % label)
    path = value.get("path")
    if (
        not isinstance(path, str)
        or not path
        or not Path(path).is_absolute()
        or any(character in path for character in "\x00\n\r")
    ):
        raise ValidationError("%s path is invalid" % label)
    for name in ("device", "inode"):
        observed = value.get(name)
        if isinstance(observed, bool) or not isinstance(observed, int) or observed <= 0:
            raise ValidationError("%s identity is invalid" % label)
    uid = value.get("uid")
    if isinstance(uid, bool) or not isinstance(uid, int) or uid < 0:
        raise ValidationError("%s owner is invalid" % label)
    if uid != os.getuid():
        raise ValidationError("%s owner is invalid" % label)
    mode = value.get("mode")
    if isinstance(mode, bool) or not isinstance(mode, int) or mode <= 0:
        raise ValidationError("%s mode is invalid" % label)
    return dict(value)


def _validate_recorded_directory(value: Any, *, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _DIRECTORY_IDENTITY_FIELDS:
        raise ValidationError("%s identity fields are invalid" % label)
    path = value.get("path")
    if (
        not isinstance(path, str)
        or not path
        or not Path(path).is_absolute()
        or any(character in path for character in "\x00\n\r")
    ):
        raise ValidationError("%s path is invalid" % label)
    for name in ("device", "inode"):
        observed = value.get(name)
        if isinstance(observed, bool) or not isinstance(observed, int) or observed <= 0:
            raise ValidationError("%s identity is invalid" % label)
    uid = value.get("uid")
    if isinstance(uid, bool) or not isinstance(uid, int) or uid < 0:
        raise ValidationError("%s owner is invalid" % label)
    if value.get("mode") != 0o700:
        raise ValidationError("%s mode is invalid" % label)
    return dict(value)


def validate_subscription_launch_binding(
    value: Any,
    *,
    expected_target: str | None = None,
    require_logged_in: bool = True,
) -> Dict[str, Any]:
    """Validate one body-free profile proof without reading credential content."""

    if not isinstance(value, dict) or set(value) != _PUBLIC_BINDING_FIELDS:
        raise ValidationError("subscription launch binding fields are invalid")
    if value.get("schema") != LAUNCH_BINDING_SCHEMA:
        raise ValidationError("subscription launch binding schema is unsupported")
    target = validate_identifier(value.get("target"), "profile target")
    if target not in _PROFILE_LAYOUTS or (
        expected_target is not None and target != expected_target
    ):
        raise IdentityError("subscription launch binding target changed")
    root = _validate_recorded_directory(
        value.get("root_identity"), label="subscription profile root"
    )
    if value.get("profile_root") != root["path"]:
        raise IdentityError("subscription launch binding root changed")
    directories = value.get("directory_identities")
    if not isinstance(directories, dict) or set(directories) != set(
        _PROFILE_LAYOUTS[target]
    ):
        raise ValidationError("subscription launch directory map is invalid")
    checked_directories = {}
    for name in _PROFILE_LAYOUTS[target]:
        directory = _validate_recorded_directory(
            directories.get(name), label="subscription profile %s" % name
        )
        if Path(directory["path"]) != Path(root["path"]) / name:
            raise IdentityError("subscription launch directory path changed")
        checked_directories[name] = directory
    auth_route = value.get("auth_route")
    expected_auth_route = _auth_route_for_target(target)
    if auth_route != expected_auth_route:
        raise IdentityError("subscription launch auth route changed")
    real_home = _validate_recorded_real_home(
        value.get("real_home_identity"), label="subscription profile real home"
    )
    expected_real_home = _expected_real_home_identity(target, checked_directories)
    if real_home != expected_real_home:
        raise IdentityError("subscription launch real home identity changed")
    if target == "claude" and real_home["path"] == checked_directories["home"]["path"]:
        raise UnsupportedError(CLAUDE_LEGACY_PROFILE_MIGRATION_BLOCKER)
    manifest_path = value.get("manifest_path")
    if (
        not isinstance(manifest_path, str)
        or Path(manifest_path) != Path(root["path"]) / "profile.json"
    ):
        raise IdentityError("subscription launch manifest path changed")
    manifest_sha256 = value.get("manifest_sha256")
    if (
        not isinstance(manifest_sha256, str)
        or len(manifest_sha256) != 64
        or any(character not in "0123456789abcdef" for character in manifest_sha256)
    ):
        raise ValidationError("subscription launch manifest fingerprint is invalid")
    executable = validate_execution_file_identity(
        value.get("executable"),
        "subscription launch executable",
        verify_current=False,
    )
    profile_environment = _profile_environment(
        target, checked_directories, real_home=real_home
    )
    expected_login_only = sorted(
        name for name in profile_environment if name in _LOGIN_ONLY_ENVIRONMENT_NAMES
    )
    expected_launch_names = sorted(
        name
        for name in profile_environment
        if name not in _LOGIN_ONLY_ENVIRONMENT_NAMES
    )
    if (
        value.get("launch_env_names") != expected_launch_names
        or value.get("login_only_env_names") != expected_login_only
    ):
        raise IdentityError("subscription launch environment names changed")
    status = value.get("status")
    base_status_fields = {
        "schema",
        "target",
        "profile_root",
        "auth_route",
        "login_state",
        "method",
        "status_exit",
        "raw_output_retained",
        "login_performed",
        "model_launched",
    }
    optional_status_fields = (
        {"provider"}
        if target == "claude"
        else {"default_model"}
        if target == "grok"
        else set()
    )
    if not isinstance(status, dict) or set(status) != (
        base_status_fields | optional_status_fields
    ):
        raise ValidationError("subscription launch status fields are invalid")
    allowed_methods = {
        "codex": {"chatgpt", "none", "unknown"},
        "claude": {"claude.ai", "none", "other", "unknown"},
        "cursor": {"private_file_store", "unknown"},
        "grok": {"private_grok_home", "unknown"},
    }
    if (
        status.get("schema") != STATUS_SCHEMA
        or status.get("target") != target
        or status.get("profile_root") != root["path"]
        or status.get("auth_route") != expected_auth_route
        or status.get("login_state") not in {"logged_in", "logged_out", "unknown"}
        or status.get("method") not in allowed_methods[target]
        or isinstance(status.get("status_exit"), bool)
        or not isinstance(status.get("status_exit"), int)
        or status.get("raw_output_retained") is not False
        or status.get("login_performed") is not False
        or status.get("model_launched") is not False
    ):
        raise ValidationError("subscription launch status is invalid")
    if target == "claude" and status.get("provider") not in {
        "firstParty",
        "other",
    }:
        raise ValidationError("subscription launch provider is invalid")
    if target == "grok" and status.get("default_model") not in {
        "grok-4.5",
        "unknown",
    }:
        raise ValidationError("subscription launch default model is invalid")
    if require_logged_in and (
        status["login_state"] != "logged_in" or status["status_exit"] != 0
    ):
        raise IdentityError("subscription launch profile is not authenticated")
    return {
        **dict(value),
        "root_identity": root,
        "directory_identities": checked_directories,
        "real_home_identity": real_home,
        "auth_route": auth_route,
        "executable": executable,
        "status": dict(status),
    }


def subscription_binding_environment(
    value: Any, *, expected_target: str
) -> tuple[Dict[str, str], Dict[str, str], Path]:
    """Reconstruct the exact closed launch values committed by a proof binding."""

    binding = validate_subscription_launch_binding(
        value, expected_target=expected_target, require_logged_in=True
    )
    environment = _profile_environment(
        binding["target"],
        binding["directory_identities"],
        real_home=binding["real_home_identity"],
    )
    source = {
        name: environment[name] for name in sorted(_BASE_LAUNCH_ENVIRONMENT_NAMES)
    }
    bindings = {
        name: selected
        for name, selected in environment.items()
        if name not in _BASE_LAUNCH_ENVIRONMENT_NAMES
        and name not in _LOGIN_ONLY_ENVIRONMENT_NAMES
    }
    return source, bindings, Path(binding["profile_root"])


def execute_subscription_profile_login(
    *,
    profile_root: Path | str,
    helper_path: Path | str,
    interpreter_path: Path | str,
    _execve: Any = os.execve,
) -> None:
    """Revalidate a human handoff and replace this helper with native login."""

    root = _private_directory(Path(profile_root), label="profile root", create=False)
    manifest_path = Path(root["path"]) / "profile.json"
    manifest = _validate_manifest(read_json(manifest_path), verify_current=True)
    lock_path = Path(manifest["root"]["path"]) / ".profile-init.lock"
    with exclusive_lock(lock_path):
        manifest = _validate_manifest(read_json(manifest_path), verify_current=True)
        helper = execution_file_identity(Path(helper_path).resolve(strict=True))
        interpreter = execution_file_identity(
            Path(interpreter_path).resolve(strict=True)
        )
        if helper != manifest["helper"] or interpreter != manifest["interpreter"]:
            raise IdentityError("subscription profile login helper identity changed")
        _execve(
            manifest["executable"]["path"],
            manifest["commands"]["login"],
            manifest["bindings"],
        )


__all__ = [
    "CLAUDE_LEGACY_PROFILE_MIGRATION_BLOCKER",
    "CLAUDE_NATIVE_KEYRING_AUTH_ROUTE",
    "LAUNCH_BINDING_SCHEMA",
    "MAX_STATUS_OUTPUT_BYTES",
    "PROFILE_HUMAN_LOGIN_POLICY",
    "PROFILE_OPERATOR_GLOBAL_ADOPTION",
    "PROFILE_REUSE_SCOPE",
    "PROFILE_SCHEMA",
    "PROFILE_STATUS_POLICY",
    "STATUS_SCHEMA",
    "SYNTHETIC_PROFILE_HOME_AUTH_ROUTE",
    "SubscriptionLaunchContext",
    "build_subscription_launch_binding",
    "execute_subscription_profile_login",
    "initialize_subscription_profile",
    "subscription_profile_launch_context",
    "subscription_profile_preflight",
    "subscription_profile_status",
    "subscription_binding_environment",
    "validate_subscription_launch_binding",
]
