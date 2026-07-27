"""Fixed local controller authority for real-harness admission and attestation.

This is a cooperative same-UID authority, not a hostile-user security boundary.
The root is deliberately checkout- and CLI-independent so a target-writable
proof root cannot mint or serialize qualification on its own.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import os
import pwd
import stat
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .contracts import PROCESS_IDENTITY_FIELDS
from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .journal import Journal
from .safety import (
    absolute_root,
    atomic_write_json,
    canonical_json_bytes,
    read_json,
    sha256_bytes,
    validate_bounded_json,
    validate_identifier,
    validate_sha256,
)


AUTHORITY_ID = "puppet-local-controller-v1"
LEASE_SCHEMA_VERSION = 2
QUALIFICATION_ATTESTATION_SCHEMA_VERSION = 5
LEASE_TARGETS = frozenset({"agy", "cursor", "claude", "codex", "grok"})
ACTIVE_LEASE_STATES = {"launching", "active", "halting"}
LEGACY_FENCE_CONTROLLER = "per-target-lease-fence-v1"
LEASE_TRANSITIONS = {
    "launching": {"active", "failed"},
    "active": {"halting", "failed"},
    "halting": {"halting", "halted", "failed"},
    "halted": {"halted"},
    "failed": {"failed"},
}

_LEASE_V1_FIELDS = {
    "schema_version",
    "authority_id",
    "generation",
    "session",
    "target",
    "controller",
    "owner",
    "state",
    "created_at",
    "updated_at",
    "process",
}
_LEASE_V2_FIELDS = _LEASE_V1_FIELDS | {"instruction_manifest_sha256"}


def _lease_required_fields(value: Any) -> set[str]:
    if not isinstance(value, dict):
        raise ValidationError("controller session lease is invalid")
    version = value.get("schema_version")
    if type(version) is not int:
        raise ValidationError("controller session lease schema is invalid")
    if version == 1:
        return _LEASE_V1_FIELDS
    if version == LEASE_SCHEMA_VERSION:
        return _LEASE_V2_FIELDS
    raise ValidationError("controller session lease schema is invalid")


def _lease_instruction_sha(value: Dict[str, Any]) -> Optional[str]:
    if value.get("schema_version") == 1:
        return None
    return validate_sha256(
        value.get("instruction_manifest_sha256"),
        "lease instruction manifest fingerprint",
    )


def _lease_row_matches(row: Any, lease: Dict[str, Any]) -> bool:
    return (
        isinstance(row, dict)
        and row.get("request_id")
        == "lease-%d-%s" % (lease["generation"], lease["state"])
        and row.get("event") == {"kind": "session_lease", "lease": lease}
    )


def _is_v2_process_identity(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == PROCESS_IDENTITY_FIELDS
        and value.get("identity_version") == 2
        and not isinstance(value.get("pid"), bool)
        and isinstance(value.get("pid"), int)
        and value["pid"] > 1
        and isinstance(value.get("kernel_birth_id"), str)
        and bool(value["kernel_birth_id"])
        and len(value["kernel_birth_id"]) <= 200
        and not any(character in value["kernel_birth_id"] for character in "\x00\n\r")
        and isinstance(value.get("start"), str)
        and bool(value["start"])
        and len(value["start"]) <= 200
        and not any(character in value["start"] for character in "\x00\n\r")
        and isinstance(value.get("command"), str)
        and bool(value["command"])
        and len(value["command"]) <= 1000
        and "\x00" not in value["command"]
        and isinstance(value.get("executable_path"), str)
        and bool(value["executable_path"])
        and len(value["executable_path"]) <= 4096
        and "\x00" not in value["executable_path"]
        and Path(value["executable_path"]).is_absolute()
        and not isinstance(value.get("device"), bool)
        and isinstance(value.get("device"), int)
        and value["device"] > 0
        and not isinstance(value.get("inode"), bool)
        and isinstance(value.get("inode"), int)
        and value["inode"] > 0
    )


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def canonical_authority_root() -> Path:
    """Return the non-configurable authority root for the current OS account."""
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve(strict=True)
    return account_home / ".local" / "state" / "saarius-puppet-controller-v1"


def controller_authority_root(override: Optional[Path] = None) -> Path:
    """Create and validate the private authority root.

    ``override`` exists only for deterministic unit tests. Public CLI paths do
    not expose it and always use :func:`canonical_authority_root`.
    """
    requested = Path(override) if override is not None else canonical_authority_root()
    if not requested.is_absolute():
        raise ValidationError("controller authority root must be absolute")
    if requested.exists() and requested.is_symlink():
        raise IdentityError("controller authority root is a symlink")
    requested.mkdir(mode=0o700, parents=True, exist_ok=True)
    root = requested.resolve(strict=True)
    details = root.stat()
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) & 0o077
    ):
        raise IdentityError("controller authority root is not user-private")
    return root


def existing_controller_authority_root(
    override: Optional[Path] = None,
) -> Path:
    """Validate the fixed authority root without creating or repairing it."""

    requested = Path(override) if override is not None else canonical_authority_root()
    if not requested.is_absolute():
        raise ValidationError("controller authority root must be absolute")
    if requested.is_symlink() or not requested.is_dir():
        raise IdentityError("controller authority root is unavailable")
    root = requested.resolve(strict=True)
    details = root.stat()
    if (
        not stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) & 0o077
    ):
        raise IdentityError("controller authority root is not user-private")
    return root


def _validated_lease_target(target: str) -> str:
    if target not in LEASE_TARGETS:
        raise ValidationError("controller session lease target is invalid")
    return target


def _lock_path(root: Path, target: Optional[str] = None) -> Path:
    if target is None:
        return root / "real-harness.lock"
    return root / ("real-harness.%s.lock" % _validated_lease_target(target))


def acquire_real_harness_lock(
    authority_root: Optional[Path] = None,
    *,
    target: Optional[str] = None,
    reject_active_lease: bool = True,
    wait_seconds: float = 0.0,
) -> tuple[int, Dict[str, Any]]:
    """Acquire the legacy fence lock or one target-specific admission lock."""
    if (
        isinstance(wait_seconds, bool)
        or not isinstance(wait_seconds, (int, float))
        or wait_seconds < 0
        or wait_seconds > 5.0
    ):
        raise ValidationError("real-harness lock wait is invalid")
    root = controller_authority_root(authority_root)
    lock_path = _lock_path(root, target)
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(lock_path), flags, 0o600)
    try:
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) & 0o077
        ):
            raise IdentityError("real-harness authority lock is not user-private")
        deadline = time.monotonic() + float(wait_seconds)
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ConflictError(
                        "another real-harness probe owns the campaign lock"
                    ) from exc
                time.sleep(min(0.01, remaining))
        identity = {
            "authority_id": AUTHORITY_ID,
            "path": str(lock_path.resolve(strict=True)),
            "device": details.st_dev,
            "inode": details.st_ino,
            "uid": details.st_uid,
            "mode": stat.S_IMODE(details.st_mode),
        }
        if reject_active_lease:
            lease = current_session_lease(root, target=target)
            if lease is not None and lease["state"] in ACTIVE_LEASE_STATES:
                raise ConflictError(
                    "an admitted real-harness session owns the controller lease"
                )
            if target is not None:
                legacy = current_session_lease(root)
                if (
                    legacy is not None
                    and legacy["state"] in ACTIVE_LEASE_STATES
                    and not _is_backed_legacy_fence(root, legacy)
                ):
                    raise ConflictError(
                        "a legacy real-harness session owns the controller lease"
                    )
        return descriptor, identity
    except BaseException:
        os.close(descriptor)
        raise


def acquire_existing_real_harness_lock(
    authority_root: Optional[Path] = None,
    *,
    target: Optional[str] = None,
    wait_seconds: float = 0.0,
) -> tuple[int, Dict[str, Any]]:
    """Acquire an existing target or legacy lock without creating authority state."""

    if (
        isinstance(wait_seconds, bool)
        or not isinstance(wait_seconds, (int, float))
        or wait_seconds < 0
        or wait_seconds > 5.0
    ):
        raise ValidationError("real-harness lock wait is invalid")
    root = existing_controller_authority_root(authority_root)
    lock_path = _lock_path(
        root,
        None if target is None else _validated_lease_target(target),
    )
    if lock_path.is_symlink() or not lock_path.is_file():
        raise IdentityError("real-harness authority lock is unavailable")
    flags = os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(lock_path), flags)
    try:
        details = os.fstat(descriptor)
        path_details = lock_path.stat()
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_dev != path_details.st_dev
            or details.st_ino != path_details.st_ino
            or details.st_uid != os.getuid()
            or path_details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) & 0o077
            or stat.S_IMODE(path_details.st_mode) & 0o077
        ):
            raise IdentityError("real-harness authority lock is not user-private")
        deadline = time.monotonic() + float(wait_seconds)
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ConflictError(
                        "another real-harness probe owns the campaign lock"
                    ) from exc
                time.sleep(min(0.01, remaining))
        return descriptor, {
            "authority_id": AUTHORITY_ID,
            "path": str(lock_path.resolve(strict=True)),
            "device": details.st_dev,
            "inode": details.st_ino,
            "uid": details.st_uid,
            "mode": stat.S_IMODE(details.st_mode),
        }
    except BaseException:
        os.close(descriptor)
        raise


def release_real_harness_lock(descriptor: Optional[int]) -> None:
    if descriptor is None:
        return
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _lease_path(root: Path, target: Optional[str] = None) -> Path:
    if target is None:
        return root / "current-session-lease.json"
    return root / ("current-session-lease.%s.json" % _validated_lease_target(target))


def _lease_history_path(root: Path, target: Optional[str] = None) -> Path:
    if target is None:
        return root / "session-lease-history"
    return root / ("session-lease-history.%s" % _validated_lease_target(target))


def _strict_v2_lease(value: Any, *, target: str) -> Dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value) != _LEASE_V2_FIELDS
        or value.get("schema_version") != LEASE_SCHEMA_VERSION
        or value.get("authority_id") != AUTHORITY_ID
        or type(value.get("generation")) is not int
        or value["generation"] <= 0
        or value.get("target") != target
        or value.get("state") not in LEASE_TRANSITIONS
    ):
        raise ValidationError("controller session lease is not canonical")
    validate_identifier(value.get("session"), "lease session")
    validate_identifier(value.get("controller"), "lease controller")
    if validate_lease_owner(value.get("owner")) != value["owner"]:
        raise IdentityError("controller session lease owner changed")
    _lease_instruction_sha(value)
    for name in ("created_at", "updated_at"):
        if (
            not isinstance(value.get(name), str)
            or not value[name]
            or len(value[name]) > 80
        ):
            raise ValidationError("controller session lease timestamp is invalid")
    process = value.get("process")
    if value["state"] == "launching":
        if process is not None:
            raise IdentityError("launching controller lease has a process identity")
    elif value["state"] in {"active", "halting", "halted"}:
        if not _is_v2_process_identity(process):
            raise IdentityError("controller session lease lacks v2 process identity")
    elif process is not None and not _is_v2_process_identity(process):
        raise IdentityError("failed controller lease process identity is invalid")
    validate_bounded_json(
        value,
        max_items=64,
        max_string=1000,
        reject_sensitive_fields=True,
    )
    return dict(value)


def strict_session_lease_projection(
    authority_root: Optional[Path] = None,
    *,
    target: str,
) -> Dict[str, Any]:
    """Read one exact per-target projection and its canonical ledger, without repair."""

    target = _validated_lease_target(target)
    root = existing_controller_authority_root(authority_root)
    projection_path = _lease_path(root, target)
    history_path = _lease_history_path(root, target)
    if (
        projection_path.is_symlink()
        or not projection_path.is_file()
        or history_path.is_symlink()
        or not history_path.is_dir()
    ):
        raise IdentityError("controller session lease evidence is unavailable")
    for path in (projection_path, history_path):
        details = path.stat()
        if (
            details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) & 0o077
        ):
            raise IdentityError("controller session lease evidence is not user-private")
    try:
        rows = Journal(history_path).read_only_snapshot()
    except ValidationError as exc:
        raise IdentityError("controller session lease ledger is not canonical") from exc
    if not rows:
        raise IdentityError("controller session lease lacks its authority ledger")

    previous: Optional[Dict[str, Any]] = None
    observed_request_ids = set()
    fixed_fields = {
        "schema_version",
        "authority_id",
        "generation",
        "session",
        "target",
        "controller",
        "owner",
        "instruction_manifest_sha256",
        "created_at",
    }
    for row in rows:
        event = row.get("event")
        lease = _strict_v2_lease(
            event.get("lease") if isinstance(event, dict) else None,
            target=target,
        )
        request_id = "lease-%d-%s" % (lease["generation"], lease["state"])
        if (
            set(event) != {"kind", "lease"}
            or event.get("kind") != "session_lease"
            or row.get("request_id") != request_id
            or request_id in observed_request_ids
        ):
            raise IdentityError("controller session lease ledger is not canonical")
        observed_request_ids.add(request_id)
        if previous is None:
            if (
                lease["generation"] != 1
                or lease["state"] != "launching"
                or lease["process"] is not None
            ):
                raise IdentityError(
                    "controller session lease ledger is not canonical"
                )
        elif lease["generation"] == previous["generation"]:
            if (
                any(lease[name] != previous[name] for name in fixed_fields)
                or lease["state"] == previous["state"]
                or lease["state"] not in LEASE_TRANSITIONS[previous["state"]]
                or (
                    previous["process"] is not None
                    and lease["process"] != previous["process"]
                )
            ):
                raise IdentityError(
                    "controller session lease ledger is not canonical"
                )
        elif (
            previous["state"] not in {"halted", "failed"}
            or lease["generation"] != previous["generation"] + 1
            or lease["state"] != "launching"
            or lease["process"] is not None
        ):
            raise IdentityError("controller session lease ledger is not canonical")
        previous = lease

    projection = _strict_v2_lease(
        read_json(
            projection_path,
            max_bytes=32768,
            reject_sensitive_fields=True,
        ),
        target=target,
    )
    if projection != previous:
        raise IdentityError("controller session lease projection diverged")
    return projection


def _strict_legacy_lease(value: Any) -> Dict[str, Any]:
    required = _lease_required_fields(value)
    if (
        set(value) != required
        or value.get("authority_id") != AUTHORITY_ID
        or type(value.get("generation")) is not int
        or value["generation"] <= 0
        or value.get("target") not in LEASE_TARGETS
        or value.get("state") not in LEASE_TRANSITIONS
    ):
        raise ValidationError("legacy controller session lease is not canonical")
    validate_identifier(value.get("session"), "lease session")
    validate_identifier(value.get("controller"), "lease controller")
    if validate_lease_owner(value.get("owner")) != value["owner"]:
        raise IdentityError("legacy controller session lease owner changed")
    _lease_instruction_sha(value)
    for name in ("created_at", "updated_at"):
        if (
            not isinstance(value.get(name), str)
            or not value[name]
            or len(value[name]) > 80
        ):
            raise ValidationError(
                "legacy controller session lease timestamp is invalid"
            )
    process = value.get("process")
    if value["state"] == "launching":
        if process is not None:
            raise IdentityError("launching legacy controller lease has a process")
    elif value["state"] in {"active", "halting"}:
        if not _is_v2_process_identity(process):
            raise IdentityError("legacy controller lease lacks v2 process identity")
    elif value["state"] == "halted":
        if not isinstance(process, dict):
            raise IdentityError("halted legacy controller lease lacks process identity")
    elif process is not None and not isinstance(process, dict):
        raise IdentityError("failed legacy controller lease process is invalid")
    validate_bounded_json(
        value,
        max_items=64,
        max_string=1000,
        reject_sensitive_fields=True,
    )
    return dict(value)


def _strict_legacy_session_lease_projection(
    authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read the legacy projection and its canonical ledger, without repair."""

    root = existing_controller_authority_root(authority_root)
    projection_path = _lease_path(root)
    history_path = _lease_history_path(root)
    if (
        projection_path.is_symlink()
        or not projection_path.is_file()
        or history_path.is_symlink()
        or not history_path.is_dir()
    ):
        raise IdentityError("legacy controller lease evidence is unavailable")
    for path in (projection_path, history_path):
        details = path.stat()
        if (
            details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) & 0o077
        ):
            raise IdentityError(
                "legacy controller lease evidence is not user-private"
            )
    try:
        rows = Journal(history_path).read_only_snapshot()
    except ValidationError as exc:
        raise IdentityError("legacy controller lease ledger is not canonical") from exc
    if not rows:
        raise IdentityError("legacy controller lease lacks its authority ledger")

    previous: Optional[Dict[str, Any]] = None
    observed_request_ids = set()
    fixed_fields = {
        "schema_version",
        "authority_id",
        "generation",
        "session",
        "target",
        "controller",
        "owner",
        "created_at",
    }
    for row in rows:
        event = row.get("event")
        lease = _strict_legacy_lease(
            event.get("lease") if isinstance(event, dict) else None
        )
        request_id = "lease-%d-%s" % (lease["generation"], lease["state"])
        if (
            set(event) != {"kind", "lease"}
            or event.get("kind") != "session_lease"
            or row.get("request_id") != request_id
            or request_id in observed_request_ids
        ):
            raise IdentityError("legacy controller lease ledger is not canonical")
        observed_request_ids.add(request_id)
        if previous is None:
            if (
                lease["generation"] != 1
                or lease["state"] != "launching"
                or lease["process"] is not None
            ):
                raise IdentityError(
                    "legacy controller lease ledger is not canonical"
                )
        elif lease["generation"] == previous["generation"]:
            same_generation_fields = set(fixed_fields)
            if lease["schema_version"] == LEASE_SCHEMA_VERSION:
                same_generation_fields.add("instruction_manifest_sha256")
            if (
                any(
                    lease[name] != previous.get(name)
                    for name in same_generation_fields
                )
                or lease["state"] == previous["state"]
                or lease["state"] not in LEASE_TRANSITIONS[previous["state"]]
                or (
                    previous["process"] is not None
                    and lease["process"] != previous["process"]
                )
            ):
                raise IdentityError(
                    "legacy controller lease ledger is not canonical"
                )
        elif (
            previous["state"] not in {"halted", "failed"}
            or lease["generation"] != previous["generation"] + 1
            or lease["state"] != "launching"
            or lease["process"] is not None
        ):
            raise IdentityError("legacy controller lease ledger is not canonical")
        previous = lease

    projection = _strict_legacy_lease(
        read_json(
            projection_path,
            max_bytes=32768,
            reject_sensitive_fields=True,
        )
    )
    if projection != previous:
        raise IdentityError("legacy controller lease projection diverged")
    return projection


