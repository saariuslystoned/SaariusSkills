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
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import ConflictError, IdentityError, ValidationError
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
ACTIVE_LEASE_STATES = {"launching", "active", "halting"}
LEASE_TRANSITIONS = {
    "launching": {"active", "failed"},
    "active": {"halting", "failed"},
    "halting": {"halting", "halted", "failed"},
    "halted": {"halted"},
    "failed": {"failed"},
}


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


def acquire_real_harness_lock(
    authority_root: Optional[Path] = None,
    *,
    reject_active_lease: bool = True,
) -> tuple[int, Dict[str, Any]]:
    """Acquire the one fixed per-account real-harness admission lock."""
    root = controller_authority_root(authority_root)
    lock_path = root / "real-harness.lock"
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
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ConflictError("another real-harness probe owns the campaign lock") from exc
        identity = {
            "authority_id": AUTHORITY_ID,
            "path": str(lock_path.resolve(strict=True)),
            "device": details.st_dev,
            "inode": details.st_ino,
            "uid": details.st_uid,
            "mode": stat.S_IMODE(details.st_mode),
        }
        if reject_active_lease:
            lease = current_session_lease(root)
            if lease is not None and lease["state"] in ACTIVE_LEASE_STATES:
                raise ConflictError(
                    "an admitted real-harness session owns the controller lease"
                )
        return descriptor, identity
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


def _lease_path(root: Path) -> Path:
    return root / "current-session-lease.json"


def lease_owner(
    *,
    activity: str,
    run_id: str,
    campaign_id: str,
    goal_fingerprint: str,
    proof_root: Path,
) -> Dict[str, str]:
    if activity not in {"probe", "session"}:
        raise ValidationError("controller lease activity is invalid")
    return {
        "activity": activity,
        "run_id": validate_identifier(run_id, "lease run id"),
        "campaign_id": validate_identifier(campaign_id, "lease campaign id"),
        "goal_fingerprint": validate_sha256(
            goal_fingerprint, "lease goal fingerprint"
        ),
        "proof_root": str(absolute_root(str(proof_root), "lease proof root")),
    }


def validate_lease_owner(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict) or set(value) != {
        "activity",
        "run_id",
        "campaign_id",
        "goal_fingerprint",
        "proof_root",
    }:
        raise ValidationError("controller lease owner fields are invalid")
    return lease_owner(
        activity=value["activity"],
        run_id=value["run_id"],
        campaign_id=value["campaign_id"],
        goal_fingerprint=value["goal_fingerprint"],
        proof_root=Path(value["proof_root"]),
    )


