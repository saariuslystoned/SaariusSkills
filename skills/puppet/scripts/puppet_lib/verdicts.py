"""Controller-only checkpoint review and acceptance records."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict

from .contracts import Contract, assert_controller
from .errors import UnsupportedError, ValidationError
from .handoffs import ValidatedHandoff
from .safety import (
    atomic_write_json,
    canonical_json_bytes,
    read_json,
    sha256_bytes,
    sha256_file,
    validate_sha256,
)


VERDICTS = frozenset({"repair", "conformance_accept", "source_accept", "block", "fail"})
REVIEW_SCHEMA_VERSION = 2
ACCEPTANCE_SCHEMA_VERSION = 2
LEGACY_VERDICT_SCHEMA_VERSIONS = frozenset({1})
REVIEW_FIELDS = {
    "schema_version",
    "timestamp",
    "actor",
    "target",
    "contract_fingerprint",
    "checkpoint_id",
    "checkpoint_kind",
    "checkpoint_identity",
    "artifact_sha256",
    "verdict",
    "evidence_sha256",
    "evidence_summary",
}
ACCEPTANCE_FIELDS = {
    "schema_version",
    "timestamp",
    "actor",
    "checkpoint_id",
    "review_verdict",
    "review_evidence_sha256",
    "contract_fingerprint",
    "terminal_criteria",
    "acceptance_evidence_sha256",
}


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def record_review(
    *,
    contract: Contract,
    actor: str,
    handoff: ValidatedHandoff,
    verdict: str,
    evidence_path: Path,
    verdict_root: Path,
) -> Dict[str, Any]:
    assert_controller(contract, actor)
    if actor == contract.target:
        raise ValidationError("a target cannot review itself")
    if verdict not in VERDICTS:
        raise ValidationError("invalid controller verdict")
    if handoff.checkpoint_kind == "conformance" and verdict not in {
        "conformance_accept",
        "block",
        "fail",
    }:
        raise ValidationError("invalid conformance checkpoint verdict")
    if handoff.checkpoint_kind == "source" and verdict not in {
        "repair",
        "source_accept",
        "block",
        "fail",
    }:
        raise ValidationError("invalid source checkpoint verdict")
    if verdict == "conformance_accept":
        if (
            handoff.checkpoint_kind != "conformance"
            or handoff.identity.get("phase") != "followup"
        ):
            raise ValidationError(
                "conformance acceptance requires a followup checkpoint"
            )
    if verdict == "source_accept" and handoff.checkpoint_kind != "source":
        raise ValidationError("source acceptance requires a source checkpoint")
    evidence = read_json(
        Path(evidence_path), max_bytes=65536, reject_sensitive_fields=True
    )
    evidence_sha256 = sha256_file(Path(evidence_path), max_bytes=65536)
    destination = Path(verdict_root) / (handoff.checkpoint_id + ".json")
    if destination.exists():
        existing = validate_review_record(read_json(destination, max_bytes=131072))
        expected_existing = {
            "actor": actor,
            "target": contract.target,
            "contract_fingerprint": contract.fingerprint,
            "checkpoint_id": handoff.checkpoint_id,
            "artifact_sha256": handoff.artifact_sha256,
            "verdict": verdict,
            "evidence_sha256": evidence_sha256,
        }
        if all(existing.get(key) == value for key, value in expected_existing.items()):
            return existing
        raise ValidationError("checkpoint already has a different verdict")
    record = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "timestamp": _utc_now(),
        "actor": actor,
        "target": contract.target,
        "contract_fingerprint": contract.fingerprint,
        "checkpoint_id": handoff.checkpoint_id,
        "checkpoint_kind": handoff.checkpoint_kind,
        "checkpoint_identity": handoff.identity,
        "artifact_sha256": handoff.artifact_sha256,
        "verdict": verdict,
        "evidence_sha256": evidence_sha256,
        "evidence_summary": evidence,
    }
    atomic_write_json(destination, record)
    return record


def validate_review_record(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("review record root must be an object")
    schema_version = value.get("schema_version")
    if schema_version in LEGACY_VERDICT_SCHEMA_VERSIONS:
        raise UnsupportedError(
            "legacy review record lacks authoritative runtime execution identity"
        )
    if schema_version != REVIEW_SCHEMA_VERSION:
        raise ValidationError("unsupported review record schema")
    if set(value) != REVIEW_FIELDS:
        raise ValidationError("review record fields do not match schema")
    identity = value.get("checkpoint_identity")
    if not isinstance(identity, dict):
        raise ValidationError("review checkpoint identity is invalid")
    if identity.get("checkpoint_kind") != value.get("checkpoint_kind"):
        raise ValidationError("review checkpoint kind identity is mixed")
    validate_sha256(
        identity.get("execution_fingerprint"),
        "review checkpoint execution fingerprint",
    )
    for name in (
        "checkpoint_id",
        "artifact_sha256",
        "evidence_sha256",
        "contract_fingerprint",
    ):
        validate_sha256(value.get(name), "review %s" % name.replace("_", " "))
    expected_checkpoint_id = sha256_bytes(
        canonical_json_bytes(
            {
                "identity": identity,
                "artifact_sha256": value["artifact_sha256"],
            }
        )
    )
    if value["checkpoint_id"] != expected_checkpoint_id:
        raise ValidationError("review checkpoint id does not bind its exact identity")
    return dict(value)


def validate_acceptance_record(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("acceptance record root must be an object")
    schema_version = value.get("schema_version")
    if schema_version in LEGACY_VERDICT_SCHEMA_VERSIONS:
        raise UnsupportedError(
            "legacy acceptance record cannot bind a runtime-identity review"
        )
    if schema_version != ACCEPTANCE_SCHEMA_VERSION:
        raise ValidationError("unsupported acceptance record schema")
    if set(value) != ACCEPTANCE_FIELDS:
        raise ValidationError("acceptance record fields do not match schema")
    for name in (
        "checkpoint_id",
        "review_evidence_sha256",
        "contract_fingerprint",
        "acceptance_evidence_sha256",
    ):
        validate_sha256(value.get(name), "acceptance %s" % name.replace("_", " "))
    return dict(value)


def verify_current_identity(
    review: Dict[str, Any],
    *,
    checkpoint_id: str,
    artifact_sha256: str,
    candidate_commit: str = None,
) -> None:
    if not isinstance(review, dict):
        raise ValidationError("review identity root must be an object")
    if "schema_version" in review:
        review = validate_review_record(review)
    validate_sha256(checkpoint_id, "checkpoint id")
    validate_sha256(artifact_sha256, "artifact fingerprint")
    if review.get("checkpoint_id") != checkpoint_id:
        raise ValidationError("review checkpoint identity is stale")
    if review.get("artifact_sha256") != artifact_sha256:
        raise ValidationError("review artifact identity is stale")
    identity = review.get("checkpoint_identity", {})
    if (
        candidate_commit is not None
        and identity.get("candidate_commit") != candidate_commit
    ):
        raise ValidationError("review candidate head is stale")


def record_acceptance(
    *,
    contract: Contract,
    actor: str,
    review: Dict[str, Any],
    evidence_path: Path,
    acceptance_root: Path,
) -> Dict[str, Any]:
    assert_controller(contract, actor)
    if actor == contract.target:
        raise ValidationError("a target cannot accept itself")
    review = validate_review_record(review)
    if (
        review.get("actor") != actor
        or review.get("target") != contract.target
        or review.get("contract_fingerprint") != contract.fingerprint
    ):
        raise ValidationError("acceptance review authority identity is invalid")
    if (
        review.get("checkpoint_kind") == "conformance"
        and review.get("verdict") != "conformance_accept"
    ) or (
        review.get("checkpoint_kind") == "source"
        and review.get("verdict") != "source_accept"
    ):
        raise ValidationError("acceptance review kind and verdict are incoherent")
    if review.get("checkpoint_kind") not in {"conformance", "source"}:
        raise ValidationError("acceptance review checkpoint kind is invalid")
    if review.get("verdict") not in {"conformance_accept", "source_accept"}:
        raise ValidationError("acceptance requires a controller accept verdict")
    evidence = read_json(
        Path(evidence_path), max_bytes=65536, reject_sensitive_fields=True
    )
    satisfied = evidence.get("terminal_criteria")
    expected = {item["id"] for item in contract.terminal_criteria}
    if not isinstance(satisfied, list) or set(satisfied) != expected:
        raise ValidationError(
            "acceptance evidence does not satisfy exact terminal criteria"
        )
    record = {
        "schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "timestamp": _utc_now(),
        "actor": actor,
        "checkpoint_id": review["checkpoint_id"],
        "review_verdict": review["verdict"],
        "review_evidence_sha256": review["evidence_sha256"],
        "contract_fingerprint": contract.fingerprint,
        "terminal_criteria": sorted(expected),
        "acceptance_evidence_sha256": sha256_file(Path(evidence_path), max_bytes=65536),
    }
    destination = Path(acceptance_root) / (review["checkpoint_id"] + ".json")
    if destination.exists():
        existing = validate_acceptance_record(read_json(destination, max_bytes=131072))
        comparable = dict(record)
        comparable.pop("timestamp", None)
        existing_comparable = dict(existing)
        existing_comparable.pop("timestamp", None)
        if existing_comparable == comparable:
            return existing
        raise ValidationError("checkpoint already has different acceptance evidence")
    atomic_write_json(destination, record)
    return record