def lease_owner(
    *,
    activity: str,
    run_id: str,
    campaign_id: str,
    goal_fingerprint: str,
    proof_root: Path,
    state_root: Path,
) -> Dict[str, str]:
    if activity not in {"probe", "session"}:
        raise ValidationError("controller lease activity is invalid")
    return {
        "activity": activity,
        "run_id": validate_identifier(run_id, "lease run id"),
        "campaign_id": validate_identifier(campaign_id, "lease campaign id"),
        "goal_fingerprint": validate_sha256(goal_fingerprint, "lease goal fingerprint"),
        "proof_root": str(absolute_root(str(proof_root), "lease proof root")),
        "state_root": str(absolute_root(str(state_root), "lease state root")),
    }


def validate_lease_owner(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict) or set(value) != {
        "activity",
        "run_id",
        "campaign_id",
        "goal_fingerprint",
        "proof_root",
        "state_root",
    }:
        raise ValidationError("controller lease owner fields are invalid")
    return lease_owner(
        activity=value["activity"],
        run_id=value["run_id"],
        campaign_id=value["campaign_id"],
        goal_fingerprint=value["goal_fingerprint"],
        proof_root=Path(value["proof_root"]),
        state_root=Path(value["state_root"]),
    )


def current_session_lease(
    authority_root: Optional[Path] = None,
    *,
    target: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    root = controller_authority_root(authority_root)
    if target is not None:
        target = _validated_lease_target(target)
    path = _lease_path(root, target)
    history_path = _lease_history_path(root, target)
    rows = Journal(history_path).snapshot()
    latest = rows[-1]["event"].get("lease") if rows else None
    projection_missing = not path.exists()
    if projection_missing and latest is None:
        return None
    lease = (
        read_json(path, max_bytes=32768, reject_sensitive_fields=True)
        if path.exists()
        else latest
    )
    required = _lease_required_fields(lease)
    if (
        set(lease) != required
        or lease.get("authority_id") != AUTHORITY_ID
        or isinstance(lease.get("generation"), bool)
        or not isinstance(lease.get("generation"), int)
        or lease["generation"] <= 0
        or lease.get("state")
        not in {"launching", "active", "halting", "halted", "failed"}
    ):
        raise ValidationError("controller session lease is invalid")
    _lease_instruction_sha(lease)
    validate_identifier(lease.get("session"), "lease session")
    validate_identifier(lease.get("controller"), "lease controller")
    if validate_lease_owner(lease.get("owner")) != lease["owner"]:
        raise IdentityError("controller session lease owner changed")
    if lease.get("target") not in LEASE_TARGETS:
        raise ValidationError("controller session lease target is invalid")
    if target is not None and lease.get("target") != target:
        raise IdentityError("target lease projection is misrouted")
    for name in ("created_at", "updated_at"):
        if (
            not isinstance(lease.get(name), str)
            or not lease[name]
            or len(lease[name]) > 80
        ):
            raise ValidationError("controller session lease timestamp is invalid")
    if latest is None:
        raise IdentityError("controller session lease lacks its authority history")
    if latest != lease:
        identity_fields = [
            "schema_version",
            "authority_id",
            "generation",
            "session",
            "target",
            "controller",
            "owner",
            "created_at",
        ]
        if lease.get("schema_version") == LEASE_SCHEMA_VERSION:
            identity_fields.append("instruction_manifest_sha256")
        current_identity = {name: lease[name] for name in identity_fields}
        latest_identity = (
            {name: latest.get(name) for name in current_identity}
            if isinstance(latest, dict)
            else None
        )
        same_generation_successor = (
            latest_identity == current_identity
            and latest.get("state") in LEASE_TRANSITIONS[lease["state"]]
        )
        next_generation_admission = (
            isinstance(latest, dict)
            and lease["state"] in {"halted", "failed"}
            and latest.get("generation") == lease["generation"] + 1
            and latest.get("state") == "launching"
            and latest.get("process") is None
        )
        if not same_generation_successor and not next_generation_admission:
            raise IdentityError("controller session lease projection diverged")
        lease = latest
        required = _lease_required_fields(lease)
        if (
            set(lease) != required
            or lease.get("authority_id") != AUTHORITY_ID
            or isinstance(lease.get("generation"), bool)
            or not isinstance(lease.get("generation"), int)
            or lease["generation"] <= 0
            or lease.get("state") not in LEASE_TRANSITIONS
            or validate_lease_owner(lease.get("owner")) != lease["owner"]
        ):
            raise IdentityError("recovered controller lease is invalid")
        _lease_instruction_sha(lease)
        validate_identifier(lease.get("session"), "lease session")
        validate_identifier(lease.get("controller"), "lease controller")
        if lease.get("target") not in LEASE_TARGETS:
            raise IdentityError("recovered controller lease target is invalid")
        if target is not None and lease.get("target") != target:
            raise IdentityError("recovered target lease projection is misrouted")
        for name in ("created_at", "updated_at"):
            if (
                not isinstance(lease.get(name), str)
                or not lease[name]
                or len(lease[name]) > 80
            ):
                raise IdentityError(
                    "recovered controller session lease timestamp is invalid"
                )
        if lease["state"] == "launching" and lease.get("process") is not None:
            raise IdentityError("recovered launching lease has a process identity")
        if lease["state"] in {"active", "halting"} and not _is_v2_process_identity(
            lease.get("process")
        ):
            raise IdentityError("recovered controller lease lacks v2 process identity")
        if lease["state"] == "halted" and not isinstance(lease.get("process"), dict):
            raise IdentityError("recovered controller lease lacks process identity")
        if not _lease_row_matches(rows[-1], lease):
            raise IdentityError(
                "recovered controller session lease is not in its authority ledger"
            )
        atomic_write_json(path, lease)
    if lease["state"] == "launching":
        if lease.get("process") is not None:
            raise ValidationError("launching controller lease has a process identity")
    elif lease["state"] in {"active", "halting"} and not _is_v2_process_identity(
        lease.get("process")
    ):
        raise ValidationError("controller lease lacks its v2 process identity")
    elif lease["state"] == "halted" and not isinstance(lease.get("process"), dict):
        raise ValidationError("controller lease lacks its process identity")
    row = Journal(history_path).lookup(
        "lease-%d-%s" % (lease["generation"], lease["state"])
    )
    if row is None or row.get("event") != {
        "kind": "session_lease",
        "lease": lease,
    }:
        raise IdentityError("controller session lease is not in its authority ledger")
    if projection_missing:
        if not _lease_row_matches(rows[-1], lease):
            raise IdentityError(
                "recovered controller session lease is not in its authority ledger"
            )
        if path.is_symlink():
            raise IdentityError("controller session lease projection is a symlink")
        atomic_write_json(path, lease)
    return lease


def require_session_lease(
    *,
    session: str,
    target: str,
    controller: str,
    owner: Dict[str, str],
    instruction_manifest_sha256: str,
    states: set[str],
    authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Require the exact durable lease while the caller holds admission."""
    if not states or not states <= {
        "launching",
        "active",
        "halting",
        "halted",
        "failed",
    }:
        raise ValidationError("required controller lease states are invalid")
    root = controller_authority_root(authority_root)
    lease = current_session_lease(root, target=target)
    expected_owner = validate_lease_owner(owner)
    expected_instruction_sha = validate_sha256(
        instruction_manifest_sha256,
        "required lease instruction manifest fingerprint",
    )
    if lease is None:
        legacy = current_session_lease(root)
        if _lease_identity_matches(
            legacy,
            session=session,
            target=target,
            controller=controller,
            owner=expected_owner,
            instruction_manifest_sha256=expected_instruction_sha,
        ):
            lease = legacy
    if (
        lease is None
        or lease["session"] != validate_identifier(session, "lease session")
        or lease["target"] != target
        or lease["controller"] != validate_identifier(controller, "lease controller")
        or lease["owner"] != expected_owner
        or lease.get("instruction_manifest_sha256") != expected_instruction_sha
        or lease["state"] not in states
    ):
        raise IdentityError("controller session lease identity mismatch")
    return lease


def _lease_identity_matches(
    lease: Any,
    *,
    session: str,
    target: str,
    controller: str,
    owner: Dict[str, str],
    instruction_manifest_sha256: str,
) -> bool:
    return (
        isinstance(lease, dict)
        and lease.get("session") == validate_identifier(session, "lease session")
        and lease.get("target") == _validated_lease_target(target)
        and lease.get("controller")
        == validate_identifier(controller, "lease controller")
        and lease.get("owner") == owner
        and lease.get("instruction_manifest_sha256")
        == validate_sha256(
            instruction_manifest_sha256,
            "lease instruction manifest fingerprint",
        )
    )


def _append_lease(
    root: Path,
    lease: Dict[str, Any],
    *,
    target: Optional[str] = None,
) -> Dict[str, Any]:
    row = Journal(_lease_history_path(root, target)).append(
        request_id="lease-%d-%s" % (lease["generation"], lease["state"]),
        event={"kind": "session_lease", "lease": lease},
    )
    recorded = row["event"]["lease"]
    atomic_write_json(_lease_path(root, target), recorded)
    return recorded


def _legacy_fence_session(target: str, target_generation: int) -> str:
    return validate_identifier(
        "target-fence-%s-%d"
        % (
            _validated_lease_target(target),
            target_generation,
        ),
        "legacy fence session",
    )


def _legacy_fence_anchor(value: Any) -> Optional[tuple[str, int]]:
    if (
        not isinstance(value, dict)
        or value.get("controller") != LEGACY_FENCE_CONTROLLER
    ):
        return None
    session = value.get("session")
    target = value.get("target")
    if not isinstance(session, str) or target not in LEASE_TARGETS:
        return None
    prefix = "target-fence-%s-" % target
    if not session.startswith(prefix):
        return None
    generation_text = session[len(prefix) :]
    if not generation_text.isdigit() or int(generation_text) <= 0:
        return None
    return target, int(generation_text)


def _is_backed_legacy_fence(root: Path, lease: Dict[str, Any]) -> bool:
    anchor = _legacy_fence_anchor(lease)
    if anchor is None:
        return False
    target, generation = anchor
    target_lease = current_session_lease(root, target=target)
    return (
        target_lease is not None
        and target_lease["generation"] == generation
        and target_lease["owner"] == lease["owner"]
    )


def _target_leases(root: Path) -> Dict[str, Dict[str, Any]]:
    leases: Dict[str, Dict[str, Any]] = {}
    for target in sorted(LEASE_TARGETS):
        lease = current_session_lease(root, target=target)
        if lease is not None:
            leases[target] = lease
    return leases


def _advance_legacy_fence(
    root: Path,
    fence: Dict[str, Any],
    anchor: Dict[str, Any],
) -> Dict[str, Any]:
    if _legacy_fence_anchor(fence) != (
        anchor["target"],
        anchor["generation"],
    ):
        raise IdentityError("legacy compatibility fence anchor changed")
    if fence["owner"] != anchor["owner"]:
        raise IdentityError("legacy compatibility fence owner changed")
    if fence.get("schema_version") != 1:
        raise IdentityError("legacy compatibility fence schema changed")
    desired = anchor["state"]
    if fence["state"] == desired:
        if desired in {"active", "halting", "halted"} and fence.get(
            "process"
        ) != anchor.get("process"):
            raise IdentityError("legacy compatibility fence process changed")
        return fence
    if desired == "failed":
        states = ["failed"]
    else:
        order = ["launching", "active", "halting", "halted"]
        try:
            start = order.index(fence["state"])
            finish = order.index(desired)
        except ValueError as exc:
            raise IdentityError("legacy compatibility fence state is invalid") from exc
        if finish < start:
            raise IdentityError("legacy compatibility fence state regressed")
        states = order[start + 1 : finish + 1]
    current = fence
    for state in states:
        if state not in LEASE_TRANSITIONS[current["state"]]:
            raise IdentityError("legacy compatibility fence transition is invalid")
        process = anchor.get("process")
        if state in {"active", "halting", "halted"} and not _is_v2_process_identity(
            process
        ):
            raise IdentityError("legacy compatibility fence lacks process identity")
        current = dict(
            current,
            state=state,
            updated_at=_utc_now(),
            process=process if process is not None else current.get("process"),
        )
        current = _append_lease(root, current)
    return current


def _start_legacy_fence(
    root: Path,
    anchor: Dict[str, Any],
    previous: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    if anchor["state"] not in ACTIVE_LEASE_STATES:
        raise IdentityError("cannot fence a terminal target lease")
    now = _utc_now()
    fence = {
        "schema_version": 1,
        "authority_id": AUTHORITY_ID,
        "generation": 1 if previous is None else previous["generation"] + 1,
        "session": _legacy_fence_session(anchor["target"], anchor["generation"]),
        "target": anchor["target"],
        "controller": LEGACY_FENCE_CONTROLLER,
        "owner": anchor["owner"],
        "state": "launching",
        "created_at": now,
        "updated_at": now,
        "process": None,
    }
    fence = _append_lease(root, fence)
    return _advance_legacy_fence(root, fence, anchor)


def _sync_legacy_fence(root: Path) -> Optional[Dict[str, Any]]:
    """Project per-target truth into the legacy lease so old controllers fail closed.

    The caller holds one target lock and then the legacy global lock. Per-target
    projections remain authoritative; this projection is intentionally lossy
    and anchors one active target at a time for v1 compatibility.
    """

    leases = _target_leases(root)
    active = {
        target: lease
        for target, lease in leases.items()
        if lease["state"] in ACTIVE_LEASE_STATES
    }
    legacy = current_session_lease(root)
    anchor_key = _legacy_fence_anchor(legacy)
    if legacy is not None and legacy["state"] in ACTIVE_LEASE_STATES:
        if anchor_key is None or not _is_backed_legacy_fence(root, legacy):
            raise ConflictError(
                "a legacy real-harness session owns the controller lease"
            )
        anchor_target, anchor_generation = anchor_key
        anchor = leases[anchor_target]
        if anchor["generation"] != anchor_generation:
            raise IdentityError("legacy compatibility fence generation changed")
        legacy = _advance_legacy_fence(root, legacy, anchor)
        if legacy["state"] in ACTIVE_LEASE_STATES:
            return legacy
    if not active:
        return legacy
    selected = active[sorted(active)[0]]
    return _start_legacy_fence(root, selected, legacy)


def _validate_lock_descriptor(
    root: Path,
    target: Optional[str],
    descriptor: int,
) -> None:
    details = os.fstat(descriptor)
    lock_path = _lock_path(root, target)
    if not lock_path.exists() or lock_path.is_symlink():
        raise IdentityError("controller lease lock descriptor changed")
    lock_details = lock_path.stat()
    if (
        details.st_dev != lock_details.st_dev
        or details.st_ino != lock_details.st_ino
        or not stat.S_ISREG(details.st_mode)
        or details.st_uid != os.getuid()
        or lock_details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) & 0o077
        or stat.S_IMODE(lock_details.st_mode) & 0o077
    ):
        raise IdentityError("controller lease lock descriptor changed")


def admit_session_lease(
    *,
    session: str,
    target: str,
    controller: str,
    owner: Dict[str, str],
    instruction_manifest_sha256: str,
    authority_root: Optional[Path] = None,
    _lock_descriptor: Optional[int] = None,
) -> Dict[str, Any]:
    validate_identifier(session, "lease session")
    validate_identifier(controller, "lease controller")
    target = _validated_lease_target(target)
    owner = validate_lease_owner(owner)
    instruction_manifest_sha256 = validate_sha256(
        instruction_manifest_sha256,
        "lease instruction manifest fingerprint",
    )
    descriptor: Optional[int] = None
    legacy_descriptor: Optional[int] = None
    owns_descriptor = _lock_descriptor is None
    try:
        root = controller_authority_root(authority_root)
        if _lock_descriptor is None:
            descriptor, _ = acquire_real_harness_lock(
                authority_root,
                target=target,
                reject_active_lease=False,
            )
        else:
            descriptor = _lock_descriptor
            _validate_lock_descriptor(root, target, descriptor)
        legacy_descriptor, _ = acquire_real_harness_lock(
            authority_root,
            reject_active_lease=False,
            wait_seconds=1.0,
        )
        _sync_legacy_fence(root)
        current = current_session_lease(root, target=target)
        if current is not None and current["state"] in ACTIVE_LEASE_STATES:
            if (
                current["state"] == "launching"
                and current["session"] == session
                and current["target"] == target
                and current["controller"] == controller
                and current["owner"] == owner
                and current.get("instruction_manifest_sha256")
                == instruction_manifest_sha256
            ):
                _sync_legacy_fence(root)
                return current
            raise ConflictError(
                "another real-harness session owns the controller lease"
            )
        now = _utc_now()
        lease = {
            "schema_version": LEASE_SCHEMA_VERSION,
            "authority_id": AUTHORITY_ID,
            "generation": 1 if current is None else current["generation"] + 1,
            "session": session,
            "target": target,
            "controller": controller,
            "owner": owner,
            "instruction_manifest_sha256": instruction_manifest_sha256,
            "state": "launching",
            "created_at": now,
            "updated_at": now,
            "process": None,
        }
        recorded = _append_lease(root, lease, target=target)
        _sync_legacy_fence(root)
        return recorded
    finally:
        release_real_harness_lock(legacy_descriptor)
        if owns_descriptor:
            release_real_harness_lock(descriptor)


def transition_session_lease(
    *,
    session: str,
    target: str,
    controller: str,
    owner: Dict[str, str],
    instruction_manifest_sha256: str,
    state: str,
    process: Optional[Dict[str, Any]],
    authority_root: Optional[Path] = None,
    _lock_descriptor: Optional[int] = None,
) -> Dict[str, Any]:
    if state not in {"active", "halting", "halted", "failed"}:
        raise ValidationError("unsupported controller lease transition")
    owner = validate_lease_owner(owner)
    instruction_manifest_sha256 = validate_sha256(
        instruction_manifest_sha256,
        "lease instruction manifest fingerprint",
    )
    target = _validated_lease_target(target)
    descriptor: Optional[int] = None
    legacy_descriptor: Optional[int] = None
    owns_descriptor = _lock_descriptor is None
    try:
        root = controller_authority_root(authority_root)
        if _lock_descriptor is None:
            descriptor, _ = acquire_real_harness_lock(
                authority_root,
                target=target,
                reject_active_lease=False,
            )
        else:
            descriptor = _lock_descriptor
            _validate_lock_descriptor(root, target, descriptor)
        legacy_descriptor, _ = acquire_real_harness_lock(
            authority_root,
            reject_active_lease=False,
            wait_seconds=1.0,
        )
        current = current_session_lease(root, target=target)
        legacy_current = current_session_lease(root)
        legacy_transition = current is None and _lease_identity_matches(
            legacy_current,
            session=session,
            target=target,
            controller=controller,
            owner=owner,
            instruction_manifest_sha256=instruction_manifest_sha256,
        )
        if legacy_transition:
            current = legacy_current
        if (
            current is None
            or current["session"] != session
            or current["target"] != target
            or current["controller"] != controller
            or current["owner"] != owner
            or current.get("instruction_manifest_sha256") != instruction_manifest_sha256
        ):
            raise IdentityError("controller session lease identity mismatch")
        if (
            current["state"] in {"active", "halting", "halted"}
            and process is not None
            and current.get("process") != process
        ):
            raise IdentityError("controller session lease process identity changed")
        if current["state"] == state:
            if state in {"active", "halting"} and not _is_v2_process_identity(process):
                raise ValidationError(
                    "controller lease transition lacks v2 process identity"
                )
            if (
                state in {"active", "halting", "halted"}
                and current.get("process") != process
            ):
                raise IdentityError(
                    "%s controller lease process identity changed" % state
                )
            if not legacy_transition:
                _sync_legacy_fence(root)
            return current
        if state in {"active", "halting", "halted"} and not _is_v2_process_identity(
            process
        ):
            raise ValidationError(
                "controller lease transition lacks v2 process identity"
            )
        if state not in LEASE_TRANSITIONS[current["state"]]:
            raise ValidationError("illegal controller session lease transition")
        if state != "failed" and not isinstance(process, dict):
            raise ValidationError("controller lease transition lacks process identity")
        updated = dict(
            current,
            state=state,
            updated_at=_utc_now(),
            process=process if process is not None else current.get("process"),
        )
        validate_bounded_json(
            updated, max_items=64, max_string=1000, reject_sensitive_fields=True
        )
        recorded = _append_lease(
            root,
            updated,
            target=None if legacy_transition else target,
        )
        if not legacy_transition:
            _sync_legacy_fence(root)
        return recorded
    finally:
        release_real_harness_lock(legacy_descriptor)
        if owns_descriptor:
            release_real_harness_lock(descriptor)


def reconcile_halted_session_lease(
    *,
    session: str,
    target: str,
    controller: str,
    owner: Dict[str, str],
    instruction_manifest_sha256: str,
    process: Dict[str, Any],
    authority_root: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Finish an interrupted terminal transition without touching a later lease.

    The session registry and the fixed authority ledger are separate durable
    records.  A controller can therefore stop after committing ``HALTED`` to
    the registry while its exact authority lease is still ``halting``.  This
    helper reconciles only that same lease under its target authority lock.  A
    newer or unrelated lease is deliberately left unchanged.
    """

    expected_owner = validate_lease_owner(owner)
    instruction_manifest_sha256 = validate_sha256(
        instruction_manifest_sha256,
        "lease instruction manifest fingerprint",
    )
    descriptor: Optional[int] = None
    try:
        root = controller_authority_root(authority_root)
        descriptor, _ = acquire_real_harness_lock(
            authority_root,
            target=target,
            reject_active_lease=False,
        )
        current = current_session_lease(root, target=target)
        if current is None:
            legacy = current_session_lease(root)
            if _lease_identity_matches(
                legacy,
                session=session,
                target=target,
                controller=controller,
                owner=expected_owner,
                instruction_manifest_sha256=instruction_manifest_sha256,
            ):
                current = legacy
        if current is None or (
            current["session"] != validate_identifier(session, "lease session")
            or current["target"] != target
            or current["controller"]
            != validate_identifier(controller, "lease controller")
            or current["owner"] != expected_owner
            or current.get("instruction_manifest_sha256") != instruction_manifest_sha256
        ):
            return None
        if current["state"] not in {"halting", "halted"}:
            raise IdentityError("HALTED registry has a non-terminal controller lease")
        return transition_session_lease(
            session=session,
            target=target,
            controller=controller,
            owner=expected_owner,
            instruction_manifest_sha256=instruction_manifest_sha256,
            state="halted",
            process=process,
            authority_root=root,
            _lock_descriptor=descriptor,
        )
    finally:
        release_real_harness_lock(descriptor)


def halt_exact_session_lease_generation(
    *,
    session: str,
    target: str,
    controller: str,
    owner: Dict[str, str],
    instruction_manifest_sha256: str,
    process: Dict[str, Any],
    generation: int,
    authority_root: Optional[Path] = None,
    _lock_descriptor: int,
) -> tuple[Dict[str, Any], bool, Dict[str, Any], bool]:
    """Commit one exact target generation and its backed legacy fence."""

    target = _validated_lease_target(target)
    if type(generation) is not int or generation <= 0:
        raise ValidationError("controller lease generation is invalid")
    root = existing_controller_authority_root(authority_root)
    _validate_lock_descriptor(root, target, _lock_descriptor)
    expected_owner = validate_lease_owner(owner)
    instruction_manifest_sha256 = validate_sha256(
        instruction_manifest_sha256,
        "lease instruction manifest fingerprint",
    )
    expected_session = validate_identifier(session, "lease session")
    legacy_descriptor: Optional[int] = None
    try:
        legacy_descriptor, _ = acquire_existing_real_harness_lock(
            root,
            wait_seconds=1.0,
        )
        _validate_lock_descriptor(root, target, _lock_descriptor)
        _validate_lock_descriptor(root, None, legacy_descriptor)
        current = strict_session_lease_projection(root, target=target)
        legacy = _strict_legacy_session_lease_projection(root)
        if (
            current["generation"] != generation
            or current["session"] != expected_session
            or current["target"] != target
            or current["controller"]
            != validate_identifier(controller, "lease controller")
            or current["owner"] != expected_owner
            or current["instruction_manifest_sha256"]
            != instruction_manifest_sha256
            or current["process"] != process
            or current["state"] not in {"halting", "halted"}
        ):
            raise IdentityError("controller session lease identity mismatch")
        if (
            legacy.get("schema_version") != 1
            or _legacy_fence_anchor(legacy) != (target, generation)
            or legacy["target"] != target
            or legacy["owner"] != expected_owner
            or legacy["process"] != process
            or legacy["state"] not in {"halting", "halted"}
            or (
                current["state"] == "halting"
                and legacy["state"] == "halted"
            )
        ):
            raise IdentityError("legacy compatibility fence identity mismatch")

        target_transitioned = current["state"] == "halting"
        legacy_transitioned = legacy["state"] == "halting"
        if target_transitioned:
            current = _append_lease(
                root,
                dict(current, state="halted", updated_at=_utc_now()),
                target=target,
            )
        if legacy_transitioned:
            legacy = _append_lease(
                root,
                dict(legacy, state="halted", updated_at=_utc_now()),
            )
        return current, target_transitioned, legacy, legacy_transitioned
    finally:
        release_real_harness_lock(legacy_descriptor)


def _attestation_event(receipt_core: Dict[str, Any]) -> Dict[str, Any]:
    validate_bounded_json(
        receipt_core,
        max_depth=10,
        max_items=256,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    receipt_schema = receipt_core.get("schema_version")
    if receipt_schema in {1, 2, 3, 4}:
        raise UnsupportedError(
            "legacy qualification receipt cannot authorize a runtime attestation"
        )
    if receipt_schema != QUALIFICATION_ATTESTATION_SCHEMA_VERSION:
        raise ValidationError("unsupported qualification receipt attestation schema")
    receipt_digest = sha256_bytes(canonical_json_bytes(receipt_core))
    for name in (
        "goal_fingerprint",
        "executable_fingerprint",
        "execution_fingerprint",
        "platform_fingerprint",
        "adapter_fingerprint",
        "protocol_fingerprint",
        "yolo_mapping_sha256",
        "launch_plan_sha256",
        "instruction_policy_fingerprint",
        "accepted_checkpoint_id",
        "acceptance_sha256",
        "halt_receipt_sha256",
    ):
        validate_sha256(receipt_core.get(name), name.replace("_", " "))
    validate_sha256(
        receipt_core.get("subscription_profile_sha256"),
        "subscription profile fingerprint",
    )
    return {
        "schema_version": QUALIFICATION_ATTESTATION_SCHEMA_VERSION,
        "kind": "qualification_attestation",
        "authority_id": AUTHORITY_ID,
        "receipt_digest": receipt_digest,
        "campaign_id": validate_identifier(
            receipt_core.get("campaign_id"), "campaign id"
        ),
        "goal_fingerprint": receipt_core["goal_fingerprint"],
        "run_id": validate_identifier(receipt_core.get("run_id"), "run id"),
        "target": receipt_core.get("target"),
        "controller": validate_identifier(receipt_core.get("controller"), "controller"),
        "executable_fingerprint": receipt_core["executable_fingerprint"],
        "execution_fingerprint": receipt_core["execution_fingerprint"],
        "platform_fingerprint": receipt_core["platform_fingerprint"],
        "adapter_fingerprint": receipt_core["adapter_fingerprint"],
        "protocol_fingerprint": receipt_core["protocol_fingerprint"],
        "yolo_mapping_sha256": receipt_core["yolo_mapping_sha256"],
        "accepted_checkpoint_id": receipt_core["accepted_checkpoint_id"],
        "acceptance_sha256": receipt_core["acceptance_sha256"],
        "halt_receipt_sha256": receipt_core["halt_receipt_sha256"],
    }


def attest_qualification(
    receipt_core: Dict[str, Any],
    *,
    authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Append one idempotent controller attestation for a complete receipt core."""
    root = controller_authority_root(authority_root)
    event = _attestation_event(receipt_core)
    request_id = "qualify-%s" % event["receipt_digest"][:40]
    row = Journal(root / "qualification-attestations").append(
        request_id=request_id,
        event=event,
    )
    return {
        "schema_version": QUALIFICATION_ATTESTATION_SCHEMA_VERSION,
        "authority_id": AUTHORITY_ID,
        "authority_root": str(root),
        "request_id": request_id,
        "ledger_sequence": row["sequence"],
        "ledger_entry_hash": row["entry_hash"],
        "receipt_digest": event["receipt_digest"],
    }


def verify_qualification_attestation(
    receipt_core: Dict[str, Any],
    attestation: Dict[str, Any],
    *,
    authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Require exact inclusion in the fixed controller-owned hash chain."""
    root = controller_authority_root(authority_root)
    expected_fields = {
        "schema_version",
        "authority_id",
        "authority_root",
        "request_id",
        "ledger_sequence",
        "ledger_entry_hash",
        "receipt_digest",
    }
    if not isinstance(attestation, dict) or set(attestation) != expected_fields:
        raise ValidationError("qualification controller attestation fields are invalid")
    attestation_schema = attestation.get("schema_version")
    if attestation_schema in {1, 2, 3}:
        raise UnsupportedError(
            "legacy qualification controller attestation is not authoritative"
        )
    if attestation_schema != QUALIFICATION_ATTESTATION_SCHEMA_VERSION:
        raise ValidationError("unsupported qualification controller attestation schema")
    if attestation.get("authority_id") != AUTHORITY_ID or attestation.get(
        "authority_root"
    ) != str(root):
        raise IdentityError("qualification controller authority identity mismatch")
    validate_identifier(attestation.get("request_id"), "attestation request id")
    validate_sha256(attestation.get("ledger_entry_hash"), "attestation entry")
    validate_sha256(attestation.get("receipt_digest"), "attested receipt")
    if (
        isinstance(attestation.get("ledger_sequence"), bool)
        or not isinstance(attestation.get("ledger_sequence"), int)
        or attestation["ledger_sequence"] <= 0
    ):
        raise ValidationError("qualification attestation sequence is invalid")
    event = _attestation_event(receipt_core)
    if event["receipt_digest"] != attestation["receipt_digest"]:
        raise IdentityError("qualification receipt is not the attested receipt")
    row = Journal(root / "qualification-attestations").lookup(attestation["request_id"])
    if (
        row is None
        or row.get("sequence") != attestation["ledger_sequence"]
        or row.get("entry_hash") != attestation["ledger_entry_hash"]
        or row.get("event") != event
    ):
        raise IdentityError("qualification controller attestation is unavailable")
    return row
