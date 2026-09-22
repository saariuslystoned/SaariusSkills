"""Isolated-root ownership for the explicit antigravity-acp candidate.

Ordinary launch stays unavailable. Reuses puppet_lib.safety helpers and the
existing PuppetError(detail, *, blocker=...) signatures.
"""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from puppet_lib.authority import AUTHORITY_ID
from puppet_lib.caller import make_blocker
from puppet_lib.errors import ConflictError, IdentityError, UnsupportedError, ValidationError
from puppet_lib.safety import (
    absolute_root,
    atomic_write_json,
    exclusive_lock,
    read_json,
    validate_identifier,
)


ADAPTER_ID = "antigravity-acpx"
TRANSPORT_ID = "antigravity-acp"
TARGET = "agy"
GENERIC_ACP_ID = "acp"
ACPX_QUALIFICATION = "non_qualifying"

OWNERSHIP_SCHEMA = "puppet.antigravity-acpx-ownership/v1"
ACPX_ARTIFACT_SHA256 = (
    "5df327172d83644b5f44925386095c8facce28eb78d1ea81f243d7b100d6e614"
)
ACPX_ARTIFACT_PATH = (
    "runs/puppet-dual-acp-controller-runs/20260921/artifacts-refresh-2e05de52/acpx-0.18.0.tgz"
)
ACPX_MERGE_COMMIT = "2e05de525dd1ab62e9e74bf02d91e3638920fcf3"

_TURN_STOP_REASONS = frozenset(
    {
        "end_turn",
        "max_tokens",
        "cancelled",
        "canceled",
        "error",
        "stop",
        "refused",
        "timeout",
        "length",
        "content_filter",
    }
)
_TURN_SECRET_CODE_PARTS = ("token", "secret", "password", "prompt", "credential")
_TURN_PERMISSION_ACP_KINDS = frozenset(
    {
        "read",
        "edit",
        "delete",
        "move",
        "search",
        "execute",
        "think",
        "fetch",
        "switch_mode",
        "other",
        "absent",
    }
)
_TURN_PERMISSION_KIND_SOURCES = frozenset({"standardized", "inferred", "absent"})
_TURN_PERMISSION_ID_CLASSES = frozenset({"opaque", "interaction", "absent"})
_TURN_PERMISSION_PATH_SOURCES = frozenset(
    {"raw_input", "locations", "both", "absent", "multiple", "conflicting"}
)
_TURN_PERMISSION_PATH_CARDINALITIES = frozenset({"zero", "one", "multiple"})
_TURN_PERMISSION_PATH_CLASSES = frozenset(
    {"intended", "non_intended", "absent", "ambiguous"}
)
_TURN_PERMISSION_OPTION_KINDS = (
    "allow_once",
    "allow_always",
    "reject_once",
    "reject_always",
)
_TURN_PERMISSION_OPTION_KIND_SET = frozenset(_TURN_PERMISSION_OPTION_KINDS)
_TURN_PERMISSION_REASONS = frozenset(
    {
        "granted_once",
        "replay",
        "absent_kind",
        "other_kind",
        "inferred_kind_only",
        "absent_path",
        "multiple_paths",
        "conflicting_paths",
        "non_intended_path",
        "absent_allow_once",
        "interaction",
        "elicitation",
        "ambiguous",
        "missing_session",
    }
)
_TURN_PERMISSION_DIAGNOSTIC_ENUMS = (
    ("kind", _TURN_PERMISSION_ACP_KINDS),
    ("kind_source", _TURN_PERMISSION_KIND_SOURCES),
    ("id_class", _TURN_PERMISSION_ID_CLASSES),
    ("path_source", _TURN_PERMISSION_PATH_SOURCES),
    ("path_cardinality", _TURN_PERMISSION_PATH_CARDINALITIES),
    ("path_class", _TURN_PERMISSION_PATH_CLASSES),
    ("reason", _TURN_PERMISSION_REASONS),
)

OWNERSHIP_KEYS = frozenset(
    {
        "schema",
        "authority_id",
        "adapter",
        "transport",
        "target",
        "owner",
        "isolated_root",
        "session",
        "conversation_id",
        "lease",
        "ordinary_launch",
        "qualification",
        "available",
        "cleanup",
        "replacement_blocked",
    }
)


