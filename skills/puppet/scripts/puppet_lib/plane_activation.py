"""FD-bound, create-only native instruction-plane activation.

This module intentionally supports one narrow qualification surface: Claude
2.1.215's per-run ``--append-system-prompt-file`` additive instruction plane.
It never launches an agent session. Planning may run the bounded executable
census needed to refresh version and file identity. Durable records contain
identities and hashes, never instruction bytes.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .adapter_manifest import AdapterManifest
from .census import adapter_implementation_fingerprint, census_target
from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .instruction_planes import (
    descriptor_fingerprint,
    validate_instruction_plane_descriptor,
)
from .instructions import validate_instruction_manifest
from .launch import (
    build_admitted_launch_plan,
    build_launch_identity,
    public_launch_identity,
    validate_admitted_launch_plan,
    validate_public_launch_identity,
)
from .profiles import (
    PROMPT_TRANSPORT,
    SUBMIT_SETTLE_SECONDS,
    session_profiles_for,
    startup_settle_seconds_for,
)
from .safety import (
    canonical_json_bytes,
    ensure_within,
    sha256_bytes,
    sha256_file,
    validate_bounded_json,
    validate_identifier,
    validate_sha256,
)


PLAN_SCHEMA = "puppet.plane-activation-plan/v2"
INTENT_SCHEMA = "puppet.plane-activation-intent/v2"
RECEIPT_SCHEMA = "puppet.plane-activation-receipt/v2"
ROLLBACK_SCHEMA = "puppet.plane-activation-rollback/v2"
ROLLBACK_INTENT_SCHEMA = "puppet.plane-activation-rollback-intent/v2"
LAUNCH_CONTEXT_SCHEMA = "puppet.plane-activation-launch-context/v1"
PROBE_PLANE_ACTIVATION_SCHEMA = "puppet.probe-plane-activation/v1"
ACTIVATION_LIFECYCLE_SCOPE = "activation_lifecycle_only"

# This trigger deliberately carries no task, run, fixture, nonce, or contract
# body.  The native additive instruction artifact must supply all qualification
# authority; re-sending the rendered contract as the first user message would
# make a native-plane result a false positive.
CLAUDE_NATIVE_TRIGGER = "Proceed using the active Puppet qualification contract."
CLAUDE_NATIVE_TRIGGER_SHA256 = sha256_bytes(
    (CLAUDE_NATIVE_TRIGGER + "\n").encode("utf-8")
)

INTENT_FILENAME = "activation-intent.json"
RECEIPT_FILENAME = "activation-receipt.json"
ROLLBACK_FILENAME = "rollback-receipt.json"
ROLLBACK_INTENT_FILENAME = "rollback-intent.json"

_DIR_MODE = 0o700
_FILE_MODE = 0o600
_MAX_JSON_BYTES = 131072
_READ_CHUNK = 65536
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW
_READ_FLAGS = os.O_RDONLY | _NOFOLLOW
_CREATE_FLAGS = os.O_CREAT | os.O_EXCL | os.O_RDWR | _NOFOLLOW

# Exact-version policy belongs at activation, not in the historical descriptor
# parser.  The digest is sha256 of Claude's exact bounded ``--version`` output
# (``2.1.215 (Claude Code)\n``) from the admitted census.
_SUPPORTED_VERSION_OBSERVATIONS = {
    (
        "claude",
        "2.1.215",
    ): "3c95eff850dac10d40c5692a73957f526b54a74767163913dc858c4f8d4c8c63",
}

_DIRECTORY_IDENTITY_KEYS = {
    "path",
    "device",
    "inode",
    "uid",
    "gid",
    "mode",
    "nlink",
}
_CREATED_DIRECTORY_KEYS = {
    "relative_path",
    "device",
    "inode",
    "uid",
    "gid",
    "mode",
    "nlink",
}
_ARTIFACT_KEYS = {
    "artifact_id",
    "relative_path",
    "device",
    "inode",
    "uid",
    "gid",
    "mode",
    "nlink",
    "size",
    "sha256",
}
_CLAUDE_SYMBOLIC_ENV = [
    {
        "name": "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
        "value_ref": "true_literal",
    },
    {"name": "CLAUDE_CONFIG_DIR", "value_ref": "config_root_path"},
]
_PLAN_KEYS = {
    "schema",
    "config_root",
    "descriptor_id",
    "descriptor_sha256",
    "instruction_manifest_sha256",
    "effective_contract_fingerprint",
    "effective_contract_sha256",
    "effective_contract_bytes",
    "adapter_manifest_sha256",
    "adapter_implementation_sha256",
    "version_observation_sha256",
    "artifact_id",
    "artifact_relative_path",
    "created_directory_paths",
    "ephemeral_root",
    "workspace_root",
    "transaction_root",
    "launch",
    "launch_plan_sha256",
    "plan_sha256",
}


def _require_fd_primitives() -> None:
    required = (os.open, os.mkdir, os.unlink, os.rmdir, os.stat)
    if not _NOFOLLOW or any(item not in os.supports_dir_fd for item in required):
        raise UnsupportedError("native activation requires no-follow dir-FD primitives")
    if os.listdir not in os.supports_fd:
        raise UnsupportedError("native activation requires FD directory listing")


def _exact_int(value: Any, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError("%s is invalid" % label)
    return value


def _absolute_lexical(path: Path | str, *, label: str) -> Path:
    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise ValidationError("%s must be a filesystem path" % label) from exc
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise ValidationError("%s must be a non-empty path" % label)
    candidate = Path(os.path.abspath(raw))
    if not candidate.is_absolute():
        raise ValidationError("%s must be absolute" % label)
    return candidate


def _relative_parts(value: str, *, label: str) -> Tuple[str, ...]:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
    ):
        raise ValidationError("%s must be a safe relative path" % label)
    parts = tuple(value.split("/"))
    if any(not part or part in {".", ".."} for part in parts):
        raise ValidationError("%s must be a safe relative path" % label)
    return parts


def _canonical_json_with_newline(value: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(dict(value)) + b"\n"


def _paths_overlap(first: str, second: str) -> bool:
    first_parts = Path(first).resolve().parts
    second_parts = Path(second).resolve().parts
    return (
        first_parts == second_parts[: len(first_parts)]
        or second_parts == first_parts[: len(second_parts)]
    )


def _assert_root_topology(*, roots: Sequence[Tuple[str, Mapping[str, Any]]]) -> None:
    for index, (left_label, left) in enumerate(roots):
        for right_label, right in roots[index + 1 :]:
            left_identity = (left["device"], left["inode"])
            right_identity = (right["device"], right["inode"])
            if left_identity == right_identity:
                raise ConflictError("activation roots must be distinct")
            if _paths_overlap(left["path"], right["path"]):
                raise ConflictError(
                    "activation roots must be pairwise non-overlapping: %s and %s"
                    % (left_label, right_label)
                )


def _stat_directory_identity(details: os.stat_result, *, path: str) -> Dict[str, Any]:
    if not stat.S_ISDIR(details.st_mode):
        raise IdentityError("bound root is not a directory")
    return {
        "path": path,
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "gid": details.st_gid,
        "mode": stat.S_IMODE(details.st_mode),
        "nlink": details.st_nlink,
    }


def _created_directory_identity(
    details: os.stat_result, *, relative_path: str
) -> Dict[str, Any]:
    if not stat.S_ISDIR(details.st_mode):
        raise IdentityError("activation parent is not a directory")
    return {
        "relative_path": relative_path,
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "gid": details.st_gid,
        "mode": stat.S_IMODE(details.st_mode),
        "nlink": details.st_nlink,
    }


def _validate_directory_identity(
    value: Any,
    *,
    label: str,
    private: bool,
) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _DIRECTORY_IDENTITY_KEYS:
        raise ValidationError("%s identity fields are invalid" % label)
    path = _absolute_lexical(value["path"], label="%s path" % label)
    if str(path) != value["path"]:
        raise ValidationError("%s path is not normalized" % label)
    result = {
        "path": str(path),
        "device": _exact_int(value["device"], label="%s device" % label),
        "inode": _exact_int(value["inode"], label="%s inode" % label, minimum=1),
        "uid": _exact_int(value["uid"], label="%s uid" % label),
        "gid": _exact_int(value["gid"], label="%s gid" % label),
        "mode": _exact_int(value["mode"], label="%s mode" % label),
        "nlink": _exact_int(value["nlink"], label="%s nlink" % label, minimum=1),
    }
    if result["mode"] > 0o7777:
        raise ValidationError("%s mode is invalid" % label)
    if private and (result["uid"] != os.getuid() or result["mode"] != _DIR_MODE):
        raise IdentityError("%s must be current-UID 0700" % label)
    return result


def _validate_created_directory(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CREATED_DIRECTORY_KEYS:
        raise ValidationError("created directory identity fields are invalid")
    relative_path = "/".join(
        _relative_parts(value["relative_path"], label="created directory path")
    )
    result = {
        "relative_path": relative_path,
        "device": _exact_int(value["device"], label="created directory device"),
        "inode": _exact_int(value["inode"], label="created directory inode", minimum=1),
        "uid": _exact_int(value["uid"], label="created directory uid"),
        "gid": _exact_int(value["gid"], label="created directory gid"),
        "mode": _exact_int(value["mode"], label="created directory mode"),
        "nlink": _exact_int(value["nlink"], label="created directory nlink", minimum=1),
    }
    if result["uid"] != os.getuid() or result["mode"] != _DIR_MODE:
        raise IdentityError("created directory must be current-UID 0700")
    return result


def _validate_artifact(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ARTIFACT_KEYS:
        raise ValidationError("artifact identity fields are invalid")
    result = {
        "artifact_id": validate_identifier(value["artifact_id"], "artifact id"),
        "relative_path": "/".join(
            _relative_parts(value["relative_path"], label="artifact path")
        ),
        "device": _exact_int(value["device"], label="artifact device"),
        "inode": _exact_int(value["inode"], label="artifact inode", minimum=1),
        "uid": _exact_int(value["uid"], label="artifact uid"),
        "gid": _exact_int(value["gid"], label="artifact gid"),
        "mode": _exact_int(value["mode"], label="artifact mode"),
        "nlink": _exact_int(value["nlink"], label="artifact nlink", minimum=1),
        "size": _exact_int(value["size"], label="artifact size"),
        "sha256": validate_sha256(value["sha256"], "artifact sha256"),
    }
    if (
        result["uid"] != os.getuid()
        or result["mode"] != _FILE_MODE
        or result["nlink"] != 1
    ):
        raise IdentityError("artifact must be current-UID 0600 with one link")
    return result


def _open_root(
    path: Path | str,
    *,
    label: str,
    private: bool,
    empty: bool = False,
) -> Tuple[int, Dict[str, Any]]:
    _require_fd_primitives()
    candidate = _absolute_lexical(path, label=label)
    try:
        lexical = os.lstat(candidate)
    except FileNotFoundError as exc:
        raise ValidationError("%s does not exist" % label) from exc
    if stat.S_ISLNK(lexical.st_mode):
        raise IdentityError("%s must not be a symlink" % label)
    try:
        descriptor = os.open(str(candidate), _DIRECTORY_FLAGS)
    except OSError as exc:
        raise IdentityError(
            "%s cannot be opened without following links" % label
        ) from exc
    try:
        details = os.fstat(descriptor)
        if (details.st_dev, details.st_ino) != (lexical.st_dev, lexical.st_ino):
            raise IdentityError("%s changed while opening" % label)
        identity = _stat_directory_identity(details, path=str(candidate))
        if private and (
            identity["uid"] != os.getuid() or identity["mode"] != _DIR_MODE
        ):
            raise IdentityError("%s must be current-UID 0700" % label)
        if empty and os.listdir(descriptor):
            raise ConflictError("%s must be empty and dedicated" % label)
        return descriptor, identity
    except Exception:
        os.close(descriptor)
        raise


def _assert_identity(
    live: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    label: str,
    compare_nlink: bool = True,
) -> None:
    keys = _DIRECTORY_IDENTITY_KEYS
    if not compare_nlink:
        keys = keys - {"nlink"}
    if any(live[key] != expected[key] for key in keys):
        raise IdentityError("%s identity changed" % label)


def _open_bound_root(
    expected: Mapping[str, Any],
    *,
    label: str,
    private: bool,
    empty: bool = False,
    compare_nlink: bool = True,
) -> int:
    descriptor, live = _open_root(
        expected["path"], label=label, private=private, empty=empty
    )
    try:
        _assert_identity(live, expected, label=label, compare_nlink=compare_nlink)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _sha256_fd(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        block = os.read(descriptor, _READ_CHUNK)
        if not block:
            break
        digest.update(block)
    return digest.hexdigest()


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    offset = 0
    while offset < len(view):
        written = os.write(descriptor, view[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "short write")
        offset += written


def _write_contract_bytes(descriptor: int, payload: bytes) -> None:
    _write_all(descriptor, payload)


def _safe_stat_at(parent_descriptor: int, name: str) -> Optional[os.stat_result]:
    try:
        return os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _unlink_open_leaf(
    parent_descriptor: int,
    name: str,
    open_descriptor: int,
    *,
    expected_device: int,
    expected_inode: int,
    expected: Optional[Mapping[str, Any]] = None,
) -> None:
    opened = os.fstat(open_descriptor)
    live = _safe_stat_at(parent_descriptor, name)
    if live is None:
        raise IdentityError("owned leaf disappeared before cleanup")
    if (
        stat.S_ISLNK(live.st_mode)
        or not stat.S_ISREG(live.st_mode)
        or not stat.S_ISREG(opened.st_mode)
        or opened.st_uid != os.getuid()
        or live.st_uid != os.getuid()
        or stat.S_IMODE(opened.st_mode) != _FILE_MODE
        or stat.S_IMODE(live.st_mode) != _FILE_MODE
        or opened.st_nlink != 1
        or live.st_nlink != 1
        or (
            live.st_dev,
            live.st_ino,
            opened.st_dev,
            opened.st_ino,
        )
        != (expected_device, expected_inode, expected_device, expected_inode)
    ):
        raise IdentityError("owned leaf changed before cleanup")
    if expected is not None:
        checks = {
            "device": opened.st_dev,
            "inode": opened.st_ino,
            "uid": opened.st_uid,
            "gid": opened.st_gid,
            "mode": stat.S_IMODE(opened.st_mode),
            "nlink": opened.st_nlink,
            "size": opened.st_size,
        }
        if any(checks[key] != expected[key] for key in checks):
            raise IdentityError("owned leaf identity changed before cleanup")
        if "sha256" in expected and _sha256_fd(open_descriptor) != expected["sha256"]:
            raise IdentityError("owned leaf content changed before cleanup")
        live = _safe_stat_at(parent_descriptor, name)
        if live is None or (live.st_dev, live.st_ino, live.st_nlink) != (
            expected_device,
            expected_inode,
            1,
        ):
            raise IdentityError("owned leaf changed during cleanup verification")
    os.unlink(name, dir_fd=parent_descriptor)
    os.fsync(parent_descriptor)
    if _safe_stat_at(parent_descriptor, name) is not None:
        raise IdentityError("owned leaf removal could not be proven")


def _unlink_new_leaf(
    parent_descriptor: int,
    name: str,
    open_descriptor: int,
    *,
    expected_device: int,
    expected_inode: int,
) -> None:
    """Remove a just-created leaf when final mode setup did not complete."""

    opened = os.fstat(open_descriptor)
    live = _safe_stat_at(parent_descriptor, name)
    if (
        live is None
        or stat.S_ISLNK(live.st_mode)
        or not stat.S_ISREG(live.st_mode)
        or not stat.S_ISREG(opened.st_mode)
        or opened.st_uid != os.getuid()
        or live.st_uid != os.getuid()
        or opened.st_nlink != 1
        or live.st_nlink != 1
        or (stat.S_IMODE(opened.st_mode) | _FILE_MODE) != _FILE_MODE
        or (stat.S_IMODE(live.st_mode) | _FILE_MODE) != _FILE_MODE
        or (
            opened.st_dev,
            opened.st_ino,
            live.st_dev,
            live.st_ino,
        )
        != (expected_device, expected_inode, expected_device, expected_inode)
    ):
        raise IdentityError("new activation leaf changed before cleanup")
    os.unlink(name, dir_fd=parent_descriptor)
    os.fsync(parent_descriptor)
    if _safe_stat_at(parent_descriptor, name) is not None:
        raise IdentityError("new activation leaf removal could not be proven")


def _new_leaf_identity(open_descriptor: int) -> Tuple[int, int]:
    """Capture the minimum authority needed to clean a new private leaf."""

    details = os.fstat(open_descriptor)
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_uid != os.getuid()
        or details.st_nlink != 1
        or (stat.S_IMODE(details.st_mode) | _FILE_MODE) != _FILE_MODE
    ):
        raise IdentityError("artifact creation identity is unsafe")
    return details.st_dev, details.st_ino


def _decode_json(raw: bytes, *, label: str) -> Dict[str, Any]:
    def object_pairs(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValidationError("%s contains duplicate fields" % label)
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=object_pairs)
    except ValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValidationError("%s is malformed" % label) from exc
    if not isinstance(value, dict):
        raise ValidationError("%s must be an object" % label)
    return value


def _read_named_bytes(
    root_descriptor: int, name: str, *, label: str
) -> Tuple[bytes, Dict[str, Any]]:
    if "/" in name or not name:
        raise ValidationError("durable filename is invalid")
    try:
        descriptor = os.open(name, _READ_FLAGS, dir_fd=root_descriptor)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise IdentityError("%s cannot be opened safely" % label) from exc
    try:
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) != _FILE_MODE
            or details.st_nlink != 1
        ):
            raise IdentityError("%s is not an owned private regular file" % label)
        if details.st_size > _MAX_JSON_BYTES:
            raise ValidationError("%s is oversized" % label)
        chunks = []
        total = 0
        while True:
            block = os.read(descriptor, min(_READ_CHUNK, _MAX_JSON_BYTES + 1 - total))
            if not block:
                break
            total += len(block)
            if total > _MAX_JSON_BYTES:
                raise ValidationError("%s is oversized" % label)
            chunks.append(block)
        return b"".join(chunks), {
            "device": details.st_dev,
            "inode": details.st_ino,
        }
    finally:
        os.close(descriptor)


def _read_named_json(root_descriptor: int, name: str, *, label: str) -> Dict[str, Any]:
    raw, _ = _read_named_bytes(root_descriptor, name, label=label)
    value = _decode_json(raw, label=label)
    canonical = _canonical_json_with_newline(value)
    if raw != canonical:
        raise ValidationError("%s is not canonical durable JSON" % label)
    return value


def _persist_immutable_json(
    root_descriptor: int,
    name: str,
    value: Mapping[str, Any],
    *,
    label: str,
) -> None:
    payload = _canonical_json_with_newline(value)
    if len(payload) > _MAX_JSON_BYTES:
        raise ValidationError("%s is oversized" % label)
    descriptor: Optional[int] = None
    created: Optional[Tuple[int, int]] = None
    try:
        try:
            descriptor = os.open(
                name, _CREATE_FLAGS, _FILE_MODE, dir_fd=root_descriptor
            )
        except FileExistsError:
            existing, _ = _read_named_bytes(root_descriptor, name, label=label)
            if existing != payload:
                raise ConflictError("%s already exists with different content" % label)
            return
        os.fchmod(descriptor, _FILE_MODE)
        details = os.fstat(descriptor)
        created = (details.st_dev, details.st_ino)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) != _FILE_MODE
            or details.st_nlink != 1
        ):
            raise IdentityError("%s was not created as a private regular file" % label)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.fsync(root_descriptor)
    except Exception:
        cleanup_error: Optional[Exception] = None
        if descriptor is not None and created is not None:
            try:
                _unlink_open_leaf(
                    root_descriptor,
                    name,
                    descriptor,
                    expected_device=created[0],
                    expected_inode=created[1],
                )
            except Exception as exc:
                cleanup_error = exc
        if cleanup_error is not None:
            raise IdentityError(
                "%s write failed and exact cleanup was blocked" % label
            ) from cleanup_error
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _open_parent_from_root_impl(
    root_descriptor: int,
    parent_parts: Sequence[str],
    *,
    allow_missing: bool = False,
) -> Optional[int]:
    current = os.dup(root_descriptor)
    try:
        for name in parent_parts:
            try:
                child = os.open(name, _DIRECTORY_FLAGS, dir_fd=current)
            except FileNotFoundError:
                if allow_missing:
                    os.close(current)
                    return None
                raise IdentityError("activation parent path changed")
            except OSError as exc:
                raise IdentityError("activation parent path changed") from exc
            os.close(current)
            current = child
        return current
    except Exception:
        os.close(current)
        raise


@dataclass(frozen=True)
class ActivationPlan:
    """Pure, body-free native activation plan."""

    raw: Dict[str, Any]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ActivationPlan":
        normalized = _validate_plan(value)
        return cls(raw=normalized)

    def to_dict(self) -> Dict[str, Any]:
        return json.loads(canonical_json_bytes(self.raw).decode("utf-8"))

    @property
    def plan_sha256(self) -> str:
        return self.raw["plan_sha256"]

    @property
    def artifact_path(self) -> Path:
        return (
            Path(self.raw["ephemeral_root"]["path"])
            / self.raw["artifact_relative_path"]
        )

    @property
    def intent_path(self) -> Path:
        return Path(self.raw["transaction_root"]["path"]) / INTENT_FILENAME

    @property
    def receipt_path(self) -> Path:
        return Path(self.raw["transaction_root"]["path"]) / RECEIPT_FILENAME

    @property
    def rollback_receipt_path(self) -> Path:
        return Path(self.raw["transaction_root"]["path"]) / ROLLBACK_FILENAME

    @property
    def rollback_intent_path(self) -> Path:
        return Path(self.raw["transaction_root"]["path"]) / ROLLBACK_INTENT_FILENAME


@dataclass(frozen=True)
class ActivationRecovery:
    """Body-free recovery classification for one transaction."""

    state: str
    plan: ActivationPlan
    receipt: Optional[Dict[str, Any]] = None
    rollback_receipt: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ActivationLaunchContext:
    """Exact private launch values plus their body- and value-free authority."""

    target: str
    session: str
    run_id: str
    session_profile: str
    adapter_manifest_sha256: str
    adapter_implementation_sha256: str
    activation_plan_sha256: str
    activation_receipt_sha256: str
    activation_delta_sha256: str
    artifact_sha256: str
    workspace_root_sha256: str
    config_root_sha256: str
    admitted_lane_root_sha256: str
    admitted_launch_plan_sha256: str
    _argv: Tuple[str, ...] = field(repr=False)
    _environment_items: Tuple[Tuple[str, str], ...] = field(repr=False)
    _launch_identity_json: bytes = field(repr=False)
    _admitted_launch_plan_json: bytes = field(repr=False)

    @property
    def argv(self) -> list[str]:
        """Return a fresh copy of the exact admitted argv."""

        return list(self._argv)

    @property
    def environment(self) -> Dict[str, str]:
        """Return a fresh copy of the private, closed launch environment."""

        return dict(self._environment_items)

    @property
    def launch_identity(self) -> Dict[str, Any]:
        """Return the value-free public identity for the private launch values."""

        return json.loads(self._launch_identity_json.decode("utf-8"))

    @property
    def admitted_launch_plan(self) -> Dict[str, Any]:
        """Return the existing value-private pre-lease launch-plan schema."""

        return json.loads(self._admitted_launch_plan_json.decode("utf-8"))

    def verify_launch_values(
        self,
        *,
        argv: Sequence[str],
        environment: Mapping[str, str],
    ) -> None:
        """Reject in-memory mutation of either private launch input."""

        if (
            isinstance(argv, (str, bytes, bytearray))
            or not isinstance(argv, Sequence)
            or tuple(argv) != self._argv
        ):
            raise IdentityError("activation launch argv changed")
        if not isinstance(environment, Mapping):
            raise IdentityError("activation launch environment changed")
        try:
            environment_items = tuple(sorted(environment.items()))
        except (TypeError, ValueError) as exc:
            raise IdentityError("activation launch environment changed") from exc
        if environment_items != self._environment_items:
            raise IdentityError("activation launch environment changed")

    @property
    def public_context_sha256(self) -> str:
        """Return the canonical fingerprint of the value-free public context."""

        return sha256_bytes(canonical_json_bytes(self.to_public_dict()))

    def to_public_dict(self) -> Dict[str, Any]:
        """Return the persistable binding without argv-adjacent env values."""

        value = {
            "schema": LAUNCH_CONTEXT_SCHEMA,
            "target": self.target,
            "session": self.session,
            "run_id": self.run_id,
            "session_profile": self.session_profile,
            "adapter_manifest_sha256": self.adapter_manifest_sha256,
            "adapter_implementation_sha256": self.adapter_implementation_sha256,
            "activation_plan_sha256": self.activation_plan_sha256,
            "activation_receipt_sha256": self.activation_receipt_sha256,
            "activation_delta_sha256": self.activation_delta_sha256,
            "artifact_sha256": self.artifact_sha256,
            "workspace_root_sha256": self.workspace_root_sha256,
            "config_root_sha256": self.config_root_sha256,
            "admitted_lane_root_sha256": self.admitted_lane_root_sha256,
            "project_isolation": "activation_bound_workspace_config_lane_roots",
            "launch_identity": self.launch_identity,
            "admitted_launch_plan_sha256": self.admitted_launch_plan_sha256,
        }
        validate_bounded_json(
            value,
            max_depth=4,
            max_items=32,
            max_string=4096,
            reject_sensitive_fields=True,
        )
        return json.loads(canonical_json_bytes(value).decode("utf-8"))


def _validate_launch(value: Any, *, plan: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"cwd", "env", "argv"}:
        raise ValidationError("launch plan fields are invalid")
    expected_artifact = str(
        Path(plan["ephemeral_root"]["path"]) / plan["artifact_relative_path"]
    )
    expected = {
        "cwd": plan["workspace_root"]["path"],
        "env": list(_CLAUDE_SYMBOLIC_ENV),
        "argv": ["--append-system-prompt-file", expected_artifact],
    }
    if dict(value) != expected:
        raise ValidationError("launch plan is outside the closed Claude grammar")
    return expected


def _validate_plan(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("activation plan fields are invalid")
    if value.get("schema") != PLAN_SCHEMA:
        raise ValidationError("activation plan schema is unsupported")
    if set(value) != _PLAN_KEYS:
        raise ValidationError("activation plan fields are invalid")
    validate_bounded_json(
        dict(value),
        max_depth=6,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    result: Dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "config_root": _validate_directory_identity(
            value["config_root"], label="config root", private=True
        ),
        "descriptor_id": validate_identifier(value["descriptor_id"], "descriptor id"),
        "descriptor_sha256": validate_sha256(
            value["descriptor_sha256"], "descriptor sha256"
        ),
        "instruction_manifest_sha256": validate_sha256(
            value["instruction_manifest_sha256"], "instruction manifest sha256"
        ),
        "effective_contract_fingerprint": validate_sha256(
            value["effective_contract_fingerprint"],
            "effective contract fingerprint",
        ),
        "effective_contract_sha256": validate_sha256(
            value["effective_contract_sha256"], "effective contract sha256"
        ),
        "effective_contract_bytes": _exact_int(
            value["effective_contract_bytes"],
            label="effective contract bytes",
            minimum=1,
        ),
        "adapter_manifest_sha256": validate_sha256(
            value["adapter_manifest_sha256"], "adapter manifest sha256"
        ),
        "adapter_implementation_sha256": validate_sha256(
            value["adapter_implementation_sha256"],
            "adapter implementation sha256",
        ),
        "version_observation_sha256": validate_sha256(
            value["version_observation_sha256"], "version observation sha256"
        ),
        "artifact_id": validate_identifier(value["artifact_id"], "artifact id"),
        "artifact_relative_path": "/".join(
            _relative_parts(value["artifact_relative_path"], label="artifact path")
        ),
        "ephemeral_root": _validate_directory_identity(
            value["ephemeral_root"], label="ephemeral root", private=True
        ),
        "workspace_root": _validate_directory_identity(
            value["workspace_root"], label="workspace root", private=False
        ),
        "transaction_root": _validate_directory_identity(
            value["transaction_root"], label="transaction root", private=True
        ),
    }
    _assert_root_topology(
        roots=(
            ("workspace", result["workspace_root"]),
            ("ephemeral", result["ephemeral_root"]),
            ("transaction", result["transaction_root"]),
            ("config", result["config_root"]),
        )
    )
    paths = value["created_directory_paths"]
    if not isinstance(paths, list):
        raise ValidationError("created directory paths must be a list")
    normalized_paths = [
        "/".join(_relative_parts(item, label="created directory path"))
        for item in paths
    ]
    parts = _relative_parts(result["artifact_relative_path"], label="artifact path")
    expected_paths = ["/".join(parts[: index + 1]) for index in range(len(parts) - 1)]
    if normalized_paths != expected_paths:
        raise ValidationError("created directory paths do not match the artifact path")
    result["created_directory_paths"] = normalized_paths
    result["launch"] = _validate_launch(value["launch"], plan=result)
    expected_launch_hash = sha256_bytes(canonical_json_bytes(result["launch"]))
    launch_hash = validate_sha256(value["launch_plan_sha256"], "launch plan sha256")
    if launch_hash != expected_launch_hash:
        raise IdentityError("launch plan hash changed")
    result["launch_plan_sha256"] = launch_hash
    supplied_plan_hash = validate_sha256(value["plan_sha256"], "activation plan sha256")
    expected_plan_hash = sha256_bytes(canonical_json_bytes(result))
    if supplied_plan_hash != expected_plan_hash:
        raise IdentityError("activation plan hash changed")
    result["plan_sha256"] = supplied_plan_hash
    return result


def _unsupported_descriptor(descriptor: Mapping[str, Any]) -> None:
    target = descriptor["target"]
    materialize = descriptor["materialize"]
    launch = descriptor["launch_delta"]
    rollback = descriptor["rollback"]
    exact = (
        target["harness"] == "claude"
        and target["version"] == "2.1.215"
        and descriptor["plane"] == "per_run_additive"
        and descriptor["status"]
        == {"surface": "factual", "activation": "qualification_only"}
        and len(materialize) == 1
        and materialize[0]["artifact_id"] == "effective_contract_file"
        and materialize[0]["root_ref"] == "ephemeral_root"
        and materialize[0]["relative_path"] == "puppet-instructions.md"
        and materialize[0]["content_ref"] == "effective_contract"
        and materialize[0]["write_mode"] == "create_only"
        and launch["cwd_ref"] == "workspace_root"
        and launch["env"] == _CLAUDE_SYMBOLIC_ENV
        and launch["argv"]
        == [
            {"literal": "--append-system-prompt-file"},
            {"path_ref": materialize[0]["artifact_id"]},
        ]
        and rollback["owned_artifacts"] == [materialize[0]["artifact_id"]]
        and rollback["preimage_sha256"] == []
        and rollback["retain_hash_only_proof"] is True
    )
    if not exact:
        raise UnsupportedError(
            "only Claude 2.1.215 factual qualification-only per-run create-only "
            "activation is supported"
        )


def _validated_census_manifest(
    supplied: AdapterManifest,
    *,
    expected_target: str,
    expected_version: str,
    expected_manifest_sha256: str,
    current_manifest: Optional[AdapterManifest | Mapping[str, Any]],
) -> Tuple[str, str, str]:
    """Bind staging to the source-owned, exact current zero-agent census."""

    implementation_hash = adapter_implementation_fingerprint()
    manifest_hash = supplied.fingerprint
    if manifest_hash != expected_manifest_sha256:
        raise IdentityError(
            "descriptor does not bind the exact supplied adapter manifest"
        )
    if current_manifest is None:
        current = census_target(expected_target, implementation_hash)
    elif isinstance(current_manifest, AdapterManifest):
        current = current_manifest
    else:
        current = AdapterManifest.from_dict(dict(current_manifest))

    if (
        supplied.raw["target"] != expected_target
        or current.raw["target"] != expected_target
    ):
        raise IdentityError("adapter manifest target does not match descriptor")
    if (
        current.raw["adapter_fingerprint"] != implementation_hash
        or supplied.raw["adapter_fingerprint"] != implementation_hash
    ):
        raise IdentityError("adapter implementation fingerprint is not current")
    if not supplied.raw["doctor_only"] or supplied.raw["qualification"] is not None:
        raise IdentityError(
            "qualification staging requires the current doctor-only census"
        )
    if not current.raw["doctor_only"] or current.raw["qualification"] is not None:
        raise IdentityError("current census must be doctor-only")

    # ``generated_at`` is observation metadata, not executable or policy
    # identity.  Compare every other canonical field so a fresh census can
    # prove the exact supplied manifest without demanding the same timestamp.
    supplied_identity = {
        name: value for name, value in supplied.raw.items() if name != "generated_at"
    }
    current_identity = {
        name: value for name, value in current.raw.items() if name != "generated_at"
    }
    if canonical_json_bytes(supplied_identity) != canonical_json_bytes(
        current_identity
    ):
        raise IdentityError("adapter manifest does not match the current exact census")

    supplied.verify_execution_files()
    current.verify_execution_files()
    executable = current.raw["executable"]
    executable_path = Path(executable["resolved_path"])
    if executable_path.is_symlink() or not executable_path.is_file():
        raise IdentityError("censused executable is unavailable")
    details = executable_path.stat()
    if (
        details.st_dev != executable["device"]
        or details.st_ino != executable["inode"]
        or details.st_size != executable["size"]
        or details.st_mtime_ns != executable["mtime_ns"]
        or sha256_file(executable_path) != executable["sha256"]
    ):
        raise IdentityError("censused executable identity changed")

    version_key = (expected_target, expected_version)
    expected_version_hash = _SUPPORTED_VERSION_OBSERVATIONS.get(version_key)
    if expected_version_hash is None:
        raise UnsupportedError("descriptor version is not enabled for activation")
    if executable["version_sha256"] != expected_version_hash:
        raise IdentityError(
            "exact harness version observation does not match descriptor"
        )
    return manifest_hash, implementation_hash, expected_version_hash


def plan_activation(
    descriptor: Mapping[str, Any],
    *,
    instruction_manifest: Mapping[str, Any],
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    effective_contract: bytes,
    workspace_root: Path | str,
    ephemeral_root: Path | str,
    transaction_root: Path | str,
    config_root: Path | str,
    template_root: Optional[Path | str] = None,
    _current_manifest: Optional[AdapterManifest | Mapping[str, Any]] = None,
) -> ActivationPlan:
    """Create a body-free plan; the exact bounded census may run."""
    if config_root is None:
        raise ValidationError("config root is required")
    normalized_descriptor = validate_instruction_plane_descriptor(descriptor)
    _unsupported_descriptor(normalized_descriptor)
    if isinstance(adapter_manifest, AdapterManifest):
        manifest_instance = adapter_manifest
    else:
        manifest_instance = AdapterManifest.from_dict(dict(adapter_manifest))

    adapter_hash, implementation_hash, version_hash = _validated_census_manifest(
        manifest_instance,
        expected_target=normalized_descriptor["target"]["harness"],
        expected_version=normalized_descriptor["target"]["version"],
        expected_manifest_sha256=normalized_descriptor["target"][
            "adapter_manifest_sha256"
        ],
        current_manifest=_current_manifest,
    )
    if not isinstance(effective_contract, bytes) or not effective_contract:
        raise ValidationError("effective contract must be non-empty bytes")
    compiled_manifest = validate_instruction_manifest(
        instruction_manifest,
        target="claude",
        template_root=template_root,
    )
    contract_hash = sha256_bytes(effective_contract)
    if (
        contract_hash != compiled_manifest["rendered_sha256"]
        or len(effective_contract) != compiled_manifest["byte_count"]
    ):
        raise IdentityError(
            "effective contract does not match its instruction manifest"
        )

    opened: list[int] = []
    try:
        workspace_descriptor, workspace_identity = _open_root(
            workspace_root, label="workspace root", private=False
        )
        opened.append(workspace_descriptor)
        ephemeral_descriptor, ephemeral_identity = _open_root(
            ephemeral_root, label="ephemeral root", private=True, empty=True
        )
        opened.append(ephemeral_descriptor)
        transaction_descriptor, transaction_identity = _open_root(
            transaction_root, label="transaction root", private=True, empty=True
        )
        opened.append(transaction_descriptor)
        config_descriptor, config_identity = _open_root(
            config_root, label="config root", private=True
        )
        opened.append(config_descriptor)
        _assert_root_topology(
            roots=(
                ("workspace", workspace_identity),
                ("ephemeral", ephemeral_identity),
                ("transaction", transaction_identity),
                ("config", config_identity),
            )
        )
    finally:
        for descriptor in reversed(opened):
            os.close(descriptor)

    artifact = normalized_descriptor["materialize"][0]
    artifact_parts = _relative_parts(artifact["relative_path"], label="artifact path")
    created_paths = [
        "/".join(artifact_parts[: index + 1])
        for index in range(len(artifact_parts) - 1)
    ]
    launch = {
        "cwd": workspace_identity["path"],
        # Keep descriptor bindings symbolic here.  Launch ownership resolves
        # them later; this non-live substrate never reads config or spawns.
        "env": list(_CLAUDE_SYMBOLIC_ENV),
        "argv": [
            "--append-system-prompt-file",
            str(Path(ephemeral_identity["path"]) / artifact["relative_path"]),
        ],
    }
    plan: Dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "config_root": config_identity,
        "descriptor_id": normalized_descriptor["descriptor_id"],
        "descriptor_sha256": descriptor_fingerprint(normalized_descriptor),
        "instruction_manifest_sha256": sha256_bytes(
            _canonical_json_with_newline(compiled_manifest)
        ),
        "effective_contract_fingerprint": compiled_manifest[
            "effective_contract_fingerprint"
        ],
        "effective_contract_sha256": contract_hash,
        "effective_contract_bytes": len(effective_contract),
        "adapter_manifest_sha256": adapter_hash,
        "adapter_implementation_sha256": implementation_hash,
        "version_observation_sha256": version_hash,
        "artifact_id": artifact["artifact_id"],
        "artifact_relative_path": artifact["relative_path"],
        "created_directory_paths": created_paths,
        "ephemeral_root": ephemeral_identity,
        "workspace_root": workspace_identity,
        "transaction_root": transaction_identity,
        "launch": launch,
        "launch_plan_sha256": sha256_bytes(canonical_json_bytes(launch)),
    }
    plan["plan_sha256"] = sha256_bytes(canonical_json_bytes(plan))
    return ActivationPlan.from_dict(plan)


def _context_manifest(
    supplied: AdapterManifest,
    plan: ActivationPlan,
) -> Tuple[str, str]:
    """Revalidate a plan-bound manifest without starting any process."""

    manifest_hash = supplied.fingerprint
    if manifest_hash != plan.raw["adapter_manifest_sha256"]:
        raise IdentityError("adapter manifest changed after activation planning")
    implementation_hash = adapter_implementation_fingerprint()
    if (
        supplied.raw["target"] != "claude"
        or supplied.raw["adapter_fingerprint"] != implementation_hash
        or plan.raw["adapter_implementation_sha256"] != implementation_hash
    ):
        raise IdentityError("adapter implementation changed after activation planning")
    if not supplied.raw["doctor_only"] or supplied.raw["qualification"] is not None:
        raise IdentityError("activation launch context requires its doctor-only census")
    if (
        supplied.raw["executable"]["version_sha256"]
        != plan.raw["version_observation_sha256"]
    ):
        raise IdentityError("adapter version observation changed after activation")
    mapping = supplied.raw["yolo_mapping"]
    expected_mapping = {
        "complete": False,
        "launch_argv": [
            supplied.raw["executable"]["resolved_path"],
            "--dangerously-skip-permissions",
        ],
        "permission_declared": True,
        "permission_flags": ["--dangerously-skip-permissions"],
        "prompt_transport": PROMPT_TRANSPORT,
        "prompt_transport_declared": True,
        "sandbox_disable_declared": True,
        "sandbox_flags": [],
        "project_isolation_declared": False,
        "project_isolation_flags": [],
        "session_profiles": session_profiles_for("claude"),
        "session_profiles_declared": True,
        "startup_settle_seconds": startup_settle_seconds_for("claude"),
        "submit_settle_seconds": SUBMIT_SETTLE_SECONDS,
        "model_flag": "--model",
        "effort_flag": "--effort",
    }
    if mapping != expected_mapping:
        raise UnsupportedError(
            "Claude activation may close only the missing project-isolation dimension"
        )
    supplied.verify_execution_files()
    return manifest_hash, implementation_hash


def _exact_context_root(
    path: Path | str,
    expected: Mapping[str, Any],
    *,
    label: str,
    private: bool,
) -> Path:
    candidate = _absolute_lexical(path, label=label)
    if str(candidate) != expected["path"]:
        raise IdentityError("%s does not match the activation plan" % label)
    descriptor, live = _open_root(candidate, label=label, private=private)
    try:
        _assert_identity(
            live,
            expected,
            label=label,
            compare_nlink=False,
        )
    finally:
        os.close(descriptor)
    return candidate


def build_activation_launch_context(
    plan: ActivationPlan,
    *,
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    session: str,
    run_id: str,
    session_profile: str,
    workspace_root: Path | str,
    config_root: Path | str,
    admitted_lane_root: Path | str,
    source_environment: Optional[Mapping[str, str]] = None,
) -> ActivationLaunchContext:
    """Join a verified activation to exact pre-lease Claude launch authority.

    The function starts no process and writes no state.  Its private environment
    exists only in the returned in-memory context; the persistable record keeps
    names and fingerprints but never values or instruction bytes.
    """

    plan = ActivationPlan.from_dict(plan.to_dict())
    # Artifact, receipt, transaction, workspace, config, and root authority must
    # all verify before resolving any launch value.
    receipt = verify_activation(plan)
    if session_profile != "regular":
        raise UnsupportedError("activation launch context requires the regular profile")

    workspace = _exact_context_root(
        workspace_root,
        plan.raw["workspace_root"],
        label="workspace root",
        private=False,
    )
    config = _exact_context_root(
        config_root,
        plan.raw["config_root"],
        label="config root",
        private=True,
    )
    lane_root = _absolute_lexical(admitted_lane_root, label="admitted lane root")
    expected_lane_root = Path(
        os.path.commonpath(
            [
                plan.raw[name]["path"]
                for name in (
                    "workspace_root",
                    "config_root",
                    "ephemeral_root",
                    "transaction_root",
                )
            ]
        )
    )
    if str(lane_root) != str(expected_lane_root):
        raise IdentityError("admitted lane root is not the exact activation parent")
    lane_descriptor, lane_identity = _open_root(
        lane_root,
        label="admitted lane root",
        private=True,
    )
    os.close(lane_descriptor)
    for bound_root in (
        workspace,
        config,
        Path(plan.raw["ephemeral_root"]["path"]),
        Path(plan.raw["transaction_root"]["path"]),
    ):
        ensure_within(bound_root, lane_root, must_exist=True)

    if isinstance(adapter_manifest, AdapterManifest):
        manifest = adapter_manifest
    else:
        manifest = AdapterManifest.from_dict(dict(adapter_manifest))
    manifest_hash, implementation_hash = _context_manifest(manifest, plan)

    activation_delta = plan.raw["launch"]
    base_argv = list(manifest.raw["yolo_mapping"]["launch_argv"])
    additive_argv = list(activation_delta["argv"])
    if set(base_argv) & set(additive_argv):
        raise IdentityError("activation argv overlaps the adapter base mapping")
    argv = [*base_argv, *additive_argv]

    value_refs = {
        "true_literal": "true",
        "config_root_path": str(config),
    }
    bindings: Dict[str, str] = {}
    for symbolic in activation_delta["env"]:
        try:
            resolved = value_refs[symbolic["value_ref"]]
        except KeyError as exc:
            raise IdentityError(
                "activation environment binding is unsupported"
            ) from exc
        if symbolic["name"] in bindings:
            raise IdentityError("activation environment binding is duplicated")
        bindings[symbolic["name"]] = resolved

    environment, launch_identity = build_launch_identity(
        target="claude",
        repo=workspace,
        argv=argv,
        source_environment=source_environment,
        bindings=bindings,
        admitted_lane_root=lane_root,
    )
    manifest.verify_launch_execution_environment(environment)
    admitted_plan = build_admitted_launch_plan(
        target="claude",
        session=session,
        run_id=run_id,
        repo=workspace,
        argv=argv,
        environment=environment,
        admitted_lane_root=lane_root,
    )
    validated_admitted = validate_admitted_launch_plan(
        admitted_plan,
        expected_target="claude",
        expected_session=session,
        expected_run_id=run_id,
    )
    if (
        validated_admitted["argv"] != argv
        or validated_admitted["launch_identity"] != launch_identity
    ):
        raise IdentityError("admitted launch plan changed during activation join")

    context = ActivationLaunchContext(
        target="claude",
        session=session,
        run_id=run_id,
        session_profile=session_profile,
        adapter_manifest_sha256=manifest_hash,
        adapter_implementation_sha256=implementation_hash,
        activation_plan_sha256=plan.plan_sha256,
        activation_receipt_sha256=sha256_bytes(canonical_json_bytes(dict(receipt))),
        activation_delta_sha256=plan.raw["launch_plan_sha256"],
        artifact_sha256=receipt["artifact"]["sha256"],
        workspace_root_sha256=sha256_bytes(
            canonical_json_bytes(plan.raw["workspace_root"])
        ),
        config_root_sha256=sha256_bytes(canonical_json_bytes(plan.raw["config_root"])),
        admitted_lane_root_sha256=sha256_bytes(canonical_json_bytes(lane_identity)),
        admitted_launch_plan_sha256=sha256_bytes(canonical_json_bytes(admitted_plan)),
        _argv=tuple(argv),
        _environment_items=tuple(sorted(environment.items())),
        _launch_identity_json=canonical_json_bytes(launch_identity),
        _admitted_launch_plan_json=canonical_json_bytes(admitted_plan),
    )
    context.verify_launch_values(argv=argv, environment=environment)
    return context


def _canonical_context_mapping(value: Any, *, label: str) -> bytes:
    if not isinstance(value, Mapping):
        raise ValidationError("%s must be a mapping" % label)
    try:
        return canonical_json_bytes(dict(value))
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValidationError("%s is not canonical JSON" % label) from exc


def revalidate_activation_launch_context(
    context: ActivationLaunchContext,
    plan: ActivationPlan,
    *,
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    workspace_root: Path | str,
    config_root: Path | str,
    admitted_lane_root: Path | str,
    argv: Sequence[str],
    environment: Mapping[str, str],
    admitted_launch_plan: Mapping[str, Any],
    public_context: Mapping[str, Any],
) -> ActivationLaunchContext:
    """Re-prove and rebuild one context immediately before consumption.

    This starts no process and writes no state.  Callers must consume only the
    returned context after this function succeeds; the earlier context remains
    an untrusted preflight snapshot.
    """

    if not isinstance(context, ActivationLaunchContext):
        raise ValidationError("activation launch context is invalid")

    # Rebuilding performs the durable checks first: verify_activation reopens
    # the transaction and all plan-bound roots and rechecks the exact receipt,
    # artifact inode/content, while _context_manifest rechecks the canonical
    # manifest, execution files, and current controller implementation.
    current = build_activation_launch_context(
        plan,
        adapter_manifest=adapter_manifest,
        session=context.session,
        run_id=context.run_id,
        session_profile=context.session_profile,
        workspace_root=workspace_root,
        config_root=config_root,
        admitted_lane_root=admitted_lane_root,
        source_environment=environment,
    )

    context.verify_launch_values(argv=argv, environment=environment)
    current.verify_launch_values(argv=argv, environment=environment)
    live_identity = public_launch_identity(
        repo=Path(current.launch_identity["cwd"]),
        argv=argv,
        environment=environment,
        admitted_lane_root=Path(admitted_lane_root),
    )
    if (
        live_identity != context.launch_identity
        or live_identity != current.launch_identity
    ):
        raise IdentityError("activation public launch identity changed")

    supplied_admitted_bytes = _canonical_context_mapping(
        admitted_launch_plan,
        label="admitted launch plan",
    )
    context_admitted_bytes = canonical_json_bytes(context.admitted_launch_plan)
    current_admitted_bytes = canonical_json_bytes(current.admitted_launch_plan)
    if (
        sha256_bytes(context_admitted_bytes) != context.admitted_launch_plan_sha256
        or sha256_bytes(current_admitted_bytes) != current.admitted_launch_plan_sha256
        or supplied_admitted_bytes != context_admitted_bytes
        or context_admitted_bytes != current_admitted_bytes
    ):
        raise IdentityError("admitted launch plan changed before consumption")
    validated_admitted = validate_admitted_launch_plan(
        dict(admitted_launch_plan),
        expected_target=context.target,
        expected_session=context.session,
        expected_run_id=context.run_id,
    )
    if validated_admitted["launch_identity"] != live_identity:
        raise IdentityError("admitted launch identity changed before consumption")

    supplied_public_bytes = _canonical_context_mapping(
        public_context,
        label="activation public context",
    )
    context_public_bytes = canonical_json_bytes(context.to_public_dict())
    current_public_bytes = canonical_json_bytes(current.to_public_dict())
    if (
        sha256_bytes(supplied_public_bytes) != context.public_context_sha256
        or context.public_context_sha256 != current.public_context_sha256
        or supplied_public_bytes != context_public_bytes
        or context_public_bytes != current_public_bytes
    ):
        raise IdentityError("activation public context changed before consumption")
    return current


def _intent_for(plan: ActivationPlan) -> Dict[str, Any]:
    return {"schema": INTENT_SCHEMA, "plan": plan.to_dict()}


def _validate_intent(value: Mapping[str, Any]) -> ActivationPlan:
    if not isinstance(value, Mapping):
        raise ValidationError("activation intent fields are invalid")
    if value.get("schema") != INTENT_SCHEMA:
        raise ValidationError("activation intent schema is unsupported")
    if set(value) != {"schema", "plan"}:
        raise ValidationError("activation intent fields are invalid")
    validate_bounded_json(dict(value), max_depth=8, max_items=64, max_string=4096)
    return ActivationPlan.from_dict(value["plan"])


def _transaction_entries(descriptor: int) -> set[str]:
    entries = set(os.listdir(descriptor))
    allowed = {
        INTENT_FILENAME,
        RECEIPT_FILENAME,
        ROLLBACK_FILENAME,
        ROLLBACK_INTENT_FILENAME,
    }
    if not entries <= allowed:
        raise ConflictError("transaction root contains unexpected entries")
    return entries


def _open_or_create_parents(
    root_descriptor: int, paths: Sequence[str]
) -> Tuple[int, list[Dict[str, Any]]]:
    current = os.dup(root_descriptor)
    created: list[Dict[str, Any]] = []
    try:
        for relative_path in paths:
            name = relative_path.split("/")[-1]
            try:
                os.mkdir(name, _DIR_MODE, dir_fd=current)
            except FileExistsError as exc:
                raise ConflictError("activation parent path collided") from exc
            child: Optional[int] = None
            created_identity: Optional[Dict[str, Any]] = None
            try:
                lexical = os.stat(name, dir_fd=current, follow_symlinks=False)
                if not stat.S_ISDIR(lexical.st_mode) or lexical.st_uid != os.getuid():
                    raise IdentityError("activation parent creation identity is unsafe")
                created_identity = _created_directory_identity(
                    lexical, relative_path=relative_path
                )
                child = os.open(name, _DIRECTORY_FLAGS, dir_fd=current)
                opened = os.fstat(child)
                if (opened.st_dev, opened.st_ino) != (
                    created_identity["device"],
                    created_identity["inode"],
                ):
                    raise IdentityError("activation parent changed while opening")
                os.fchmod(child, _DIR_MODE)
                details = os.fstat(child)
                identity = _created_directory_identity(
                    details, relative_path=relative_path
                )
                if identity["uid"] != os.getuid() or identity["mode"] != _DIR_MODE:
                    raise IdentityError("activation parent is not current-UID 0700")
                os.fsync(current)
            except Exception as exc:
                if child is not None:
                    os.close(child)
                    child = None
                cleanup_error: Optional[Exception] = None
                try:
                    live = _safe_stat_at(current, name)
                    if (
                        created_identity is None
                        or live is None
                        or not stat.S_ISDIR(live.st_mode)
                        or live.st_uid != os.getuid()
                        or (live.st_dev, live.st_ino)
                        != (
                            created_identity["device"],
                            created_identity["inode"],
                        )
                    ):
                        raise IdentityError(
                            "failed activation parent changed before cleanup"
                        )
                    os.rmdir(name, dir_fd=current)
                    os.fsync(current)
                except Exception as cleanup_exc:
                    cleanup_error = cleanup_exc
                if cleanup_error is not None:
                    raise IdentityError(
                        "activation parent failed and exact cleanup was blocked"
                    ) from cleanup_error
                if isinstance(exc, IdentityError):
                    raise
                raise IdentityError(
                    "activation parent cannot be opened safely"
                ) from exc

            assert child is not None
            created.append(identity)
            os.close(current)
            current = child
        return current, created
    except Exception:
        os.close(current)
        if created:
            try:
                _remove_created_directories(
                    root_descriptor, created, compare_nlink=False
                )
            except Exception as cleanup_exc:
                raise IdentityError(
                    "activation parent creation failed and cleanup was blocked"
                ) from cleanup_exc
        raise


def _artifact_from_fd(
    descriptor: int, *, artifact_id: str, relative_path: str
) -> Dict[str, Any]:
    details = os.fstat(descriptor)
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) != _FILE_MODE
        or details.st_nlink != 1
    ):
        raise IdentityError("artifact is not current-UID 0600 with one link")
    return {
        "artifact_id": artifact_id,
        "relative_path": relative_path,
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "gid": details.st_gid,
        "mode": stat.S_IMODE(details.st_mode),
        "nlink": details.st_nlink,
        "size": details.st_size,
        "sha256": _sha256_fd(descriptor),
    }


def _open_parent_from_root(
    root_descriptor: int,
    parent_parts: Sequence[str],
    *,
    allow_missing: bool = False,
) -> Optional[int]:
    return _open_parent_from_root_impl(
        root_descriptor, parent_parts, allow_missing=allow_missing
    )


def _directory_live_at(root_descriptor: int, relative_path: str) -> Dict[str, Any]:
    parts = _relative_parts(relative_path, label="created directory path")
    parent = _open_parent_from_root(root_descriptor, parts[:-1])
    try:
        details = _safe_stat_at(parent, parts[-1])
        if details is None or stat.S_ISLNK(details.st_mode):
            raise IdentityError("created directory changed")
        return _created_directory_identity(details, relative_path=relative_path)
    finally:
        os.close(parent)


def _remove_created_directories(
    root_descriptor: int,
    created: Sequence[Mapping[str, Any]],
    *,
    compare_nlink: bool,
    allow_missing: bool = False,
) -> None:
    for expected in reversed(created):
        parts = _relative_parts(
            expected["relative_path"], label="created directory path"
        )
        parent = _open_parent_from_root(
            root_descriptor, parts[:-1], allow_missing=allow_missing
        )
        try:
            if parent is None:
                if allow_missing:
                    continue
                raise IdentityError("transaction-created directory changed")
            details = _safe_stat_at(parent, parts[-1])
            if details is None or stat.S_ISLNK(details.st_mode):
                if allow_missing:
                    continue
                raise IdentityError("transaction-created directory changed")
            live = _created_directory_identity(
                details, relative_path=expected["relative_path"]
            )
            keys = (
                _CREATED_DIRECTORY_KEYS
                if compare_nlink
                else (_CREATED_DIRECTORY_KEYS - {"nlink"})
            )
            if any(live[key] != expected[key] for key in keys):
                raise IdentityError("transaction-created directory identity changed")
            confirmed = _safe_stat_at(parent, parts[-1])
            if confirmed is None or stat.S_ISLNK(confirmed.st_mode):
                raise IdentityError("transaction-created directory changed")
            confirmed_live = _created_directory_identity(
                confirmed, relative_path=expected["relative_path"]
            )
            if any(confirmed_live[key] != expected[key] for key in keys):
                raise IdentityError("transaction-created directory changed")
            try:
                os.rmdir(parts[-1], dir_fd=parent)
            except OSError as exc:
                raise IdentityError(
                    "transaction-created directory is not empty"
                ) from exc
            os.fsync(parent)
            if _safe_stat_at(parent, parts[-1]) is not None:
                raise IdentityError("directory removal could not be proven")
        finally:
            os.close(parent)


def _cleanup_failed_materialization(
    plan: ActivationPlan,
    *,
    artifact: Optional[Mapping[str, Any]],
    created: Sequence[Mapping[str, Any]],
) -> None:
    root = _open_bound_root(
        plan.raw["ephemeral_root"],
        label="ephemeral root",
        private=True,
        compare_nlink=False,
    )
    try:
        if artifact is not None:
            parts = _relative_parts(artifact["relative_path"], label="artifact path")
            parent = _open_parent_from_root(root, parts[:-1])
            try:
                descriptor = os.open(parts[-1], _READ_FLAGS, dir_fd=parent)
                try:
                    _unlink_open_leaf(
                        parent,
                        parts[-1],
                        descriptor,
                        expected_device=artifact["device"],
                        expected_inode=artifact["inode"],
                        expected=artifact,
                    )
                finally:
                    os.close(descriptor)
            finally:
                os.close(parent)
        _remove_created_directories(root, created, compare_nlink=False)
        if os.listdir(root):
            raise IdentityError("failed activation left ambiguous root content")
        final = _stat_directory_identity(
            os.fstat(root), path=plan.raw["ephemeral_root"]["path"]
        )
        _assert_identity(final, plan.raw["ephemeral_root"], label="ephemeral root")
    finally:
        os.close(root)


def _receipt_for(
    plan: ActivationPlan,
    *,
    root_after: Mapping[str, Any],
    artifact: Mapping[str, Any],
    created: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    intent = _intent_for(plan)
    return {
        "schema": RECEIPT_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "intent_sha256": sha256_bytes(canonical_json_bytes(intent)),
        "descriptor_sha256": plan.raw["descriptor_sha256"],
        "instruction_manifest_sha256": plan.raw["instruction_manifest_sha256"],
        "effective_contract_fingerprint": plan.raw["effective_contract_fingerprint"],
        "effective_contract_sha256": plan.raw["effective_contract_sha256"],
        "adapter_manifest_sha256": plan.raw["adapter_manifest_sha256"],
        "adapter_implementation_sha256": plan.raw["adapter_implementation_sha256"],
        "version_observation_sha256": plan.raw["version_observation_sha256"],
        "launch_plan_sha256": plan.raw["launch_plan_sha256"],
        "root_before": plan.raw["ephemeral_root"],
        "root_after": dict(root_after),
        "artifact": dict(artifact),
        "created_directories": [dict(item) for item in created],
    }


def _validate_receipt(value: Mapping[str, Any], plan: ActivationPlan) -> Dict[str, Any]:
    keys = {
        "schema",
        "plan_sha256",
        "intent_sha256",
        "descriptor_sha256",
        "instruction_manifest_sha256",
        "effective_contract_fingerprint",
        "effective_contract_sha256",
        "adapter_manifest_sha256",
        "adapter_implementation_sha256",
        "version_observation_sha256",
        "launch_plan_sha256",
        "root_before",
        "root_after",
        "artifact",
        "created_directories",
    }
    if not isinstance(value, Mapping):
        raise ValidationError("activation receipt fields are invalid")
    if value.get("schema") != RECEIPT_SCHEMA:
        raise ValidationError("activation receipt schema is unsupported")
    if set(value) != keys:
        raise ValidationError("activation receipt fields are invalid")
    validate_bounded_json(dict(value), max_depth=8, max_items=64, max_string=4096)
    expected_hashes = {
        "plan_sha256": plan.plan_sha256,
        "intent_sha256": sha256_bytes(canonical_json_bytes(_intent_for(plan))),
        "descriptor_sha256": plan.raw["descriptor_sha256"],
        "instruction_manifest_sha256": plan.raw["instruction_manifest_sha256"],
        "effective_contract_fingerprint": plan.raw["effective_contract_fingerprint"],
        "effective_contract_sha256": plan.raw["effective_contract_sha256"],
        "adapter_manifest_sha256": plan.raw["adapter_manifest_sha256"],
        "adapter_implementation_sha256": plan.raw["adapter_implementation_sha256"],
        "version_observation_sha256": plan.raw["version_observation_sha256"],
        "launch_plan_sha256": plan.raw["launch_plan_sha256"],
    }
    for key, expected in expected_hashes.items():
        supplied = validate_sha256(value[key], key.replace("_", " "))
        if supplied != expected:
            raise IdentityError("activation receipt binding changed")
    before = _validate_directory_identity(
        value["root_before"], label="receipt root before", private=True
    )
    after = _validate_directory_identity(
        value["root_after"], label="receipt root after", private=True
    )
    if before != plan.raw["ephemeral_root"]:
        raise IdentityError("activation receipt root binding changed")
    if any(after[key] != before[key] for key in _DIRECTORY_IDENTITY_KEYS - {"nlink"}):
        raise IdentityError("activation receipt root identity changed")
    artifact = _validate_artifact(value["artifact"])
    if (
        artifact["artifact_id"] != plan.raw["artifact_id"]
        or artifact["relative_path"] != plan.raw["artifact_relative_path"]
        or artifact["sha256"] != plan.raw["effective_contract_sha256"]
        or artifact["size"] != plan.raw["effective_contract_bytes"]
    ):
        raise IdentityError("activation receipt artifact binding changed")
    created_raw = value["created_directories"]
    if not isinstance(created_raw, list):
        raise ValidationError("created directories must be a list")
    created = [_validate_created_directory(item) for item in created_raw]
    if [item["relative_path"] for item in created] != plan.raw[
        "created_directory_paths"
    ]:
        raise IdentityError("activation receipt directory binding changed")
    return {
        "schema": RECEIPT_SCHEMA,
        **expected_hashes,
        "root_before": before,
        "root_after": after,
        "artifact": artifact,
        "created_directories": created,
    }


def _verify_tree_inventory(root_descriptor: int, parts: Sequence[str]) -> None:
    current = os.dup(root_descriptor)
    try:
        for index, name in enumerate(parts):
            if set(os.listdir(current)) != {name}:
                raise IdentityError("activation root contains unexpected content")
            if index < len(parts) - 1:
                try:
                    child = os.open(name, _DIRECTORY_FLAGS, dir_fd=current)
                except OSError as exc:
                    raise IdentityError("activation tree changed") from exc
                os.close(current)
                current = child
    finally:
        os.close(current)


def _verify_active_with_root(
    plan: ActivationPlan, receipt: Mapping[str, Any]
) -> Dict[str, Any]:
    normalized = _validate_receipt(receipt, plan)
    workspace = _open_bound_root(
        plan.raw["workspace_root"],
        label="workspace root",
        private=False,
        compare_nlink=False,
    )
    os.close(workspace)
    config = _open_bound_root(
        plan.raw["config_root"],
        label="config root",
        private=True,
        compare_nlink=False,
    )
    os.close(config)
    root = _open_bound_root(
        normalized["root_after"], label="ephemeral root", private=True
    )
    try:
        parts = _relative_parts(
            plan.raw["artifact_relative_path"], label="artifact path"
        )
        _verify_tree_inventory(root, parts)
        for expected in normalized["created_directories"]:
            live = _directory_live_at(root, expected["relative_path"])
            if live != expected:
                raise IdentityError("transaction-created directory changed")
        parent = _open_parent_from_root(root, parts[:-1])
        try:
            try:
                artifact_descriptor = os.open(parts[-1], _READ_FLAGS, dir_fd=parent)
            except OSError as exc:
                raise IdentityError("activation artifact is missing or unsafe") from exc
            try:
                live_artifact = _artifact_from_fd(
                    artifact_descriptor,
                    artifact_id=plan.raw["artifact_id"],
                    relative_path=plan.raw["artifact_relative_path"],
                )
            finally:
                os.close(artifact_descriptor)
        finally:
            os.close(parent)
        if live_artifact != normalized["artifact"]:
            raise IdentityError("activation artifact identity or content changed")
        return normalized
    finally:
        os.close(root)


def _load_intent_from_tx(transaction_descriptor: int) -> ActivationPlan:
    try:
        value = _read_named_json(
            transaction_descriptor, INTENT_FILENAME, label="activation intent"
        )
    except FileNotFoundError as exc:
        raise ValidationError("activation intent is missing") from exc
    return _validate_intent(value)


def load_activation_plan(transaction_root: Path | str) -> ActivationPlan:
    """Load and validate the body-free immutable intent for a transaction."""
    transaction_descriptor, _ = _open_root(
        transaction_root, label="transaction root", private=True
    )
    try:
        plan = _load_intent_from_tx(transaction_descriptor)
        expected = plan.raw["transaction_root"]
        live = _stat_directory_identity(
            os.fstat(transaction_descriptor), path=expected["path"]
        )
        _assert_identity(live, expected, label="transaction root", compare_nlink=False)
        return plan
    finally:
        os.close(transaction_descriptor)


def _validate_contract_for_plan(
    plan: ActivationPlan, effective_contract: bytes
) -> None:
    if not isinstance(effective_contract, bytes) or not effective_contract:
        raise ValidationError("effective contract must be non-empty bytes")
    if (
        len(effective_contract) != plan.raw["effective_contract_bytes"]
        or sha256_bytes(effective_contract) != plan.raw["effective_contract_sha256"]
    ):
        raise IdentityError("effective contract changed after planning")


def materialize_activation(
    plan: ActivationPlan, *, effective_contract: bytes
) -> Dict[str, Any]:
    """Persist intent first, then create and prove the single private artifact."""
    plan = ActivationPlan.from_dict(plan.to_dict())
    _validate_contract_for_plan(plan, effective_contract)
    transaction = _open_bound_root(
        plan.raw["transaction_root"],
        label="transaction root",
        private=True,
        compare_nlink=False,
    )
    try:
        workspace = _open_bound_root(
            plan.raw["workspace_root"],
            label="workspace root",
            private=False,
            compare_nlink=False,
        )
        os.close(workspace)
        config = _open_bound_root(
            plan.raw["config_root"],
            label="config root",
            private=True,
            compare_nlink=False,
        )
        os.close(config)
        entries = _transaction_entries(transaction)
        if ROLLBACK_FILENAME in entries:
            raise ConflictError("rolled-back activation cannot be materialized again")
        if RECEIPT_FILENAME in entries:
            if INTENT_FILENAME not in entries:
                raise IdentityError("activation receipt exists without intent")
            loaded = _load_intent_from_tx(transaction)
            if loaded.to_dict() != plan.to_dict():
                raise IdentityError("activation intent does not match the plan")
            receipt = _read_named_json(
                transaction, RECEIPT_FILENAME, label="activation receipt"
            )
            return _verify_active_with_root(plan, receipt)
        if entries not in (set(), {INTENT_FILENAME}):
            raise ConflictError("transaction state is not materializable")

        _persist_immutable_json(
            transaction,
            INTENT_FILENAME,
            _intent_for(plan),
            label="activation intent",
        )
        loaded = _load_intent_from_tx(transaction)
        if loaded.to_dict() != plan.to_dict():
            raise IdentityError("persisted activation intent changed")

        root = _open_bound_root(
            plan.raw["ephemeral_root"],
            label="ephemeral root",
            private=True,
            empty=True,
        )
        created: list[Dict[str, Any]] = []
        artifact: Optional[Dict[str, Any]] = None
        receipt_committed = False
        try:
            parent, created = _open_or_create_parents(
                root, plan.raw["created_directory_paths"]
            )
            try:
                leaf = _relative_parts(
                    plan.raw["artifact_relative_path"], label="artifact path"
                )[-1]
                try:
                    artifact_descriptor = os.open(
                        leaf, _CREATE_FLAGS, _FILE_MODE, dir_fd=parent
                    )
                except FileExistsError as exc:
                    raise ConflictError("activation artifact path collided") from exc
                created_leaf: Optional[Tuple[int, int]] = None
                try:
                    created_leaf = _new_leaf_identity(artifact_descriptor)
                    os.fchmod(artifact_descriptor, _FILE_MODE)
                    initial = os.fstat(artifact_descriptor)
                    if (initial.st_dev, initial.st_ino) != created_leaf:
                        raise IdentityError("artifact changed during mode setup")
                    artifact = {
                        "artifact_id": plan.raw["artifact_id"],
                        "relative_path": plan.raw["artifact_relative_path"],
                        "device": initial.st_dev,
                        "inode": initial.st_ino,
                        "uid": initial.st_uid,
                        "gid": initial.st_gid,
                        "mode": stat.S_IMODE(initial.st_mode),
                        "nlink": initial.st_nlink,
                        "size": initial.st_size,
                        "sha256": sha256_bytes(b""),
                    }
                    if (
                        not stat.S_ISREG(initial.st_mode)
                        or initial.st_uid != os.getuid()
                        or stat.S_IMODE(initial.st_mode) != _FILE_MODE
                        or initial.st_nlink != 1
                    ):
                        raise IdentityError("artifact creation identity is unsafe")
                    _write_contract_bytes(artifact_descriptor, effective_contract)
                    os.fsync(artifact_descriptor)
                    artifact = _artifact_from_fd(
                        artifact_descriptor,
                        artifact_id=plan.raw["artifact_id"],
                        relative_path=plan.raw["artifact_relative_path"],
                    )
                    if (
                        artifact["sha256"] != plan.raw["effective_contract_sha256"]
                        or artifact["size"] != plan.raw["effective_contract_bytes"]
                    ):
                        raise IdentityError("materialized artifact hash changed")
                except Exception:
                    if created_leaf is None:
                        try:
                            created_leaf = _new_leaf_identity(artifact_descriptor)
                        except Exception:
                            pass
                    if created_leaf is not None:
                        try:
                            _unlink_new_leaf(
                                parent,
                                leaf,
                                artifact_descriptor,
                                expected_device=created_leaf[0],
                                expected_inode=created_leaf[1],
                            )
                            artifact = None
                        except Exception:
                            pass
                    raise
                finally:
                    os.close(artifact_descriptor)
                os.fsync(parent)
            finally:
                os.close(parent)

            # Parent nlink values may have changed as deeper parents were created.
            created = [
                _directory_live_at(root, path)
                for path in plan.raw["created_directory_paths"]
            ]
            root_after = _stat_directory_identity(
                os.fstat(root), path=plan.raw["ephemeral_root"]["path"]
            )
            receipt = _receipt_for(
                plan,
                root_after=root_after,
                artifact=artifact,
                created=created,
            )
            _verify_active_with_root(plan, receipt)
            _persist_immutable_json(
                transaction,
                RECEIPT_FILENAME,
                receipt,
                label="activation receipt",
            )
            receipt_committed = True
            persisted = _read_named_json(
                transaction, RECEIPT_FILENAME, label="activation receipt"
            )
            return _verify_active_with_root(plan, persisted)
        except Exception:
            if receipt_committed:
                raise
            try:
                _cleanup_failed_materialization(
                    plan, artifact=artifact, created=created
                )
            except Exception as cleanup_exc:
                raise IdentityError(
                    "activation failed and exact cleanup was blocked"
                ) from cleanup_exc
            raise
        finally:
            os.close(root)
    finally:
        os.close(transaction)


def verify_activation(plan: ActivationPlan) -> Dict[str, Any]:
    """Verify intent, receipt, roots, directories, and artifact exactly."""
    plan = ActivationPlan.from_dict(plan.to_dict())
    transaction = _open_bound_root(
        plan.raw["transaction_root"],
        label="transaction root",
        private=True,
        compare_nlink=False,
    )
    try:
        entries = _transaction_entries(transaction)
        if entries != {INTENT_FILENAME, RECEIPT_FILENAME}:
            raise ConflictError("activation transaction is not in active state")
        intent = _load_intent_from_tx(transaction)
        if intent.to_dict() != plan.to_dict():
            raise IdentityError("activation intent does not match the plan")
        receipt = _read_named_json(
            transaction, RECEIPT_FILENAME, label="activation receipt"
        )
        return _verify_active_with_root(plan, receipt)
    finally:
        os.close(transaction)


def _rollback_for(
    plan: ActivationPlan,
    receipt: Mapping[str, Any],
    *,
    removed_directories: Sequence[str],
    root_after: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "schema": ROLLBACK_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "activation_receipt_sha256": sha256_bytes(canonical_json_bytes(dict(receipt))),
        "artifact_sha256": plan.raw["effective_contract_sha256"],
        "artifact_state": "absent",
        "removed_directories": list(removed_directories),
        "root_after": dict(root_after),
    }


def _rollback_intent_for(
    plan: ActivationPlan, receipt: Mapping[str, Any]
) -> Dict[str, Any]:
    return {
        "schema": ROLLBACK_INTENT_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "activation_receipt_sha256": sha256_bytes(canonical_json_bytes(dict(receipt))),
        "artifact_state": "absent",
        "artifact_sha256": plan.raw["effective_contract_sha256"],
        "artifact": dict(receipt["artifact"]),
        "created_directories": [dict(item) for item in receipt["created_directories"]],
        "root_before": dict(receipt["root_after"]),
    }


def _validate_rollback_intent(
    value: Mapping[str, Any], plan: ActivationPlan, receipt: Mapping[str, Any]
) -> Dict[str, Any]:
    keys = {
        "schema",
        "plan_sha256",
        "activation_receipt_sha256",
        "artifact_state",
        "artifact_sha256",
        "artifact",
        "created_directories",
        "root_before",
    }
    if not isinstance(value, Mapping):
        raise ValidationError("rollback intent fields are invalid")
    if value.get("schema") != ROLLBACK_INTENT_SCHEMA:
        raise ValidationError("rollback intent schema is unsupported")
    if set(value) != keys:
        raise ValidationError("rollback intent fields are invalid")
    if value["artifact_state"] != "absent":
        raise ValidationError("rollback intent is invalid")
    validate_bounded_json(dict(value), max_depth=6, max_items=64, max_string=4096)
    expected = {
        "plan_sha256": plan.plan_sha256,
        "activation_receipt_sha256": sha256_bytes(canonical_json_bytes(dict(receipt))),
        "artifact_sha256": plan.raw["effective_contract_sha256"],
    }
    for key, digest in expected.items():
        if validate_sha256(value[key], key.replace("_", " ")) != digest:
            raise IdentityError("rollback intent binding changed")
    artifact = _validate_artifact(value["artifact"])
    if artifact != receipt["artifact"]:
        raise IdentityError("rollback intent artifact binding changed")
    created_raw = value["created_directories"]
    if not isinstance(created_raw, list):
        raise ValidationError("rollback intent directories are invalid")
    created = [_validate_created_directory(item) for item in created_raw]
    if created != receipt["created_directories"]:
        raise IdentityError("rollback intent directory binding changed")
    root_before = _validate_directory_identity(
        value["root_before"], label="rollback intent root", private=True
    )
    if root_before != receipt["root_after"]:
        raise IdentityError("rollback intent root binding changed")
    return {
        "schema": ROLLBACK_INTENT_SCHEMA,
        **expected,
        "artifact_state": "absent",
        "artifact": artifact,
        "created_directories": created,
        "root_before": root_before,
    }


def _perform_rollback_cleanup(
    plan: ActivationPlan, receipt: Mapping[str, Any], *, allow_missing: bool
) -> Dict[str, Any]:
    root = _open_bound_root(
        receipt["root_after"],
        label="ephemeral root",
        private=True,
        compare_nlink=not allow_missing,
    )
    try:
        parts = _relative_parts(
            plan.raw["artifact_relative_path"], label="artifact path"
        )
        parent = _open_parent_from_root(root, parts[:-1], allow_missing=allow_missing)
        try:
            if parent is None:
                if not allow_missing:
                    raise IdentityError("activation artifact parent changed")
            else:
                try:
                    descriptor = os.open(parts[-1], _READ_FLAGS, dir_fd=parent)
                except FileNotFoundError:
                    if not allow_missing:
                        raise IdentityError("activation artifact is missing or unsafe")
                except OSError as exc:
                    raise IdentityError(
                        "activation artifact is missing or unsafe"
                    ) from exc
                else:
                    try:
                        live = _artifact_from_fd(
                            descriptor,
                            artifact_id=plan.raw["artifact_id"],
                            relative_path=plan.raw["artifact_relative_path"],
                        )
                        if live != receipt["artifact"]:
                            raise IdentityError(
                                "activation artifact changed before rollback"
                            )
                        _unlink_open_leaf(
                            parent,
                            parts[-1],
                            descriptor,
                            expected_device=live["device"],
                            expected_inode=live["inode"],
                            expected=live,
                        )
                    finally:
                        os.close(descriptor)
        finally:
            if parent is not None:
                os.close(parent)

        _remove_created_directories(
            root,
            receipt["created_directories"],
            compare_nlink=False,
            allow_missing=allow_missing,
        )
        if os.listdir(root):
            raise IdentityError("ephemeral root is not empty after rollback")
        root_after = _stat_directory_identity(
            os.fstat(root), path=plan.raw["ephemeral_root"]["path"]
        )
        _assert_identity(
            root_after,
            plan.raw["ephemeral_root"],
            label="ephemeral root",
            compare_nlink=not allow_missing,
        )
        return root_after
    finally:
        os.close(root)


def _validate_rollback_receipt(
    value: Mapping[str, Any], plan: ActivationPlan, receipt: Mapping[str, Any]
) -> Dict[str, Any]:
    keys = {
        "schema",
        "plan_sha256",
        "activation_receipt_sha256",
        "artifact_sha256",
        "artifact_state",
        "removed_directories",
        "root_after",
    }
    if not isinstance(value, Mapping):
        raise ValidationError("rollback receipt fields are invalid")
    if value.get("schema") != ROLLBACK_SCHEMA:
        raise ValidationError("rollback receipt schema is unsupported")
    if set(value) != keys:
        raise ValidationError("rollback receipt fields are invalid")
    if value["artifact_state"] != "absent":
        raise ValidationError("rollback receipt is invalid")
    validate_bounded_json(dict(value), max_depth=6, max_items=64, max_string=4096)
    expected = {
        "plan_sha256": plan.plan_sha256,
        "activation_receipt_sha256": sha256_bytes(canonical_json_bytes(dict(receipt))),
        "artifact_sha256": plan.raw["effective_contract_sha256"],
    }
    for key, digest in expected.items():
        if validate_sha256(value[key], key.replace("_", " ")) != digest:
            raise IdentityError("rollback receipt binding changed")
    removed = value["removed_directories"]
    if removed != list(reversed(plan.raw["created_directory_paths"])):
        raise IdentityError("rollback directory evidence changed")
    root_after = _validate_directory_identity(
        value["root_after"], label="rollback root", private=True
    )
    _assert_identity(
        root_after,
        plan.raw["ephemeral_root"],
        label="rollback root",
        compare_nlink=False,
    )
    return {
        "schema": ROLLBACK_SCHEMA,
        **expected,
        "artifact_state": "absent",
        "removed_directories": removed,
        "root_after": root_after,
    }


def _prove_rolled_back(
    plan: ActivationPlan,
    receipt: Mapping[str, Any],
    rollback: Mapping[str, Any],
) -> Dict[str, Any]:
    normalized = _validate_rollback_receipt(rollback, plan, receipt)
    root = _open_bound_root(
        plan.raw["ephemeral_root"],
        label="ephemeral root",
        private=True,
        empty=True,
    )
    try:
        parts = _relative_parts(
            plan.raw["artifact_relative_path"], label="artifact path"
        )
        if _safe_stat_at(root, parts[0]) is not None:
            raise IdentityError("rolled-back activation path reappeared")
    finally:
        os.close(root)
    return normalized


def validate_terminal_activation_evidence(
    activation: Mapping[str, Any],
    *,
    descriptor: Mapping[str, Any],
    intent: Mapping[str, Any],
    materialization_receipt: Mapping[str, Any],
    public_context: Mapping[str, Any],
    admitted_launch_plan: Mapping[str, Any],
    rollback_intent: Mapping[str, Any],
    rollback_receipt: Mapping[str, Any],
) -> Dict[str, Any]:
    """Validate one body-free, post-rollback activation proof family.

    Unlike :func:`verify_activation`, this validator intentionally runs after
    the native instruction artifact has been removed.  It joins the immutable
    descriptor, intent-embedded plan, materialization receipt, public launch
    context, admitted launch plan, rollback intent, rollback receipt, and the
    live empty activation root.  It never needs instruction bytes or private
    environment values.
    """

    activation_keys = {
        "schema",
        "qualification_scope",
        "terminal_state",
        "descriptor_sha256",
        "plan_sha256",
        "intent_sha256",
        "materialization_receipt_sha256",
        "launch_context_sha256",
        "artifact_sha256",
        "initial_trigger_sha256",
        "rollback_intent_sha256",
        "rollback_receipt_sha256",
    }
    if not isinstance(activation, Mapping) or set(activation) != activation_keys:
        raise ValidationError("probe plane activation fields are invalid")
    if (
        activation.get("schema") != PROBE_PLANE_ACTIVATION_SCHEMA
        or activation.get("qualification_scope") != ACTIVATION_LIFECYCLE_SCOPE
        or activation.get("terminal_state") != "rolled_back"
    ):
        raise ValidationError("probe plane activation state is invalid")
    validate_bounded_json(
        dict(activation),
        max_depth=3,
        max_items=32,
        max_string=4096,
        reject_sensitive_fields=True,
    )

    normalized_descriptor = validate_instruction_plane_descriptor(descriptor)
    if (
        normalized_descriptor["target"]["harness"] != "claude"
        or normalized_descriptor["plane"] != "per_run_additive"
        or normalized_descriptor["status"]
        != {"surface": "factual", "activation": "qualification_only"}
    ):
        raise IdentityError("terminal activation descriptor is not the Claude plane")
    _unsupported_descriptor(normalized_descriptor)

    plan = _validate_intent(intent)
    descriptor_target = normalized_descriptor["target"]
    descriptor_artifact = normalized_descriptor["materialize"][0]
    version_hash = _SUPPORTED_VERSION_OBSERVATIONS.get(
        (descriptor_target["harness"], descriptor_target["version"])
    )
    if (
        plan.raw["descriptor_id"] != normalized_descriptor["descriptor_id"]
        or plan.raw["adapter_manifest_sha256"]
        != descriptor_target["adapter_manifest_sha256"]
        or plan.raw["version_observation_sha256"] != version_hash
        or plan.raw["artifact_id"] != descriptor_artifact["artifact_id"]
        or plan.raw["artifact_relative_path"] != descriptor_artifact["relative_path"]
    ):
        raise IdentityError("terminal activation descriptor authority changed")
    normalized_receipt = _validate_receipt(materialization_receipt, plan)
    normalized_rollback_intent = _validate_rollback_intent(
        rollback_intent,
        plan,
        normalized_receipt,
    )
    normalized_rollback = _prove_rolled_back(
        plan,
        normalized_receipt,
        rollback_receipt,
    )
    if descriptor_fingerprint(normalized_descriptor) != plan.raw["descriptor_sha256"]:
        raise IdentityError("terminal activation descriptor binding changed")

    launch_plan = validate_admitted_launch_plan(
        admitted_launch_plan,
        expected_target="claude",
        expected_session=(
            public_context.get("session")
            if isinstance(public_context, Mapping)
            else None
        ),
        expected_run_id=(
            public_context.get("run_id")
            if isinstance(public_context, Mapping)
            else None
        ),
    )
    context_keys = {
        "schema",
        "target",
        "session",
        "run_id",
        "session_profile",
        "adapter_manifest_sha256",
        "adapter_implementation_sha256",
        "activation_plan_sha256",
        "activation_receipt_sha256",
        "activation_delta_sha256",
        "artifact_sha256",
        "workspace_root_sha256",
        "config_root_sha256",
        "admitted_lane_root_sha256",
        "project_isolation",
        "launch_identity",
        "admitted_launch_plan_sha256",
    }
    if not isinstance(public_context, Mapping) or set(public_context) != context_keys:
        raise ValidationError("activation public context fields are invalid")
    if (
        public_context.get("schema") != LAUNCH_CONTEXT_SCHEMA
        or public_context.get("target") != "claude"
        or public_context.get("session_profile") != "regular"
        or public_context.get("project_isolation")
        != "activation_bound_workspace_config_lane_roots"
    ):
        raise ValidationError("activation public context is invalid")
    validate_identifier(public_context.get("session"), "activation context session")
    validate_identifier(public_context.get("run_id"), "activation context run id")
    launch_identity = validate_public_launch_identity(
        public_context.get("launch_identity"),
        target="claude",
    )
    if launch_identity != launch_plan["launch_identity"]:
        raise IdentityError("terminal activation launch identity changed")

    lane_path = Path(
        os.path.commonpath(
            [
                plan.raw[name]["path"]
                for name in (
                    "workspace_root",
                    "config_root",
                    "ephemeral_root",
                    "transaction_root",
                )
            ]
        )
    )
    lane_descriptor, lane_identity = _open_root(
        lane_path,
        label="admitted lane root",
        private=True,
    )
    os.close(lane_descriptor)
    expected_context = {
        "adapter_manifest_sha256": plan.raw["adapter_manifest_sha256"],
        "adapter_implementation_sha256": plan.raw["adapter_implementation_sha256"],
        "activation_plan_sha256": plan.plan_sha256,
        "activation_receipt_sha256": sha256_bytes(
            canonical_json_bytes(normalized_receipt)
        ),
        "activation_delta_sha256": plan.raw["launch_plan_sha256"],
        "artifact_sha256": plan.raw["effective_contract_sha256"],
        "workspace_root_sha256": sha256_bytes(
            canonical_json_bytes(plan.raw["workspace_root"])
        ),
        "config_root_sha256": sha256_bytes(
            canonical_json_bytes(plan.raw["config_root"])
        ),
        "admitted_lane_root_sha256": sha256_bytes(canonical_json_bytes(lane_identity)),
        "admitted_launch_plan_sha256": sha256_bytes(
            canonical_json_bytes(dict(admitted_launch_plan))
        ),
    }
    for name, expected in expected_context.items():
        if (
            validate_sha256(public_context.get(name), name.replace("_", " "))
            != expected
        ):
            raise IdentityError("activation public context binding changed: %s" % name)

    expected_activation = {
        "schema": PROBE_PLANE_ACTIVATION_SCHEMA,
        "qualification_scope": ACTIVATION_LIFECYCLE_SCOPE,
        "terminal_state": "rolled_back",
        "descriptor_sha256": descriptor_fingerprint(normalized_descriptor),
        "plan_sha256": plan.plan_sha256,
        "intent_sha256": sha256_bytes(canonical_json_bytes(dict(intent))),
        "materialization_receipt_sha256": sha256_bytes(
            canonical_json_bytes(normalized_receipt)
        ),
        "launch_context_sha256": sha256_bytes(
            canonical_json_bytes(dict(public_context))
        ),
        "artifact_sha256": plan.raw["effective_contract_sha256"],
        "initial_trigger_sha256": CLAUDE_NATIVE_TRIGGER_SHA256,
        "rollback_intent_sha256": sha256_bytes(
            canonical_json_bytes(normalized_rollback_intent)
        ),
        "rollback_receipt_sha256": sha256_bytes(
            canonical_json_bytes(normalized_rollback)
        ),
    }
    for name in activation_keys - {
        "schema",
        "qualification_scope",
        "terminal_state",
    }:
        supplied = validate_sha256(activation.get(name), name.replace("_", " "))
        if supplied != expected_activation[name]:
            raise IdentityError("probe plane activation binding changed: %s" % name)
    if (
        expected_activation["initial_trigger_sha256"]
        == expected_activation["artifact_sha256"]
    ):
        raise IdentityError("native trigger duplicates the rendered contract")
    return expected_activation


def rollback_activation(plan: ActivationPlan) -> Dict[str, Any]:
    """Delete only the exact received artifact and transaction-created parents."""
    plan = ActivationPlan.from_dict(plan.to_dict())
    transaction = _open_bound_root(
        plan.raw["transaction_root"],
        label="transaction root",
        private=True,
        compare_nlink=False,
    )
    try:
        entries = _transaction_entries(transaction)
        if not {INTENT_FILENAME, RECEIPT_FILENAME} <= entries:
            raise ConflictError("active activation evidence is incomplete")
        intent = _load_intent_from_tx(transaction)
        if intent.to_dict() != plan.to_dict():
            raise IdentityError("activation intent does not match the plan")
        receipt_raw = _read_named_json(
            transaction, RECEIPT_FILENAME, label="activation receipt"
        )
        receipt = _validate_receipt(receipt_raw, plan)
        if ROLLBACK_FILENAME in entries:
            rollback = _read_named_json(
                transaction, ROLLBACK_FILENAME, label="rollback receipt"
            )
            return _prove_rolled_back(plan, receipt, rollback)
        if ROLLBACK_INTENT_FILENAME in entries:
            rollback_intent = _read_named_json(
                transaction, ROLLBACK_INTENT_FILENAME, label="rollback intent"
            )
            _validate_rollback_intent(rollback_intent, plan, receipt)
            root_after = _perform_rollback_cleanup(plan, receipt, allow_missing=True)
            rollback = _rollback_for(
                plan,
                receipt,
                removed_directories=list(reversed(plan.raw["created_directory_paths"])),
                root_after=root_after,
            )
            _persist_immutable_json(
                transaction,
                ROLLBACK_FILENAME,
                rollback,
                label="rollback receipt",
            )
            persisted = _read_named_json(
                transaction, ROLLBACK_FILENAME, label="rollback receipt"
            )
            return _prove_rolled_back(plan, receipt, persisted)
        if entries != {INTENT_FILENAME, RECEIPT_FILENAME}:
            raise ConflictError("activation transaction state is ambiguous")

        # Verify the complete active state, then persist write-ahead cleanup
        # authority before the first destructive operation.
        receipt = _verify_active_with_root(plan, receipt)
        rollback_intent = _rollback_intent_for(
            plan,
            receipt,
        )
        _persist_immutable_json(
            transaction,
            ROLLBACK_INTENT_FILENAME,
            rollback_intent,
            label="rollback intent",
        )
        persisted_intent = _read_named_json(
            transaction, ROLLBACK_INTENT_FILENAME, label="rollback intent"
        )
        _validate_rollback_intent(persisted_intent, plan, receipt)
        root_after = _perform_rollback_cleanup(plan, receipt, allow_missing=False)

        rollback = _rollback_for(
            plan,
            receipt,
            removed_directories=list(reversed(plan.raw["created_directory_paths"])),
            root_after=root_after,
        )
        _persist_immutable_json(
            transaction,
            ROLLBACK_FILENAME,
            rollback,
            label="rollback receipt",
        )
        persisted = _read_named_json(
            transaction, ROLLBACK_FILENAME, label="rollback receipt"
        )
        return _prove_rolled_back(plan, receipt, persisted)
    finally:
        os.close(transaction)


def recover_activation(transaction_root: Path | str) -> ActivationRecovery:
    """Classify a durable transaction; refuse any ambiguous partial artifact."""
    transaction_descriptor, _ = _open_root(
        transaction_root, label="transaction root", private=True
    )
    try:
        entries = _transaction_entries(transaction_descriptor)
        if INTENT_FILENAME not in entries:
            raise ValidationError("activation intent is missing")
        plan = _load_intent_from_tx(transaction_descriptor)
        expected_tx = plan.raw["transaction_root"]
        live_tx = _stat_directory_identity(
            os.fstat(transaction_descriptor), path=expected_tx["path"]
        )
        _assert_identity(
            live_tx,
            expected_tx,
            label="transaction root",
            compare_nlink=False,
        )
        if ROLLBACK_FILENAME in entries:
            if RECEIPT_FILENAME not in entries:
                raise IdentityError(
                    "rollback evidence exists without activation receipt"
                )
            receipt = _validate_receipt(
                _read_named_json(
                    transaction_descriptor,
                    RECEIPT_FILENAME,
                    label="activation receipt",
                ),
                plan,
            )
            rollback = _read_named_json(
                transaction_descriptor,
                ROLLBACK_FILENAME,
                label="rollback receipt",
            )
            normalized_rollback = _prove_rolled_back(plan, receipt, rollback)
            return ActivationRecovery(
                state="rolled_back",
                plan=plan,
                receipt=receipt,
                rollback_receipt=normalized_rollback,
            )
        if ROLLBACK_INTENT_FILENAME in entries:
            if RECEIPT_FILENAME not in entries:
                raise IdentityError(
                    "rollback evidence exists without activation receipt"
                )
            receipt = _validate_receipt(
                _read_named_json(
                    transaction_descriptor,
                    RECEIPT_FILENAME,
                    label="activation receipt",
                ),
                plan,
            )
            rollback_intent = _read_named_json(
                transaction_descriptor,
                ROLLBACK_INTENT_FILENAME,
                label="rollback intent",
            )
            _validate_rollback_intent(rollback_intent, plan, receipt)
            try:
                verified = _verify_active_with_root(plan, receipt)
            except IdentityError:
                root = _open_bound_root(
                    plan.raw["ephemeral_root"],
                    label="ephemeral root",
                    private=True,
                )
                try:
                    parts = _relative_parts(
                        plan.raw["artifact_relative_path"],
                        label="artifact path",
                    )
                    parent = _open_parent_from_root(
                        root,
                        parts[:-1],
                        allow_missing=True,
                    )
                    try:
                        if (
                            parent is not None
                            and _safe_stat_at(parent, parts[-1]) is not None
                        ):
                            raise IdentityError("rollback state is ambiguous")
                    finally:
                        if parent is not None:
                            os.close(parent)
                    if os.listdir(root):
                        raise IdentityError("rollback state is ambiguous")
                    root_after = _stat_directory_identity(
                        os.fstat(root),
                        path=plan.raw["ephemeral_root"]["path"],
                    )
                    _assert_identity(
                        root_after,
                        plan.raw["ephemeral_root"],
                        label="ephemeral root",
                    )
                    rollback = _rollback_for(
                        plan,
                        receipt,
                        removed_directories=list(
                            reversed(plan.raw["created_directory_paths"])
                        ),
                        root_after=root_after,
                    )
                    return ActivationRecovery(
                        state="rolled_back",
                        plan=plan,
                        receipt=receipt,
                        rollback_receipt=rollback,
                    )
                finally:
                    os.close(root)
            else:
                return ActivationRecovery(
                    state="active",
                    plan=plan,
                    receipt=verified,
                )
        if RECEIPT_FILENAME in entries:
            receipt = _verify_active_with_root(
                plan,
                _read_named_json(
                    transaction_descriptor,
                    RECEIPT_FILENAME,
                    label="activation receipt",
                ),
            )
            return ActivationRecovery(state="active", plan=plan, receipt=receipt)
        if entries != {INTENT_FILENAME}:
            raise IdentityError("activation transaction is ambiguous")
        root = _open_bound_root(
            plan.raw["ephemeral_root"],
            label="ephemeral root",
            private=True,
            empty=True,
        )
        os.close(root)
        return ActivationRecovery(state="prepared", plan=plan)
    finally:
        os.close(transaction_descriptor)


__all__ = [
    "ACTIVATION_LIFECYCLE_SCOPE",
    "ActivationLaunchContext",
    "ActivationPlan",
    "ActivationRecovery",
    "CLAUDE_NATIVE_TRIGGER",
    "CLAUDE_NATIVE_TRIGGER_SHA256",
    "PROBE_PLANE_ACTIVATION_SCHEMA",
    "build_activation_launch_context",
    "load_activation_plan",
    "materialize_activation",
    "plan_activation",
    "recover_activation",
    "revalidate_activation_launch_context",
    "rollback_activation",
    "validate_terminal_activation_evidence",
    "verify_activation",
]
