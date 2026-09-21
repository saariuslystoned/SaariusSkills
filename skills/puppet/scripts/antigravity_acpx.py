"""Isolated-root ownership for the explicit antigravity-acp candidate.

Ordinary launch stays unavailable. Reuses puppet_lib.safety helpers and the
existing PuppetError(detail, *, blocker=...) signatures.
"""

from __future__ import annotations

import json
import os
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
    "642d4c299bd58b275ca1a360196f3077fc4f84997e2654542f492b1e0001c162"
)
ACPX_ARTIFACT_PATH = (
    "runs/puppet-dual-acp-controller-runs/20260921/artifacts/acpx-0.18.0.tgz"
)
ACPX_MERGE_COMMIT = "f8883645c261e07b2df7f9c3b4ad243b62d8168a"

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


def mark_cleanup_unknown(isolated_root: Path) -> Dict[str, Any]:
    root = _require_private_root(isolated_root)
    with exclusive_lock(_lock_path(root)):
        current = validate_ownership(read_json(_ownership_path(root)))
        current["cleanup"] = "unknown"
        current["replacement_blocked"] = True
        atomic_write_json(_ownership_path(root), current)
        _write_event(
            root,
            {
                "event": "cleanup_unknown",
                "session": current["session"],
                "conversation_id": current["conversation_id"],
                "replacement_blocked": True,
            },
        )
        return current


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
    "require_antigravity_acp_target",
    "validate_ownership",
]