def _blocker(code: str, detail: str, **identity: Any) -> Dict[str, Any]:
    return make_blocker(code=code, detail=detail, **identity)


def _raise_identity(code: str, detail: str, **identity: Any) -> None:
    raise IdentityError(detail, blocker=_blocker(code, detail, **identity))


def _raise_unsupported(code: str, detail: str) -> None:
    raise UnsupportedError(detail, blocker=_blocker(code, detail))


def _raise_conflict(detail: str) -> None:
    raise ConflictError(detail, blocker=_blocker("isolated_root_owned", detail))


def require_antigravity_acp_target(target: Optional[str]) -> str:
    if target != TARGET:
        raise ValidationError("antigravity-acp transport requires target agy")
    return target


def _require_private_root(path: Path) -> Path:
    resolved = absolute_root(str(path), "isolated state root")
    mode = stat.S_IMODE(resolved.stat().st_mode)
    if resolved.stat().st_uid != os.getuid() or mode != 0o700:
        raise ValidationError("isolated state root is not current-UID mode 0700")
    return resolved


def _ownership_path(root: Path) -> Path:
    return root / "ownership.json"


def _lock_path(root: Path) -> Path:
    return root / "ownership.lock"


def _events_path(root: Path) -> Path:
    return root / "ownership.events.jsonl"


