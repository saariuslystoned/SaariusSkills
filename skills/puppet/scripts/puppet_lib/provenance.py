"""Explicit provenance-and-delta admission records."""

from __future__ import annotations

from typing import Any, Dict, List

from .errors import ValidationError
from .safety import canonical_json_bytes, sha256_bytes


DECISIONS = frozenset(
    {
        "reuse_contract",
        "extract_with_attribution",
        "reimplement",
        "design_input_only",
        "fresh_live_proof",
    }
)
REQUIRED = {
    "source_identity",
    "revision",
    "date",
    "owner",
    "invariant",
    "proof_artifact",
    "proof_strength",
    "mechanism_version_match",
    "portability",
    "operator_assumptions",
    "license_path",
    "decision",
    "deterministic_tests",
    "remaining_live_delta",
}


def validate_admission_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(rows, list) or not rows:
        raise ValidationError("evidence admission must contain rows")
    normalized = []
    identities = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != REQUIRED:
            raise ValidationError("evidence admission row fields do not match schema")
        if row["decision"] not in DECISIONS:
            raise ValidationError("invalid evidence admission decision")
        identity = (row["source_identity"], row["revision"], row["invariant"])
        if identity in identities:
            raise ValidationError("duplicate evidence admission identity")
        identities.add(identity)
        if row["decision"] == "extract_with_attribution" and not row["license_path"]:
            raise ValidationError("source extraction requires a license path")
        tests = row["deterministic_tests"]
        if not isinstance(tests, list) or not tests:
            raise ValidationError("admitted evidence requires deterministic tests")
        normalized.append(dict(row))
    return normalized


def admission_fingerprint(rows: List[Dict[str, Any]]) -> str:
    return sha256_bytes(canonical_json_bytes(validate_admission_rows(rows)))