def current_session_lease(
    authority_root: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    root = controller_authority_root(authority_root)
    path = _lease_path(root)
    rows = Journal(root / "session-lease-history").snapshot()
    latest = rows[-1]["event"].get("lease") if rows else None
    if not path.exists() and latest is None:
        return None
    lease = (
        read_json(path, max_bytes=32768, reject_sensitive_fields=True)
        if path.exists()
        else latest
    )
    required = {
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
    if (
        set(lease) != required
        or lease.get("schema_version") != 1
        or lease.get("authority_id") != AUTHORITY_ID
        or isinstance(lease.get("generation"), bool)
        or not isinstance(lease.get("generation"), int)
        or lease["generation"] <= 0
        or lease.get("state")
        not in {"launching", "active", "halting", "halted", "failed"}
    ):
        raise ValidationError("controller session lease is invalid")
    validate_identifier(lease.get("session"), "lease session")
    validate_identifier(lease.get("controller"), "lease controller")
    if validate_lease_owner(lease.get("owner")) != lease["owner"]:
        raise IdentityError("controller session lease owner changed")
    if lease.get("target") not in {"agy", "cursor", "claude", "codex", "grok"}:
        raise ValidationError("controller session lease target is invalid")
    for name in ("created_at", "updated_at"):
        if (
            not isinstance(lease.get(name), str)
            or not lease[name]
            or len(lease[name]) > 80
        ):
            raise ValidationError("controller session lease timestamp is invalid")
    if lease["state"] == "launching":
        if lease.get("process") is not None:
            raise ValidationError("launching controller lease has a process identity")
    elif lease["state"] in {"active", "halting", "halted"} and not isinstance(
        lease.get("process"), dict
    ):
        raise ValidationError("controller lease lacks its process identity")
    if latest is None:
        raise IdentityError("controller session lease lacks its authority history")
    if latest != lease:
        current_identity = {
            name: lease[name]
            for name in (
                "authority_id",
                "generation",
                "session",
                "target",
                "controller",
                "owner",
                "created_at",
            )
        }
        latest_identity = {
            name: latest.get(name)
            for name in current_identity
        } if isinstance(latest, dict) else None
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
        atomic_write_json(path, latest)
        lease = latest
        if (
            set(lease) != required
            or lease.get("schema_version") != 1
            or lease.get("authority_id") != AUTHORITY_ID
            or isinstance(lease.get("generation"), bool)
            or not isinstance(lease.get("generation"), int)
            or lease["generation"] <= 0
            or lease.get("state") not in LEASE_TRANSITIONS
            or validate_lease_owner(lease.get("owner")) != lease["owner"]
        ):
            raise IdentityError("recovered controller lease is invalid")
        validate_identifier(lease.get("session"), "lease session")
        validate_identifier(lease.get("controller"), "lease controller")
        if lease.get("target") not in {"agy", "cursor", "claude", "codex", "grok"}:
            raise IdentityError("recovered controller lease target is invalid")
        if lease["state"] == "launching" and lease.get("process") is not None:
            raise IdentityError("recovered launching lease has a process identity")
        if lease["state"] in {"active", "halting", "halted"} and not isinstance(
            lease.get("process"), dict
        ):
            raise IdentityError("recovered controller lease lacks process identity")
    row = Journal(root / "session-lease-history").lookup(
        "lease-%d-%s" % (lease["generation"], lease["state"])
    )
    if row is None or row.get("event") != {
        "kind": "session_lease",
        "lease": lease,
    }:
        raise IdentityError("controller session lease is not in its authority ledger")
    return lease


def require_session_lease(
    *,
    session: str,
    target: str,
    controller: str,
    owner: Dict[str, str],
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
    lease = current_session_lease(authority_root)
    expected_owner = validate_lease_owner(owner)
    if (
        lease is None
        or lease["session"] != validate_identifier(session, "lease session")
        or lease["target"] != target
        or lease["controller"]
        != validate_identifier(controller, "lease controller")
        or lease["owner"] != expected_owner
        or lease["state"] not in states
    ):
        raise IdentityError("controller session lease identity mismatch")
    return lease


def _append_lease(root: Path, lease: Dict[str, Any]) -> Dict[str, Any]:
    row = Journal(root / "session-lease-history").append(
        request_id="lease-%d-%s" % (lease["generation"], lease["state"]),
        event={"kind": "session_lease", "lease": lease},
    )
    recorded = row["event"]["lease"]
    atomic_write_json(_lease_path(root), recorded)
    return recorded


def admit_session_lease(
    *,
    session: str,
    target: str,
    controller: str,
    owner: Dict[str, str],
    authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    validate_identifier(session, "lease session")
    validate_identifier(controller, "lease controller")
    if target not in {"agy", "cursor", "claude", "codex", "grok"}:
        raise ValidationError("controller session lease target is invalid")
    owner = validate_lease_owner(owner)
    descriptor: Optional[int] = None
    try:
        descriptor, _ = acquire_real_harness_lock(
            authority_root, reject_active_lease=False
        )
        root = controller_authority_root(authority_root)
        current = current_session_lease(root)
        if current is not None and current["state"] in ACTIVE_LEASE_STATES:
            if (
                current["state"] == "launching"
                and current["session"] == session
                and current["target"] == target
                and current["controller"] == controller
                and current["owner"] == owner
            ):
                return current
            raise ConflictError("another real-harness session owns the controller lease")
        now = _utc_now()
        lease = {
            "schema_version": 1,
            "authority_id": AUTHORITY_ID,
            "generation": 1 if current is None else current["generation"] + 1,
            "session": session,
            "target": target,
            "controller": controller,
            "owner": owner,
            "state": "launching",
            "created_at": now,
            "updated_at": now,
            "process": None,
        }
        return _append_lease(root, lease)
    finally:
        release_real_harness_lock(descriptor)


def transition_session_lease(
    *,
    session: str,
    target: str,
    controller: str,
    owner: Dict[str, str],
    state: str,
    process: Optional[Dict[str, Any]],
    authority_root: Optional[Path] = None,
    _lock_descriptor: Optional[int] = None,
) -> Dict[str, Any]:
    if state not in {"active", "halting", "halted", "failed"}:
        raise ValidationError("unsupported controller lease transition")
    owner = validate_lease_owner(owner)
    descriptor: Optional[int] = None
    owns_descriptor = _lock_descriptor is None
    try:
        root = controller_authority_root(authority_root)
        if _lock_descriptor is None:
            descriptor, _ = acquire_real_harness_lock(
                authority_root, reject_active_lease=False
            )
        else:
            descriptor = _lock_descriptor
            details = os.fstat(descriptor)
            lock_details = (root / "real-harness.lock").stat()
            if (
                details.st_dev != lock_details.st_dev
                or details.st_ino != lock_details.st_ino
                or not stat.S_ISREG(details.st_mode)
            ):
                raise IdentityError("controller lease lock descriptor changed")
        current = current_session_lease(root)
        if (
            current is None
            or current["session"] != session
            or current["target"] != target
            or current["controller"] != controller
            or current["owner"] != owner
        ):
            raise IdentityError("controller session lease identity mismatch")
        if (
            current["state"] in {"active", "halting", "halted"}
            and process is not None
            and current.get("process") != process
        ):
            raise IdentityError("controller session lease process identity changed")
        if current["state"] == state:
            if state == "active" and current.get("process") != process:
                raise IdentityError("active controller lease process identity changed")
            return current
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
        return _append_lease(root, updated)
    finally:
        if owns_descriptor:
            release_real_harness_lock(descriptor)


def _attestation_event(receipt_core: Dict[str, Any]) -> Dict[str, Any]:
    validate_bounded_json(
        receipt_core,
        max_depth=10,
        max_items=256,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    receipt_digest = sha256_bytes(canonical_json_bytes(receipt_core))
    for name in (
        "goal_fingerprint",
        "executable_fingerprint",
        "platform_fingerprint",
        "adapter_fingerprint",
        "protocol_fingerprint",
        "yolo_mapping_sha256",
        "accepted_checkpoint_id",
        "acceptance_sha256",
        "halt_receipt_sha256",
    ):
        validate_sha256(receipt_core.get(name), name.replace("_", " "))
    return {
        "kind": "qualification_attestation",
        "authority_id": AUTHORITY_ID,
        "receipt_digest": receipt_digest,
        "campaign_id": validate_identifier(
            receipt_core.get("campaign_id"), "campaign id"
        ),
        "goal_fingerprint": receipt_core["goal_fingerprint"],
        "run_id": validate_identifier(receipt_core.get("run_id"), "run id"),
        "target": receipt_core.get("target"),
        "controller": validate_identifier(
            receipt_core.get("controller"), "controller"
        ),
        "executable_fingerprint": receipt_core["executable_fingerprint"],
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
        "authority_id",
        "authority_root",
        "request_id",
        "ledger_sequence",
        "ledger_entry_hash",
        "receipt_digest",
    }
    if not isinstance(attestation, dict) or set(attestation) != expected_fields:
        raise ValidationError("qualification controller attestation fields are invalid")
    if (
        attestation.get("authority_id") != AUTHORITY_ID
        or attestation.get("authority_root") != str(root)
    ):
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
    row = Journal(root / "qualification-attestations").lookup(
        attestation["request_id"]
    )
    if (
        row is None
        or row.get("sequence") != attestation["ledger_sequence"]
        or row.get("entry_hash") != attestation["ledger_entry_hash"]
        or row.get("event") != event
    ):
        raise IdentityError("qualification controller attestation is unavailable")
    return row
