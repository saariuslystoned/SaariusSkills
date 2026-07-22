"""Source-only Cursor workspace instruction-plane substrate.

This module owns one deliberately disabled experiment for the exact installed
Cursor Agent tuple.  It can plan, create, verify, recover, and roll back one
workspace-local ``.cursor/rules`` artifact.  It never starts a process, runs a
census, reads Cursor configuration, or authorizes launch.

All returned and persisted records are body-free.  The caller supplies the
private guidance bytes separately whenever materialization is requested.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .adapter_manifest import AdapterManifest
from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .safety import (
    canonical_json_bytes,
    sha256_bytes,
    validate_bounded_json,
    validate_identifier,
    validate_sha256,
)


CURSOR_VERSION = "2026.07.17-3e2a980"
CURSOR_VERSION_OBSERVATION_SHA256 = (
    "ff67fa8c4d173904e13f0da944d7f763f5399ec48052b81c1ae3c7d87f118f4a"
)
CURSOR_LAUNCHER_SHA256 = (
    "eed61c5224668c9236334c4c68936a16aecc37374b592f59e31eb50433817831"
)
CURSOR_RUNTIME_SHA256 = (
    "336b5b3ebc5deb86df842102b20b6e4761605b7a667823e68dda7761b91a161b"
)
CURSOR_ENTRYPOINT_SHA256 = (
    "f45ce0860ce8c282110c2f8cfc04e0e8d8b3bc6a83ad01fcded0b5916e1e3a6e"
)
CURSOR_HELP_SHA256 = "bb2aed29e46b3c80635858d2181c140985dbf9f6a96d788f1b6a8adbb0d725af"

PLAN_SCHEMA = "puppet.cursor-workspace-plane-plan/v1"
INTENT_SCHEMA = "puppet.cursor-workspace-plane-intent/v1"
RECEIPT_SCHEMA = "puppet.cursor-workspace-plane-receipt/v1"
ROLLBACK_SCHEMA = "puppet.cursor-workspace-plane-rollback/v1"
SIMULATED_HALT_SCHEMA = "puppet.cursor-workspace-plane-simulated-halt/v1"

INTENT_FILENAME = "cursor-workspace-plane-intent.json"
RECEIPT_FILENAME = "cursor-workspace-plane-receipt.json"
ROLLBACK_FILENAME = "cursor-workspace-plane-rollback.json"

STATUS = {"surface": "hypothesis", "activation": "disabled"}
BLOCKERS = (
    "cursor_auth_isolation_unproved",
    "cursor_default_model_resolution_unavailable",
    "cursor_live_process_population_unproved",
    "cursor_workspace_plane_no_bleed_unproved",
    "cursor_workspace_rule_activation_unqualified",
)

_DIR_MODE = 0o700
_FILE_MODE = 0o600
_MAX_GUIDANCE_BYTES = 131072
_MAX_JSON_BYTES = 131072
_READ_CHUNK = 65536
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | _NOFOLLOW | _CLOEXEC
_READ_FLAGS = os.O_RDONLY | _NOFOLLOW | _CLOEXEC
_CREATE_FLAGS = os.O_CREAT | os.O_EXCL | os.O_RDWR | _NOFOLLOW | _CLOEXEC
_EMPTY_PREIMAGE_SHA256 = sha256_bytes(canonical_json_bytes([]))

_ROOT_KEYS = {
    "kind",
    "path",
    "lane_relative_path",
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
_FILE_IDENTITY_KEYS = {
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
_ARTIFACT_KEYS = _FILE_IDENTITY_KEYS | {"artifact_id"}
_PLAN_KEYS = {
    "schema",
    "target",
    "cursor_version",
    "scope_id",
    "status",
    "blockers",
    "launch_authorized",
    "launch_delta",
    "adapter_manifest_sha256",
    "adapter_implementation_sha256",
    "adapter_protocol_sha256",
    "execution_fingerprint",
    "admitted_lane_root",
    "workspace_root",
    "transaction_root",
    "artifact",
    "workspace_preimage_sha256",
    "transaction_preimage_sha256",
    "retain_hash_only_terminal_proof",
    "plan_sha256",
}


def _require_fd_primitives() -> None:
    required = (os.open, os.mkdir, os.unlink, os.rmdir, os.stat)
    if not _NOFOLLOW or any(item not in os.supports_dir_fd for item in required):
        raise UnsupportedError(
            "Cursor workspace plane requires no-follow dir-FD primitives"
        )
    if os.listdir not in os.supports_fd:
        raise UnsupportedError("Cursor workspace plane requires FD directory listing")


def _exact_int(value: Any, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError("%s is invalid" % label)
    return value


def _absolute_lexical(path: Path | str, *, label: str) -> Path:
    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise ValidationError("%s must be a filesystem path" % label) from exc
    if (
        not isinstance(raw, str)
        or not raw
        or "\x00" in raw
        or len(raw) > 4096
        or not os.path.isabs(raw)
    ):
        raise ValidationError("%s must be an absolute path" % label)
    normalized = os.path.normpath(raw)
    if normalized != raw:
        raise ValidationError("%s must be normalized" % label)
    return Path(normalized)


def _safe_relative_parts(value: str, *, label: str) -> Tuple[str, ...]:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or "\x00" in value
    ):
        raise ValidationError("%s must be a safe relative path" % label)
    parts = tuple(value.split("/"))
    if any(not part or part in {".", ".."} for part in parts):
        raise ValidationError("%s must be a safe relative path" % label)
    return parts


def _descendant_parts(path: Path, lane: Path, *, label: str) -> Tuple[str, ...]:
    try:
        relative = path.relative_to(lane)
    except ValueError as exc:
        raise ValidationError("%s must be beneath the admitted lane" % label) from exc
    parts = relative.parts
    if not parts:
        raise ValidationError(
            "%s must be beneath, not equal to, the admitted lane" % label
        )
    if any(part in {"", ".", ".."} for part in parts):
        raise ValidationError("%s has an invalid lane-relative path" % label)
    return tuple(parts)


def _paths_overlap(first: Sequence[str], second: Sequence[str]) -> bool:
    left = tuple(first)
    right = tuple(second)
    return left == right[: len(left)] or right == left[: len(right)]


def _canonical_json_with_newline(value: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(dict(value)) + b"\n"


def _document_sha256(value: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(dict(value)))


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


def _directory_identity(
    details: os.stat_result,
    *,
    kind: str,
    path: str,
    lane_relative_path: str,
) -> Dict[str, Any]:
    if not stat.S_ISDIR(details.st_mode):
        raise IdentityError("bound root is not a directory")
    return {
        "kind": kind,
        "path": path,
        "lane_relative_path": lane_relative_path,
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
        raise IdentityError("created path is not a directory")
    return {
        "relative_path": relative_path,
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "gid": details.st_gid,
        "mode": stat.S_IMODE(details.st_mode),
        "nlink": details.st_nlink,
    }


def _file_identity(
    descriptor: int,
    *,
    relative_path: str,
    artifact_id: Optional[str] = None,
) -> Dict[str, Any]:
    details = os.fstat(descriptor)
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) != _FILE_MODE
        or details.st_nlink != 1
    ):
        raise IdentityError("owned file must be current-UID 0600 with one hard link")
    result = {
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
    if artifact_id is not None:
        result["artifact_id"] = artifact_id
    return result


def _validate_root(value: Any, *, kind: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ROOT_KEYS:
        raise ValidationError("%s identity fields are invalid" % kind)
    if value.get("kind") != kind:
        raise ValidationError("%s type is invalid" % kind)
    path = _absolute_lexical(value.get("path"), label=kind)
    relative = value.get("lane_relative_path")
    if kind == "admitted_lane_root":
        if relative != ".":
            raise ValidationError("admitted lane relative path is invalid")
    else:
        relative = "/".join(
            _safe_relative_parts(relative, label="%s lane-relative path" % kind)
        )
    result = {
        "kind": kind,
        "path": str(path),
        "lane_relative_path": relative,
        "device": _exact_int(value.get("device"), label="%s device" % kind),
        "inode": _exact_int(value.get("inode"), label="%s inode" % kind, minimum=1),
        "uid": _exact_int(value.get("uid"), label="%s uid" % kind),
        "gid": _exact_int(value.get("gid"), label="%s gid" % kind),
        "mode": _exact_int(value.get("mode"), label="%s mode" % kind),
        "nlink": _exact_int(value.get("nlink"), label="%s nlink" % kind, minimum=1),
    }
    if result["uid"] != os.getuid() or result["mode"] != _DIR_MODE:
        raise IdentityError("%s must be current-UID 0700" % kind)
    return result


def _validate_created_directory(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CREATED_DIRECTORY_KEYS:
        raise ValidationError("created directory identity fields are invalid")
    result = {
        "relative_path": "/".join(
            _safe_relative_parts(
                value.get("relative_path"), label="created directory path"
            )
        ),
        "device": _exact_int(value.get("device"), label="directory device"),
        "inode": _exact_int(value.get("inode"), label="directory inode", minimum=1),
        "uid": _exact_int(value.get("uid"), label="directory uid"),
        "gid": _exact_int(value.get("gid"), label="directory gid"),
        "mode": _exact_int(value.get("mode"), label="directory mode"),
        "nlink": _exact_int(value.get("nlink"), label="directory nlink", minimum=1),
    }
    if result["uid"] != os.getuid() or result["mode"] != _DIR_MODE:
        raise IdentityError("created directory must be current-UID 0700")
    return result


def _validate_file_identity(
    value: Any, *, label: str, artifact_id: Optional[str] = None
) -> Dict[str, Any]:
    expected_keys = _ARTIFACT_KEYS if artifact_id is not None else _FILE_IDENTITY_KEYS
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise ValidationError("%s identity fields are invalid" % label)
    result = {
        "relative_path": "/".join(
            _safe_relative_parts(value.get("relative_path"), label="%s path" % label)
        ),
        "device": _exact_int(value.get("device"), label="%s device" % label),
        "inode": _exact_int(value.get("inode"), label="%s inode" % label, minimum=1),
        "uid": _exact_int(value.get("uid"), label="%s uid" % label),
        "gid": _exact_int(value.get("gid"), label="%s gid" % label),
        "mode": _exact_int(value.get("mode"), label="%s mode" % label),
        "nlink": _exact_int(value.get("nlink"), label="%s nlink" % label, minimum=1),
        "size": _exact_int(value.get("size"), label="%s size" % label),
        "sha256": validate_sha256(value.get("sha256"), "%s sha256" % label),
    }
    if artifact_id is not None:
        if value.get("artifact_id") != artifact_id:
            raise IdentityError("%s artifact id changed" % label)
        result["artifact_id"] = artifact_id
    if (
        result["uid"] != os.getuid()
        or result["mode"] != _FILE_MODE
        or result["nlink"] != 1
    ):
        raise IdentityError("%s must be current-UID 0600 with one link" % label)
    return result


def _assert_identity(
    live: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    label: str,
    compare_nlink: bool = True,
) -> None:
    ignored = set() if compare_nlink else {"nlink"}
    if any(live[key] != expected[key] for key in expected if key not in ignored):
        raise IdentityError("%s identity changed" % label)


def _open_lane(path: Path) -> Tuple[int, Dict[str, Any]]:
    _require_fd_primitives()
    try:
        lexical = os.lstat(path)
    except FileNotFoundError as exc:
        raise ValidationError("admitted lane root does not exist") from exc
    if stat.S_ISLNK(lexical.st_mode):
        raise IdentityError("admitted lane root must not be a symlink")
    try:
        descriptor = os.open(str(path), _DIRECTORY_FLAGS)
    except OSError as exc:
        raise IdentityError("admitted lane root cannot be opened safely") from exc
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (lexical.st_dev, lexical.st_ino):
            raise IdentityError("admitted lane root changed while opening")
        identity = _directory_identity(
            opened,
            kind="admitted_lane_root",
            path=str(path),
            lane_relative_path=".",
        )
        if identity["uid"] != os.getuid() or identity["mode"] != _DIR_MODE:
            raise IdentityError("admitted lane root must be current-UID 0700")
        return descriptor, identity
    except Exception:
        os.close(descriptor)
        raise


def _open_descendant(
    lane_descriptor: int,
    *,
    parts: Sequence[str],
    kind: str,
    path: Path,
) -> Tuple[int, Dict[str, Any]]:
    current = os.dup(lane_descriptor)
    try:
        for name in parts:
            try:
                lexical = os.stat(name, dir_fd=current, follow_symlinks=False)
                child = os.open(name, _DIRECTORY_FLAGS, dir_fd=current)
            except OSError as exc:
                raise IdentityError(
                    "%s path is missing, replaced, or linked" % kind
                ) from exc
            opened = os.fstat(child)
            if (
                stat.S_ISLNK(lexical.st_mode)
                or not stat.S_ISDIR(lexical.st_mode)
                or (lexical.st_dev, lexical.st_ino) != (opened.st_dev, opened.st_ino)
            ):
                os.close(child)
                raise IdentityError("%s changed while opening" % kind)
            os.close(current)
            current = child
        identity = _directory_identity(
            os.fstat(current),
            kind=kind,
            path=str(path),
            lane_relative_path="/".join(parts),
        )
        if identity["uid"] != os.getuid() or identity["mode"] != _DIR_MODE:
            raise IdentityError("%s must be current-UID 0700" % kind)
        return current, identity
    except Exception:
        os.close(current)
        raise


def _capture_roots(
    *,
    admitted_lane_root: Path | str,
    workspace_root: Path | str,
    transaction_root: Path | str,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    lane_path = _absolute_lexical(admitted_lane_root, label="admitted lane root")
    workspace_path = _absolute_lexical(workspace_root, label="workspace root")
    transaction_path = _absolute_lexical(transaction_root, label="transaction root")
    workspace_parts = _descendant_parts(
        workspace_path, lane_path, label="workspace root"
    )
    transaction_parts = _descendant_parts(
        transaction_path, lane_path, label="transaction root"
    )
    if _paths_overlap(workspace_parts, transaction_parts):
        raise ConflictError("workspace and transaction roots must not overlap")

    lane_descriptor, lane_identity = _open_lane(lane_path)
    try:
        workspace_descriptor, workspace_identity = _open_descendant(
            lane_descriptor,
            parts=workspace_parts,
            kind="workspace_root",
            path=workspace_path,
        )
        try:
            if os.listdir(workspace_descriptor):
                raise ConflictError(
                    "workspace root must be an empty Puppet-owned scope"
                )
        finally:
            os.close(workspace_descriptor)
        transaction_descriptor, transaction_identity = _open_descendant(
            lane_descriptor,
            parts=transaction_parts,
            kind="transaction_root",
            path=transaction_path,
        )
        try:
            if os.listdir(transaction_descriptor):
                raise ConflictError("transaction root must be empty and dedicated")
        finally:
            os.close(transaction_descriptor)
    finally:
        os.close(lane_descriptor)
    return lane_identity, workspace_identity, transaction_identity


def _open_bound_roots(
    plan: "CursorWorkspacePlan",
    *,
    workspace_expected: Optional[Mapping[str, Any]] = None,
    compare_workspace_nlink: bool = False,
) -> Tuple[int, int, int]:
    lane_expected = plan.raw["admitted_lane_root"]
    lane_path = Path(lane_expected["path"])
    lane_descriptor, lane_live = _open_lane(lane_path)
    try:
        # APFS directory link counts may change when descendants gain or lose
        # entries.  Content is joined separately through exact preimage/tree
        # checks; root replacement authority is device+inode+owner+mode.
        _assert_identity(
            lane_live,
            lane_expected,
            label="admitted lane root",
            compare_nlink=False,
        )
        workspace_descriptor, workspace_live = _open_descendant(
            lane_descriptor,
            parts=_safe_relative_parts(
                plan.raw["workspace_root"]["lane_relative_path"],
                label="workspace lane-relative path",
            ),
            kind="workspace_root",
            path=Path(plan.raw["workspace_root"]["path"]),
        )
        try:
            _assert_identity(
                workspace_live,
                workspace_expected or plan.raw["workspace_root"],
                label="workspace root",
                compare_nlink=compare_workspace_nlink,
            )
            transaction_descriptor, transaction_live = _open_descendant(
                lane_descriptor,
                parts=_safe_relative_parts(
                    plan.raw["transaction_root"]["lane_relative_path"],
                    label="transaction lane-relative path",
                ),
                kind="transaction_root",
                path=Path(plan.raw["transaction_root"]["path"]),
            )
            try:
                _assert_identity(
                    transaction_live,
                    plan.raw["transaction_root"],
                    label="transaction root",
                    compare_nlink=False,
                )
            except Exception:
                os.close(transaction_descriptor)
                raise
            return lane_descriptor, workspace_descriptor, transaction_descriptor
        except Exception:
            os.close(workspace_descriptor)
            raise
    except Exception:
        os.close(lane_descriptor)
        raise


def _close_roots(*descriptors: int) -> None:
    for descriptor in reversed(descriptors):
        os.close(descriptor)


def _directory_preimage(descriptor: int) -> str:
    entries = sorted(os.listdir(descriptor))
    return sha256_bytes(canonical_json_bytes(entries))


def _safe_stat_at(parent_descriptor: int, name: str) -> Optional[os.stat_result]:
    try:
        return os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _open_relative_parent(
    root_descriptor: int, parts: Sequence[str], *, allow_missing: bool = False
) -> Optional[int]:
    current = os.dup(root_descriptor)
    try:
        for name in parts:
            try:
                child = os.open(name, _DIRECTORY_FLAGS, dir_fd=current)
            except FileNotFoundError:
                if allow_missing:
                    os.close(current)
                    return None
                raise IdentityError("owned parent path is missing")
            except OSError as exc:
                raise IdentityError("owned parent path is linked or replaced") from exc
            os.close(current)
            current = child
        return current
    except Exception:
        os.close(current)
        raise


def _required_descriptor(value: Optional[int], *, label: str) -> int:
    if value is None:
        raise IdentityError("%s is missing" % label)
    return value


def _decode_json(raw: bytes, *, label: str) -> Dict[str, Any]:
    def object_pairs(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValidationError("%s contains duplicate fields" % label)
            result[key] = item
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


def _read_record(
    transaction_descriptor: int, name: str, *, label: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    try:
        descriptor = os.open(name, _READ_FLAGS, dir_fd=transaction_descriptor)
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
            or details.st_size > _MAX_JSON_BYTES
        ):
            raise IdentityError("%s is not an owned private record" % label)
        raw = bytearray()
        while len(raw) <= _MAX_JSON_BYTES:
            block = os.read(
                descriptor, min(_READ_CHUNK, _MAX_JSON_BYTES + 1 - len(raw))
            )
            if not block:
                break
            raw.extend(block)
        if len(raw) > _MAX_JSON_BYTES:
            raise ValidationError("%s is oversized" % label)
        value = _decode_json(bytes(raw), label=label)
        if bytes(raw) != _canonical_json_with_newline(value):
            raise ValidationError("%s is not canonical durable JSON" % label)
        os.lseek(descriptor, 0, os.SEEK_SET)
        identity = _file_identity(descriptor, relative_path=name)
        if identity["sha256"] != sha256_bytes(bytes(raw)):
            raise IdentityError("%s content changed while reading" % label)
        path_details = _safe_stat_at(transaction_descriptor, name)
        if (
            path_details is None
            or stat.S_ISLNK(path_details.st_mode)
            or (path_details.st_dev, path_details.st_ino)
            != (identity["device"], identity["inode"])
        ):
            raise IdentityError("%s path changed while reading" % label)
        return value, identity
    finally:
        os.close(descriptor)


def _persist_record(
    transaction_descriptor: int,
    name: str,
    value: Mapping[str, Any],
    *,
    label: str,
) -> Dict[str, Any]:
    validate_bounded_json(
        dict(value),
        max_depth=8,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    payload = _canonical_json_with_newline(value)
    if len(payload) > _MAX_JSON_BYTES:
        raise ValidationError("%s is oversized" % label)
    try:
        descriptor = os.open(
            name, _CREATE_FLAGS, _FILE_MODE, dir_fd=transaction_descriptor
        )
    except FileExistsError:
        existing, identity = _read_record(transaction_descriptor, name, label=label)
        if canonical_json_bytes(existing) != canonical_json_bytes(dict(value)):
            raise ConflictError("%s already exists with different content" % label)
        return identity
    except OSError as exc:
        raise IdentityError("%s cannot be created safely" % label) from exc
    try:
        os.fchmod(descriptor, _FILE_MODE)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.fsync(transaction_descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        identity = _file_identity(descriptor, relative_path=name)
        if identity["sha256"] != sha256_bytes(payload):
            raise IdentityError("%s content changed during creation" % label)
        path_details = _safe_stat_at(transaction_descriptor, name)
        if (
            path_details is None
            or stat.S_ISLNK(path_details.st_mode)
            or (path_details.st_dev, path_details.st_ino)
            != (identity["device"], identity["inode"])
        ):
            raise IdentityError("%s path changed during creation" % label)
        return identity
    finally:
        os.close(descriptor)


def _transaction_entries(descriptor: int) -> set[str]:
    entries = set(os.listdir(descriptor))
    allowed = {INTENT_FILENAME, RECEIPT_FILENAME, ROLLBACK_FILENAME}
    if not entries <= allowed:
        raise ConflictError("transaction root contains unexpected entries")
    return entries


def _validate_guidance(value: bytes) -> bytes:
    if not isinstance(value, bytes) or not value or len(value) > _MAX_GUIDANCE_BYTES:
        raise ValidationError("guidance bytes are missing or exceed the bound")
    if b"\x00" in value:
        raise ValidationError("guidance bytes contain a NUL")
    try:
        value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("guidance bytes must be UTF-8") from exc
    return value


def _adapter_manifest(
    value: AdapterManifest | Mapping[str, Any],
    *,
    expected_manifest_sha256: str,
    expected_adapter_implementation_sha256: str,
    observed_version: str,
) -> AdapterManifest:
    expected_manifest_sha256 = validate_sha256(
        expected_manifest_sha256, "adapter manifest sha256"
    )
    expected_adapter_implementation_sha256 = validate_sha256(
        expected_adapter_implementation_sha256,
        "adapter implementation sha256",
    )
    if observed_version != CURSOR_VERSION:
        raise UnsupportedError("Cursor workspace plane version is unsupported")
    manifest = AdapterManifest.from_dict(
        dict(value.raw) if isinstance(value, AdapterManifest) else dict(value)
    )
    raw = manifest.raw
    if manifest.fingerprint != expected_manifest_sha256:
        raise IdentityError("Cursor doctor manifest fingerprint changed")
    if raw["target"] != "cursor":
        raise IdentityError("Cursor workspace plane requires a Cursor manifest")
    if raw["platform"].get("system") != "Darwin":
        raise IdentityError("Cursor workspace plane requires the observed Darwin tuple")
    if not raw["doctor_only"] or raw["qualification"] is not None:
        raise IdentityError("Cursor workspace plane requires a doctor-only manifest")
    if raw["adapter_fingerprint"] != expected_adapter_implementation_sha256:
        raise IdentityError("Cursor adapter implementation fingerprint changed")
    if any(state != "declared" for state in raw["capabilities"].values()):
        raise IdentityError("Cursor doctor capabilities must remain declared-only")

    executable = raw["executable"]
    version_root = Path(executable["resolved_path"]).parent
    if (
        executable["sha256"] != CURSOR_LAUNCHER_SHA256
        or executable["version_sha256"] != CURSOR_VERSION_OBSERVATION_SHA256
        or executable["help_sha256"] != CURSOR_HELP_SHA256
        or Path(executable["resolved_path"]).name != "cursor-agent"
        or version_root.name != CURSOR_VERSION
    ):
        raise IdentityError("Cursor executable tuple is not the exact supported build")
    execution = raw["execution"]
    support = execution["support_files"]
    if (
        execution["transition"] != "same_pid_exec"
        or execution["runtime_executable"]["path"] != str(version_root / "node")
        or execution["runtime_executable"]["sha256"] != CURSOR_RUNTIME_SHA256
        or len(support) != 1
        or support[0]["path"] != str(version_root / "index.js")
        or support[0]["sha256"] != CURSOR_ENTRYPOINT_SHA256
    ):
        raise IdentityError("Cursor runtime bundle is not the exact supported build")

    mapping = raw["yolo_mapping"]
    expected_argv = [
        executable["resolved_path"],
        "--yolo",
        "--sandbox",
        "disabled",
    ]
    if (
        mapping["complete"] is not False
        or mapping["launch_argv"] != expected_argv
        or mapping["permission_flags"] != ["--yolo"]
        or mapping["permission_declared"] is not True
        or mapping["sandbox_flags"] != ["--sandbox", "disabled"]
        or mapping["sandbox_disable_declared"] is not True
        or mapping["project_isolation_flags"] != []
        or mapping["project_isolation_declared"] is not False
        or mapping.get("model_flag") != "--model"
    ):
        raise IdentityError("Cursor doctor mapping is not the expected disabled base")
    return manifest


def _validate_manifest_for_plan(
    plan: "CursorWorkspacePlan",
    value: AdapterManifest | Mapping[str, Any],
) -> AdapterManifest:
    manifest = _adapter_manifest(
        value,
        expected_manifest_sha256=plan.raw["adapter_manifest_sha256"],
        expected_adapter_implementation_sha256=plan.raw[
            "adapter_implementation_sha256"
        ],
        observed_version=plan.raw["cursor_version"],
    )
    if (
        manifest.raw["protocol_fingerprint"] != plan.raw["adapter_protocol_sha256"]
        or manifest.execution_fingerprint != plan.raw["execution_fingerprint"]
    ):
        raise IdentityError("Cursor manifest binding changed")
    return manifest


def _artifact_relative_path(scope_id: str) -> str:
    return ".cursor/rules/puppet-%s.mdc" % scope_id


def _validate_artifact_plan(value: Any, *, scope_id: str) -> Dict[str, Any]:
    keys = {
        "artifact_id",
        "relative_path",
        "write_mode",
        "content_sha256",
        "content_size",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValidationError("Cursor artifact plan fields are invalid")
    expected_path = _artifact_relative_path(scope_id)
    if (
        value.get("artifact_id") != "cursor_workspace_guidance"
        or value.get("relative_path") != expected_path
        or value.get("write_mode") != "create_only"
    ):
        raise IdentityError("Cursor artifact plan changed")
    return {
        "artifact_id": "cursor_workspace_guidance",
        "relative_path": expected_path,
        "write_mode": "create_only",
        "content_sha256": validate_sha256(
            value.get("content_sha256"), "guidance sha256"
        ),
        "content_size": _exact_int(
            value.get("content_size"), label="guidance size", minimum=1
        ),
    }


def _validate_plan(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PLAN_KEYS:
        raise ValidationError("Cursor workspace plan fields are invalid")
    if value.get("schema") != PLAN_SCHEMA or value.get("target") != "cursor":
        raise ValidationError("Cursor workspace plan schema is unsupported")
    if value.get("cursor_version") != CURSOR_VERSION:
        raise UnsupportedError("Cursor workspace plane version is unsupported")
    scope_id = validate_identifier(value.get("scope_id"), "Cursor plane scope")
    if value.get("status") != STATUS:
        raise IdentityError("Cursor workspace plane must remain hypothesis/disabled")
    if value.get("blockers") != list(BLOCKERS):
        raise IdentityError("Cursor workspace plane blockers changed")
    if value.get("launch_authorized") is not False:
        raise UnsupportedError("Cursor workspace plane cannot authorize launch")

    lane = _validate_root(value.get("admitted_lane_root"), kind="admitted_lane_root")
    workspace = _validate_root(value.get("workspace_root"), kind="workspace_root")
    transaction = _validate_root(value.get("transaction_root"), kind="transaction_root")
    for root in (workspace, transaction):
        expected_path = Path(lane["path"]).joinpath(
            *root["lane_relative_path"].split("/")
        )
        if str(expected_path) != root["path"]:
            raise IdentityError("%s containment binding changed" % root["kind"])
    if _paths_overlap(
        workspace["lane_relative_path"].split("/"),
        transaction["lane_relative_path"].split("/"),
    ):
        raise ConflictError("workspace and transaction roots must not overlap")

    expected_delta = {"argv": ["--workspace", workspace["path"]]}
    if value.get("launch_delta") != expected_delta:
        raise IdentityError("Cursor workspace launch delta changed")
    artifact = _validate_artifact_plan(value.get("artifact"), scope_id=scope_id)
    if artifact["content_size"] > _MAX_GUIDANCE_BYTES:
        raise ValidationError("guidance size exceeds the bound")

    result = {
        "schema": PLAN_SCHEMA,
        "target": "cursor",
        "cursor_version": CURSOR_VERSION,
        "scope_id": scope_id,
        "status": dict(STATUS),
        "blockers": list(BLOCKERS),
        "launch_authorized": False,
        "launch_delta": expected_delta,
        "adapter_manifest_sha256": validate_sha256(
            value.get("adapter_manifest_sha256"), "adapter manifest sha256"
        ),
        "adapter_implementation_sha256": validate_sha256(
            value.get("adapter_implementation_sha256"),
            "adapter implementation sha256",
        ),
        "adapter_protocol_sha256": validate_sha256(
            value.get("adapter_protocol_sha256"), "adapter protocol sha256"
        ),
        "execution_fingerprint": validate_sha256(
            value.get("execution_fingerprint"), "execution fingerprint"
        ),
        "admitted_lane_root": lane,
        "workspace_root": workspace,
        "transaction_root": transaction,
        "artifact": artifact,
        "workspace_preimage_sha256": validate_sha256(
            value.get("workspace_preimage_sha256"), "workspace preimage sha256"
        ),
        "transaction_preimage_sha256": validate_sha256(
            value.get("transaction_preimage_sha256"),
            "transaction preimage sha256",
        ),
        "retain_hash_only_terminal_proof": value.get("retain_hash_only_terminal_proof"),
    }
    if (
        result["workspace_preimage_sha256"] != _EMPTY_PREIMAGE_SHA256
        or result["transaction_preimage_sha256"] != _EMPTY_PREIMAGE_SHA256
        or result["retain_hash_only_terminal_proof"] is not True
    ):
        raise IdentityError("Cursor workspace preimage or retention policy changed")
    supplied_hash = validate_sha256(value.get("plan_sha256"), "plan sha256")
    expected_hash = _document_sha256(result)
    if supplied_hash != expected_hash:
        raise IdentityError("Cursor workspace plan fingerprint changed")
    result["plan_sha256"] = supplied_hash
    validate_bounded_json(
        result,
        max_depth=8,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


@dataclass(frozen=True)
class CursorWorkspacePlan:
    """Typed, body-free, launch-disabled Cursor workspace plan."""

    raw: Dict[str, Any]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CursorWorkspacePlan":
        return cls(raw=_validate_plan(value))

    def to_dict(self) -> Dict[str, Any]:
        return json.loads(canonical_json_bytes(self.raw).decode("utf-8"))

    @property
    def plan_sha256(self) -> str:
        return self.raw["plan_sha256"]

    @property
    def artifact_path(self) -> Path:
        return (
            Path(self.raw["workspace_root"]["path"])
            / self.raw["artifact"]["relative_path"]
        )


@dataclass(frozen=True)
class CursorWorkspaceRecovery:
    """Body-free classification of a durable workspace-plane transaction."""

    state: str
    materialization_receipt: Optional[Dict[str, Any]] = None
    rollback_receipt: Optional[Dict[str, Any]] = None


def plan_cursor_workspace_plane(
    *,
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    expected_manifest_sha256: str,
    expected_adapter_implementation_sha256: str,
    observed_version: str,
    admitted_lane_root: Path | str,
    workspace_root: Path | str,
    transaction_root: Path | str,
    scope_id: str,
    guidance: bytes,
) -> CursorWorkspacePlan:
    """Build a body-free plan without launching or writing any state."""

    scope_id = validate_identifier(scope_id, "Cursor plane scope")
    guidance = _validate_guidance(guidance)
    manifest = _adapter_manifest(
        adapter_manifest,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_adapter_implementation_sha256=(expected_adapter_implementation_sha256),
        observed_version=observed_version,
    )
    lane, workspace, transaction = _capture_roots(
        admitted_lane_root=admitted_lane_root,
        workspace_root=workspace_root,
        transaction_root=transaction_root,
    )
    value = {
        "schema": PLAN_SCHEMA,
        "target": "cursor",
        "cursor_version": CURSOR_VERSION,
        "scope_id": scope_id,
        "status": dict(STATUS),
        "blockers": list(BLOCKERS),
        "launch_authorized": False,
        "launch_delta": {"argv": ["--workspace", workspace["path"]]},
        "adapter_manifest_sha256": manifest.fingerprint,
        "adapter_implementation_sha256": manifest.raw["adapter_fingerprint"],
        "adapter_protocol_sha256": manifest.raw["protocol_fingerprint"],
        "execution_fingerprint": manifest.execution_fingerprint,
        "admitted_lane_root": lane,
        "workspace_root": workspace,
        "transaction_root": transaction,
        "artifact": {
            "artifact_id": "cursor_workspace_guidance",
            "relative_path": _artifact_relative_path(scope_id),
            "write_mode": "create_only",
            "content_sha256": sha256_bytes(guidance),
            "content_size": len(guidance),
        },
        "workspace_preimage_sha256": _EMPTY_PREIMAGE_SHA256,
        "transaction_preimage_sha256": _EMPTY_PREIMAGE_SHA256,
        "retain_hash_only_terminal_proof": True,
    }
    value["plan_sha256"] = _document_sha256(value)
    return CursorWorkspacePlan.from_dict(value)


def _intent_for(plan: CursorWorkspacePlan) -> Dict[str, Any]:
    artifact = plan.raw["artifact"]
    return {
        "schema": INTENT_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "adapter_manifest_sha256": plan.raw["adapter_manifest_sha256"],
        "artifact_relative_path": artifact["relative_path"],
        "artifact_sha256": artifact["content_sha256"],
        "artifact_size": artifact["content_size"],
        "workspace_preimage_sha256": plan.raw["workspace_preimage_sha256"],
        "transaction_preimage_sha256": plan.raw["transaction_preimage_sha256"],
    }


def _validate_intent(value: Any, plan: CursorWorkspacePlan) -> Dict[str, Any]:
    expected = _intent_for(plan)
    if not isinstance(value, Mapping) or set(value) != set(expected):
        raise ValidationError("Cursor workspace intent fields are invalid")
    if dict(value) != expected:
        raise IdentityError("Cursor workspace intent binding changed")
    validate_bounded_json(
        expected,
        max_depth=4,
        max_items=32,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return expected


def _create_parents(
    workspace_descriptor: int,
) -> Tuple[int, list[Dict[str, Any]]]:
    current = os.dup(workspace_descriptor)
    created = []
    try:
        for name, relative_path in (
            (".cursor", ".cursor"),
            ("rules", ".cursor/rules"),
        ):
            try:
                os.mkdir(name, _DIR_MODE, dir_fd=current)
            except FileExistsError as exc:
                raise ConflictError(
                    "Cursor workspace guidance parent collided"
                ) from exc
            except OSError as exc:
                raise IdentityError("Cursor workspace guidance parent failed") from exc
            child: Optional[int] = None
            try:
                lexical = os.stat(name, dir_fd=current, follow_symlinks=False)
                child = os.open(name, _DIRECTORY_FLAGS, dir_fd=current)
                os.fchmod(child, _DIR_MODE)
                details = os.fstat(child)
                if (
                    stat.S_ISLNK(lexical.st_mode)
                    or not stat.S_ISDIR(lexical.st_mode)
                    or (lexical.st_dev, lexical.st_ino)
                    != (details.st_dev, details.st_ino)
                    or not stat.S_ISDIR(details.st_mode)
                    or details.st_uid != os.getuid()
                    or stat.S_IMODE(details.st_mode) != _DIR_MODE
                ):
                    raise IdentityError(
                        "Cursor workspace guidance parent is not private"
                    )
                confirmed = os.stat(name, dir_fd=current, follow_symlinks=False)
                if stat.S_ISLNK(confirmed.st_mode) or (
                    confirmed.st_dev,
                    confirmed.st_ino,
                ) != (details.st_dev, details.st_ino):
                    raise IdentityError(
                        "Cursor workspace guidance parent changed during creation"
                    )
                created.append(
                    _created_directory_identity(details, relative_path=relative_path)
                )
                os.fsync(current)
            except OSError as exc:
                if child is not None:
                    os.close(child)
                raise IdentityError(
                    "Cursor workspace guidance parent cannot be opened safely"
                ) from exc
            except Exception:
                if child is not None:
                    os.close(child)
                raise
            if child is None:  # pragma: no cover - successful open assigns it
                raise IdentityError("Cursor workspace guidance parent is unavailable")
            os.close(current)
            current = child
        return current, created
    except Exception:
        os.close(current)
        raise


def _create_artifact(
    parent_descriptor: int,
    *,
    name: str,
    relative_path: str,
    payload: bytes,
) -> Dict[str, Any]:
    try:
        descriptor = os.open(name, _CREATE_FLAGS, _FILE_MODE, dir_fd=parent_descriptor)
    except FileExistsError as exc:
        raise ConflictError("Cursor workspace guidance already exists") from exc
    except OSError as exc:
        raise IdentityError(
            "Cursor workspace guidance cannot be created safely"
        ) from exc
    try:
        os.fchmod(descriptor, _FILE_MODE)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.fsync(parent_descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        identity = _file_identity(
            descriptor,
            relative_path=relative_path,
            artifact_id="cursor_workspace_guidance",
        )
        path_details = _safe_stat_at(parent_descriptor, name)
        if (
            path_details is None
            or stat.S_ISLNK(path_details.st_mode)
            or (path_details.st_dev, path_details.st_ino)
            != (identity["device"], identity["inode"])
        ):
            raise IdentityError("Cursor guidance path changed during creation")
        return identity
    finally:
        os.close(descriptor)


def _live_created_directories(
    workspace_descriptor: int,
) -> list[Dict[str, Any]]:
    result = []
    for relative_path in (".cursor", ".cursor/rules"):
        parts = _safe_relative_parts(relative_path, label="created directory path")
        parent = _required_descriptor(
            _open_relative_parent(workspace_descriptor, parts[:-1]),
            label="created Cursor directory parent",
        )
        try:
            details = _safe_stat_at(parent, parts[-1])
            if details is None or stat.S_ISLNK(details.st_mode):
                raise IdentityError("created Cursor directory changed")
            result.append(
                _created_directory_identity(details, relative_path=relative_path)
            )
        finally:
            os.close(parent)
    return result


def _assert_exact_workspace_tree(
    workspace_descriptor: int, *, artifact_name: str
) -> None:
    if set(os.listdir(workspace_descriptor)) != {".cursor"}:
        raise IdentityError("Cursor workspace preimage or tree changed")
    cursor_descriptor = _required_descriptor(
        _open_relative_parent(workspace_descriptor, (".cursor",)),
        label="Cursor guidance root",
    )
    try:
        if set(os.listdir(cursor_descriptor)) != {"rules"}:
            raise IdentityError("Cursor workspace guidance scope changed")
        rules_descriptor = _required_descriptor(
            _open_relative_parent(cursor_descriptor, ("rules",)),
            label="Cursor guidance rules root",
        )
        try:
            if set(os.listdir(rules_descriptor)) != {artifact_name}:
                raise IdentityError("Cursor workspace guidance scope changed")
        finally:
            os.close(rules_descriptor)
    finally:
        os.close(cursor_descriptor)


def _receipt_for(
    plan: CursorWorkspacePlan,
    *,
    intent: Mapping[str, Any],
    intent_record: Mapping[str, Any],
    artifact: Mapping[str, Any],
    created_directories: Sequence[Mapping[str, Any]],
    workspace_root_after: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "intent_sha256": _document_sha256(intent),
        "adapter_manifest_sha256": plan.raw["adapter_manifest_sha256"],
        "intent_record": dict(intent_record),
        "artifact": dict(artifact),
        "created_directories": [dict(item) for item in created_directories],
        "workspace_root_after": dict(workspace_root_after),
    }


def _validate_receipt(
    value: Any, plan: CursorWorkspacePlan, intent: Mapping[str, Any]
) -> Dict[str, Any]:
    keys = {
        "schema",
        "plan_sha256",
        "intent_sha256",
        "adapter_manifest_sha256",
        "intent_record",
        "artifact",
        "created_directories",
        "workspace_root_after",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValidationError("Cursor workspace receipt fields are invalid")
    expected_scalars = {
        "schema": RECEIPT_SCHEMA,
        "plan_sha256": plan.plan_sha256,
        "intent_sha256": _document_sha256(intent),
        "adapter_manifest_sha256": plan.raw["adapter_manifest_sha256"],
    }
    if any(value.get(key) != expected for key, expected in expected_scalars.items()):
        raise IdentityError("Cursor workspace receipt binding changed")
    intent_record = _validate_file_identity(
        value.get("intent_record"), label="intent record"
    )
    if intent_record["relative_path"] != INTENT_FILENAME:
        raise IdentityError("Cursor workspace intent record path changed")
    artifact = _validate_file_identity(
        value.get("artifact"),
        label="Cursor guidance artifact",
        artifact_id="cursor_workspace_guidance",
    )
    artifact_plan = plan.raw["artifact"]
    if (
        artifact["relative_path"] != artifact_plan["relative_path"]
        or artifact["sha256"] != artifact_plan["content_sha256"]
        or artifact["size"] != artifact_plan["content_size"]
    ):
        raise IdentityError("Cursor guidance artifact binding changed")
    raw_directories = value.get("created_directories")
    if not isinstance(raw_directories, list):
        raise ValidationError("Cursor created directories are invalid")
    directories = [_validate_created_directory(item) for item in raw_directories]
    if [item["relative_path"] for item in directories] != [
        ".cursor",
        ".cursor/rules",
    ]:
        raise IdentityError("Cursor created directory set changed")
    workspace_after = _validate_root(
        value.get("workspace_root_after"), kind="workspace_root"
    )
    before = plan.raw["workspace_root"]
    _assert_identity(
        workspace_after, before, label="workspace root", compare_nlink=False
    )
    result = {
        **expected_scalars,
        "intent_record": intent_record,
        "artifact": artifact,
        "created_directories": directories,
        "workspace_root_after": workspace_after,
    }
    validate_bounded_json(
        result,
        max_depth=7,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def materialize_cursor_workspace_plane(
    plan: CursorWorkspacePlan,
    *,
    guidance: bytes,
    adapter_manifest: AdapterManifest | Mapping[str, Any],
) -> Dict[str, Any]:
    """Create one private guidance artifact, or return an exact prior receipt."""

    if not isinstance(plan, CursorWorkspacePlan):
        raise ValidationError("Cursor workspace plan is invalid")
    plan = CursorWorkspacePlan.from_dict(plan.to_dict())
    guidance = _validate_guidance(guidance)
    if (
        sha256_bytes(guidance) != plan.raw["artifact"]["content_sha256"]
        or len(guidance) != plan.raw["artifact"]["content_size"]
    ):
        raise IdentityError("Cursor guidance bytes changed after planning")
    _validate_manifest_for_plan(plan, adapter_manifest)

    roots = _open_bound_roots(plan)
    lane_descriptor, workspace_descriptor, transaction_descriptor = roots
    try:
        entries = _transaction_entries(transaction_descriptor)
        if entries:
            if entries == {INTENT_FILENAME, RECEIPT_FILENAME}:
                return _verify_active_with_open_roots(
                    plan, workspace_descriptor, transaction_descriptor
                )
            raise ConflictError("Cursor workspace transaction recovery is ambiguous")
        if (
            _directory_preimage(workspace_descriptor)
            != plan.raw["workspace_preimage_sha256"]
            or _directory_preimage(transaction_descriptor)
            != plan.raw["transaction_preimage_sha256"]
        ):
            raise IdentityError("Cursor workspace or transaction preimage drifted")

        intent = _intent_for(plan)
        intent_record = _persist_record(
            transaction_descriptor,
            INTENT_FILENAME,
            intent,
            label="Cursor workspace intent",
        )
        rules_descriptor, initially_created = _create_parents(workspace_descriptor)
        try:
            artifact_name = Path(plan.raw["artifact"]["relative_path"]).name
            artifact = _create_artifact(
                rules_descriptor,
                name=artifact_name,
                relative_path=plan.raw["artifact"]["relative_path"],
                payload=guidance,
            )
        finally:
            os.close(rules_descriptor)
        if (
            artifact["sha256"] != plan.raw["artifact"]["content_sha256"]
            or artifact["size"] != plan.raw["artifact"]["content_size"]
        ):
            raise IdentityError("Cursor guidance changed during creation")
        _assert_exact_workspace_tree(workspace_descriptor, artifact_name=artifact_name)
        created = _live_created_directories(workspace_descriptor)
        if len(initially_created) != len(created):
            raise IdentityError("created Cursor directory set changed")
        for initial, live in zip(initially_created, created):
            _assert_identity(
                live,
                initial,
                label="created Cursor directory",
                compare_nlink=False,
            )
        workspace_after = _directory_identity(
            os.fstat(workspace_descriptor),
            kind="workspace_root",
            path=plan.raw["workspace_root"]["path"],
            lane_relative_path=plan.raw["workspace_root"]["lane_relative_path"],
        )
        receipt = _receipt_for(
            plan,
            intent=intent,
            intent_record=intent_record,
            artifact=artifact,
            created_directories=created,
            workspace_root_after=workspace_after,
        )
        _persist_record(
            transaction_descriptor,
            RECEIPT_FILENAME,
            receipt,
            label="Cursor workspace receipt",
        )
        return _validate_receipt(receipt, plan, intent)
    finally:
        _close_roots(lane_descriptor, workspace_descriptor, transaction_descriptor)


def _verify_live_file(
    parent_descriptor: int,
    name: str,
    expected: Mapping[str, Any],
    *,
    label: str,
    artifact_id: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        descriptor = os.open(name, _READ_FLAGS, dir_fd=parent_descriptor)
    except OSError as exc:
        raise IdentityError("%s is missing, linked, or replaced" % label) from exc
    try:
        live = _file_identity(
            descriptor, relative_path=expected["relative_path"], artifact_id=artifact_id
        )
        if live != expected:
            raise IdentityError("%s identity or content changed" % label)
        path_details = _safe_stat_at(parent_descriptor, name)
        opened = os.fstat(descriptor)
        if (
            path_details is None
            or stat.S_ISLNK(path_details.st_mode)
            or (path_details.st_dev, path_details.st_ino)
            != (opened.st_dev, opened.st_ino)
        ):
            raise IdentityError("%s path changed while verifying" % label)
        return live
    finally:
        os.close(descriptor)


def _verify_active_with_open_roots(
    plan: CursorWorkspacePlan,
    workspace_descriptor: int,
    transaction_descriptor: int,
    *,
    supplied_receipt: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if _transaction_entries(transaction_descriptor) != {
        INTENT_FILENAME,
        RECEIPT_FILENAME,
    }:
        raise ConflictError("Cursor workspace transaction is not active")
    intent, intent_record = _read_record(
        transaction_descriptor, INTENT_FILENAME, label="Cursor workspace intent"
    )
    intent = _validate_intent(intent, plan)
    receipt, _ = _read_record(
        transaction_descriptor, RECEIPT_FILENAME, label="Cursor workspace receipt"
    )
    receipt = _validate_receipt(receipt, plan, intent)
    if supplied_receipt is not None and canonical_json_bytes(
        receipt
    ) != canonical_json_bytes(dict(supplied_receipt)):
        raise IdentityError("caller-supplied Cursor receipt is not exact")
    if intent_record != receipt["intent_record"]:
        raise IdentityError("Cursor intent record identity changed")

    workspace_live = _directory_identity(
        os.fstat(workspace_descriptor),
        kind="workspace_root",
        path=plan.raw["workspace_root"]["path"],
        lane_relative_path=plan.raw["workspace_root"]["lane_relative_path"],
    )
    _assert_identity(
        workspace_live, receipt["workspace_root_after"], label="workspace root"
    )
    artifact_name = Path(plan.raw["artifact"]["relative_path"]).name
    _assert_exact_workspace_tree(workspace_descriptor, artifact_name=artifact_name)
    live_directories = _live_created_directories(workspace_descriptor)
    if live_directories != receipt["created_directories"]:
        raise IdentityError("Cursor created directory identity changed")
    rules_descriptor = _required_descriptor(
        _open_relative_parent(workspace_descriptor, (".cursor", "rules")),
        label="Cursor guidance rules root",
    )
    try:
        _verify_live_file(
            rules_descriptor,
            artifact_name,
            receipt["artifact"],
            label="Cursor guidance artifact",
            artifact_id="cursor_workspace_guidance",
        )
    finally:
        os.close(rules_descriptor)
    return receipt


def verify_cursor_workspace_plane(
    plan: CursorWorkspacePlan,
    *,
    receipt: Optional[Mapping[str, Any]] = None,
    adapter_manifest: AdapterManifest | Mapping[str, Any],
) -> Dict[str, Any]:
    """Rejoin the exact manifest, records, roots, directories, and artifact."""

    if not isinstance(plan, CursorWorkspacePlan):
        raise ValidationError("Cursor workspace plan is invalid")
    plan = CursorWorkspacePlan.from_dict(plan.to_dict())
    _validate_manifest_for_plan(plan, adapter_manifest)
    roots = _open_bound_roots(plan, compare_workspace_nlink=False)
    lane_descriptor, workspace_descriptor, transaction_descriptor = roots
    try:
        return _verify_active_with_open_roots(
            plan,
            workspace_descriptor,
            transaction_descriptor,
            supplied_receipt=receipt,
        )
    finally:
        _close_roots(lane_descriptor, workspace_descriptor, transaction_descriptor)


def _validate_simulated_halt(
    value: Any, plan: CursorWorkspacePlan, receipt: Mapping[str, Any]
) -> Dict[str, Any]:
    expected = {
        "schema": SIMULATED_HALT_SCHEMA,
        "target": "cursor",
        "simulation": True,
        "exact_halt": True,
        "plan_sha256": plan.plan_sha256,
        "materialization_receipt_sha256": _document_sha256(receipt),
    }
    if not isinstance(value, Mapping) or set(value) != set(expected):
        raise ValidationError("simulated exact-halt proof fields are invalid")
    if dict(value) != expected:
        raise IdentityError("simulated exact-halt proof binding changed")
    validate_bounded_json(
        expected,
        max_depth=3,
        max_items=16,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return expected


def simulated_exact_halt_proof(
    plan: CursorWorkspacePlan, receipt: Mapping[str, Any]
) -> Dict[str, Any]:
    """Build the caller-owned source-only halt proof used by tests/planners."""

    if not isinstance(plan, CursorWorkspacePlan):
        raise ValidationError("Cursor workspace plan is invalid")
    plan = CursorWorkspacePlan.from_dict(plan.to_dict())
    intent = _intent_for(plan)
    normalized_receipt = _validate_receipt(receipt, plan, intent)
    return _validate_simulated_halt(
        {
            "schema": SIMULATED_HALT_SCHEMA,
            "target": "cursor",
            "simulation": True,
            "exact_halt": True,
            "plan_sha256": plan.plan_sha256,
            "materialization_receipt_sha256": _document_sha256(normalized_receipt),
        },
        plan,
        normalized_receipt,
    )


def _remove_artifact(workspace_descriptor: int, receipt: Mapping[str, Any]) -> None:
    artifact = receipt["artifact"]
    parts = _safe_relative_parts(
        artifact["relative_path"], label="Cursor guidance artifact path"
    )
    parent = _required_descriptor(
        _open_relative_parent(workspace_descriptor, parts[:-1]),
        label="Cursor guidance artifact parent",
    )
    try:
        try:
            descriptor = os.open(parts[-1], _READ_FLAGS, dir_fd=parent)
        except OSError as exc:
            raise IdentityError(
                "Cursor guidance artifact is missing or unsafe"
            ) from exc
        try:
            live = _file_identity(
                descriptor,
                relative_path=artifact["relative_path"],
                artifact_id="cursor_workspace_guidance",
            )
            if live != artifact:
                raise IdentityError("Cursor guidance artifact changed before rollback")
            path_details = _safe_stat_at(parent, parts[-1])
            if (
                path_details is None
                or stat.S_ISLNK(path_details.st_mode)
                or (path_details.st_dev, path_details.st_ino)
                != (live["device"], live["inode"])
            ):
                raise IdentityError("Cursor guidance path changed before rollback")
            os.unlink(parts[-1], dir_fd=parent)
            os.fsync(parent)
            if _safe_stat_at(parent, parts[-1]) is not None:
                raise IdentityError("Cursor guidance removal could not be proven")
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)


def _remove_created_directories(
    workspace_descriptor: int, directories: Sequence[Mapping[str, Any]]
) -> list[str]:
    removed = []
    for expected in reversed(directories):
        parts = _safe_relative_parts(
            expected["relative_path"], label="created directory path"
        )
        parent = _required_descriptor(
            _open_relative_parent(workspace_descriptor, parts[:-1]),
            label="created Cursor directory parent",
        )
        try:
            details = _safe_stat_at(parent, parts[-1])
            if details is None or stat.S_ISLNK(details.st_mode):
                raise IdentityError("created Cursor directory changed before rollback")
            live = _created_directory_identity(
                details, relative_path=expected["relative_path"]
            )
            _assert_identity(
                live,
                expected,
                label="created Cursor directory",
                compare_nlink=False,
            )
            child = os.open(parts[-1], _DIRECTORY_FLAGS, dir_fd=parent)
            try:
                if os.listdir(child):
                    raise IdentityError(
                        "created Cursor directory is not empty before rollback"
                    )
                opened = _created_directory_identity(
                    os.fstat(child), relative_path=expected["relative_path"]
                )
                _assert_identity(
                    opened,
                    expected,
                    label="created Cursor directory",
                    compare_nlink=False,
                )
                confirmed = _safe_stat_at(parent, parts[-1])
                if (
                    confirmed is None
                    or stat.S_ISLNK(confirmed.st_mode)
                    or (confirmed.st_dev, confirmed.st_ino)
                    != (opened["device"], opened["inode"])
                ):
                    raise IdentityError(
                        "created Cursor directory changed during rollback"
                    )
                os.rmdir(parts[-1], dir_fd=parent)
                os.fsync(parent)
                if _safe_stat_at(parent, parts[-1]) is not None:
                    raise IdentityError("Cursor directory removal could not be proven")
            finally:
                os.close(child)
            removed.append(expected["relative_path"])
        except OSError as exc:
            raise IdentityError(
                "created Cursor directory could not be removed"
            ) from exc
        finally:
            os.close(parent)
    return removed


def _rollback_for(
    plan: CursorWorkspacePlan,
    *,
    intent: Mapping[str, Any],
    receipt: Mapping[str, Any],
    halt_proof: Mapping[str, Any],
    removed_directories: Sequence[str],
    workspace_root_after: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "schema": ROLLBACK_SCHEMA,
        "terminal_state": "rolled_back",
        "plan_sha256": plan.plan_sha256,
        "intent_sha256": _document_sha256(intent),
        "materialization_receipt_sha256": _document_sha256(receipt),
        "simulated_exact_halt_proof_sha256": _document_sha256(halt_proof),
        "artifact_sha256": plan.raw["artifact"]["content_sha256"],
        "removed_directories": list(removed_directories),
        "workspace_root_after": dict(workspace_root_after),
        "retain_hash_only_terminal_proof": True,
    }


def _validate_rollback(
    value: Any,
    plan: CursorWorkspacePlan,
    *,
    intent: Mapping[str, Any],
    receipt: Mapping[str, Any],
    halt_proof: Mapping[str, Any],
) -> Dict[str, Any]:
    keys = {
        "schema",
        "terminal_state",
        "plan_sha256",
        "intent_sha256",
        "materialization_receipt_sha256",
        "simulated_exact_halt_proof_sha256",
        "artifact_sha256",
        "removed_directories",
        "workspace_root_after",
        "retain_hash_only_terminal_proof",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValidationError("Cursor workspace rollback fields are invalid")
    expected_scalars = {
        "schema": ROLLBACK_SCHEMA,
        "terminal_state": "rolled_back",
        "plan_sha256": plan.plan_sha256,
        "intent_sha256": _document_sha256(intent),
        "materialization_receipt_sha256": _document_sha256(receipt),
        "simulated_exact_halt_proof_sha256": _document_sha256(halt_proof),
        "artifact_sha256": plan.raw["artifact"]["content_sha256"],
        "retain_hash_only_terminal_proof": True,
    }
    if any(value.get(key) != expected for key, expected in expected_scalars.items()):
        raise IdentityError("Cursor workspace rollback binding changed")
    expected_removed = [".cursor/rules", ".cursor"]
    if value.get("removed_directories") != expected_removed:
        raise IdentityError("Cursor workspace rollback scope changed")
    workspace_after = _validate_root(
        value.get("workspace_root_after"), kind="workspace_root"
    )
    _assert_identity(
        workspace_after,
        plan.raw["workspace_root"],
        label="rolled-back workspace root",
    )
    result = {
        **expected_scalars,
        "removed_directories": expected_removed,
        "workspace_root_after": workspace_after,
    }
    validate_bounded_json(
        result,
        max_depth=6,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    return result


def rollback_cursor_workspace_plane(
    plan: CursorWorkspacePlan,
    receipt: Mapping[str, Any],
    *,
    exact_halt_proof: Mapping[str, Any],
    adapter_manifest: AdapterManifest | Mapping[str, Any],
) -> Dict[str, Any]:
    """Remove only the receipted artifact/parents after exact simulated halt."""

    if not isinstance(plan, CursorWorkspacePlan):
        raise ValidationError("Cursor workspace plan is invalid")
    plan = CursorWorkspacePlan.from_dict(plan.to_dict())
    _validate_manifest_for_plan(plan, adapter_manifest)
    intent = _intent_for(plan)
    normalized_receipt = _validate_receipt(receipt, plan, intent)
    halt = _validate_simulated_halt(exact_halt_proof, plan, normalized_receipt)

    roots = _open_bound_roots(plan, compare_workspace_nlink=False)
    lane_descriptor, workspace_descriptor, transaction_descriptor = roots
    try:
        entries = _transaction_entries(transaction_descriptor)
        if entries == {INTENT_FILENAME, RECEIPT_FILENAME, ROLLBACK_FILENAME}:
            if os.listdir(workspace_descriptor):
                raise IdentityError("rolled-back Cursor workspace is no longer empty")
            persisted_intent, persisted_intent_identity = _read_record(
                transaction_descriptor,
                INTENT_FILENAME,
                label="Cursor workspace intent",
            )
            persisted_receipt, _ = _read_record(
                transaction_descriptor,
                RECEIPT_FILENAME,
                label="Cursor workspace receipt",
            )
            persisted_rollback, _ = _read_record(
                transaction_descriptor,
                ROLLBACK_FILENAME,
                label="Cursor workspace rollback",
            )
            if canonical_json_bytes(persisted_receipt) != canonical_json_bytes(
                normalized_receipt
            ):
                raise IdentityError("caller-supplied Cursor receipt is not exact")
            if persisted_intent_identity != normalized_receipt["intent_record"]:
                raise IdentityError("Cursor intent record identity changed")
            return _validate_rollback(
                persisted_rollback,
                plan,
                intent=_validate_intent(persisted_intent, plan),
                receipt=normalized_receipt,
                halt_proof=halt,
            )
        if entries != {INTENT_FILENAME, RECEIPT_FILENAME}:
            raise ConflictError("Cursor workspace rollback recovery is ambiguous")

        active = _verify_active_with_open_roots(
            plan,
            workspace_descriptor,
            transaction_descriptor,
            supplied_receipt=normalized_receipt,
        )
        _remove_artifact(workspace_descriptor, active)
        removed = _remove_created_directories(
            workspace_descriptor, active["created_directories"]
        )
        if os.listdir(workspace_descriptor):
            raise IdentityError("Cursor workspace is not empty after rollback")
        workspace_after = _directory_identity(
            os.fstat(workspace_descriptor),
            kind="workspace_root",
            path=plan.raw["workspace_root"]["path"],
            lane_relative_path=plan.raw["workspace_root"]["lane_relative_path"],
        )
        _assert_identity(
            workspace_after,
            plan.raw["workspace_root"],
            label="rolled-back workspace root",
        )
        rollback = _rollback_for(
            plan,
            intent=intent,
            receipt=active,
            halt_proof=halt,
            removed_directories=removed,
            workspace_root_after=workspace_after,
        )
        _persist_record(
            transaction_descriptor,
            ROLLBACK_FILENAME,
            rollback,
            label="Cursor workspace rollback",
        )
        return _validate_rollback(
            rollback,
            plan,
            intent=intent,
            receipt=active,
            halt_proof=halt,
        )
    finally:
        _close_roots(lane_descriptor, workspace_descriptor, transaction_descriptor)


def recover_cursor_workspace_plane(
    plan: CursorWorkspacePlan,
    *,
    adapter_manifest: AdapterManifest | Mapping[str, Any],
) -> CursorWorkspaceRecovery:
    """Classify only exact empty, active, or rolled-back durable states."""

    if not isinstance(plan, CursorWorkspacePlan):
        raise ValidationError("Cursor workspace plan is invalid")
    plan = CursorWorkspacePlan.from_dict(plan.to_dict())
    _validate_manifest_for_plan(plan, adapter_manifest)
    roots = _open_bound_roots(plan, compare_workspace_nlink=False)
    lane_descriptor, workspace_descriptor, transaction_descriptor = roots
    try:
        entries = _transaction_entries(transaction_descriptor)
        if not entries:
            if os.listdir(workspace_descriptor):
                raise ConflictError("Cursor workspace recovery is ambiguous")
            live = _directory_identity(
                os.fstat(workspace_descriptor),
                kind="workspace_root",
                path=plan.raw["workspace_root"]["path"],
                lane_relative_path=plan.raw["workspace_root"]["lane_relative_path"],
            )
            _assert_identity(live, plan.raw["workspace_root"], label="workspace root")
            return CursorWorkspaceRecovery(state="not_materialized")
        if entries == {INTENT_FILENAME, RECEIPT_FILENAME}:
            receipt = _verify_active_with_open_roots(
                plan, workspace_descriptor, transaction_descriptor
            )
            return CursorWorkspaceRecovery(
                state="materialized", materialization_receipt=receipt
            )
        if entries == {INTENT_FILENAME, RECEIPT_FILENAME, ROLLBACK_FILENAME}:
            if os.listdir(workspace_descriptor):
                raise ConflictError("Cursor workspace rollback recovery is ambiguous")
            intent, intent_identity = _read_record(
                transaction_descriptor,
                INTENT_FILENAME,
                label="Cursor workspace intent",
            )
            intent = _validate_intent(intent, plan)
            receipt, _ = _read_record(
                transaction_descriptor,
                RECEIPT_FILENAME,
                label="Cursor workspace receipt",
            )
            receipt = _validate_receipt(receipt, plan, intent)
            if intent_identity != receipt["intent_record"]:
                raise IdentityError("Cursor intent record identity changed")
            rollback, _ = _read_record(
                transaction_descriptor,
                ROLLBACK_FILENAME,
                label="Cursor workspace rollback",
            )
            # Recovery can bind the stored terminal proof without inventing or
            # replaying a halt claim.  Its hash remains authoritative; a new
            # rollback request must still supply the exact halt proof.
            expected_static = {
                "schema": ROLLBACK_SCHEMA,
                "terminal_state": "rolled_back",
                "plan_sha256": plan.plan_sha256,
                "intent_sha256": _document_sha256(intent),
                "materialization_receipt_sha256": _document_sha256(receipt),
                "artifact_sha256": plan.raw["artifact"]["content_sha256"],
                "removed_directories": [".cursor/rules", ".cursor"],
                "retain_hash_only_terminal_proof": True,
            }
            if (
                not isinstance(rollback, Mapping)
                or set(rollback)
                != set(expected_static)
                | {
                    "simulated_exact_halt_proof_sha256",
                    "workspace_root_after",
                }
                or any(
                    rollback.get(key) != item for key, item in expected_static.items()
                )
            ):
                raise IdentityError("Cursor workspace rollback binding changed")
            validate_sha256(
                rollback.get("simulated_exact_halt_proof_sha256"),
                "simulated exact-halt proof sha256",
            )
            workspace_after = _validate_root(
                rollback.get("workspace_root_after"), kind="workspace_root"
            )
            _assert_identity(
                workspace_after,
                plan.raw["workspace_root"],
                label="rolled-back workspace root",
            )
            live = _directory_identity(
                os.fstat(workspace_descriptor),
                kind="workspace_root",
                path=plan.raw["workspace_root"]["path"],
                lane_relative_path=plan.raw["workspace_root"]["lane_relative_path"],
            )
            _assert_identity(live, workspace_after, label="rolled-back workspace root")
            return CursorWorkspaceRecovery(
                state="rolled_back",
                materialization_receipt=receipt,
                rollback_receipt=dict(rollback),
            )
        raise ConflictError("Cursor workspace transaction recovery is ambiguous")
    finally:
        _close_roots(lane_descriptor, workspace_descriptor, transaction_descriptor)
