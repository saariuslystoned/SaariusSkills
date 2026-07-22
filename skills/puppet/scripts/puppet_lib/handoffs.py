"""Bounded source and source-free conformance checkpoint validation."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, Optional

from .errors import ValidationError
from .safety import (
    canonical_json_bytes,
    ensure_within,
    sha256_bytes,
    validate_bounded_json,
    validate_identifier,
    validate_sha1,
    validate_sha256,
)


MAX_HANDOFF_BYTES = 65536
COMMON_FIELDS = {
    "schema_version",
    "checkpoint_kind",
    "session",
    "run_id",
    "nonce",
    "executable_fingerprint",
    "execution_fingerprint",
    "adapter_fingerprint",
    "protocol_fingerprint",
    "timestamp",
    "claims",
    "evidence_refs",
    "decisions_requested",
    "limitations",
}
SOURCE_FIELDS = COMMON_FIELDS | {
    "candidate_commit",
    "summary",
    "suggested_next_assignment",
}
CONFORMANCE_FIELDS = COMMON_FIELDS | {
    "phase",
    "sequence",
    "message_id",
    "prior_checkpoint_sha256",
}
CONFORMANCE_PROTOCOL_DESCRIPTOR = {
    "schema_version": 1,
    "name": "PUPPET_CONFORMANCE_V1",
    "checkpoint_kind": "conformance",
    "fields": sorted(CONFORMANCE_FIELDS),
    "phases": {
        "ready": {
            "sequence": 0,
            "forbidden": ["message_id", "prior_checkpoint_sha256"],
        },
        "followup": {
            "sequence": 1,
            "required": ["message_id", "prior_checkpoint_sha256"],
        },
    },
    "max_handoff_bytes": MAX_HANDOFF_BYTES,
    "max_list_items": 32,
    "transcript_fields_forbidden": True,
}
PROTOCOL_FINGERPRINT = sha256_bytes(
    canonical_json_bytes(CONFORMANCE_PROTOCOL_DESCRIPTOR)
)


@dataclass(frozen=True)
class ValidatedHandoff:
    checkpoint_id: str
    artifact_sha256: str
    checkpoint_kind: str
    identity: Dict[str, Any]
    data: Dict[str, Any]
    path: Path

    def reference(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "artifact_sha256": self.artifact_sha256,
            "checkpoint_kind": self.checkpoint_kind,
            "identity": self.identity,
            "path": str(self.path),
            "validation": "valid",
        }


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 40:
        raise ValidationError("invalid handoff timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("invalid handoff timestamp") from exc
    if parsed.tzinfo is None:
        raise ValidationError("handoff timestamp requires a timezone")
    return value


def _bounded_list(value: Any, label: str, *, dict_items: bool = False) -> list:
    if not isinstance(value, list) or len(value) > 32:
        raise ValidationError("%s must be a bounded list" % label)
    for item in value:
        if dict_items:
            if not isinstance(item, dict):
                raise ValidationError("%s entries must be objects" % label)
        elif not isinstance(item, str) or len(item) > 1000:
            raise ValidationError("%s entries must be bounded strings" % label)
    return value


def _evidence_reference(value: str) -> str:
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValidationError("evidence reference escapes its declared root")
    if value.startswith(".") or "\\" in value:
        raise ValidationError("invalid evidence reference")
    return value


def _read_handoff(path: Path, allowed_roots: Iterable[Path]) -> tuple:
    path = Path(path)
    matched = None
    for root in allowed_roots:
        try:
            matched = ensure_within(path, Path(root), must_exist=True)
            break
        except ValidationError:
            continue
    if matched is None or matched.is_symlink() or not matched.is_file():
        raise ValidationError("handoff is outside the allowed roots")
    raw = matched.read_bytes()
    if len(raw) > MAX_HANDOFF_BYTES:
        raise ValidationError("handoff exceeds the size limit")
    try:
        import json

        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValidationError("invalid handoff JSON") from exc
    if not isinstance(data, dict):
        raise ValidationError("handoff root must be an object")
    validate_bounded_json(data, reject_sensitive_fields=True)
    return matched, raw, data


def validate_handoff(
    path: Path,
    *,
    allowed_roots: Iterable[Path],
    expected: Optional[Dict[str, Any]] = None,
) -> ValidatedHandoff:
    matched, raw, data = _read_handoff(path, allowed_roots)
    if data.get("schema_version") != 1:
        raise ValidationError("unsupported handoff schema")
    kind = data.get("checkpoint_kind")
    if kind not in {"source", "conformance"}:
        raise ValidationError("invalid checkpoint kind")
    allowed = SOURCE_FIELDS if kind == "source" else CONFORMANCE_FIELDS
    unknown = set(data) - allowed
    missing = COMMON_FIELDS - set(data)
    if unknown or missing:
        raise ValidationError("handoff fields do not match the selected schema")
    session = validate_identifier(data.get("session"), "session")
    run_id = validate_identifier(data.get("run_id"), "run id")
    nonce = validate_identifier(data.get("nonce"), "nonce")
    executable = validate_sha256(
        data.get("executable_fingerprint"), "executable fingerprint"
    )
    execution = validate_sha256(
        data.get("execution_fingerprint"), "execution fingerprint"
    )
    adapter = validate_sha256(data.get("adapter_fingerprint"), "adapter fingerprint")
    protocol = validate_sha256(data.get("protocol_fingerprint"), "protocol fingerprint")
    _timestamp(data.get("timestamp"))
    _bounded_list(data.get("claims"), "claims", dict_items=True)
    evidence_refs = _bounded_list(data.get("evidence_refs"), "evidence_refs")
    for ref in evidence_refs:
        _evidence_reference(ref)
    _bounded_list(data.get("decisions_requested"), "decisions_requested")
    _bounded_list(data.get("limitations"), "limitations")
    identity: Dict[str, Any] = {
        "checkpoint_kind": kind,
        "session": session,
        "run_id": run_id,
        "nonce": nonce,
        "executable_fingerprint": executable,
        "execution_fingerprint": execution,
        "adapter_fingerprint": adapter,
        "protocol_fingerprint": protocol,
    }
    if kind == "source":
        if "candidate_commit" not in data:
            raise ValidationError("source handoff requires candidate_commit")
        identity["candidate_commit"] = validate_sha1(data["candidate_commit"])
        summary = data.get("summary")
        next_assignment = data.get("suggested_next_assignment")
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 2000:
            raise ValidationError("source handoff requires a bounded summary")
        if not isinstance(next_assignment, str) or len(next_assignment) > 1000:
            raise ValidationError("invalid suggested next assignment")
    else:
        if "candidate_commit" in data:
            raise ValidationError("conformance handoff forbids candidate_commit")
        phase = data.get("phase")
        sequence = data.get("sequence")
        if phase == "ready":
            if (
                sequence != 0
                or "message_id" in data
                or "prior_checkpoint_sha256" in data
            ):
                raise ValidationError("invalid ready checkpoint identity")
        elif phase == "followup":
            if sequence != 1:
                raise ValidationError("followup sequence must be one")
            identity["message_id"] = validate_identifier(
                data.get("message_id"), "message id"
            )
            identity["prior_checkpoint_sha256"] = validate_sha256(
                data.get("prior_checkpoint_sha256"), "prior checkpoint fingerprint"
            )
        else:
            raise ValidationError("invalid conformance phase")
        identity["phase"] = phase
        identity["sequence"] = sequence
    if expected:
        for key, value in expected.items():
            if identity.get(key) != value:
                raise ValidationError("handoff identity mismatch: %s" % key)
    artifact_sha = sha256_bytes(raw)
    checkpoint_id = sha256_bytes(
        canonical_json_bytes({"identity": identity, "artifact_sha256": artifact_sha})
    )
    return ValidatedHandoff(
        checkpoint_id=checkpoint_id,
        artifact_sha256=artifact_sha,
        checkpoint_kind=kind,
        identity=identity,
        data=data,
        path=matched,
    )
