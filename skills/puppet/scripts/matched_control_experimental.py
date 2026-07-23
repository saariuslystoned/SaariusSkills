"""Non-promotable Claude matched-control protocol candidate.

This module validates only a body-free *candidate index*.  It does not inspect
the referenced artifacts, derive a no-bleed result, attest controller
authority, or qualify an adapter.  Production qualification deliberately does
not import this module.  A future controller-owned producer and verifier must
replace every non-authoritative reference with journal-joined evidence before
any promotion path may consume it.
"""

from __future__ import annotations

from typing import Any, Dict

from puppet_lib.errors import IdentityError, ValidationError
from puppet_lib.safety import (
    validate_bounded_json,
    validate_identifier,
    validate_sha256,
)


EXPERIMENTAL_MATCHED_CONTROL_SCHEMA = (
    "puppet.experimental-claude-matched-control-index/v1"
)
EXPERIMENTAL_MATCHED_CONTROL_SCOPE = "experimental_protocol_candidate_only"
NON_AUTHORITATIVE = "non_authoritative_until_controller_journal_verification"
PROMOTION_FORBIDDEN = "forbidden_missing_controller_producer_and_verifier"
PROCESS_REFERENCE_SCHEMA = "puppet.experimental-process-identity-ref/v1"

REQUIRED_CONTROLLER_EVIDENCE = (
    {
        "kind": "compiled_marker_binding",
        "producer_hook": "compile_instruction_wrapper_marker_binding",
        "session_role": "activated",
    },
    {
        "kind": "activated_checkpoint_scan",
        "producer_hook": "controller_checkpoint_read_and_marker_scan",
        "session_role": "activated",
    },
    {
        "kind": "control_checkpoint_scan",
        "producer_hook": "controller_checkpoint_read_and_marker_scan",
        "session_role": "control",
    },
    {
        "kind": "activated_pre_census",
        "producer_hook": "controller_exact_target_census",
        "session_role": "activated",
    },
    {
        "kind": "activated_post_halt_census",
        "producer_hook": "controller_exact_target_census",
        "session_role": "activated",
    },
    {
        "kind": "control_pre_census",
        "producer_hook": "controller_exact_target_census",
        "session_role": "control",
    },
    {
        "kind": "control_post_halt_census",
        "producer_hook": "controller_exact_target_census",
        "session_role": "control",
    },
    {
        "kind": "activated_tmux_terminal",
        "producer_hook": "controller_tmux_server_target_terminal_probe",
        "session_role": "activated",
    },
    {
        "kind": "control_tmux_terminal",
        "producer_hook": "controller_tmux_server_target_terminal_probe",
        "session_role": "control",
    },
    {
        "kind": "activated_halt_journal",
        "producer_hook": "controller_halt_control_journal_terminal_row",
        "session_role": "activated",
    },
    {
        "kind": "control_halt_journal",
        "producer_hook": "controller_halt_control_journal_terminal_row",
        "session_role": "control",
    },
    {
        "kind": "activation_rollback_transaction",
        "producer_hook": "controller_activation_transaction_terminal_row",
        "session_role": "activated",
    },
    {
        "kind": "entry_mode_pair",
        "producer_hook": "controller_launch_entry_receipt",
        "session_role": "pair",
    },
    {
        "kind": "current_manifest_revalidation",
        "producer_hook": "controller_current_manifest_revalidation",
        "session_role": "pair",
    },
)

_ROOT_FIELDS = {"path_sha256", "device", "inode", "uid", "mode"}
_PROCESS_REFERENCE_FIELDS = {
    "schema",
    "pid",
    "device",
    "inode",
    "process_identity_sha256",
}
_SESSION_FIELDS = {
    "authority",
    "role",
    "session",
    "run_id",
    "target",
    "controller",
    "process",
    "lease_sha256",
    "workspace",
    "config",
    "entry_mode",
    "native_plane",
}
_REFERENCE_FIELDS = {
    "authority",
    "kind",
    "producer_hook",
    "session_role",
    "path",
    "sha256",
}
_CANDIDATE_FIELDS = {
    "schema",
    "qualification_scope",
    "promotion_status",
    "result",
    "target",
    "controller",
    "campaign_id",
    "goal_fingerprint",
    "manifest_fingerprint",
    "descriptor_sha256",
    "compiled_marker_sha256",
    "runtime_defaults",
    "activated",
    "control",
    "evidence_refs",
}
_RUNTIME_DEFAULTS = {
    "authority": NON_AUTHORITATIVE,
    "model_selection": "current_default_unqualified",
    "model_identity": "live_controller_observation_required",
    "provider_selection": "current_default_unqualified",
    "provider_identity": "live_controller_observation_required",
    "effort_selection": "current_default_unqualified",
    "effort_identity": "unavailable",
    "config_selection": "exact_controller_owned_lane_required",
}


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError("%s is invalid" % label)
    return value


def _process(value: Any, role: str) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _PROCESS_REFERENCE_FIELDS:
        raise ValidationError("%s process reference fields are invalid" % role)
    if (
        value.get("schema") != PROCESS_REFERENCE_SCHEMA
        or isinstance(value.get("pid"), bool)
        or not isinstance(value.get("pid"), int)
        or value["pid"] <= 1
        or any(
            not isinstance(value.get(name), int)
            or isinstance(value.get(name), bool)
            or value[name] <= 0
            for name in ("device", "inode")
        )
    ):
        raise ValidationError("%s process reference is invalid" % role)
    validate_sha256(value.get("process_identity_sha256"), "%s process identity" % role)
    return dict(value)