def _write_event(root: Path, payload: Mapping[str, Any]) -> None:
    path = _events_path(root)
    encoded = (json.dumps(dict(payload), separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(path), flags, 0o600)
    try:
        os.write(descriptor, encoded)
    finally:
        os.close(descriptor)


def _bounded_path(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise ValidationError("isolated-root path is invalid")
    if any(character in value for character in "\x00\n\r"):
        raise ValidationError("isolated-root path is invalid")
    return value


def validate_ownership(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != OWNERSHIP_KEYS:
        raise ValidationError("isolated-root ownership fields do not match schema")
    if value.get("schema") != OWNERSHIP_SCHEMA:
        raise ValidationError("isolated-root ownership schema is invalid")
    if value.get("authority_id") != AUTHORITY_ID:
        _raise_identity("identity_mismatch", "Puppet authority identity drifted")
    if value.get("adapter") != ADAPTER_ID:
        _raise_identity("identity_mismatch", "antigravity-acpx adapter identity drifted")
    if value.get("transport") != TRANSPORT_ID:
        _raise_identity("identity_mismatch", "antigravity-acp transport identity drifted")
    if value.get("transport") == GENERIC_ACP_ID:
        _raise_identity("identity_mismatch", "generic acp is not an Antigravity transport")
    require_antigravity_acp_target(value.get("target"))
    if value.get("lease") != "not_admitted":
        raise ValidationError("antigravity-acpx must not admit an ordinary lease")
    if value.get("ordinary_launch") != "unavailable" or value.get("available") is not False:
        raise ValidationError("antigravity-acpx ordinary launch must stay unavailable")
    if value.get("qualification") != ACPX_QUALIFICATION:
        raise ValidationError("antigravity-acpx cannot claim live qualification")
    cleanup = value.get("cleanup")
    if cleanup not in {"owned", "unknown", "confirmed_absent"}:
        raise ValidationError("isolated-root cleanup state is invalid")
    if not isinstance(value.get("replacement_blocked"), bool):
        raise ValidationError("replacement block flag is invalid")
    return {
        "schema": OWNERSHIP_SCHEMA,
        "authority_id": AUTHORITY_ID,
        "adapter": ADAPTER_ID,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "owner": validate_identifier(value.get("owner"), "isolated-root owner"),
        "isolated_root": _bounded_path(value.get("isolated_root")),
        "session": validate_identifier(value.get("session"), "antigravity-acp session"),
        "conversation_id": validate_identifier(
            value.get("conversation_id"), "antigravity-acp conversation"
        ),
        "lease": "not_admitted",
        "ordinary_launch": "unavailable",
        "qualification": ACPX_QUALIFICATION,
        "available": False,
        "cleanup": cleanup,
        "replacement_blocked": value["replacement_blocked"],
    }


def claim_isolated_root(
    isolated_root: Path,
    *,
    owner: str,
    session: str,
    conversation_id: str,
) -> Dict[str, Any]:
    """Claim one isolated state root. Duplicate owners are rejected."""

    root = _require_private_root(isolated_root)
    owner = validate_identifier(owner, "isolated-root owner")
    session = validate_identifier(session, "antigravity-acp session")
    conversation_id = validate_identifier(conversation_id, "antigravity-acp conversation")
    claim = {
        "schema": OWNERSHIP_SCHEMA,
        "authority_id": AUTHORITY_ID,
        "adapter": ADAPTER_ID,
        "transport": TRANSPORT_ID,
        "target": TARGET,
        "owner": owner,
        "isolated_root": str(root),
        "session": session,
        "conversation_id": conversation_id,
        "lease": "not_admitted",
        "ordinary_launch": "unavailable",
        "qualification": ACPX_QUALIFICATION,
        "available": False,
        "cleanup": "owned",
        "replacement_blocked": False,
    }
    validate_ownership(claim)
    with exclusive_lock(_lock_path(root)):
        path = _ownership_path(root)
        if path.exists():
            existing = validate_ownership(read_json(path))
            if existing["owner"] != owner:
                _raise_conflict(
                    "isolated state root is already owned by a different adapter"
                )
            if existing["cleanup"] == "unknown" or existing["replacement_blocked"]:
                _raise_identity(
                    "cleanup_unknown",
                    "process-query failure left cleanup unknown; replacement is blocked",
                )
            if (
                existing["session"] != session
                or existing["conversation_id"] != conversation_id
            ):
                _raise_identity(
                    "session_identity_mismatch",
                    "isolated-root session identity does not match the bound session",
                )
            return existing
        atomic_write_json(path, claim)
        _write_event(
            root,
            {
                "event": "ownership_claimed",
                "owner": owner,
                "session": session,
                "conversation_id": conversation_id,
            },
        )
        return claim


def load_isolated_root(isolated_root: Path) -> Dict[str, Any]:
    root = _require_private_root(isolated_root)
    path = _ownership_path(root)
    if not path.is_file():
        _raise_unsupported("proof_missing", "isolated-root ownership proof is missing")
    return validate_ownership(read_json(path))


_BODY_FIELD_NAMES = frozenset(
    {
        "body",
        "content",
        "prompt",
        "text",
        "rawInput",
        "rawOutput",
        "output",
    }
)


def _reject_body_keys(value: Any, label: str) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key) in _BODY_FIELD_NAMES or str(key).lower() in {
                item.lower() for item in _BODY_FIELD_NAMES
            }:
                raise ValidationError("%s contains body-bearing field %s" % (label, key))
            _reject_body_keys(nested, label)
    elif isinstance(value, list):
        for nested in value:
            _reject_body_keys(nested, label)


def _public_worker_identity(process: Mapping[str, Any]) -> Dict[str, Any]:
    identity = {
        "pid": process.get("pid"),
        "startedAt": process.get("startedAt"),
        "launchId": process.get("launchId"),
        "scope": dict(process["scope"]) if isinstance(process.get("scope"), Mapping) else {},
    }
    for key in ("signal", "exitCode", "exitedAt"):
        if key in process:
            identity[key] = process[key]
    return identity


def _cleanup_receipt_fields(extras: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    if extras is None:
        return {}
    _reject_body_keys(extras, "cleanup extras")
    fields: Dict[str, Any] = {}
    for key in ("observed", "message", "selected_model", "current_model"):
        value = extras.get(key)
        if isinstance(value, str) and value:
            fields[key] = value
    discard = extras.get("backendSessionDiscard") or extras.get("backend_session_discard")
    if isinstance(discard, str) and discard:
        fields["backendSessionDiscard"] = discard
    worker = extras.get("worker")
    if isinstance(worker, Mapping):
        fields["worker"] = _public_worker_identity(worker)
    for key in ("worker_termination",):
        if extras.get(key) in {"proven", "unknown"}:
            fields[key] = extras[key]
    for key in ("cleanup_uncertain", "replacement_blocked", "local_release", "final_discard"):
        if isinstance(extras.get(key), bool):
            fields[key] = extras[key]
    if extras.get("persistent_state") in {"absent", "retained", "discarded", "unknown"}:
        fields["persistent_state"] = extras["persistent_state"]
    if isinstance(extras.get("backend_discard"), str) and extras["backend_discard"]:
        fields["backend_discard"] = extras["backend_discard"]
    terminal = extras.get("terminal")
    if isinstance(terminal, Mapping):
        fields["terminal"] = _turn_receipt_fields(terminal)
    lifecycle = extras.get("process_lifecycle")
    if isinstance(lifecycle, Mapping):
        fields["process_lifecycle"] = {
            "started": [
                _public_worker_identity(item)
                for item in lifecycle.get("started", [])
                if isinstance(item, Mapping)
            ],
            "exits": [
                _public_worker_identity(item)
                for item in lifecycle.get("exits", [])
                if isinstance(item, Mapping)
            ],
        }
    return fields


def mark_cleanup_unknown(
    isolated_root: Path,
    extras: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    root = _require_private_root(isolated_root)
    with exclusive_lock(_lock_path(root)):
        current = validate_ownership(read_json(_ownership_path(root)))
        current["cleanup"] = "unknown"
        current["replacement_blocked"] = True
        atomic_write_json(_ownership_path(root), current)
        event = {
            "event": "cleanup_unknown",
            "session": current["session"],
            "conversation_id": current["conversation_id"],
            "replacement_blocked": True,
        }
        event.update(_cleanup_receipt_fields(extras))
        _write_event(root, event)
        return current


def _bound_receipt_option_kinds(value: Any) -> list:
    if not isinstance(value, list):
        return []
    bounded = []
    for item in value:
        if item in _TURN_PERMISSION_OPTION_KIND_SET and item not in bounded:
            bounded.append(item)
        if len(bounded) >= len(_TURN_PERMISSION_OPTION_KIND_SET):
            break
    return bounded


def _bound_receipt_permission_diagnostics(item: Mapping[str, Any]) -> Dict[str, Any]:
    bounded: Dict[str, Any] = {}
    for key, allowed in _TURN_PERMISSION_DIAGNOSTIC_ENUMS:
        candidate = item.get(key)
        if candidate in allowed:
            bounded[key] = candidate
    offered = item.get("offered_option_kinds")
    if isinstance(offered, list):
        bounded["offered_option_kinds"] = _bound_receipt_option_kinds(offered)
    return bounded


def _turn_receipt_fields(value: Mapping[str, Any]) -> Dict[str, Any]:
    _reject_body_keys(value, "turn receipt")
    fields: Dict[str, Any] = {}
    if value.get("status") in {"completed", "failed", "cancelled"}:
        fields["status"] = value["status"]
    stop_reason = value.get("stop_reason")
    if isinstance(stop_reason, str) and stop_reason in _TURN_STOP_REASONS:
        fields["stop_reason"] = stop_reason
    error_code = value.get("error_code")
    if (
        isinstance(error_code, str)
        and 0 < len(error_code) <= 64
        and re.fullmatch(r"[A-Za-z0-9_.-]+", error_code)
        and not any(part in error_code.lower() for part in _TURN_SECRET_CODE_PARTS)
    ):
        fields["error_code"] = error_code
    kinds = value.get("event_kinds")
    if isinstance(kinds, list):
        fields["event_kinds"] = [
            item
            for item in kinds
            if isinstance(item, str)
            and 0 < len(item) <= 64
        ][:16]
    timeout_ms = value.get("timeout_ms")
    if isinstance(timeout_ms, int) and not isinstance(timeout_ms, bool) and 1_000 <= timeout_ms <= 1_800_000:
        fields["timeout_ms"] = timeout_ms
    permission = value.get("permission")
    if isinstance(permission, Mapping):
        _reject_body_keys(permission, "permission receipt")
        outcome = permission.get("outcome")
        grant_count = permission.get("grant_count")
        if (
            outcome in {"allow_once", "denied", "cancelled"}
            and permission.get("persisted") is False
            and permission.get("approve_all") is False
            and permission.get("os_sandbox") is False
            and permission.get("fs") is False
            and permission.get("terminal") is False
            and permission.get("ordinary_launch") == "unavailable"
            and permission.get("body_retained") is False
            and permission.get("invented_decision") is None
            and grant_count in {0, 1}
        ):
            fields["permission"] = {
                "schema": permission.get("schema"),
                "state": outcome,
                "outcome": outcome,
                "permission_id": permission.get("permission_id"),
                "permission_kind": permission.get("permission_kind"),
                "grant_count": grant_count,
                "allowed": permission.get("allowed") is True,
                "persisted": False,
                "approve_all": False,
                "os_sandbox": False,
                "fs": False,
                "terminal": False,
                "ordinary_launch": "unavailable",
                "body_retained": False,
                "invented_decision": None,
            }
            fields["permission"].update(_bound_receipt_permission_diagnostics(permission))
            decisions = permission.get("decisions")
            if isinstance(decisions, list):
                bounded_decisions = []
                for item in decisions:
                    if not isinstance(item, Mapping):
                        continue
                    if item.get("outcome") not in {"allow_once", "denied", "cancelled"}:
                        continue
                    decision = {
                        "outcome": item.get("outcome"),
                        "permission_kind": item.get("permission_kind"),
                    }
                    decision.update(_bound_receipt_permission_diagnostics(item))
                    bounded_decisions.append(decision)
                fields["permission"]["decisions"] = bounded_decisions
    return fields


def persist_turn_receipt(
    isolated_root: Path,
    *,
    session: str,
    conversation_id: str,
    request_id: str,
    extras: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    root = _require_private_root(isolated_root)
    event = {
        "event": "runtime_turn_observed",
        "session": validate_identifier(session, "antigravity-acp session"),
        "conversation_id": validate_identifier(
            conversation_id, "antigravity-acp conversation"
        ),
        "request_id": validate_identifier(request_id, "antigravity-acp request"),
        "body_retained": False,
    }
    if extras is not None:
        event.update(_turn_receipt_fields(extras))
        lifecycle = extras.get("process_lifecycle")
        if isinstance(lifecycle, Mapping):
            event["process_lifecycle"] = {
                "started": [
                    _public_worker_identity(item)
                    for item in lifecycle.get("started", [])
                    if isinstance(item, Mapping)
                ],
                "exits": [
                    _public_worker_identity(item)
                    for item in lifecycle.get("exits", [])
                    if isinstance(item, Mapping)
                ],
            }
    _reject_body_keys(event, "turn receipt")
    _write_event(root, event)
    return event


def persist_turn_models(
    isolated_root: Path,
    *,
    session: str,
    conversation_id: str,
    selected_model: str,
    current_model: str,
) -> Dict[str, Any]:
    root = _require_private_root(isolated_root)
    event = {
        "event": "runtime_models_observed",
        "session": validate_identifier(session, "antigravity-acp session"),
        "conversation_id": validate_identifier(conversation_id, "antigravity-acp conversation"),
        "selected_model": selected_model,
        "current_model": current_model,
        "body_retained": False,
    }
    _reject_body_keys(event, "model receipt")
    _write_event(root, event)
    return event


def persist_cleanup_receipt(
    isolated_root: Path,
    *,
    status: str,
    observed: str,
    extras: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    root = _require_private_root(isolated_root)
    current = validate_ownership(read_json(_ownership_path(root)))
    if status not in {"completed", "uncertain"}:
        raise ValidationError("cleanup receipt status is invalid")
    event = {
        "event": "cleanup_completed" if status == "completed" else "cleanup_uncertain",
        "session": current["session"],
        "conversation_id": current["conversation_id"],
        "observed": observed,
        "replacement_blocked": status != "completed",
    }
    event.update(_cleanup_receipt_fields(extras))
    _write_event(root, event)
    return event


__all__ = [
    "ACPX_ARTIFACT_PATH",
    "ACPX_ARTIFACT_SHA256",
    "ACPX_MERGE_COMMIT",
    "ACPX_QUALIFICATION",
    "ADAPTER_ID",
    "AUTHORITY_ID",
    "GENERIC_ACP_ID",
    "OWNERSHIP_SCHEMA",
    "TARGET",
    "TRANSPORT_ID",
    "claim_isolated_root",
    "load_isolated_root",
    "mark_cleanup_unknown",
    "persist_cleanup_receipt",
    "persist_turn_models",
    "persist_turn_receipt",
    "require_antigravity_acp_target",
    "validate_ownership",
]
