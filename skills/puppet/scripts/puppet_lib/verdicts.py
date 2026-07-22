"""Controller-only checkpoint review and acceptance records."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Dict

from .contracts import Contract, assert_controller
from .errors import ValidationError
from .handoffs import ValidatedHandoff
from .safety import atomic_write_json, read_json, sha256_file, validate_sha256


VERDICTS = frozenset(
    {"repair", "conformance_accept", "source_accept", "block", "fail"}
)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        if handoff.checkpoint_kind != "conformance" or handoff.identity.get("phase") != "followup":
            raise ValidationError("conformance acceptance requires a followup checkpoint")
    if verdict == "source_accept" and handoff.checkpoint_kind != "source":
        raise ValidationError("source acceptance requires a source checkpoint")
    evidence = read_json(
        Path(evidence_path), max_bytes=65536, reject_sensitive_fields=True
    )
    evidence_sha256 = sha256_file(Path(evidence_path), max_bytes=65536)
    destination = Path(verdict_root) / (handoff.checkpoint_id + ".json")
    if destination.exists():
        existing = read_json(destination, max_bytes=131072)
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
        "schema_version": 1,
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


def verify_current_identity(
    review: Dict[str, Any],
    *,
    checkpoint_id: str,
    artifact_sha256: str,
    candidate_commit: str = None,
) -> None:
    validate_sha256(checkpoint_id, "checkpoint id")
    validate_sha256(artifact_sha256, "artifact fingerprint")
    if review.get("checkpoint_id") != checkpoint_id:
        raise ValidationError("review checkpoint identity is stale")
    if review.get("artifact_sha256") != artifact_sha256:
        raise ValidationError("review artifact identity is stale")
    identity = review.get("checkpoint_identity", {})
    if candidate_commit is not None and identity.get("candidate_commit") != candidate_commit:
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
    if review.get("verdict") not in {"conformance_accept", "source_accept"}:
        raise ValidationError("acceptance requires a controller accept verdict")
    evidence = read_json(
        Path(evidence_path), max_bytes=65536, reject_sensitive_fields=True
    )
    satisfied = evidence.get("terminal_criteria")
    expected = {item["id"] for item in contract.terminal_criteria}
    if not isinstance(satisfied, list) or set(satisfied) != expected:
        raise ValidationError("acceptance evidence does not satisfy exact terminal criteria")
    record = {
        "schema_version": 1,
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
        existing = read_json(destination, max_bytes=131072)
        comparable = dict(record)
        comparable.pop("timestamp", None)
        existing_comparable = dict(existing)
        existing_comparable.pop("timestamp", None)
        if existing_comparable == comparable:
            return existing
        raise ValidationError("checkpoint already has different acceptance evidence")
    atomic_write_json(destination, record)
    return record