def _root(value: Any, role: str, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _ROOT_FIELDS:
        raise ValidationError("%s %s identity fields are invalid" % (role, label))
    validate_sha256(value.get("path_sha256"), "%s %s path" % (role, label))
    for name in ("device", "inode", "uid", "mode"):
        _positive_int(value.get(name), "%s %s %s" % (role, label, name))
    return dict(value)


def _session(value: Any, role: str) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _SESSION_FIELDS:
        raise ValidationError("%s candidate session fields are invalid" % role)
    if (
        value.get("authority") != NON_AUTHORITATIVE
        or value.get("role") != role
        or value.get("target") != "claude"
        or value.get("entry_mode") not in {"direct", "cockpit"}
        or value.get("native_plane")
        != ("per_run_additive_candidate" if role == "activated" else "none")
    ):
        raise ValidationError("%s candidate session is invalid" % role)
    for name in ("session", "run_id", "controller"):
        validate_identifier(value.get(name), "%s %s" % (role, name))
    process = _process(value.get("process"), role)
    validate_sha256(value.get("lease_sha256"), "%s lease" % role)
    workspace = _root(value.get("workspace"), role, "workspace")
    config = _root(value.get("config"), role, "config")
    return {
        **dict(value),
        "process": process,
        "workspace": workspace,
        "config": config,
    }


def _evidence_path(index: int, kind: str) -> str:
    return "candidate/%02d-%s.json" % (index, kind)


def _evidence_refs(value: Any) -> list[Dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(REQUIRED_CONTROLLER_EVIDENCE):
        raise ValidationError("experimental evidence reference set is incomplete")
    normalized = []
    for index, (expected, reference) in enumerate(
        zip(REQUIRED_CONTROLLER_EVIDENCE, value), start=1
    ):
        if not isinstance(reference, dict) or set(reference) != _REFERENCE_FIELDS:
            raise ValidationError("experimental evidence reference fields are invalid")
        expected_path = _evidence_path(index, expected["kind"])
        if (
            reference.get("authority") != NON_AUTHORITATIVE
            or reference.get("path") != expected_path
            or any(
                reference.get(name) != expected[name]
                for name in ("kind", "producer_hook", "session_role")
            )
        ):
            raise ValidationError("experimental evidence reference order is invalid")
        normalized.append(
            {
                **dict(reference),
                "path": expected_path,
                "sha256": validate_sha256(
                    reference.get("sha256"), "%s evidence" % expected["kind"]
                ),
            }
        )
    paths = [item["path"] for item in normalized]
    digests = [item["sha256"] for item in normalized]
    if len(paths) != len(set(paths)) or len(digests) != len(set(digests)):
        raise ValidationError("experimental evidence references are not unique")
    return normalized


def validate_experimental_matched_control_candidate(value: Any) -> Dict[str, Any]:
    """Validate a non-authoritative index without producing a verdict.

    Hashes and identities in this object remain claims until a future producer
    writes them through controller-owned journals and a future verifier rejoins
    those journals to exact live/terminal authority.  Returning this object is
    never evidence that the referenced observations occurred.
    """

    if not isinstance(value, dict) or set(value) != _CANDIDATE_FIELDS:
        raise ValidationError("experimental matched-control fields are invalid")
    validate_bounded_json(
        value,
        max_depth=8,
        max_items=64,
        max_string=4096,
        reject_sensitive_fields=True,
    )
    if (
        value.get("schema") != EXPERIMENTAL_MATCHED_CONTROL_SCHEMA
        or value.get("qualification_scope") != EXPERIMENTAL_MATCHED_CONTROL_SCOPE
        or value.get("promotion_status") != PROMOTION_FORBIDDEN
        or value.get("result") != "not_evaluated"
        or value.get("target") != "claude"
    ):
        raise ValidationError("experimental matched-control status is invalid")
    validate_identifier(value.get("controller"), "experimental controller")
    validate_identifier(value.get("campaign_id"), "experimental campaign")
    for name in (
        "goal_fingerprint",
        "manifest_fingerprint",
        "descriptor_sha256",
        "compiled_marker_sha256",
    ):
        validate_sha256(value.get(name), "experimental %s" % name)
    if value.get("runtime_defaults") != _RUNTIME_DEFAULTS:
        raise ValidationError("experimental runtime defaults are invalid")
    activated = _session(value.get("activated"), "activated")
    control = _session(value.get("control"), "control")
    if (
        activated["controller"] != value["controller"]
        or control["controller"] != value["controller"]
    ):
        raise IdentityError("experimental controller binding changed")
    if activated["entry_mode"] != control["entry_mode"]:
        raise IdentityError("experimental direct/cockpit entry modes are not paired")
    if any(
        left == right
        for left, right in (
            (activated["session"], control["session"]),
            (activated["run_id"], control["run_id"]),
            (activated["process"]["pid"], control["process"]["pid"]),
            (activated["lease_sha256"], control["lease_sha256"]),
            (
                (activated["workspace"]["device"], activated["workspace"]["inode"]),
                (control["workspace"]["device"], control["workspace"]["inode"]),
            ),
            (
                (activated["config"]["device"], activated["config"]["inode"]),
                (control["config"]["device"], control["config"]["inode"]),
            ),
        )
    ):
        raise IdentityError("experimental matched control reuses an activated identity")
    references = _evidence_refs(value.get("evidence_refs"))
    return {
        **dict(value),
        "activated": activated,
        "control": control,
        "evidence_refs": references,
    }


__all__ = [
    "EXPERIMENTAL_MATCHED_CONTROL_SCHEMA",
    "EXPERIMENTAL_MATCHED_CONTROL_SCOPE",
    "NON_AUTHORITATIVE",
    "PROCESS_REFERENCE_SCHEMA",
    "PROMOTION_FORBIDDEN",
    "REQUIRED_CONTROLLER_EVIDENCE",
    "validate_experimental_matched_control_candidate",
]
