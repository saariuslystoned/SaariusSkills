"""Controller-owned pre-delivery authority for Claude marker plan joins.

This module attests only the body-free identity join produced by
``matched_control``.  It does not authorize delivery, launch, checkpoint
scanning, no-bleed evaluation, qualification, or promotion.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .adapter_manifest import AdapterManifest
from .authority import AUTHORITY_ID, controller_authority_root
from .errors import IdentityError, ValidationError
from .journal import Journal
from .matched_control import (
    CompiledMarkerInstruction,
    bind_claude_marker_activation_plan,
)
from .plane_activation import ActivationPlan
from .safety import (
    canonical_json_bytes,
    sha256_bytes,
    validate_identifier,
    validate_sha256,
)


ACTIVATION_MARKER_ATTESTATION_SCHEMA_VERSION = 1
ACTIVATION_MARKER_ATTESTATION_EVENT_SCHEMA = (
    "puppet.claude-activation-marker-join-attestation-event/v1"
)
ACTIVATION_MARKER_ATTESTATION_KIND = "claude_activation_marker_plan_join"
_JOURNAL_NAME = "claude-marker-activation-joins"
_ATTESTATION_FIELDS = {
    "schema_version",
    "authority_id",
    "authority_root",
    "request_id",
    "ledger_sequence",
    "ledger_entry_hash",
    "activation_join_sha256",
}


def _activation_join_event(
    compiled: CompiledMarkerInstruction,
    *,
    activation_plan: ActivationPlan,
    descriptor: Mapping[str, Any],
    adapter_manifest: AdapterManifest | Mapping[str, Any],
) -> Dict[str, Any]:
    joined = bind_claude_marker_activation_plan(
        compiled,
        activation_plan=activation_plan,
        descriptor=descriptor,
        adapter_manifest=adapter_manifest,
    )
    if any(
        joined[name] is not False
        for name in (
            "delivery_authorized",
            "runtime_scan_authorized",
            "checkpoint_observed",
            "no_bleed_evaluated",
            "no_bleed_verified",
            "qualification_authorized",
            "promotion_authorized",
        )
    ):
        raise IdentityError("activation marker join gained runtime authority")
    return {
        "schema": ACTIVATION_MARKER_ATTESTATION_EVENT_SCHEMA,
        "kind": ACTIVATION_MARKER_ATTESTATION_KIND,
        "authority_id": AUTHORITY_ID,
        "target": "claude",
        "session_profile": "regular",
        "session": validate_identifier(joined["session"], "marker join session"),
        "run_id": validate_identifier(joined["run_id"], "marker join run id"),
        "activation_join_sha256": sha256_bytes(canonical_json_bytes(joined)),
        "activation_plan_sha256": validate_sha256(
            joined["activation_plan_sha256"], "marker activation plan"
        ),
        "descriptor_sha256": validate_sha256(
            joined["descriptor_sha256"], "marker descriptor"
        ),
        "adapter_manifest_sha256": validate_sha256(
            joined["adapter_manifest_sha256"], "marker adapter manifest"
        ),
        "adapter_implementation_sha256": validate_sha256(
            joined["adapter_implementation_sha256"],
            "marker adapter implementation",
        ),
        "delivery_authorized": False,
        "runtime_scan_authorized": False,
        "checkpoint_observed": False,
        "no_bleed_evaluated": False,
        "no_bleed_verified": False,
        "qualification_authorized": False,
        "promotion_authorized": False,
    }


def attest_claude_marker_activation_join(
    compiled: CompiledMarkerInstruction,
    *,
    activation_plan: ActivationPlan,
    descriptor: Mapping[str, Any],
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Append one idempotent, body-free pre-delivery plan-join attestation."""

    root = controller_authority_root(authority_root)
    event = _activation_join_event(
        compiled,
        activation_plan=activation_plan,
        descriptor=descriptor,
        adapter_manifest=adapter_manifest,
    )
    request_id = "claude-marker-join-%s" % event["activation_join_sha256"][:40]
    row = Journal(root / _JOURNAL_NAME).append(request_id=request_id, event=event)
    return {
        "schema_version": ACTIVATION_MARKER_ATTESTATION_SCHEMA_VERSION,
        "authority_id": AUTHORITY_ID,
        "authority_root": str(root),
        "request_id": request_id,
        "ledger_sequence": row["sequence"],
        "ledger_entry_hash": row["entry_hash"],
        "activation_join_sha256": event["activation_join_sha256"],
    }


def verify_claude_marker_activation_join_attestation(
    attestation: Mapping[str, Any],
    compiled: CompiledMarkerInstruction,
    *,
    activation_plan: ActivationPlan,
    descriptor: Mapping[str, Any],
    adapter_manifest: AdapterManifest | Mapping[str, Any],
    authority_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Rebuild the join and require its exact controller-journal inclusion."""

    root = controller_authority_root(authority_root)
    if not isinstance(attestation, Mapping) or set(attestation) != _ATTESTATION_FIELDS:
        raise ValidationError("activation marker attestation fields are invalid")
    if (
        attestation.get("schema_version")
        != ACTIVATION_MARKER_ATTESTATION_SCHEMA_VERSION
    ):
        raise ValidationError("activation marker attestation schema is invalid")
    if attestation.get("authority_id") != AUTHORITY_ID or attestation.get(
        "authority_root"
    ) != str(root):
        raise IdentityError("activation marker controller authority changed")
    request_id = validate_identifier(
        attestation.get("request_id"), "activation marker attestation request"
    )
    ledger_hash = validate_sha256(
        attestation.get("ledger_entry_hash"), "activation marker ledger entry"
    )
    join_sha = validate_sha256(
        attestation.get("activation_join_sha256"), "activation marker join"
    )
    sequence = attestation.get("ledger_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise ValidationError("activation marker attestation sequence is invalid")

    event = _activation_join_event(
        compiled,
        activation_plan=activation_plan,
        descriptor=descriptor,
        adapter_manifest=adapter_manifest,
    )
    expected_request_id = "claude-marker-join-%s" % event["activation_join_sha256"][:40]
    if join_sha != event["activation_join_sha256"] or request_id != expected_request_id:
        raise IdentityError("activation marker attestation identity changed")
    row = Journal(root / _JOURNAL_NAME).lookup(request_id)
    if (
        row is None
        or row.get("sequence") != sequence
        or row.get("entry_hash") != ledger_hash
        or row.get("event") != event
    ):
        raise IdentityError("activation marker controller attestation is unavailable")
    return row


__all__ = [
    "ACTIVATION_MARKER_ATTESTATION_EVENT_SCHEMA",
    "ACTIVATION_MARKER_ATTESTATION_KIND",
    "ACTIVATION_MARKER_ATTESTATION_SCHEMA_VERSION",
    "attest_claude_marker_activation_join",
    "verify_claude_marker_activation_join_attestation",
]
