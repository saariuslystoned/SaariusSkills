"""One-use Claude marker signal consumption with hash-only retention.

This source-only controller substrate does not launch a target, inspect a
checkpoint, prove delivery or authorship, evaluate no-bleed, or authorize
qualification.  It consumes only the fixed signal committed by the compiled
marker protocol and records the observation in the canonical controller
journal after the raw signal has been unlinked.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .adapter_manifest import AdapterManifest
from .authority import AUTHORITY_ID, controller_authority_root
from .errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from .journal import Journal
from .matched_control import (
    MARKER_SIGNAL_PROTOCOL_SHA256,
    MARKER_SIGNAL_RELATIVE_PATH,
    CompiledMarkerInstruction,
    _MARKER_PATTERN,
    bind_claude_marker_activation_plan,
    validate_compiled_marker_binding,
)
from .matched_control_authority import (
    verify_claude_marker_activation_join_attestation,
)
from .plane_activation import ActivationPlan
from .safety import (
    canonical_json_bytes,
    exclusive_lock,
    sha256_bytes,
    validate_identifier,
    validate_sha256,
)


MARKER_SIGNAL_OBSERVATION_SCHEMA_VERSION = 1
MARKER_SIGNAL_OBSERVATION_EVENT_SCHEMA = (
    "puppet.claude-marker-signal-observation-event/v1"
)
MARKER_SIGNAL_OBSERVATION_KIND = "claude_marker_signal_consumed"
_JOURNAL_NAME = "claude-marker-signal-observations"
_RESERVATION_JOURNAL_NAME = "claude-marker-signal-reservations"
_PREPARE_LOCK_NAME = ".claude-marker-signal-prepare.lock"
_RESERVATION_EVENT_SCHEMA = "puppet.claude-marker-signal-reservation-event/v1"
_RESERVATION_EVENT_KIND = "claude_marker_signal_reserved"
_SIGNAL_PARENT, _SIGNAL_LEAF = MARKER_SIGNAL_RELATIVE_PATH.split("/", 1)
_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
_PUBLIC_FIELDS = {
    "schema_version",
    "authority_id",
    "authority_root",
    "request_id",
    "ledger_sequence",
    "ledger_entry_hash",
    "activation_join_sha256",
    "signal_observation_sha256",
}
_EVENT_FIELDS = {
    "schema",
    "kind",
    "authority_id",
    "target",
    "session_profile",
    "session",
    "run_id",
    "activation_join_sha256",
    "activation_attestation_entry_sha256",
    "signal_reservation_entry_sha256",
    "compiled_binding_sha256",
    "marker_sha256",
    "signal_protocol_sha256",
    "workspace_identity_sha256",
    "signal_parent_identity_sha256",
    "signal_file_identity_sha256",
    "signal_consumed",
    "raw_signal_retained",
    "signal_path_retained",
    "delivery_authorized",
    "runtime_scan_authorized",
    "checkpoint_observed",
    "lease_bound",
    "no_bleed_evaluated",
    "no_bleed_verified",
    "qualification_authorized",
    "promotion_authorized",
    "result",
}
_RESERVATION_EVENT_FIELDS = {
    "schema",
    "kind",
    "authority_id",
    "target",
    "session_profile",
    "session",
    "run_id",
    "activation_join_sha256",
    "activation_attestation_entry_sha256",
    "compiled_binding_sha256",
    "signal_protocol_sha256",
    "workspace_identity_sha256",
    "signal_parent_identity_sha256",
    "signal_leaf_absent",
    "raw_signal_retained",
    "delivery_authorized",
    "runtime_scan_authorized",
    "checkpoint_observed",
    "lease_bound",
    "no_bleed_evaluated",
    "no_bleed_verified",
    "qualification_authorized",
    "promotion_authorized",
    "result",
}


def _require_fd_primitives() -> None:
    if not getattr(os, "O_NOFOLLOW", 0):
        raise UnsupportedError("marker signal consumption requires O_NOFOLLOW")
    if any(item not in os.supports_dir_fd for item in (os.open, os.stat, os.unlink)):
        raise UnsupportedError("marker signal consumption requires dir-FD primitives")


def _directory_identity(details: os.stat_result) -> Dict[str, int]:
    if not stat.S_ISDIR(details.st_mode):
        raise IdentityError("marker signal parent is not a directory")
    return {
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "gid": details.st_gid,
        "mode": stat.S_IMODE(details.st_mode),
        "nlink": details.st_nlink,
    }


def _stable_directory_identity(identity: Mapping[str, int]) -> Dict[str, int]:
    return {
        name: identity[name]
        for name in ("device", "inode", "uid", "gid", "mode")
    }


def _file_identity(details: os.stat_result) -> Dict[str, int]:
    return {
        "device": details.st_dev,
        "inode": details.st_ino,
        "uid": details.st_uid,
        "gid": details.st_gid,
        "mode": stat.S_IMODE(details.st_mode),
        "nlink": details.st_nlink,
        "size": details.st_size,
        "mtime_ns": details.st_mtime_ns,
        "ctime_ns": details.st_ctime_ns,
    }


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return _file_identity(left) == _file_identity(right)


def _plan_workspace_identity(plan: ActivationPlan) -> Dict[str, Any]:
    return dict(plan.raw["workspace_root"])


def _assert_workspace_fd(
    descriptor: int, *, expected: Mapping[str, Any]
) -> Dict[str, int]:
    details = os.fstat(descriptor)
    observed = _directory_identity(details)
    expected_observed = {
        name: expected[name]
        for name in ("device", "inode", "uid", "gid", "mode", "nlink")
    }
    if observed != expected_observed:
        raise IdentityError("marker signal workspace identity changed")
    try:
        live = os.stat(expected["path"], follow_symlinks=False)
    except OSError as exc:
        raise IdentityError("marker signal workspace path changed") from exc
    if _directory_identity(live) != observed:
        raise IdentityError("marker signal workspace path changed")
    return observed


def _assert_parent_fd(
    workspace_descriptor: int,
    parent_descriptor: int,
    *,
    expected: Mapping[str, int],
) -> Dict[str, int]:
    opened = _directory_identity(os.fstat(parent_descriptor))
    try:
        live = os.stat(
            _SIGNAL_PARENT, dir_fd=workspace_descriptor, follow_symlinks=False
        )
    except OSError as exc:
        raise IdentityError("marker signal parent path changed") from exc
    live_identity = _directory_identity(live)
    stable_fields = ("device", "inode", "uid", "gid", "mode")
    if (
        any(opened[name] != expected[name] for name in stable_fields)
        or any(live_identity[name] != opened[name] for name in stable_fields)
        or opened["uid"] != os.getuid()
        or opened["mode"] != 0o700
    ):
        raise IdentityError("marker signal parent identity changed")
    return opened


def _leaf_exists(parent_descriptor: int) -> bool:
    try:
        os.stat(_SIGNAL_LEAF, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise IdentityError("marker signal leaf state is ambiguous") from exc
    return True


def _source_marker(compiled: CompiledMarkerInstruction) -> bytes:
    binding = validate_compiled_marker_binding(compiled)
    matches = _MARKER_PATTERN.findall(compiled.rendered)
    if len(matches) != 1:
        raise IdentityError("source marker signal is unavailable")
    marker = matches[0]
    if sha256_bytes(marker) != binding["marker_sha256"]:
        raise IdentityError("source marker signal identity changed")
    return marker


def _validated_source(
    compiled: CompiledMarkerInstruction,
    *,
    activation_plan: ActivationPlan,
    descriptor: Mapping[str, Any],
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    activation_attestation: Mapping[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any], bytes, Dict[str, Any]]:
    binding = validate_compiled_marker_binding(compiled)
    join = bind_claude_marker_activation_plan(
        compiled,
        activation_plan=activation_plan,
        descriptor=descriptor,
        adapter_manifest=adapter_manifest,
    )
    attestation_row = verify_claude_marker_activation_join_attestation(
        activation_attestation,
        compiled,
        activation_plan=activation_plan,
        descriptor=descriptor,
        adapter_manifest=adapter_manifest,
    )
    return binding, join, _source_marker(compiled), attestation_row


def _event_source_fields(
    *,
    binding: Mapping[str, Any],
    join: Mapping[str, Any],
    attestation_row: Mapping[str, Any],
    reservation_row: Mapping[str, Any],
    workspace_identity_sha256: str,
) -> Dict[str, Any]:
    return {
        "schema": MARKER_SIGNAL_OBSERVATION_EVENT_SCHEMA,
        "kind": MARKER_SIGNAL_OBSERVATION_KIND,
        "authority_id": AUTHORITY_ID,
        "target": "claude",
        "session_profile": "regular",
        "session": validate_identifier(join["session"], "marker signal session"),
        "run_id": validate_identifier(join["run_id"], "marker signal run id"),
        "activation_join_sha256": sha256_bytes(canonical_json_bytes(dict(join))),
        "activation_attestation_entry_sha256": validate_sha256(
            attestation_row["entry_hash"], "marker activation attestation entry"
        ),
        "signal_reservation_entry_sha256": validate_sha256(
            reservation_row["entry_hash"], "marker signal reservation entry"
        ),
        "compiled_binding_sha256": sha256_bytes(canonical_json_bytes(dict(binding))),
        "marker_sha256": validate_sha256(
            binding["marker_sha256"], "source marker signal"
        ),
        "signal_protocol_sha256": MARKER_SIGNAL_PROTOCOL_SHA256,
        "workspace_identity_sha256": validate_sha256(
            workspace_identity_sha256, "marker signal workspace"
        ),
    }


def _reservation_event(
    *,
    binding: Mapping[str, Any],
    join: Mapping[str, Any],
    attestation_row: Mapping[str, Any],
    workspace_identity_sha256: str,
    parent_identity_sha256: str,
) -> Dict[str, Any]:
    event = {
        "schema": _RESERVATION_EVENT_SCHEMA,
        "kind": _RESERVATION_EVENT_KIND,
        "authority_id": AUTHORITY_ID,
        "target": "claude",
        "session_profile": "regular",
        "session": validate_identifier(join["session"], "marker signal session"),
        "run_id": validate_identifier(join["run_id"], "marker signal run id"),
        "activation_join_sha256": sha256_bytes(canonical_json_bytes(dict(join))),
        "activation_attestation_entry_sha256": validate_sha256(
            attestation_row["entry_hash"], "marker activation attestation entry"
        ),
        "compiled_binding_sha256": sha256_bytes(canonical_json_bytes(dict(binding))),
        "signal_protocol_sha256": MARKER_SIGNAL_PROTOCOL_SHA256,
        "workspace_identity_sha256": validate_sha256(
            workspace_identity_sha256, "marker signal workspace"
        ),
        "signal_parent_identity_sha256": validate_sha256(
            parent_identity_sha256, "marker signal parent"
        ),
        "signal_leaf_absent": True,
        "raw_signal_retained": False,
        "delivery_authorized": False,
        "runtime_scan_authorized": False,
        "checkpoint_observed": False,
        "lease_bound": False,
        "no_bleed_evaluated": False,
        "no_bleed_verified": False,
        "qualification_authorized": False,
        "promotion_authorized": False,
        "result": "signal_guard_prepared_only",
    }
    if set(event) != _RESERVATION_EVENT_FIELDS:
        raise IdentityError("marker signal reservation fields changed")
    return event


def _observation_request_id(activation_join_sha256: str) -> str:
    return (
        "claude-marker-signal-%s"
        % validate_sha256(activation_join_sha256, "marker signal activation join")[:40]
    )


def _reservation_request_id(activation_join_sha256: str) -> str:
    return (
        "claude-marker-rsv-%s"
        % validate_sha256(activation_join_sha256, "marker signal activation join")[:40]
    )


def _public_observation(row: Mapping[str, Any]) -> Dict[str, Any]:
    event = row.get("event")
    if not isinstance(event, dict) or set(event) != _EVENT_FIELDS:
        raise IdentityError("marker signal observation row is invalid")
    return {
        "schema_version": MARKER_SIGNAL_OBSERVATION_SCHEMA_VERSION,
        "authority_id": AUTHORITY_ID,
        "authority_root": str(controller_authority_root()),
        "request_id": row["request_id"],
        "ledger_sequence": row["sequence"],
        "ledger_entry_hash": row["entry_hash"],
        "activation_join_sha256": event["activation_join_sha256"],
        "signal_observation_sha256": sha256_bytes(canonical_json_bytes(event)),
    }


class _ClaudeMarkerSignalGuard:
    """Private FD-bound one-use signal guard with a body-free representation."""

    def __init__(
        self,
        *,
        workspace_descriptor: int,
        parent_descriptor: int,
        workspace_plan_identity: Mapping[str, Any],
        parent_identity: Mapping[str, int],
        marker: bytes,
        event_source_fields: Mapping[str, Any],
        authority_root: Path,
    ) -> None:
        self._workspace_descriptor = workspace_descriptor
        self._parent_descriptor = parent_descriptor
        self._workspace_plan_identity = dict(workspace_plan_identity)
        self._parent_identity = dict(parent_identity)
        self._marker = bytes(marker)
        self._event_source_fields = dict(event_source_fields)
        self._authority_root = Path(authority_root)
        self._closed = False
        self._signal_unlinked = False
        self._observation_recorded = False

    def __repr__(self) -> str:
        return (
            "ClaudeMarkerSignalGuard(session=%r, run_id=%r, protocol=%r, "
            "closed=%r, signal_unlinked=%r, observation_recorded=%r)"
            % (
                self._event_source_fields["session"],
                self._event_source_fields["run_id"],
                MARKER_SIGNAL_PROTOCOL_SHA256,
                self._closed,
                self._signal_unlinked,
                self._observation_recorded,
            )
        )

    def __enter__(self) -> "_ClaudeMarkerSignalGuard":
        if self._closed:
            raise IdentityError("marker signal guard is closed")
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for descriptor in (self._parent_descriptor, self._workspace_descriptor):
            try:
                os.close(descriptor)
            except OSError:
                pass

    def consume(self) -> Dict[str, Any]:
        """Consume and unlink the exact signal, then journal a hash-only row."""

        if self._closed:
            raise IdentityError("marker signal guard is closed")
        if self._signal_unlinked or self._observation_recorded:
            raise ConflictError("marker signal was already consumed")
        signal_descriptor: Optional[int] = None
        try:
            _assert_workspace_fd(
                self._workspace_descriptor,
                expected=self._workspace_plan_identity,
            )
            parent_identity = _assert_parent_fd(
                self._workspace_descriptor,
                self._parent_descriptor,
                expected=self._parent_identity,
            )
            try:
                signal_descriptor = os.open(
                    _SIGNAL_LEAF, _FILE_FLAGS, dir_fd=self._parent_descriptor
                )
            except OSError as exc:
                raise IdentityError("marker signal leaf is unavailable") from exc
            opened = os.fstat(signal_descriptor)
            try:
                live = os.stat(
                    _SIGNAL_LEAF,
                    dir_fd=self._parent_descriptor,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise IdentityError("marker signal leaf path changed") from exc
            expected_length = len(self._marker)
            if (
                not stat.S_ISREG(opened.st_mode)
                or not _same_file(opened, live)
                or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_nlink != 1
                or opened.st_size != expected_length
            ):
                raise IdentityError("marker signal file identity is invalid")
            payload = bytearray()
            while len(payload) <= expected_length:
                block = os.read(signal_descriptor, expected_length + 1 - len(payload))
                if not block:
                    break
                payload.extend(block)
            if bytes(payload) != self._marker:
                raise IdentityError("marker signal bytes do not match the source")
            after = os.fstat(signal_descriptor)
            try:
                path_after = os.stat(
                    _SIGNAL_LEAF,
                    dir_fd=self._parent_descriptor,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise IdentityError(
                    "marker signal leaf changed during consumption"
                ) from exc
            if not _same_file(opened, after) or not _same_file(after, path_after):
                raise IdentityError("marker signal leaf changed during consumption")
            signal_identity = _file_identity(after)
            os.unlink(_SIGNAL_LEAF, dir_fd=self._parent_descriptor)
            self._signal_unlinked = True
            unlinked = os.fstat(signal_descriptor)
            if (
                unlinked.st_dev != after.st_dev
                or unlinked.st_ino != after.st_ino
                or not stat.S_ISREG(unlinked.st_mode)
                or unlinked.st_uid != os.getuid()
                or stat.S_IMODE(unlinked.st_mode) != 0o600
                or unlinked.st_size != expected_length
                or unlinked.st_nlink != 0
            ):
                raise IdentityError("marker signal inode retained links after unlink")
            os.fsync(self._parent_descriptor)
            if _leaf_exists(self._parent_descriptor):
                raise IdentityError("marker signal leaf remained after unlink")
            _assert_workspace_fd(
                self._workspace_descriptor,
                expected=self._workspace_plan_identity,
            )
            _assert_parent_fd(
                self._workspace_descriptor,
                self._parent_descriptor,
                expected=self._parent_identity,
            )
            event = {
                **self._event_source_fields,
                "signal_parent_identity_sha256": sha256_bytes(
                    canonical_json_bytes(_stable_directory_identity(parent_identity))
                ),
                "signal_file_identity_sha256": sha256_bytes(
                    canonical_json_bytes(signal_identity)
                ),
                "signal_consumed": True,
                "raw_signal_retained": False,
                "signal_path_retained": False,
                "delivery_authorized": False,
                "runtime_scan_authorized": False,
                "checkpoint_observed": False,
                "lease_bound": False,
                "no_bleed_evaluated": False,
                "no_bleed_verified": False,
                "qualification_authorized": False,
                "promotion_authorized": False,
                "result": "signal_bytes_observed_only",
            }
            if set(event) != _EVENT_FIELDS:
                raise IdentityError("marker signal observation fields changed")
            request_id = _observation_request_id(event["activation_join_sha256"])
            row = Journal(self._authority_root / _JOURNAL_NAME).append(
                request_id=request_id,
                event=event,
            )
            self._observation_recorded = True
            return _public_observation(row)
        finally:
            if signal_descriptor is not None:
                os.close(signal_descriptor)
            if self._signal_unlinked:
                self.close()


def prepare_claude_marker_signal(
    compiled: CompiledMarkerInstruction,
    *,
    activation_plan: ActivationPlan,
    descriptor: Mapping[str, Any],
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    activation_attestation: Mapping[str, Any],
) -> _ClaudeMarkerSignalGuard:
    """Bind fixed workspace/parent FDs and prove the signal leaf is absent."""

    _require_fd_primitives()
    if not isinstance(activation_plan, ActivationPlan):
        raise ValidationError("marker signal requires an activation plan")
    plan = ActivationPlan.from_dict(activation_plan.to_dict())
    binding, join, marker, attestation_row = _validated_source(
        compiled,
        activation_plan=plan,
        descriptor=descriptor,
        adapter_manifest=adapter_manifest,
        activation_attestation=activation_attestation,
    )
    root = controller_authority_root()
    if activation_attestation.get("authority_root") != str(root):
        raise IdentityError("marker signal authority root changed")
    join_sha = sha256_bytes(canonical_json_bytes(dict(join)))
    observation_request_id = _observation_request_id(join_sha)
    reservation_request_id = _reservation_request_id(join_sha)
    observation_journal = Journal(root / _JOURNAL_NAME)
    reservation_journal = Journal(root / _RESERVATION_JOURNAL_NAME)
    workspace_plan_identity = _plan_workspace_identity(plan)
    workspace_descriptor: Optional[int] = None
    parent_descriptor: Optional[int] = None
    with exclusive_lock(root / _PREPARE_LOCK_NAME):
        if reservation_journal.lookup(reservation_request_id) is not None:
            raise ConflictError("marker signal reservation already exists for this join")
        if observation_journal.lookup(observation_request_id) is not None:
            raise ConflictError("marker signal observation already exists for this join")
        try:
            workspace_descriptor = os.open(
                workspace_plan_identity["path"], _DIRECTORY_FLAGS
            )
            _assert_workspace_fd(workspace_descriptor, expected=workspace_plan_identity)
            parent_descriptor = os.open(
                _SIGNAL_PARENT, _DIRECTORY_FLAGS, dir_fd=workspace_descriptor
            )
            parent_identity = _directory_identity(os.fstat(parent_descriptor))
            _assert_parent_fd(
                workspace_descriptor,
                parent_descriptor,
                expected=parent_identity,
            )
            if _leaf_exists(parent_descriptor):
                raise ConflictError("marker signal leaf already exists before delivery")
            workspace_identity_sha256 = sha256_bytes(
                canonical_json_bytes(workspace_plan_identity)
            )
            parent_identity_sha256 = sha256_bytes(
                canonical_json_bytes(_stable_directory_identity(parent_identity))
            )
            reservation_row = reservation_journal.append(
                request_id=reservation_request_id,
                event=_reservation_event(
                    binding=binding,
                    join=join,
                    attestation_row=attestation_row,
                    workspace_identity_sha256=workspace_identity_sha256,
                    parent_identity_sha256=parent_identity_sha256,
                ),
            )
            guard = _ClaudeMarkerSignalGuard(
                workspace_descriptor=workspace_descriptor,
                parent_descriptor=parent_descriptor,
                workspace_plan_identity=workspace_plan_identity,
                parent_identity=parent_identity,
                marker=marker,
                event_source_fields=_event_source_fields(
                    binding=binding,
                    join=join,
                    attestation_row=attestation_row,
                    reservation_row=reservation_row,
                    workspace_identity_sha256=workspace_identity_sha256,
                ),
                authority_root=root,
            )
            workspace_descriptor = None
            parent_descriptor = None
            return guard
        finally:
            for candidate in (parent_descriptor, workspace_descriptor):
                if candidate is not None:
                    os.close(candidate)


def recover_claude_marker_signal_observation(
    compiled: CompiledMarkerInstruction,
    *,
    activation_plan: ActivationPlan,
    descriptor: Mapping[str, Any],
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    activation_attestation: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    """Recover one reserved signal without creating or reusing a reservation.

    An existing hash-only observation is reconstructed from the fixed journal.
    Otherwise, an exact extant source signal is consumed through the original
    reservation's FD-bound identities.  An absent signal returns ``None``; an
    ambiguous or non-source leaf is preserved and fails closed.
    """

    _require_fd_primitives()
    if not isinstance(activation_plan, ActivationPlan):
        raise ValidationError("marker signal recovery requires an activation plan")
    plan = ActivationPlan.from_dict(activation_plan.to_dict())
    binding, join, marker, attestation_row = _validated_source(
        compiled,
        activation_plan=plan,
        descriptor=descriptor,
        adapter_manifest=adapter_manifest,
        activation_attestation=activation_attestation,
    )
    root = controller_authority_root()
    if activation_attestation.get("authority_root") != str(root):
        raise IdentityError("marker signal recovery authority root changed")
    join_sha = sha256_bytes(canonical_json_bytes(dict(join)))
    observation_request_id = _observation_request_id(join_sha)
    reservation_request_id = _reservation_request_id(join_sha)
    observation_journal = Journal(root / _JOURNAL_NAME)
    reservation_journal = Journal(root / _RESERVATION_JOURNAL_NAME)
    workspace_plan_identity = _plan_workspace_identity(plan)
    workspace_identity_sha256 = sha256_bytes(
        canonical_json_bytes(workspace_plan_identity)
    )
    workspace_descriptor: Optional[int] = None
    parent_descriptor: Optional[int] = None
    with exclusive_lock(root / _PREPARE_LOCK_NAME):
        reservation_row = reservation_journal.lookup(reservation_request_id)
        if (
            reservation_row is None
            or reservation_row.get("request_id") != reservation_request_id
            or not isinstance(reservation_row.get("event"), dict)
            or set(reservation_row["event"]) != _RESERVATION_EVENT_FIELDS
        ):
            raise IdentityError("marker signal recovery reservation is unavailable")
        reservation_event = reservation_row["event"]
        parent_identity_sha256 = validate_sha256(
            reservation_event.get("signal_parent_identity_sha256"),
            "marker signal recovery parent",
        )
        expected_reservation_event = _reservation_event(
            binding=binding,
            join=join,
            attestation_row=attestation_row,
            workspace_identity_sha256=workspace_identity_sha256,
            parent_identity_sha256=parent_identity_sha256,
        )
        if reservation_event != expected_reservation_event:
            raise IdentityError("marker signal recovery reservation identity changed")
        validate_sha256(
            reservation_row.get("entry_hash"), "marker signal recovery reservation"
        )
        observed_row = observation_journal.lookup(observation_request_id)
        existing_observation: Optional[Dict[str, Any]] = None
        if observed_row is not None:
            existing_observation = _public_observation(observed_row)
            verify_claude_marker_signal_observation(
                existing_observation,
                compiled,
                activation_plan=plan,
                descriptor=descriptor,
                adapter_manifest=adapter_manifest,
                activation_attestation=activation_attestation,
            )
        try:
            workspace_descriptor = os.open(
                workspace_plan_identity["path"], _DIRECTORY_FLAGS
            )
            _assert_workspace_fd(workspace_descriptor, expected=workspace_plan_identity)
            parent_descriptor = os.open(
                _SIGNAL_PARENT, _DIRECTORY_FLAGS, dir_fd=workspace_descriptor
            )
            parent_identity = _directory_identity(os.fstat(parent_descriptor))
            _assert_parent_fd(
                workspace_descriptor,
                parent_descriptor,
                expected=parent_identity,
            )
            if (
                sha256_bytes(
                    canonical_json_bytes(_stable_directory_identity(parent_identity))
                )
                != parent_identity_sha256
            ):
                raise IdentityError("marker signal recovery parent identity changed")
            if existing_observation is not None:
                if _leaf_exists(parent_descriptor):
                    raise ConflictError(
                        "marker signal leaf was recreated after observation"
                    )
                return existing_observation
            if not _leaf_exists(parent_descriptor):
                return None
            guard = _ClaudeMarkerSignalGuard(
                workspace_descriptor=workspace_descriptor,
                parent_descriptor=parent_descriptor,
                workspace_plan_identity=workspace_plan_identity,
                parent_identity=parent_identity,
                marker=marker,
                event_source_fields=_event_source_fields(
                    binding=binding,
                    join=join,
                    attestation_row=attestation_row,
                    reservation_row=reservation_row,
                    workspace_identity_sha256=workspace_identity_sha256,
                ),
                authority_root=root,
            )
            workspace_descriptor = None
            parent_descriptor = None
        finally:
            for candidate in (parent_descriptor, workspace_descriptor):
                if candidate is not None:
                    os.close(candidate)
    try:
        observation = guard.consume()
    finally:
        guard.close()
    verify_claude_marker_signal_observation(
        observation,
        compiled,
        activation_plan=plan,
        descriptor=descriptor,
        adapter_manifest=adapter_manifest,
        activation_attestation=activation_attestation,
    )
    return observation


def verify_claude_marker_signal_observation(
    observation: Mapping[str, Any],
    compiled: CompiledMarkerInstruction,
    *,
    activation_plan: ActivationPlan,
    descriptor: Mapping[str, Any],
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    activation_attestation: Mapping[str, Any],
) -> Dict[str, Any]:
    """Rejoin a hash-only observation to source and its fixed journal row."""

    root = controller_authority_root()
    if not isinstance(observation, Mapping) or set(observation) != _PUBLIC_FIELDS:
        raise ValidationError("marker signal observation fields are invalid")
    if (
        type(observation.get("schema_version")) is not int
        or observation.get("schema_version") != MARKER_SIGNAL_OBSERVATION_SCHEMA_VERSION
    ):
        raise ValidationError("marker signal observation schema is invalid")
    if observation.get("authority_id") != AUTHORITY_ID or observation.get(
        "authority_root"
    ) != str(root):
        raise IdentityError("marker signal observation authority changed")
    request_id = validate_identifier(
        observation.get("request_id"), "marker signal observation request"
    )
    entry_hash = validate_sha256(
        observation.get("ledger_entry_hash"), "marker signal ledger entry"
    )
    join_sha = validate_sha256(
        observation.get("activation_join_sha256"), "marker signal activation join"
    )
    observation_sha = validate_sha256(
        observation.get("signal_observation_sha256"), "marker signal observation"
    )
    sequence = observation.get("ledger_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValidationError("marker signal observation sequence is invalid")
    binding, join, _marker, attestation_row = _validated_source(
        compiled,
        activation_plan=activation_plan,
        descriptor=descriptor,
        adapter_manifest=adapter_manifest,
        activation_attestation=activation_attestation,
    )
    expected_join_sha = sha256_bytes(canonical_json_bytes(join))
    if join_sha != expected_join_sha or request_id != _observation_request_id(
        expected_join_sha
    ):
        raise IdentityError("marker signal activation join changed")
    reservation_request_id = _reservation_request_id(expected_join_sha)
    reservation_row = Journal(root / _RESERVATION_JOURNAL_NAME).lookup(
        reservation_request_id
    )
    if (
        reservation_row is None
        or reservation_row.get("request_id") != reservation_request_id
        or not isinstance(reservation_row.get("event"), dict)
        or set(reservation_row["event"]) != _RESERVATION_EVENT_FIELDS
    ):
        raise IdentityError("marker signal controller reservation is unavailable")
    reservation_event = reservation_row["event"]
    parent_identity_sha256 = validate_sha256(
        reservation_event.get("signal_parent_identity_sha256"),
        "marker signal reservation parent",
    )
    expected_reservation_event = _reservation_event(
        binding=binding,
        join=join,
        attestation_row=attestation_row,
        workspace_identity_sha256=sha256_bytes(
            canonical_json_bytes(_plan_workspace_identity(activation_plan))
        ),
        parent_identity_sha256=parent_identity_sha256,
    )
    if reservation_event != expected_reservation_event:
        raise IdentityError("marker signal reservation source identity changed")
    validate_sha256(
        reservation_row.get("entry_hash"), "marker signal reservation entry"
    )
    row = Journal(root / _JOURNAL_NAME).lookup(request_id)
    if (
        row is None
        or row.get("sequence") != sequence
        or row.get("entry_hash") != entry_hash
        or not isinstance(row.get("event"), dict)
        or set(row["event"]) != _EVENT_FIELDS
        or sha256_bytes(canonical_json_bytes(row["event"])) != observation_sha
    ):
        raise IdentityError("marker signal controller observation is unavailable")
    expected_source = _event_source_fields(
        binding=binding,
        join=join,
        attestation_row=attestation_row,
        reservation_row=reservation_row,
        workspace_identity_sha256=sha256_bytes(
            canonical_json_bytes(_plan_workspace_identity(activation_plan))
        ),
    )
    event = row["event"]
    if any(event.get(name) != value for name, value in expected_source.items()):
        raise IdentityError("marker signal observation source identity changed")
    for name in (
        "workspace_identity_sha256",
        "signal_parent_identity_sha256",
        "signal_file_identity_sha256",
    ):
        validate_sha256(event.get(name), name.replace("_", " "))
    if (
        event["workspace_identity_sha256"]
        != expected_source["workspace_identity_sha256"]
        or event["signal_parent_identity_sha256"] != parent_identity_sha256
        or event.get("signal_consumed") is not True
        or event.get("raw_signal_retained") is not False
        or event.get("signal_path_retained") is not False
        or event.get("result") != "signal_bytes_observed_only"
        or any(
            event.get(name) is not False
            for name in (
                "delivery_authorized",
                "runtime_scan_authorized",
                "checkpoint_observed",
                "lease_bound",
                "no_bleed_evaluated",
                "no_bleed_verified",
                "qualification_authorized",
                "promotion_authorized",
            )
        )
    ):
        raise IdentityError("marker signal observation gained runtime authority")
    return row


__all__ = [
    "MARKER_SIGNAL_OBSERVATION_EVENT_SCHEMA",
    "MARKER_SIGNAL_OBSERVATION_KIND",
    "MARKER_SIGNAL_OBSERVATION_SCHEMA_VERSION",
    "prepare_claude_marker_signal",
    "recover_claude_marker_signal_observation",
    "verify_claude_marker_signal_observation",
]
